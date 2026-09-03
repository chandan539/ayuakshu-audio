"""Phase 3 backend API tests (no full TTS generation)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.main import create_app
from app.security import PathSecurityError, resolve_under, sanitize_filename


@pytest.fixture()
def client(tmp_path: Path):
    # Point models at repo weights so /models reports installed when present.
    import os

    os.environ["OFFLINEVOICE_MODELS_DIR"] = str(ROOT / "models")
    os.environ["OFFLINEVOICE_DATA_DIR"] = str(tmp_path / "data")
    app = create_app(data_dir=tmp_path / "data", host="127.0.0.1", port=0)
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["offline_mode"] is True
    assert body["bind"].startswith("127.0.0.1:")


def test_system(client: TestClient):
    r = client.get("/system")
    assert r.status_code == 200
    assert "apple_silicon" in r.json()


def test_models(client: TestClient):
    r = client.get("/models")
    assert r.status_code == 200
    models = r.json()["models"]
    ids = {m["id"] for m in models}
    assert "chatterbox" in ids
    assert "whisper" in ids


def test_settings_roundtrip(client: TestClient):
    r = client.get("/settings")
    assert r.status_code == 200
    assert r.json()["offline_mode"] is True
    r2 = client.put("/settings", json={"mp3_bitrate": 256, "max_chunk_chars": 800})
    assert r2.status_code == 200
    assert r2.json()["mp3_bitrate"] == 256
    assert r2.json()["max_chunk_chars"] == 800


def test_projects_crud(client: TestClient):
    created = client.post(
        "/projects",
        json={"title": "Hindi Podcast", "text": "नमस्ते", "language": "hi"},
    )
    assert created.status_code == 200
    project = created.json()
    pid = project["id"]
    assert project["title"] == "Hindi Podcast"

    listed = client.get("/projects")
    assert any(p["id"] == pid for p in listed.json()["projects"])

    updated = client.put(f"/projects/{pid}", json={"title": "Updated"})
    assert updated.json()["title"] == "Updated"

    deleted = client.delete(f"/projects/{pid}")
    assert deleted.status_code == 200
    assert client.get(f"/projects/{pid}").status_code == 404


def test_voice_create_and_list(client: TestClient):
    voice_src = ROOT / "voices" / "test.wav"
    if not voice_src.is_file():
        pytest.skip("reference voice missing")
    created = client.post(
        "/voices",
        json={"name": "My Voice", "language": "hi", "source_audio": str(voice_src)},
    )
    assert created.status_code == 200, created.text
    voice = created.json()
    assert voice["name"] == "My Voice"
    assert Path(voice["reference_audio"]).is_file()

    listed = client.get("/voices")
    assert any(v["id"] == voice["id"] for v in listed.json()["voices"])

    audio = client.get(f"/voices/{voice['id']}/audio")
    assert audio.status_code == 200, audio.text
    assert audio.headers["content-type"].startswith("audio/")
    assert len(audio.content) > 100

    active = client.get("/jobs/active")
    assert active.status_code == 200
    assert "job" in active.json()


def test_generate_requires_voice(client: TestClient):
    r = client.post(
        "/generate",
        json={"text": "hello", "language": "en", "voice_id": "missing"},
    )
    assert r.status_code == 404


def test_transcribe_requires_audio_path(client: TestClient):
    # Missing body → validation error
    r = client.post("/transcribe")
    assert r.status_code == 422

    # With a missing file → 404 or 503 depending on Whisper install
    r2 = client.post(
        "/transcribe",
        json={"audio_path": "/tmp/does-not-exist-ayuakshu.wav", "language": "en"},
    )
    assert r2.status_code in {404, 503}


def test_path_security():
    root = Path("/tmp/offlinevoice_root_test")
    root.mkdir(exist_ok=True)
    ok = resolve_under(root, "voices", "voice_1")
    assert str(ok).startswith(str(root.resolve()))
    with pytest.raises(PathSecurityError):
        resolve_under(root, "..", "etc", "passwd")
    assert sanitize_filename("../../evil.wav") == "evil.wav"


def test_offline_model_install_requires_local_package(client: TestClient):
    r = client.post("/models/install", json={"model_id": "chatterbox"})
    assert r.status_code == 400
    assert "local model package" in r.text.lower() or "from_local" in r.text.lower()
