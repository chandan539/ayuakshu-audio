"""TTS engine registry / manager."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import TTSEngine
from .chatterbox_engine import ChatterboxEngine
from .xtts_engine import XTTSEngine


class TTSManager:
    def __init__(self, models_root: str | Path):
        self.models_root = Path(models_root).expanduser().resolve()
        self._engines: dict[str, TTSEngine] = {
            "chatterbox": ChatterboxEngine(self.models_root / "tts" / "chatterbox"),
            "xtts": XTTSEngine(self.models_root / "tts" / "xtts"),
        }
        self._default = "chatterbox"

    def list_engines(self) -> list[str]:
        return list(self._engines.keys())

    def get_engine(self, name: Optional[str] = None) -> TTSEngine:
        key = (name or self._default).lower()
        if key not in self._engines:
            raise KeyError(f"Unknown TTS engine: {key}")
        return self._engines[key]

    def warm_default(self) -> None:
        """Preload the default engine so the first user job is not cold."""
        eng = self.get_engine(self._default)
        warm = getattr(eng, "warm_up", None)
        if callable(warm):
            warm()
            return
        if eng.is_available():
            eng.load()

    def generate(
        self,
        text: str,
        language: str,
        reference_audio: Optional[str],
        output_path: str,
        engine: Optional[str] = None,
    ) -> Path:
        eng = self.get_engine(engine)
        return eng.generate(
            text=text,
            language=language,
            reference_audio=reference_audio,
            output_path=output_path,
        )
