#!/usr/bin/env python3
"""
Build an OfflineVoice-Models package from currently installed weights.

Usage:
  backend/.venv/bin/python backend/scripts/pack_offline_models.py \
    --out dist/OfflineVoice-Models

This copies local chatterbox weights (+ optional pkuseg) into a USB-friendly folder.
Never downloads anything.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.model_package import (  # noqa: E402
    build_manifest,
    validate_chatterbox_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack OfflineVoice offline model package")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "models" / "tts" / "chatterbox",
        help="Installed chatterbox directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / "OfflineVoice-Models",
        help="Output package directory",
    )
    parser.add_argument("--include-pkuseg", action="store_true", default=True)
    parser.add_argument("--no-pkuseg", action="store_true")
    args = parser.parse_args()

    src = args.source.expanduser().resolve()
    report = validate_chatterbox_dir(src)
    if not report.valid:
        print(f"ERROR: source model invalid: {report.message}", file=sys.stderr)
        return 1

    out = args.out.expanduser().resolve()
    if out.exists():
        shutil.rmtree(out)
    dest_cb = out / "tts" / "chatterbox"
    dest_cb.mkdir(parents=True)
    for item in src.iterdir():
        if item.name in {".cache", ".gitkeep"}:
            continue
        target = dest_cb / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    include_pkuseg = args.include_pkuseg and not args.no_pkuseg
    pkuseg_src = Path.home() / ".pkuseg"
    app_pkuseg = ROOT / "models" / "extras" / "pkuseg"
    if include_pkuseg:
        chosen = None
        if app_pkuseg.is_dir():
            chosen = app_pkuseg
        elif pkuseg_src.is_dir():
            chosen = pkuseg_src
        if chosen is not None:
            dest_pk = out / "extras" / "pkuseg"
            shutil.copytree(chosen, dest_pk)
            print(f"Included pkuseg from {chosen}")
        else:
            include_pkuseg = False
            print("WARN: pkuseg cache not found; package will omit it")

    manifest = build_manifest(chatterbox_dir=dest_cb, include_pkuseg=include_pkuseg)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote Offline Model Package → {out}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
