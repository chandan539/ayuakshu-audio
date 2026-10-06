"""TTS chunk cache helpers."""

from pathlib import Path

import numpy as np
import soundfile as sf

from app.audio.merger import crossfade_join, wav_looks_like_speech
from app.services.tts_cache import chunk_cache_path, copy_if_cached, store_chunk


def _tone(path: Path, seconds: float = 0.4, sr: int = 24000) -> None:
    t = np.arange(int(sr * seconds)) / sr
    audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(path, audio, sr)


def test_chunk_cache_hit_and_miss(tmp_path: Path):
    generated = tmp_path / "out.wav"
    _tone(generated)
    cache = chunk_cache_path(
        tmp_path,
        text="नमस्ते",
        voice_id="voice_1",
        language="hi",
        clone_mode="fast",
        ref_mtime_ns=123,
    )
    dest = tmp_path / "job" / "chunk.wav"
    assert copy_if_cached(cache, dest) is False
    store_chunk(cache, generated)
    assert cache.is_file()
    assert copy_if_cached(cache, dest) is True
    assert wav_looks_like_speech(dest)

    other = chunk_cache_path(
        tmp_path,
        text="नमस्ते!",
        voice_id="voice_1",
        language="hi",
        clone_mode="fast",
        ref_mtime_ns=123,
    )
    assert other != cache


def test_breath_join_does_not_overlap_speech():
    sr = 24000
    a = np.ones(sr, dtype=np.float32) * 0.4
    b = np.ones(sr, dtype=np.float32) * 0.4
    out = crossfade_join([a, b], sr, crossfade_ms=0.0, gap_ms=70.0)
    naive = len(a) + len(b)
    # Breath gap makes the result *longer* than concat, never overlapping.
    assert len(out) > naive
    assert abs(len(out) - naive - int(sr * 0.07)) < 80


def test_health_includes_device(client):
    body = client.get("/health").json()
    assert "tts_device" in body
    assert body["tts_device"] in {"mps", "cpu", "cuda", "unknown"}
