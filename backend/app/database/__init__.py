"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'hi',
    engine TEXT NOT NULL DEFAULT 'chatterbox',
    reference_audio TEXT NOT NULL,
    profile_json TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    voice_id TEXT,
    language TEXT NOT NULL DEFAULT 'hi',
    settings_json TEXT,
    output_wav TEXT,
    output_mp3 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(voice_id) REFERENCES voices(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    voice_id TEXT,
    language TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'chatterbox',
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    current_chunk INTEGER NOT NULL DEFAULT 0,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    error TEXT,
    output_directory TEXT,
    output_wav TEXT,
    output_mp3 TEXT,
    max_chars INTEGER,
    pronunciation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY(voice_id) REFERENCES voices(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS generation_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    kind TEXT NOT NULL,
    text TEXT,
    pause_seconds REAL DEFAULT 0,
    audio_path TEXT,
    status TEXT NOT NULL,
    error TEXT,
    UNIQUE(job_id, chunk_index),
    FOREIGN KEY(job_id) REFERENCES generation_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_chunks_job ON generation_chunks(job_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # timeout + WAL: API requests and the TTS worker share this connection.
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def db_session(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
