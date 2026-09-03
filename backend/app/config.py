"""Application paths and offline-first configuration."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path


APP_NAME = "AYUAKSHU Audio"
DEFAULT_HOST = "127.0.0.1"
# 0 = ask OS for an ephemeral free port at bind time.
DEFAULT_PORT = 0


def default_app_support_dir() -> Path:
    """macOS Application Support (or XDG-like fallback)."""
    override = os.environ.get("OFFLINEVOICE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        base = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
    return Path(xdg) / APP_NAME


@dataclass
class AppPaths:
    root: Path
    models: Path = field(init=False)
    voices: Path = field(init=False)
    projects: Path = field(init=False)
    audio_generated: Path = field(init=False)
    audio_temporary: Path = field(init=False)
    database_dir: Path = field(init=False)
    database_file: Path = field(init=False)
    logs: Path = field(init=False)
    cache: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        self.models = self.root / "models"
        self.voices = self.root / "voices"
        self.projects = self.root / "projects"
        self.audio_generated = self.root / "audio" / "generated"
        self.audio_temporary = self.root / "audio" / "temporary"
        self.database_dir = self.root / "database"
        self.database_file = self.database_dir / "app.sqlite"
        self.logs = self.root / "logs"
        self.cache = self.root / "cache"

    def ensure(self) -> "AppPaths":
        for path in (
            self.root,
            self.models / "tts" / "chatterbox",
            self.models / "whisper",
            self.voices,
            self.projects,
            self.audio_generated,
            self.audio_temporary,
            self.database_dir,
            self.logs,
            self.cache,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def clear_temporary(self) -> int:
        """Delete temporary audio files. Returns number of removed entries."""
        removed = 0
        if not self.audio_temporary.exists():
            return 0
        for child in self.audio_temporary.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
                removed += 1
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        return removed


@dataclass
class SettingsDefaults:
    offline_mode: bool = True
    default_language: str = "hi"
    default_engine: str = "chatterbox"
    # Keep short on Apple Silicon — long chunks blow MPS memory and feel "stuck".
    max_chunk_chars: int = 360
    mp3_bitrate: int = 192
    crossfade_ms: float = 40.0
    unload_model_after_inactivity: bool = False
    clone_mode: str = "fast"  # fast = speed + your voice; quality = slower, closer clone


def recommended_max_chunk_chars(memory_gb: float | None = None) -> int:
    """Safe TTS chunk size for local Chatterbox on Apple Silicon unified memory."""
    if memory_gb is None:
        memory_gb = 16.0
        try:
            import subprocess

            raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            memory_gb = int(raw) / (1024**3)
        except Exception:
            pass
    if memory_gb <= 16:
        return 360
    if memory_gb <= 24:
        return 420
    return 500


def detect_system_info() -> dict:
    """Simple compatibility payload for the UI."""
    import sys

    mem_gb = None
    try:
        import subprocess

        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        mem_gb = int(raw) / (1024**3)
    except Exception:
        mem_gb = None

    disk_free_gb = None
    try:
        usage = shutil.disk_usage(Path.home())
        disk_free_gb = usage.free / (1024**3)
    except Exception:
        disk_free_gb = None

    machine = platform.machine().lower()
    apple_silicon = machine in {"arm64", "aarch64"}
    return {
        "app": APP_NAME,
        "platform": platform.system(),
        "platform_version": platform.mac_ver()[0] or platform.version(),
        "arch": platform.machine(),
        "apple_silicon": apple_silicon,
        "memory_gb": round(mem_gb, 1) if mem_gb is not None else None,
        "disk_free_gb": round(disk_free_gb, 1) if disk_free_gb is not None else None,
        "python": sys.version.split()[0],
        "recommended": "Apple Silicon + 16 GB RAM or more",
        "recommended_max_chunk_chars": recommended_max_chunk_chars(mem_gb),
        "warning": None
        if apple_silicon and (mem_gb is None or mem_gb >= 16)
        else "Recommended: Apple Silicon + 16 GB RAM or more. Your system may generate audio more slowly.",
    }
