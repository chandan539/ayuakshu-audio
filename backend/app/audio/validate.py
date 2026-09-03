"""Reference-voice validation (non-blocking recommendations)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .convert import SUPPORTED_IMPORT_EXTENSIONS, decode_to_wav


@dataclass
class ValidationReport:
    path: str
    format: str
    duration_sec: float
    sample_rate: int
    channels: int
    peak_dbfs: float
    rms_dbfs: float
    silence_ratio: float
    quality: str  # Good | Acceptable | Poor
    usable: bool
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "Reference Voice",
            "",
            f"Duration: {self.duration_sec:.0f} seconds",
            f"Sample rate: {self.sample_rate / 1000:.1f} kHz",
            f"Channels: {'Mono' if self.channels == 1 else self.channels}",
            "",
            f"Quality: {self.quality}",
            "",
            "Recommended:",
            "10–30 seconds of clear speech",
            "minimal background noise",
            "single speaker",
        ]
        if self.warnings:
            lines.extend(["", "Notes:"])
            lines.extend(f"- {w}" for w in self.warnings)
        return "\n".join(lines)


def _dbfs(x: float) -> float:
    return 20.0 * np.log10(max(x, 1e-12))


def validate_reference_audio(
    path: str | Path,
    *,
    work_dir: str | Path | None = None,
) -> ValidationReport:
    src = Path(path).expanduser().resolve()
    ext = src.suffix.lower()
    recommendations = [
        "10–30 seconds of clear speech",
        "minimal background noise",
        "single speaker",
    ]
    warnings: list[str] = []

    if ext not in SUPPORTED_IMPORT_EXTENSIONS:
        return ValidationReport(
            path=str(src),
            format=ext or "unknown",
            duration_sec=0.0,
            sample_rate=0,
            channels=0,
            peak_dbfs=-120.0,
            rms_dbfs=-120.0,
            silence_ratio=1.0,
            quality="Poor",
            usable=False,
            recommendations=recommendations,
            warnings=[f"Unsupported format: {ext}"],
        )

    # Decode to a temp analysis WAV for consistent metrics.
    if work_dir is None:
        analysis = src if ext == ".wav" else None
        tmp_dir = src.parent / ".validate_tmp"
    else:
        tmp_dir = Path(work_dir)
        analysis = None

    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = analysis or (tmp_dir / f"{src.stem}_analysis.wav")
    if analysis is None:
        decode_to_wav(src, wav_path, sample_rate=24000)

    audio, sr = sf.read(str(wav_path), always_2d=True)
    channels = audio.shape[1]
    mono = audio.mean(axis=1)
    duration = float(len(mono) / sr) if sr else 0.0
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0
    silence_ratio = float(np.mean(np.abs(mono) < 0.01)) if len(mono) else 1.0

    usable = duration >= 1.0 and peak > 0.001
    quality = "Good"
    if duration < 5:
        warnings.append("Short clip — 10–30 seconds usually clones better.")
        quality = "Acceptable"
    if duration > 60:
        warnings.append("Long clip — consider trimming to 10–30 seconds of clear speech.")
        quality = "Acceptable"
    if channels > 1:
        warnings.append("Stereo detected — will be converted to mono.")
    if peak < 0.05:
        warnings.append("Low level — audio may be too quiet.")
        quality = "Poor" if peak < 0.01 else "Acceptable"
    if silence_ratio > 0.6:
        warnings.append("High silence ratio — trim leading/trailing silence if possible.")
        quality = "Acceptable" if usable else "Poor"
    if not usable:
        quality = "Poor"
        warnings.append("Recording may be unusable (too short or silent).")
    elif 10 <= duration <= 30 and peak >= 0.1 and silence_ratio < 0.4:
        quality = "Good"

    return ValidationReport(
        path=str(src),
        format=ext.lstrip(".") or "unknown",
        duration_sec=duration,
        sample_rate=int(sr),
        channels=int(channels),
        peak_dbfs=_dbfs(peak),
        rms_dbfs=_dbfs(rms),
        silence_ratio=silence_ratio,
        quality=quality,
        usable=usable,
        recommendations=recommendations,
        warnings=warnings,
    )
