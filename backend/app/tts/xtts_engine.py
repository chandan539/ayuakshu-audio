"""Stub for future XTTS-v2 engine. Not used in Phase 1."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import TTSEngine
from .errors import ModelNotInstalledError


class XTTSEngine(TTSEngine):
    name = "xtts"
    default_chunk_chars = 250

    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir).expanduser().resolve()

    def is_available(self) -> bool:
        return False

    def load(self) -> None:
        raise ModelNotInstalledError(self.name, hint="XTTS engine is Coming Soon")

    def generate(
        self,
        text: str,
        language: str,
        reference_audio: Optional[str],
        output_path: str,
    ) -> Path:
        raise ModelNotInstalledError(self.name, hint="XTTS engine is Coming Soon")
