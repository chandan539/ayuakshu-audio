"""Unit tests for Phase 2 audio modules (no TTS model required)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.audio.chunker import chunk_speech_text, chunk_text, parse_pause_markers
from app.audio.export import export_mp3, export_wav
from app.audio.merger import crossfade_join, join_segments, silence


def test_parse_pause_markers():
    parts = parse_pause_markers("Hello.[pause:1s]World")
    assert parts[0] == ("speech", "Hello.")
    assert parts[1][0] == "pause"
    assert parts[1][1] == 1.0
    assert parts[2] == ("speech", "World")


def test_chunk_never_splits_mid_word_when_possible():
    text = "alpha beta gamma delta epsilon zeta"
    parts = chunk_speech_text(text, max_chars=12)
    assert all(" " not in p.strip() or p in text for p in parts)
    # Rejoin should preserve words
    joined = " ".join(parts)
    assert "alpha" in joined and "zeta" in joined
    assert all(len(p) <= 12 or " " not in p for p in parts)


def test_hindi_sentence_chunking():
    text = "नमस्ते, मेरा नाम चंदन है। आज हम बात करेंगे।"
    plan = chunk_text(text, max_chars=20, language="hi")
    assert plan.total_speech_chunks >= 1
    assert all(c.text for c in plan.speech_chunks)
    # Devanagari preserved
    assert any("नमस्ते" in c.text or "चंदन" in c.text or "बात" in c.text for c in plan.speech_chunks)


def test_pronunciation_and_pause_plan():
    text = "Welcome to SUBHAG HealthTech.[pause:0.5s]Let's begin."
    plan = chunk_text(
        text,
        max_chars=200,
        pronunciation={"SUBHAG": "सुभाग", "HealthTech": "हेल्थटेक"},
    )
    speech = " ".join(c.text for c in plan.speech_chunks)
    assert "सुभाग" in speech
    assert "हेल्थटेक" in speech
    assert any(c.kind == "pause" and c.pause_seconds == 0.5 for c in plan.chunks)


def test_crossfade_join_length():
    sr = 24000
    a = np.ones(sr, dtype=np.float32) * 0.5
    b = np.ones(sr, dtype=np.float32) * 0.5
    out = crossfade_join([a, b], sr, crossfade_ms=40.0)
    # Overlap reduces total length vs naive concat
    naive = len(a) + len(b)
    assert len(out) < naive
    assert len(out) > sr  # still longer than one chunk


def test_join_segments_with_pause(tmp_path: Path):
    sr = 24000
    wav1 = tmp_path / "a.wav"
    wav2 = tmp_path / "b.wav"
    # Each clip is 0.5s
    sf.write(wav1, np.ones(sr // 2, dtype=np.float32) * 0.4, sr)
    sf.write(wav2, np.ones(sr // 2, dtype=np.float32) * 0.4, sr)
    audio, out_sr = join_segments(
        [("speech", wav1), ("pause", 0.25), ("speech", wav2)],
        crossfade_ms=20.0,
    )
    assert out_sr == sr
    # 0.5 + 0.25 + 0.5 = 1.25s
    assert 1.2 < len(audio) / sr < 1.35


def test_export_wav_and_mp3(tmp_path: Path):
    sr = 24000
    audio = silence(0.3, sr)
    # Add a soft tone so MP3 encoder has content
    t = np.arange(len(audio)) / sr
    audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav = export_wav(audio, sr, tmp_path / "t.wav")
    assert wav.is_file() and wav.stat().st_size > 100
    mp3 = export_mp3(wav, tmp_path / "t.mp3", bitrate_kbps=192)
    assert mp3.is_file() and mp3.stat().st_size > 100


def test_paragraph_priority_chunking():
    text = "First paragraph stays together if short.\n\nSecond paragraph is separate."
    plan = chunk_text(text, max_chars=100)
    assert plan.total_speech_chunks >= 1
    # With large max_chars, two paragraphs may pack into one or two chunks
    assert all(len(c.text) <= 100 for c in plan.speech_chunks)
