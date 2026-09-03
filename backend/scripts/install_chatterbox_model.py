#!/usr/bin/env python3
"""
Explicit one-time Chatterbox Multilingual model installer.

This is the ONLY place that may contact Hugging Face for model weights.
Normal generation / the desktop API must use local files only.

Usage:
  backend/.venv/bin/python backend/scripts/install_chatterbox_model.py
  backend/.venv/bin/python backend/scripts/install_chatterbox_model.py \
    --from-local dist/OfflineVoice-Models
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEST = ROOT / "models" / "tts" / "chatterbox"
REPO_ID = "ResembleAI/chatterbox"

sys.path.insert(0, str(ROOT / "backend"))
from app.services.model_package import (  # noqa: E402
    install_chatterbox_from_package,
    install_pkuseg_from_package,
    validate_chatterbox_dir,
)


def install(dest: Path, revision: str = "main") -> Path:
    dest = dest.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Allow network only inside this installer.
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    from huggingface_hub import snapshot_download

    print(f"Downloading {REPO_ID} → {dest}")
    print("Internet required: YES — first-time setup only")
    print()

    snapshot_download(
        repo_id=REPO_ID,
        repo_type="model",
        revision=revision,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        allow_patterns=[
            "ve.pt",
            "t3_mtl23ls_v2.safetensors",
            "s3gen.pt",
            "grapheme_mtl_merged_expanded_v1.json",
            "conds.pt",
            "Cangjie5_TC.json",
            "README.md",
            "LICENSE",
        ],
    )

    report = validate_chatterbox_dir(dest)
    if not report.valid:
        raise RuntimeError(report.message)

    print()
    print("Offline AI setup complete.")
    print(f"Model files stored at: {dest}")
    print("You can now disconnect from the Internet.")
    print("All speech generation happens locally.")
    return dest


def install_from_local_package(package_dir: Path, dest: Path) -> Path:
    """Air-gapped install from an Offline Model Package folder."""
    report = install_chatterbox_from_package(package_dir, dest)
    if not report.valid:
        raise ValueError(report.message)
    extras_root = dest.parents[1] if dest.name == "chatterbox" else dest.parent
    # models/tts/chatterbox -> models
    models_root = dest
    while models_root.name not in {"models", ""} and models_root != models_root.parent:
        if models_root.name == "tts" and (models_root.parent / "tts").exists():
            models_root = models_root.parent
            break
        models_root = models_root.parent
    if models_root.name != "models":
        models_root = dest.parent.parent if dest.parent.name == "tts" else dest.parent
    install_pkuseg_from_package(package_dir, models_root)
    print(f"Installed local model package → {dest}")
    print(report.message)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Chatterbox Multilingual locally")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--from-local",
        type=Path,
        default=None,
        help="Install from OfflineVoice-Models package (no Internet)",
    )
    parser.add_argument("--revision", default="main")
    args = parser.parse_args()

    try:
        if args.from_local:
            install_from_local_package(args.from_local, args.dest)
        else:
            install(args.dest, revision=args.revision)
    except Exception as exc:
        print(f"ERROR: model installation failed: {exc}", file=sys.stderr)
        print(
            "If Internet is unavailable, use --from-local /path/to/OfflineVoice-Models",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
