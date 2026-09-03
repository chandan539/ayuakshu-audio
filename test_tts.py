#!/usr/bin/env python3
"""
PHASE 1 — Offline TTS smoke test.

Loads a local Chatterbox Multilingual model + local reference voice,
generates Hindi and English WAV files, then exits.

Usage (from offline-voice/):
  source backend/.venv/bin/activate
  python test_tts.py

Or:
  backend/.venv/bin/python test_tts.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.tts.chatterbox_engine import ChatterboxEngine, detect_device
from app.tts.errors import ModelNotInstalledError

MODELS_DIR = ROOT / "models" / "tts" / "chatterbox"
VOICE_PATH = ROOT / "voices" / "test.wav"
OUTPUT_DIR = ROOT / "outputs"

HINDI_TEXT = "नमस्ते, मेरा नाम चंदन है। आज हम एक नए विषय के बारे में बात करेंगे।"
ENGLISH_TEXT = (
    "Hello, my name is Chandan. Today we are going to discuss an interesting topic."
)


def main() -> int:
    print("=== OfflineVoice PHASE 1 — TTS Engine Test ===")
    print(f"Models dir : {MODELS_DIR}")
    print(f"Reference  : {VOICE_PATH}")
    print(f"Device     : {detect_device()}")
    print()

    if not VOICE_PATH.is_file():
        print(f"ERROR: reference voice missing: {VOICE_PATH}")
        return 1

    # Generation must never download. Installer script populates MODELS_DIR.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    engine = ChatterboxEngine(MODELS_DIR)

    if not engine.is_available():
        print("TTS model is not installed.")
        print("Run:  python backend/scripts/install_chatterbox_model.py")
        print("Then re-run this test (optionally with Wi-Fi OFF).")
        return 2

    print("Loading model...")
    t0 = time.time()
    try:
        engine.load()
    except ModelNotInstalledError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Model loaded in {time.time() - t0:.1f}s.\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    hindi_out = OUTPUT_DIR / "hindi.wav"
    english_out = OUTPUT_DIR / "english.wav"

    print("Generating Hindi...")
    t1 = time.time()
    engine.generate(
        text=HINDI_TEXT,
        language="hi",
        reference_audio=str(VOICE_PATH),
        output_path=str(hindi_out),
    )
    print(f"  -> {hindi_out}  ({time.time() - t1:.1f}s)")

    print("Generating English...")
    t2 = time.time()
    engine.generate(
        text=ENGLISH_TEXT,
        language="en",
        reference_audio=str(VOICE_PATH),
        output_path=str(english_out),
    )
    print(f"  -> {english_out}  ({time.time() - t2:.1f}s)")

    print("\nDone.")
    print(f"outputs/hindi.wav   size={hindi_out.stat().st_size} bytes")
    print(f"outputs/english.wav size={english_out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
