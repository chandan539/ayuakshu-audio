"""Phase 5 — offline model manager tests."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.main import create_app
from app.services.model_package import (
    build_manifest,
    find_chatterbox_source,
    validate_chatterbox_dir,
    validate_offline_package,
)


@pytest.fixture()
def client(tmp_path: Path):
    import os

    os.environ["OFFLINEVOICE_MODELS_DIR"] = str(ROOT / "models")
    os.environ["OFFLINEVOICE_DATA_DIR"] = str(tmp_path / "data")
    app = create_app(data_dir=tmp_path / "data", host="127.0.0.1", port=0)
    with TestClient(app) as c:
        yield c


def test_validate_installed_chatterbox():
    report = validate_chatterbox_dir(ROOT / "models" / "tts" / "chatterbox")
    assert report.valid
    assert report.ready_offline
    assert not report.missing_required


def test_validate_missing_model(tmp_path: Path):
    report = validate_chatterbox_dir(tmp_path / "empty")
    assert not report.valid
    assert "ve.pt" in report.missing_required


def test_offline_package_layout(tmp_path: Path):
    src = ROOT / "models" / "tts" / "chatterbox"
    if not (src / "ve.pt").exists():
        pytest.skip("chatterbox weights missing")
    pkg = tmp_path / "OfflineVoice-Models"
    dest = pkg / "tts" / "chatterbox"
    dest.mkdir(parents=True)
    for name in ("ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json"):
        shutil.copy2(src / name, dest / name)
    (pkg / "manifest.json").write_text(
        json.dumps(build_manifest(chatterbox_dir=dest, include_pkuseg=False)),
        encoding="utf-8",
    )
    result = validate_offline_package(pkg)
    assert result["valid"] is True
    assert find_chatterbox_source(pkg) == dest.resolve()


def test_setup_status_and_skip(client: TestClient):
    r = client.get("/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert "needs_setup" in body
    assert "model_ready" in body
    # With repo models present, model should be ready.
    if body["model_ready"]:
        assert body["needs_setup"] is False
    skipped = client.post("/setup/skip")
    assert skipped.status_code == 200
    assert skipped.json()["setup_skipped"] is True


def test_validate_endpoint(client: TestClient):
    r = client.get("/models/chatterbox/validate")
    assert r.status_code == 200
    assert "valid" in r.json()


def test_install_requires_local_package(client: TestClient):
    r = client.post("/models/install", json={"model_id": "chatterbox"})
    assert r.status_code == 400
    assert "local model package" in r.text.lower() or "from_local" in r.text.lower()


def test_install_from_local_package(client: TestClient, tmp_path: Path):
    src = ROOT / "models" / "tts" / "chatterbox"
    if not (src / "ve.pt").exists():
        pytest.skip("chatterbox weights missing")

    pkg = tmp_path / "OfflineVoice-Models"
    dest = pkg / "chatterbox"
    dest.mkdir(parents=True)
    for name in ("ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt"):
        if (src / name).exists():
            shutil.copy2(src / name, dest / name)

    # Point data dir models (empty) and install package into app support.
    validated = client.post(
        "/models/validate-package",
        json={"model_id": "chatterbox", "from_local": str(pkg)},
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["valid"] is True

    installed = client.post(
        "/models/install",
        json={"model_id": "chatterbox", "from_local": str(pkg)},
    )
    assert installed.status_code == 200, installed.text
    body = installed.json()
    assert body["ok"] is True
    assert "Offline AI setup complete" in body["message"]
    assert Path(body["install_path"]).is_dir()
    assert (Path(body["install_path"]) / "ve.pt").is_file()
