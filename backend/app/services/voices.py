"""Voice profile management (local files + SQLite metadata)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from ..audio.preprocess import preprocess_reference
from ..config import AppPaths
from ..security import PathSecurityError, ensure_within, resolve_under, sanitize_filename, sanitize_id
from .ids import new_id, utc_now


class VoiceService:
    def __init__(self, conn: sqlite3.Connection, paths: AppPaths):
        self.conn = conn
        self.paths = paths

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM voices ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, voice_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM voices WHERE id = ?", (voice_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def create(
        self,
        *,
        name: str,
        source_audio: str | Path,
        language: str = "hi",
        engine: str = "chatterbox",
    ) -> dict[str, Any]:
        voice_id = new_id("voice")
        voice_dir = resolve_under(self.paths.voices, voice_id)
        voice_dir.mkdir(parents=True, exist_ok=True)

        src = Path(source_audio).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Audio file not found: {src}")

        # Allow import from anywhere once; store only under voices/.
        # Single-pass preprocess (decode + metrics) — do not validate twice.
        ref_out = voice_dir / "reference.wav"
        pre = preprocess_reference(src, ref_out)
        validation = pre.validation
        if not validation.usable:
            raise ValueError(
                "Reference audio is not usable: "
                + "; ".join(validation.warnings or ["unknown issue"])
            )

        profile = {
            "id": voice_id,
            "name": name.strip() or "My Voice",
            "language": language,
            "reference_audio": "reference.wav",
            "created_at": utc_now(),
            "engine": engine,
        }
        metadata = {
            "validation": {
                "duration_sec": validation.duration_sec,
                "sample_rate": validation.sample_rate,
                "channels": validation.channels,
                "quality": validation.quality,
                "warnings": validation.warnings,
                "recommendations": validation.recommendations,
            },
            "processed_duration_sec": pre.duration_sec,
            "source_filename": sanitize_filename(src.name),
        }
        (voice_dir / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (voice_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO voices(
                id, name, language, engine, reference_audio,
                profile_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                voice_id,
                profile["name"],
                language,
                engine,
                str(ref_out),
                json.dumps(profile, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get(voice_id)  # type: ignore[return-value]

    def delete(self, voice_id: str) -> bool:
        voice_id = sanitize_id(voice_id)
        row = self.get(voice_id)
        if not row:
            return False
        self.conn.execute("DELETE FROM voices WHERE id = ?", (voice_id,))
        self.conn.commit()
        voice_dir = resolve_under(self.paths.voices, voice_id)
        if voice_dir.exists():
            shutil.rmtree(voice_dir, ignore_errors=True)
        return True

    def reference_path(self, voice_id: str) -> Path:
        row = self.get(voice_id)
        if not row:
            raise KeyError(f"Voice not found: {voice_id}")
        path = ensure_within(Path(row["reference_audio"]), self.paths.voices, self.paths.root)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("profile_json", "metadata_json"):
            if data.get(key):
                try:
                    data[key.replace("_json", "")] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key.replace("_json", "")] = None
        return data
