#!/usr/bin/env python3
"""Production entrypoint for the OfflineVoice local backend."""

from __future__ import annotations

import os
import sys


def _prepare_env() -> None:
    # Never allow accidental online model pulls in the shipped app.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")


def main() -> None:
    _prepare_env()
    # Ensure app package is importable when frozen / launched as a binary.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        sys.path.insert(0, sys._MEIPASS)  # type: ignore[attr-defined]
    from app.main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
