"""Local audio conversion helpers (macOS afconvert + soundfile)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_IMPORT_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aiff", ".aif", ".caf"}


class AudioToolError(RuntimeError):
    pass


def find_afconvert() -> str | None:
    return shutil.which("afconvert")


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def decode_to_wav(input_path: str | Path, output_wav: str | Path, sample_rate: int = 24000) -> Path:
    """
    Decode arbitrary supported audio to mono 16-bit WAV.

    Prefer soundfile for WAV/FLAC; fall back to afconvert / ffmpeg.
    """
    src = Path(input_path).expanduser().resolve()
    dst = Path(output_wav).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not src.is_file():
        raise FileNotFoundError(f"Audio file not found: {src}")

    ext = src.suffix.lower()
    if ext not in SUPPORTED_IMPORT_EXTENSIONS:
        raise AudioToolError(
            f"Unsupported format '{ext}'. Supported: {sorted(SUPPORTED_IMPORT_EXTENSIONS)}"
        )

    # Fast path for formats soundfile reads well.
    if ext in {".wav", ".flac", ".aiff", ".aif"}:
        try:
            import numpy as np
            import soundfile as sf

            audio, sr = sf.read(str(src), always_2d=True)
            mono = audio.mean(axis=1).astype(np.float32)
            if int(sr) != sample_rate:
                # Avoid librosa/numba — linear resample is enough for reference clips.
                duration = len(mono) / float(sr)
                n = max(1, int(round(duration * sample_rate)))
                x_old = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
                mono = np.interp(x_new, x_old, mono).astype(np.float32)
            sf.write(str(dst), mono, sample_rate, subtype="PCM_16")
            return dst
        except Exception:
            pass  # fall through to system converters

    afconvert = find_afconvert()
    if afconvert:
        # afconvert: LEI16 @ rate, mono
        cmd = [
            afconvert,
            str(src),
            str(dst),
            "-f",
            "WAVE",
            "-d",
            f"LEI16@{sample_rate}",
            "-c",
            "1",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dst.is_file():
            return dst
        err = (proc.stderr or proc.stdout or "").strip()
        raise AudioToolError(f"afconvert failed for {src.name}: {err}")

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dst.is_file():
            return dst
        err = (proc.stderr or proc.stdout or "").strip()
        raise AudioToolError(f"ffmpeg failed for {src.name}: {err}")

    raise AudioToolError(
        "No local audio converter available. Install FFmpeg or use macOS afconvert."
    )


def with_temp_wav(input_path: str | Path, sample_rate: int = 24000) -> Path:
    """Decode into a temporary WAV file; caller owns cleanup if needed."""
    tmp = Path(tempfile.mkdtemp(prefix="offlinevoice_")) / "decoded.wav"
    return decode_to_wav(input_path, tmp, sample_rate=sample_rate)
