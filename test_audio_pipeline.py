#!/usr/bin/env python3
"""
PHASE 2 — Audio pipeline smoke test.

Exercises:
  - reference preprocess + validation
  - long-text chunking + pause markers
  - per-chunk TTS
  - crossfade join
  - WAV + MP3 export

Usage:
  cd offline-voice
  backend/.venv/bin/python test_audio_pipeline.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.audio.chunker import chunk_text
from app.audio.pipeline import AudioPipeline
from app.audio.preprocess import preprocess_reference
from app.audio.validate import validate_reference_audio
from app.tts.chatterbox_engine import ChatterboxEngine, detect_device
from app.tts.errors import ModelNotInstalledError

MODELS_DIR = ROOT / "models" / "tts" / "chatterbox"
VOICE_PATH = ROOT / "voices" / "test.wav"
WORK = ROOT / "outputs" / "phase2"
OUT_DIR = ROOT / "outputs"

LONG_HINDI = """नमस्ते, मेरा नाम चंदन है। आज हम एक नए विषय के बारे में बात करेंगे।

[pause:0.8s]

हम स्वास्थ्य और तकनीक के मिलन पर चर्चा करेंगे। SUBHAG HealthTech एक महत्वपूर्ण उदाहरण है।
यह पूरी तरह से स्थानीय प्रणाली पर चलता है।"""

LONG_ENGLISH = """Hello, my name is Chandan. Today we are going to discuss an interesting topic.

[pause:1s]

We will talk about fertility care and local AI voice tools. SUBHAG HealthTech is building offline-first experiences.
This generation happens entirely on your Mac."""

PRONUNCIATION = {
    "SUBHAG": "सुभाग",
    "HealthTech": "हेल्थटेक",
}


def main() -> int:
    print("=== OfflineVoice PHASE 2 — Audio Pipeline Test ===")
    print(f"Device: {detect_device()}")
    print()

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    if not VOICE_PATH.is_file():
        print(f"ERROR: missing reference voice: {VOICE_PATH}")
        return 1

    # --- Validation + preprocess (no TTS) ---
    print("Validating reference...")
    report = validate_reference_audio(VOICE_PATH, work_dir=WORK / ".validate_tmp")
    print(report.summary())
    print()

    print("Preprocessing reference...")
    pre = preprocess_reference(VOICE_PATH, WORK / "reference" / "reference.wav")
    print(f"  -> {pre.output_path} ({pre.duration_sec:.1f}s @ {pre.sample_rate} Hz)")
    print()

    # --- Chunking unit check ---
    plan = chunk_text(LONG_HINDI, max_chars=80, language="hi", pronunciation=PRONUNCIATION)
    print(f"Hindi plan: {len(plan.chunks)} segments, {plan.total_speech_chunks} speech chunks")
    for c in plan.chunks:
        if c.kind == "pause":
            print(f"  [{c.index}] PAUSE {c.pause_seconds}s")
        else:
            preview = c.text.replace("\n", " ")[:70]
            print(f"  [{c.index}] SPEECH ({len(c.text)} chars): {preview}")
    print()

    engine = ChatterboxEngine(MODELS_DIR)
    if not engine.is_available():
        print("TTS model is not installed.")
        print("Run: python backend/scripts/install_chatterbox_model.py")
        return 2

    def on_progress(stage: str, pct: float, extra: dict) -> None:
        extra_s = ""
        if "current_chunk" in extra:
            extra_s = f"  chunk {extra['current_chunk']}/{extra.get('total_chunks')}"
        print(f"[{pct:5.1f}%] {stage}{extra_s}")

    # --- Hindi long-form ---
    hi_dir = WORK / "hindi"
    pipe_hi = AudioPipeline(engine, work_dir=hi_dir, max_chars=120)
    print("Generating Hindi long-form...")
    t0 = time.time()
    try:
        hi = pipe_hi.generate(
            LONG_HINDI,
            language="hi",
            reference_audio=VOICE_PATH,
            output_basename="hindi_long",
            pronunciation=PRONUNCIATION,
            export_mp3_file=True,
            on_progress=on_progress,
        )
    except ModelNotInstalledError as exc:
        print(exc)
        return 2
    print(f"Hindi done in {time.time() - t0:.1f}s")
    print(f"  WAV: {hi.output_wav}")
    print(f"  MP3: {hi.output_mp3}")
    print(f"  duration: {hi.duration_sec:.1f}s  speech_chunks: {hi.speech_chunks}")
    print()

    # Copy convenience links into outputs/
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src_name, dst_name in [
        (hi.output_wav, "hindi_long.wav"),
        (hi.output_mp3, "hindi_long.mp3"),
    ]:
        if src_name:
            dst = OUT_DIR / dst_name
            dst.write_bytes(Path(src_name).read_bytes())

    # --- English long-form (reuse loaded model) ---
    en_dir = WORK / "english"
    pipe_en = AudioPipeline(engine, work_dir=en_dir, max_chars=120)
    print("Generating English long-form...")
    t1 = time.time()
    en = pipe_en.generate(
        LONG_ENGLISH,
        language="en",
        reference_audio=VOICE_PATH,
        output_basename="english_long",
        pronunciation={"SUBHAG": "Soobhag", "HealthTech": "Health Tech"},
        export_mp3_file=True,
        on_progress=on_progress,
    )
    print(f"English done in {time.time() - t1:.1f}s")
    print(f"  WAV: {en.output_wav}")
    print(f"  MP3: {en.output_mp3}")
    print(f"  duration: {en.duration_sec:.1f}s  speech_chunks: {en.speech_chunks}")

    for src_name, dst_name in [
        (en.output_wav, "english_long.wav"),
        (en.output_mp3, "english_long.mp3"),
    ]:
        if src_name:
            dst = OUT_DIR / dst_name
            dst.write_bytes(Path(src_name).read_bytes())

    print("\nDone.")
    print("outputs/hindi_long.wav")
    print("outputs/hindi_long.mp3")
    print("outputs/english_long.wav")
    print("outputs/english_long.mp3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
