"""Local Whisper speech-to-text (offline only)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..tts.errors import ModelNotInstalledError

WHISPER_MODEL_NAME = "small"
WHISPER_WEIGHT_NAMES = (
    "small.pt",
    "base.pt",
    "tiny.pt",
    "medium.pt",
    "large-v3.pt",
    "large-v2.pt",
    "large.pt",
)


@dataclass
class WhisperStatus:
    installed: bool
    path: str
    size_bytes: int
    model_file: Optional[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "model_file": self.model_file,
            "message": self.message,
        }


def find_whisper_weight(model_dir: Path) -> Optional[Path]:
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        return None
    # Prefer configured default name, then any known weight.
    preferred = model_dir / f"{WHISPER_MODEL_NAME}.pt"
    if preferred.is_file():
        return preferred
    for name in WHISPER_WEIGHT_NAMES:
        candidate = model_dir / name
        if candidate.is_file():
            return candidate
    return None


def validate_whisper_dir(model_dir: Path) -> WhisperStatus:
    model_dir = Path(model_dir)
    weight = find_whisper_weight(model_dir)
    size = 0
    if model_dir.is_dir():
        size = sum(p.stat().st_size for p in model_dir.rglob("*") if p.is_file())
    if weight is None:
        return WhisperStatus(
            installed=False,
            path=str(model_dir),
            size_bytes=size,
            model_file=None,
            message="Whisper weights not installed. Run backend/scripts/install_whisper_model.py",
        )
    return WhisperStatus(
        installed=True,
        path=str(model_dir),
        size_bytes=size,
        model_file=weight.name,
        message=f"✓ Installed ({weight.name}) · ✓ Ready for offline use",
    )


class WhisperEngine:
    name = "whisper"

    def __init__(self, model_dir: str | Path, model_name: str = WHISPER_MODEL_NAME):
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.model_name = model_name
        self._model = None

    def is_available(self) -> bool:
        return find_whisper_weight(self.model_dir) is not None

    def status(self) -> WhisperStatus:
        return validate_whisper_dir(self.model_dir)

    def load(self) -> None:
        if self._model is not None:
            return
        weight = find_whisper_weight(self.model_dir)
        if weight is None:
            raise ModelNotInstalledError(
                self.name,
                hint="Install with: backend/scripts/install_whisper_model.py",
            )
        import whisper

        # Infer name from filename (small.pt → small)
        name = weight.stem
        self._model = whisper.load_model(name, download_root=str(self.model_dir))

    def unload(self) -> None:
        self._model = None

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: Optional[str] = None,
    ) -> dict[str, Any]:
        self.load()
        assert self._model is not None
        path = Path(audio_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Audio not found: {path}")

        # Avoid Whisper's ffmpeg dependency — load with soundfile/librosa.
        audio = self._load_audio_16k_mono(path)

        kwargs: dict[str, Any] = {
            "fp16": False,
            "verbose": False,
        }
        if language:
            kwargs["language"] = language

        result = self._model.transcribe(audio, **kwargs)
        text = (result.get("text") or "").strip()
        return {
            "text": text,
            "language": result.get("language") or language,
            "segments": [
                {
                    "start": float(s.get("start", 0)),
                    "end": float(s.get("end", 0)),
                    "text": (s.get("text") or "").strip(),
                }
                for s in (result.get("segments") or [])
            ],
            "model": find_whisper_weight(self.model_dir).stem if find_whisper_weight(self.model_dir) else self.model_name,
            "audio_path": str(path),
        }

    @staticmethod
    def _load_audio_16k_mono(path: Path):
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(str(path), always_2d=False)
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if int(sr) != 16000:
            # Lightweight resample (avoid librosa/numba + ffmpeg).
            duration = len(data) / float(sr)
            n = max(1, int(round(duration * 16000)))
            x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
            data = np.interp(x_new, x_old, data).astype(np.float32)
        return data
