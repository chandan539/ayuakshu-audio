"""Export generated audio to a user-chosen path."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.security import PathSecurityError, ensure_export_destination
from app.services.export_audio import export_job_files


def test_export_destination_allows_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFLINEVOICE_EXPORT_ROOT", str(tmp_path))
    dest = tmp_path / "Desktop" / "track.wav"
    dest.parent.mkdir()
    assert ensure_export_destination(dest) == dest.resolve()


def test_export_destination_blocks_app_bundle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFLINEVOICE_EXPORT_ROOT", str(tmp_path))
    bundle = tmp_path / "AYUAKSHU Audio.app" / "Contents" / "out.wav"
    bundle.parent.mkdir(parents=True)
    try:
        ensure_export_destination(bundle)
        raise AssertionError("expected PathSecurityError")
    except PathSecurityError:
        pass


def test_copy_wav_and_mp3(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFLINEVOICE_EXPORT_ROOT", str(tmp_path))
    src_dir = tmp_path / "job"
    src_dir.mkdir()
    wav = src_dir / "final.wav"
    mp3 = src_dir / "final.mp3"
    wav.write_bytes(b"WAVDATA")
    mp3.write_bytes(b"MP3DATA")
    out = tmp_path / "My Folder"
    job = {"output_wav": str(wav), "output_mp3": str(mp3)}
    result = export_job_files(job, fmt="both", destination=str(out), reveal=False)
    assert Path(result["copied"][0]["path"]).read_bytes() == b"WAVDATA"
    assert Path(result["copied"][1]["path"]).read_bytes() == b"MP3DATA"
    assert Path(result["folder"]).is_dir()


def test_export_api_copies_to_custom_folder(client: TestClient, tmp_path: Path, monkeypatch):
    data = Path(os.environ["OFFLINEVOICE_DATA_DIR"])
    monkeypatch.setenv("OFFLINEVOICE_EXPORT_ROOT", str(tmp_path))
    wav = data / "audio" / "generated" / "job_export" / "final.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFFWAV")
    mp3 = wav.with_suffix(".mp3")
    mp3.write_bytes(b"ID3MP3")
    db = data / "database" / "app.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO generation_jobs(
            id, language, engine, text, status, progress, current_chunk, total_chunks,
            output_directory, output_wav, output_mp3, created_at, updated_at
        ) VALUES (?, 'hi', 'chatterbox', 'hi', 'completed', 1, 1, 1, ?, ?, ?, 't', 't')
        """,
        ("job_export", str(wav.parent), str(wav), str(mp3)),
    )
    conn.commit()
    conn.close()

    dest = tmp_path / "Desktop" / "podcast.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = client.post(
        "/jobs/job_export/export",
        json={"format": "wav", "destination": str(dest), "reveal": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert Path(body["copied"][0]["path"]).read_bytes() == b"RIFFWAV"
    settings = client.get("/settings").json()
    assert settings["export_directory"] == str(dest.parent)


def test_export_api_requires_job(client: TestClient, tmp_path: Path):
    r = client.post(
        "/jobs/missing/export",
        json={"format": "wav", "destination": str(tmp_path / "x.wav"), "reveal": False},
    )
    assert r.status_code == 404
