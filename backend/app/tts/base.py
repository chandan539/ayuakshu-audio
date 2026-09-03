"""Abstract TTS engine interface.

Engines (Chatterbox, XTTS, Qwen3-TTS, ...) must implement this contract
so the rest of the application stays model-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class TTSEngine(ABC):
    """Local, offline text-to-speech engine."""

    name: str = "base"
    # Engine-specific default chunk size for long-form text (Phase 2+).
    default_chunk_chars: int = 1200

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if model weights are present locally."""

    @abstractmethod
    def load(self) -> None:
        """Load model weights into memory. No network access."""

    @abstractmethod
    def generate(
        self,
        text: str,
        language: str,
        reference_audio: Optional[str],
        output_path: str,
    ) -> Path:
        """
        Generate speech and write a WAV file.

        Raises ModelNotInstalledError if weights are missing.
        Must not download models at generation time.
        """

    def unload(self) -> None:
        """Optional: release model memory."""
        return None
