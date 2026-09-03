#!/usr/bin/env python3
"""
PHASE 7 — Offline QA end-to-end test.

Blocks outbound network (except 127.0.0.1 / ::1), starts the local API,
loads the model, creates a voice, generates Hindi + English, and verifies
WAV/MP3 exports exist.

Usage:
  backend/.venv/bin/python backend/scripts/offline_qa.py
  ./scripts/test_offline.sh
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

VOICE = ROOT / "voices" / "test.wav"
DATA = ROOT / "outputs" / "phase7_offline_qa"
OUT = ROOT / "outputs"


def install_network_guard() -> None:
    """Deny any non-loopback TCP/UDP connect. Fail loudly if inference tries Hub."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _host(address) -> str:
        if isinstance(address, tuple) and address:
            return str(address[0])
        return str(address)

    def _allowed(host: str) -> bool:
        return host in {"127.0.0.1", "::1", "localhost", ""}

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        host = _host(address)
        if not _allowed(host):
            raise OSError(f"OFFLINE QA blocked network connect to {address!r}")
        return real_connect(self, address)

    def guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
        host = _host(address)
        if not _allowed(host):
            return 101  # ENETUNREACH-ish
        return real_connect_ex(self, address)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]


def wait_job(client, job_id: str, label: str, timeout: float = 420.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = client.get(f"/jobs/{job_id}").json()
        print(
            f"  [{label}] status={last['status']} progress={last['progress']}% "
            f"chunk={last['current_chunk']}/{last['total_chunks']} stage={last['stage']}"
        )
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(1.0)
    raise TimeoutError(f"{label} job timed out: {job_id}")


def main() -> int:
    print("=== OfflineVoice PHASE 7 — Offline QA ===")
    print(f"ROOT={ROOT}")

    if not VOICE.is_file():
        print(f"FAIL: missing reference voice {VOICE}")
        return 1

    models = ROOT / "models" / "tts" / "chatterbox"
    weight = models / "t3_mtl23ls_v2.safetensors"
    if not weight.is_file():
        print(f"FAIL: model not installed at {weight}")
        print("Install first (online once), then re-run with Wi-Fi off.")
        return 2

    # Force offline Hub / transformers before any ML imports.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["OFFLINEVOICE_MODELS_DIR"] = str(ROOT / "models")
    os.environ["OFFLINEVOICE_DATA_DIR"] = str(DATA)

    install_network_guard()
    print("OK: network guard installed (non-loopback connects blocked)")

    from fastapi.testclient import TestClient

    from app.main import create_app

    if DATA.exists():
        # Keep DB/jobs fresh for a clean QA run.
        import shutil

        shutil.rmtree(DATA)
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    app = create_app(data_dir=DATA, host="127.0.0.1", port=0)
    with TestClient(app) as client:
        # 1) Backend launches
        health = client.get("/health").json()
        print("health:", health)
        assert health["status"] == "ok"
        assert health["offline_mode"] is True
        assert str(health["bind"]).startswith("127.0.0.1:")
        print("OK: backend launches on loopback")

        # 2) Model status / load path
        models_payload = client.get("/models").json()["models"]
        chatterbox = next(m for m in models_payload if m["id"] == "chatterbox")
        print("chatterbox:", chatterbox)
        assert chatterbox.get("installed") is True, "model must be installed"
        print("OK: model detected as installed")

        # Warm validate endpoint if present
        validate = client.get("/models/chatterbox/validate")
        if validate.status_code == 200:
            print("validate:", validate.json())
            print("OK: model validate")
        else:
            print("WARN: /models/chatterbox/validate ->", validate.status_code)

        # 3) Voice loads
        voice = client.post(
            "/voices",
            json={
                "name": "Phase7 Voice",
                "language": "hi",
                "source_audio": str(VOICE),
            },
        ).json()
        print("voice:", voice["id"])
        assert voice.get("id")
        print("OK: voice created from local reference")

        # 4) Hindi generation + export
        hi_text = "नमस्ते। यह ऑफ़लाइन गुणवत्ता परीक्षण है।"
        gen_hi = client.post(
            "/generate",
            json={
                "text": hi_text,
                "language": "hi",
                "voice_id": voice["id"],
                "max_chars": 120,
                "export_mp3": True,
            },
        )
        assert gen_hi.status_code == 200, gen_hi.text
        hi_job = wait_job(client, gen_hi.json()["job_id"], "hi")
        if hi_job["status"] != "completed":
            print("FAIL hindi:", hi_job.get("error"))
            return 3
        hi_wav = Path(hi_job["output_wav"])
        hi_mp3 = Path(hi_job["output_mp3"])
        assert hi_wav.is_file() and hi_wav.stat().st_size > 1000
        assert hi_mp3.is_file() and hi_mp3.stat().st_size > 500
        (OUT / "phase7_hi.wav").write_bytes(hi_wav.read_bytes())
        (OUT / "phase7_hi.mp3").write_bytes(hi_mp3.read_bytes())
        print("OK: Hindi generation + WAV/MP3 export")

        # 5) English generation + export
        en_text = "Hello. This is an offline quality assurance test."
        gen_en = client.post(
            "/generate",
            json={
                "text": en_text,
                "language": "en",
                "voice_id": voice["id"],
                "max_chars": 120,
                "export_mp3": True,
            },
        )
        assert gen_en.status_code == 200, gen_en.text
        en_job = wait_job(client, gen_en.json()["job_id"], "en")
        if en_job["status"] != "completed":
            print("FAIL english:", en_job.get("error"))
            return 4
        en_wav = Path(en_job["output_wav"])
        en_mp3 = Path(en_job["output_mp3"])
        assert en_wav.is_file() and en_wav.stat().st_size > 1000
        assert en_mp3.is_file() and en_mp3.stat().st_size > 500
        (OUT / "phase7_en.wav").write_bytes(en_wav.read_bytes())
        (OUT / "phase7_en.mp3").write_bytes(en_mp3.read_bytes())
        print("OK: English generation + WAV/MP3 export")

        # 6) System / privacy assertions
        system = client.get("/system").json() if client.get("/system").status_code == 200 else {}
        print("system:", system or "(no /system)")
        privacy = client.get("/settings")
        if privacy.status_code == 200:
            print("settings keys:", sorted(privacy.json().keys())[:20])

    print()
    print("=== PHASE 7 PASSED ===")
    print(f"  {OUT / 'phase7_hi.wav'}")
    print(f"  {OUT / 'phase7_hi.mp3'}")
    print(f"  {OUT / 'phase7_en.wav'}")
    print(f"  {OUT / 'phase7_en.mp3'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — surface QA failures clearly
        print(f"FAIL: {exc}")
        raise
