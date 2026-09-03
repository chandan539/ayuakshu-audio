#!/usr/bin/env python3
"""
PHASE 3 — Local backend smoke test.

Starts FastAPI on 127.0.0.1 (ephemeral port), creates a voice + project,
submits a short generate job, polls until complete, then exits.

Usage:
  cd offline-voice
  backend/.venv/bin/python test_backend.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient

from app.main import create_app

VOICE = ROOT / "voices" / "test.wav"
DATA = ROOT / "outputs" / "phase3_data"


def main() -> int:
    print("=== OfflineVoice PHASE 3 — Backend Smoke Test ===")
    if not VOICE.is_file():
        print(f"ERROR: missing {VOICE}")
        return 1

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["OFFLINEVOICE_MODELS_DIR"] = str(ROOT / "models")
    os.environ["OFFLINEVOICE_DATA_DIR"] = str(DATA)

    app = create_app(data_dir=DATA, host="127.0.0.1", port=0)
    with TestClient(app) as client:
        health = client.get("/health").json()
        print("health:", health)
        assert health["status"] == "ok"
        assert health["bind"].startswith("127.0.0.1:")

        models = client.get("/models").json()["models"]
        chatterbox = next(m for m in models if m["id"] == "chatterbox")
        print("chatterbox:", chatterbox["status"], f"({chatterbox['size_bytes']} bytes)")
        if not chatterbox["installed"]:
            print("TTS model is not installed.")
            return 2

        voice = client.post(
            "/voices",
            json={
                "name": "Phase3 Voice",
                "language": "hi",
                "source_audio": str(VOICE),
            },
        ).json()
        print("voice:", voice["id"], voice["name"])

        project = client.post(
            "/projects",
            json={
                "title": "Phase3 Demo",
                "text": "नमस्ते, यह चरण तीन का परीक्षण है।",
                "voice_id": voice["id"],
                "language": "hi",
            },
        ).json()
        print("project:", project["id"])

        gen = client.post(
            "/generate",
            json={
                "text": "नमस्ते, यह चरण तीन का परीक्षण है।[pause:0.5s]OfflineVoice local backend.",
                "language": "hi",
                "voice_id": voice["id"],
                "project_id": project["id"],
                "max_chars": 80,
                "export_mp3": True,
            },
        )
        assert gen.status_code == 200, gen.text
        job_id = gen.json()["job_id"]
        print("job:", job_id)

        deadline = time.time() + 300
        while time.time() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            print(
                f"  status={job['status']} progress={job['progress']}% "
                f"chunk={job['current_chunk']}/{job['total_chunks']} stage={job['stage']}"
            )
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        else:
            print("ERROR: job timed out")
            return 3

        if job["status"] != "completed":
            print("ERROR:", job.get("error"))
            return 4

        print("output_wav:", job["output_wav"])
        print("output_mp3:", job["output_mp3"])
        assert job["output_wav"] and Path(job["output_wav"]).is_file()
        assert job["output_mp3"] and Path(job["output_mp3"]).is_file()

        # Copy to outputs for convenience
        out = ROOT / "outputs"
        out.mkdir(exist_ok=True)
        (out / "phase3_hi.wav").write_bytes(Path(job["output_wav"]).read_bytes())
        (out / "phase3_hi.mp3").write_bytes(Path(job["output_mp3"]).read_bytes())
        print("Copied to outputs/phase3_hi.wav and outputs/phase3_hi.mp3")
        print("Done.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
