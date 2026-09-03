#!/usr/bin/env python3
"""
Explicit one-time Whisper model installer (local STT).

Internet required: YES — first-time setup only
After setup: Internet required: NO

Usage:
  backend/.venv/bin/python backend/scripts/install_whisper_model.py
  backend/.venv/bin/python backend/scripts/install_whisper_model.py --size base
  backend/.venv/bin/python backend/scripts/install_whisper_model.py \\
    --dest ~/Library/Application\\ Support/AYUAKSHU\\ Audio/models/whisper
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEST = ROOT / "models" / "whisper"
DEFAULT_SIZE = "small"

sys.path.insert(0, str(ROOT / "backend"))
from app.stt.whisper_engine import validate_whisper_dir  # noqa: E402


def install(dest: Path, size: str) -> Path:
    dest = dest.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Allow network only inside this installer.
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    import ssl
    import urllib.request

    import certifi
    import whisper

    print(f"Downloading Whisper '{size}' → {dest}")
    print("Internet required: YES — first-time setup only")
    print()

    url = whisper._MODELS[size]
    target = dest / f"{size}.pt"
    if not target.is_file() or target.stat().st_size < 1_000_000:
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, context=ctx) as source, open(target, "wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)

    # Load once to verify the checkpoint
    model = whisper.load_model(size, download_root=str(dest))
    del model

    report = validate_whisper_dir(dest)
    if not report.installed:
        raise RuntimeError(report.message)

    print()
    print("Offline Whisper setup complete.")
    print(f"Model files stored at: {dest}")
    print("You can now disconnect from the Internet.")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Install local Whisper STT weights")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        choices=["tiny", "base", "small", "medium"],
        help="Whisper checkpoint size (default: small — good Hindi/English balance)",
    )
    parser.add_argument(
        "--also",
        action="append",
        default=[],
        help="Extra destination directories to copy the installed weights into",
    )
    args = parser.parse_args()

    primary = install(args.dest, args.size)
    weight = primary / f"{args.size}.pt"

    extras = list(args.also)
    # Sensible defaults for this Mac app layout
    home = Path.home()
    for auto in (
        home / "Library/Application Support/AYUAKSHU Audio/models/whisper",
        home / "Library/Application Support/OfflineVoice/models/whisper",
    ):
        if str(auto.resolve()) != str(primary.resolve()) and auto not in extras:
            extras.append(str(auto))

    for extra in extras:
        dest = Path(extra).expanduser().resolve()
        if dest == primary:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / weight.name
        if not target.exists():
            try:
                # APFS clone when possible
                import subprocess

                subprocess.run(["cp", "-c", str(weight), str(target)], check=False)
                if not target.exists():
                    shutil.copy2(weight, target)
            except Exception:
                shutil.copy2(weight, target)
        print(f"Also installed → {dest}")

    print(validate_whisper_dir(primary).message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
