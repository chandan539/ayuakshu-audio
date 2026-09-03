"""Project CRUD (metadata in SQLite; audio on disk)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..config import AppPaths
from ..security import resolve_under, sanitize_id
from .ids import new_id, utc_now


class ProjectService:
    def __init__(self, conn: sqlite3.Connection, paths: AppPaths):
        self.conn = conn
        self.paths = paths

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def create(
        self,
        *,
        title: str,
        text: str = "",
        voice_id: str | None = None,
        language: str = "hi",
        settings: dict | None = None,
    ) -> dict[str, Any]:
        project_id = new_id("project")
        now = utc_now()
        project_dir = resolve_under(self.paths.projects, project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self.conn.execute(
            """
            INSERT INTO projects(
                id, title, text, voice_id, language, settings_json,
                output_wav, output_mp3, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                project_id,
                title.strip() or "Untitled Project",
                text,
                voice_id,
                language,
                json.dumps(settings or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get(project_id)  # type: ignore[return-value]

    def update(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        existing = self.get(project_id)
        if not existing:
            return None
        allowed = {
            "title",
            "text",
            "voice_id",
            "language",
            "settings",
            "output_wav",
            "output_mp3",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "settings" in updates:
            updates["settings_json"] = json.dumps(updates.pop("settings"), ensure_ascii=False)
        if not updates:
            return existing
        updates["updated_at"] = utc_now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE projects SET {cols} WHERE id = ?",
            (*updates.values(), project_id),
        )
        self.conn.commit()
        return self.get(project_id)

    def delete(self, project_id: str) -> bool:
        project_id = sanitize_id(project_id)
        if not self.get(project_id):
            return False
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()
        project_dir = resolve_under(self.paths.projects, project_id)
        if project_dir.exists():
            import shutil

            shutil.rmtree(project_dir, ignore_errors=True)
        return True

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        if data.get("settings_json"):
            try:
                data["settings"] = json.loads(data["settings_json"])
            except json.JSONDecodeError:
                data["settings"] = {}
        return data
