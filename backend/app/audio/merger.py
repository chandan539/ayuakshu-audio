"""Join generated audio chunks without overlapping speech or extra holes."""

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


def rms(audio: np.ndarray) -> float:
    if audio is None or len(audio) == 0:
        return 0.0
    x = np.asarray(audio, dtype=np.float32)
    return float(np.sqrt(np.mean(np.square(x))))


def wav_looks_like_speech(
    path: str | Path,
    *,
    min_sec: float = 0.18,
    min_rms: float = 0.007,
) -> bool:
    try:
        audio, sr = load_audio(path)
    except Exception:
        return False
    if sr <= 0 or len(audio) < int(sr * min_sec):
        return False
    return rms(audio) >= min_rms


def audio_too_short_for_text(audio: np.ndarray, sr: int, text: str) -> bool:
    """True when the WAV is much shorter than the script should take to speak."""
    if sr <= 0 or audio is None or len(audio) == 0:
        return True
    duration = len(audio) / sr
    chars = max(1, len((text or "").strip()))
    # Hindi/English local speech is roughly 8–16 characters per second.
    expected = max(0.35, chars / 16.0)
    return duration < expected * 0.30 or rms(audio) < 0.007


def trim_edge_silence(
    audio: np.ndarray,
    sr: int,
    *,
    thresh: float = 0.014,
    max_trim_ms: float = 320.0,
    pad_ms: float = 28.0,
) -> np.ndarray:
    """Remove leading/trailing hush only — never punch holes in the middle."""
    audio = _to_mono(audio)
    if len(audio) < sr * 0.05:
        return audio
    frame = max(1, int(sr * 0.01))
    kernel = np.ones(frame, dtype=np.float32) / float(frame)
    env = np.convolve(np.abs(audio), kernel, mode="same")
    voiced = np.where(env >= thresh)[0]
    if voiced.size == 0:
        return audio
    pad = int(sr * pad_ms / 1000.0)
    max_trim = int(sr * max_trim_ms / 1000.0)
    start = max(0, int(voiced[0]) - pad)
    end = min(len(audio), int(voiced[-1]) + pad + 1)
    if start > max_trim:
        start = max_trim
    if len(audio) - end > max_trim:
        end = len(audio) - max_trim
    if end - start < int(sr * 0.08):
        return audio
    return audio[start:end].astype(np.float32)


def tighten_pauses(
    audio: np.ndarray,
    sr: int,
    *,
    min_pause_ms: float = 200.0,
    keep_ms: float = 90.0,
) -> np.ndarray:
    """Shrink the long hole a model leaves after a full stop.

    A short breath stays. Speech itself is not cut or overlapped.
    """
    audio = _to_mono(audio)
    if sr <= 0 or len(audio) < int(sr * 0.25):
        return audio
    frame = max(1, int(sr * 0.01))
    kernel = np.ones(frame, dtype=np.float32) / float(frame)
    env = np.convolve(np.abs(audio), kernel, mode="same")
    loud = float(np.percentile(env, 95)) if len(env) else 0.0
    thresh = max(0.008, loud * 0.08)
    quiet = env < thresh
    min_pause = int(sr * min_pause_ms / 1000.0)
    keep = max(1, int(sr * keep_ms / 1000.0))
    pieces: list[np.ndarray] = []
    changed = False
    i = 0
    n = len(quiet)
    while i < n:
        j = i + 1
        while j < n and quiet[j] == quiet[i]:
            j += 1
        piece = audio[i:j]
        if quiet[i] and (j - i) > min_pause:
            piece = piece[:keep]
            changed = True
        pieces.append(piece)
        i = j
    if not changed:
        return audio
    return np.concatenate(pieces).astype(np.float32)


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
    # Don't boost quiet/noisy chunks — that makes artifacts harsh.
    if peak < 0.08:
        return audio.astype(np.float32)
    return (audio * (target_peak / peak)).astype(np.float32)


def crossfade_join(
    chunks: list[np.ndarray],
    sr: int,
    *,
    crossfade_ms: float = 40.0,
    gap_ms: float = 0.0,
) -> np.ndarray:
    """
    Concatenate mono float32 arrays.

    Speech joins should use a short breath gap (gap_ms), not a long overlap.
    Overlap mixes two different sentences and sounds overspoken.
    """
    if not chunks:
        return np.zeros(0, dtype=np.float32)

    prepared = [
        apply_fade(
            trim_edge_silence(_to_mono(c), sr),
            sr,
            fade_in_ms=6.0,
            fade_out_ms=6.0,
        )
        for c in chunks
    ]
    if len(prepared) == 1:
        return prepared[0]

    # Default: no overlap. A 70 ms breath is a pause, not two voices at once.
    use_gap = gap_ms > 0 or crossfade_ms <= 0
    if use_gap:
        breath = gap_ms if gap_ms > 0 else 70.0
        parts: list[np.ndarray] = []
        for i, piece in enumerate(prepared):
            if i:
                parts.append(silence(breath / 1000.0, sr))
            parts.append(piece)
        return np.concatenate(parts).astype(np.float32)

    xfade = int(sr * crossfade_ms / 1000.0)
    out = prepared[0]
    for nxt in prepared[1:]:
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
    gap_ms: float = 40.0,
    normalize_final: bool = True,
) -> tuple[np.ndarray, int]:
    """
    segments: list of ("speech", wav_path) or ("pause", seconds)

    Sequential speech is joined with a very short breath, not an overlapping crossfade.
    Long silences after a full stop are shortened before this join.
    Explicit [pause:Ns] markers still insert that much silence.
    """
    del crossfade_ms  # overlap joins caused doubled/garbled speech at chunk borders
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
            assembled.append(crossfade_join(speech_audio, sr, crossfade_ms=0.0, gap_ms=gap_ms))
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
        audio = tighten_pauses(trim_edge_silence(audio, sr, max_trim_ms=1200.0, pad_ms=40.0), sr)
        speech_audio.append(audio)

    flush_speech()
    if sr is None:
        return np.zeros(0, dtype=np.float32), 24000

    if not assembled:
        return np.zeros(0, dtype=np.float32), sr

    final = np.concatenate(assembled) if len(assembled) > 1 else assembled[0]
    if normalize_final:
        final = match_peak(final, 0.92)
    return final.astype(np.float32), sr
