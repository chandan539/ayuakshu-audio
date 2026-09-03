"""Reference audio preprocessing pipeline.

Input → decode → WAV → mono → resample → loudness normalize → trim silence → store
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .convert import decode_to_wav
from .validate import ValidationReport

# Chatterbox S3Gen operates at 24 kHz.
TARGET_SR = 24000
TARGET_LUFS = -23.0


@dataclass
class PreprocessResult:
    source_path: str
    output_path: str
    sample_rate: int
    duration_sec: float
    validation: ValidationReport


def _trim_silence(
    audio: np.ndarray,
    sr: int,
    *,
    top_db: float = 30.0,
    pad_ms: float = 50.0,
) -> np.ndarray:
    # Fast vectorized energy trim (no librosa).
    if audio.size == 0:
        return audio
    frame = max(1, int(sr * 0.02))
    hop = max(1, frame // 2)
    if len(audio) < frame:
        return audio
    # Strided framing
    n_frames = 1 + (len(audio) - frame) // hop
    shape = (n_frames, frame)
    strides = (audio.strides[0] * hop, audio.strides[0])
    frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)
    energies = np.mean(frames * frames, axis=1)
    peak = float(np.max(energies)) + 1e-12
    thresh = peak * (10 ** (-top_db / 10.0))
    keep = np.where(energies > thresh)[0]
    if keep.size == 0:
        return audio
    start = int(keep[0] * hop)
    end = int(min(len(audio), keep[-1] * hop + frame))
    trimmed = audio[start:end]
    pad = int(sr * pad_ms / 1000.0)
    if pad > 0:
        trimmed = np.pad(trimmed, (pad, pad), mode="constant")
    return trimmed if len(trimmed) else audio


def _normalize_loudness(audio: np.ndarray, sr: int, target_lufs: float = TARGET_LUFS) -> np.ndarray:
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(audio)
        if not np.isfinite(loudness):
            return _peak_normalize(audio)
        out = pyln.normalize.loudness(audio, loudness, target_lufs)
        # Prevent clipping after loudness norm.
        peak = np.max(np.abs(out))
        if peak > 0.99:
            out = out * (0.99 / peak)
        return out.astype(np.float32)
    except Exception:
        return _peak_normalize(audio)


def _peak_normalize(audio: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if m < 1e-8:
        return audio.astype(np.float32)
    return (audio * (peak / m)).astype(np.float32)


def preprocess_reference(
    input_path: str | Path,
    output_path: str | Path,
    *,
    sample_rate: int = TARGET_SR,
    target_lufs: float = TARGET_LUFS,
    trim: bool = True,
    validation: ValidationReport | None = None,
) -> PreprocessResult:
    """
    Full local preprocessing. Never uploads audio.
    Does not reject imperfect recordings — validation is advisory.
    """
    src = Path(input_path).expanduser().resolve()
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Decode once, then reuse for validation metrics when possible.
    decoded = out.parent / f".{out.stem}_decoded.wav"
    decode_to_wav(src, decoded, sample_rate=sample_rate)

    audio, sr = sf.read(str(decoded), always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    channels = 1
    if audio.ndim == 2:
        channels = int(audio.shape[1])
        audio = audio.mean(axis=1)

    if validation is None:
        duration = float(len(audio) / sr) if sr else 0.0
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        rms = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
        silence_ratio = float(np.mean(np.abs(audio) < 0.01)) if len(audio) else 1.0
        warnings: list[str] = []
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
        from .validate import _dbfs

        validation = ValidationReport(
            path=str(src),
            format=src.suffix.lstrip(".") or "unknown",
            duration_sec=duration,
            sample_rate=int(sr),
            channels=int(channels),
            peak_dbfs=_dbfs(peak),
            rms_dbfs=_dbfs(rms),
            silence_ratio=silence_ratio,
            quality=quality,
            usable=usable,
            recommendations=[
                "10–30 seconds of clear speech",
                "minimal background noise",
                "single speaker",
            ],
            warnings=warnings,
        )

    if trim:
        audio = _trim_silence(audio, sr)
    audio = _normalize_loudness(audio, sr, target_lufs=target_lufs)

    sf.write(str(out), audio, sr, subtype="PCM_16")
    try:
        decoded.unlink(missing_ok=True)
    except OSError:
        pass

    duration = float(len(audio) / sr) if sr else 0.0
    return PreprocessResult(
        source_path=str(src),
        output_path=str(out),
        sample_rate=sr,
        duration_sec=duration,
        validation=validation,
    )
