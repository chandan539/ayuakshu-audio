"""Settings service (SQLite key/value)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..config import SettingsDefaults
from .ids import utc_now

DEFAULTS = SettingsDefaults()


class SettingsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        defaults = {
            "offline_mode": DEFAULTS.offline_mode,
            "default_language": DEFAULTS.default_language,
            "default_engine": DEFAULTS.default_engine,
            "max_chunk_chars": DEFAULTS.max_chunk_chars,
            "mp3_bitrate": DEFAULTS.mp3_bitrate,
            "crossfade_ms": DEFAULTS.crossfade_ms,
            "unload_model_after_inactivity": DEFAULTS.unload_model_after_inactivity,
            "clone_mode": DEFAULTS.clone_mode,
            "setup_completed": False,
            "setup_skipped": False,
        }
        now = utc_now()
        for key, value in defaults.items():
            row = self.conn.execute("SELECT key FROM settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), now),
                )
        self.conn.commit()

    def get_all(self) -> dict[str, Any]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        out: dict[str, Any] = {}
        for row in rows:
            out[row["key"]] = json.loads(row["value"])
        return out

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        for key, value in values.items():
            self.conn.execute(
                """
                INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), now),
            )
        self.conn.commit()
        return self.get_all()
