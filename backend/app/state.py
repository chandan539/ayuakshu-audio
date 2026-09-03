"""Application state container."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from .config import AppPaths
from .jobs.queue import JobQueue
from .services.models import ModelService
from .services.projects import ProjectService
from .services.settings import SettingsService
from .services.voices import VoiceService
from .tts.manager import TTSManager


@dataclass
class AppState:
    paths: AppPaths
    conn: sqlite3.Connection
    settings: SettingsService
    voices: VoiceService
    projects: ProjectService
    models: ModelService
    tts: TTSManager
    jobs: JobQueue
    whisper: object | None = None
    host: str = "127.0.0.1"
    port: int = 0
