"""Join generated audio chunks with crossfades (no clicky hard cuts)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def _to_mono(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        return audio.mean(axis=1).astype(np.float32)
    return audio.astype(np.float32)


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), always_2d=False)
    return _to_mono(audio), int(sr)


def silence(seconds: float, sr: int) -> np.ndarray:
    n = max(0, int(round(seconds * sr)))
    return np.zeros(n, dtype=np.float32)


def apply_fade(
    audio: np.ndarray,
    sr: int,
    *,
    fade_in_ms: float = 10.0,
    fade_out_ms: float = 10.0,
) -> np.ndarray:
    out = audio.copy()
    n_in = min(len(out), int(sr * fade_in_ms / 1000.0))
    n_out = min(len(out), int(sr * fade_out_ms / 1000.0))
    if n_in > 0:
        out[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
    if n_out > 0:
        out[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
    return out


def match_peak(audio: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak < 1e-8:
        return audio
    return (audio * (target_peak / peak)).astype(np.float32)


def crossfade_join(
    chunks: list[np.ndarray],
    sr: int,
    *,
    crossfade_ms: float = 40.0,
    gap_ms: float = 0.0,
) -> np.ndarray:
    """
    Concatenate mono float32 arrays with equal-power-ish linear crossfade.

    If gap_ms > 0, inserts silence between chunks instead of overlapping.
    """
    if not chunks:
        return np.zeros(0, dtype=np.float32)

    prepared = [apply_fade(_to_mono(c), sr, fade_in_ms=5.0, fade_out_ms=5.0) for c in chunks]
    if len(prepared) == 1:
        return prepared[0]

    xfade = int(sr * crossfade_ms / 1000.0)
    gap = int(sr * gap_ms / 1000.0)
    out = prepared[0]

    for nxt in prepared[1:]:
        if gap > 0:
            out = np.concatenate([out, silence(gap / sr, sr), nxt])
            continue

        n = min(xfade, len(out), len(nxt))
        if n <= 0:
            out = np.concatenate([out, nxt])
            continue

        fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
        mixed = out[-n:] * fade_out + nxt[:n] * fade_in
        out = np.concatenate([out[:-n], mixed, nxt[n:]])

    return out.astype(np.float32)


def join_segments(
    segments: list[tuple[str, object]],
    *,
    sample_rate: int | None = None,
    crossfade_ms: float = 40.0,
    normalize_final: bool = True,
) -> tuple[np.ndarray, int]:
    """
    segments: list of ("speech", wav_path) or ("pause", seconds)

    Speech segments are crossfaded; pauses insert exact silence (no crossfade into silence).
    """
    speech_audio: list[np.ndarray] = []
    sr = sample_rate
    assembled: list[np.ndarray] = []

    def flush_speech() -> None:
        nonlocal speech_audio
        if not speech_audio:
            return
        if len(speech_audio) == 1:
            assembled.append(speech_audio[0])
        else:
            assert sr is not None
            assembled.append(crossfade_join(speech_audio, sr, crossfade_ms=crossfade_ms))
        speech_audio = []

    for kind, payload in segments:
        if kind == "pause":
            flush_speech()
            if sr is None:
                continue
            assembled.append(silence(float(payload), sr))
            continue

        audio, file_sr = load_audio(str(payload))
        if sr is None:
            sr = file_sr
        elif file_sr != sr:
            import librosa

            audio = librosa.resample(audio, orig_sr=file_sr, target_sr=sr).astype(np.float32)
        speech_audio.append(audio)

    flush_speech()
    if sr is None:
        return np.zeros(0, dtype=np.float32), 24000

    if not assembled:
        return np.zeros(0, dtype=np.float32), sr

    final = np.concatenate(assembled) if len(assembled) > 1 else assembled[0]
    if normalize_final:
        final = match_peak(final, 0.95)
    return final.astype(np.float32), sr
