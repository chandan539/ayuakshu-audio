"""Local TTS model path validation and offline package handling.

Generation never downloads. This module only inspects / copies local files.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CHATTERBOX_REQUIRED = (
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
)

CHATTERBOX_OPTIONAL = (
    "conds.pt",
    "Cangjie5_TC.json",
    "README.md",
    "LICENSE",
)

MANIFEST_NAME = "manifest.json"
PACKAGE_VERSION = "1.0.0"


@dataclass
class FileCheck:
    name: str
    present: bool
    size_bytes: int = 0
    required: bool = True


@dataclass
class ValidationReport:
    model_id: str
    path: str
    valid: bool
    ready_offline: bool
    missing_required: list[str] = field(default_factory=list)
    files: list[FileCheck] = field(default_factory=list)
    size_bytes: int = 0
    message: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file() and p.name != ".gitkeep":
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def validate_chatterbox_dir(model_dir: Path) -> ValidationReport:
    model_dir = Path(model_dir).expanduser().resolve()
    files: list[FileCheck] = []
    missing: list[str] = []

    for name in CHATTERBOX_REQUIRED:
        p = model_dir / name
        ok = p.is_file()
        size = p.stat().st_size if ok else 0
        files.append(FileCheck(name=name, present=ok, size_bytes=size, required=True))
        if not ok:
            missing.append(name)

    for name in CHATTERBOX_OPTIONAL:
        p = model_dir / name
        ok = p.is_file()
        size = p.stat().st_size if ok else 0
        files.append(FileCheck(name=name, present=ok, size_bytes=size, required=False))

    valid = len(missing) == 0 and model_dir.is_dir()
    size = dir_size(model_dir) if model_dir.exists() else 0
    if not model_dir.exists():
        message = "Model directory does not exist."
    elif missing:
        message = f"Missing required files: {', '.join(missing)}"
    else:
        message = "✓ Installed · ✓ Ready for offline use"

    return ValidationReport(
        model_id="chatterbox",
        path=str(model_dir),
        valid=valid,
        ready_offline=valid,
        missing_required=missing,
        files=files,
        size_bytes=size,
        message=message,
    )


def find_chatterbox_source(package_dir: Path) -> Path:
    """
    Accept either:
      OfflineVoice-Models/chatterbox/...
      OfflineVoice-Models/tts/chatterbox/...
      OfflineVoice-Models/  (files directly)
    """
    package_dir = Path(package_dir).expanduser().resolve()
    if not package_dir.is_dir():
        raise FileNotFoundError(f"Local model package not found: {package_dir}")

    candidates = [
        package_dir / "tts" / "chatterbox",
        package_dir / "chatterbox",
        package_dir,
    ]
    for candidate in candidates:
        report = validate_chatterbox_dir(candidate)
        if report.valid:
            return candidate

    # Prefer the most specific path for error messaging.
    for candidate in candidates:
        if candidate.is_dir():
            report = validate_chatterbox_dir(candidate)
            raise ValueError(
                f"Invalid Offline Model Package at {candidate}: {report.message}"
            )
    raise ValueError(f"No chatterbox folder found in {package_dir}")


def read_manifest(package_dir: Path) -> dict[str, Any] | None:
    path = Path(package_dir) / MANIFEST_NAME
    if not path.is_file():
        # Also check parent-style package root when pointing at chatterbox subdir.
        alt = Path(package_dir).parent / MANIFEST_NAME
        if alt.is_file():
            path = alt
        else:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {MANIFEST_NAME}: {exc}") from exc


def validate_offline_package(package_dir: Path) -> dict[str, Any]:
    package_dir = Path(package_dir).expanduser().resolve()
    src = find_chatterbox_source(package_dir)
    report = validate_chatterbox_dir(src)
    manifest = read_manifest(package_dir if (package_dir / MANIFEST_NAME).is_file() else src.parent)
    pkuseg = _locate_pkuseg(package_dir)
    return {
        "valid": report.valid,
        "package_dir": str(package_dir),
        "chatterbox_source": str(src),
        "manifest": manifest,
        "chatterbox": report.to_dict(),
        "pkuseg_included": pkuseg is not None,
        "pkuseg_path": str(pkuseg) if pkuseg else None,
        "message": report.message
        if report.valid
        else "Internet is unavailable for downloads. Fix the local model package, then retry.",
    }


def _locate_pkuseg(package_dir: Path) -> Path | None:
    candidates = [
        package_dir / "extras" / "pkuseg",
        package_dir / "pkuseg",
        package_dir / "whisper",  # ignore
    ]
    for c in candidates[:2]:
        if c.is_dir() and any(c.iterdir()):
            return c
    return None


def install_chatterbox_from_package(package_dir: Path, dest_dir: Path) -> ValidationReport:
    src = find_chatterbox_source(package_dir)
    dest_dir = Path(dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Replace destination contents carefully (keep directory).
    for item in list(dest_dir.iterdir()):
        if item.name == ".gitkeep":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)

    for item in src.iterdir():
        target = dest_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    return validate_chatterbox_dir(dest_dir)


def install_pkuseg_from_package(package_dir: Path, dest_root: Path) -> Path | None:
    """
    Copy pkuseg assets into app models/extras/pkuseg and user ~/.pkuseg
    so Chinese tokenizer sidecars work offline (Hindi/English still work without it).
    """
    src = _locate_pkuseg(package_dir)
    if src is None:
        # Fall back to already-cached user pkuseg if present.
        home_cache = Path.home() / ".pkuseg"
        if home_cache.is_dir() and any(home_cache.iterdir()):
            dest = Path(dest_root) / "extras" / "pkuseg"
            dest.mkdir(parents=True, exist_ok=True)
            for item in home_cache.iterdir():
                target = dest / item.name
                if item.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            return dest
        return None

    dest = Path(dest_root) / "extras" / "pkuseg"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)

    home_cache = Path.home() / ".pkuseg"
    home_cache.mkdir(parents=True, exist_ok=True)
    for item in dest.iterdir():
        target = home_cache / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return dest


def build_manifest(
    *,
    chatterbox_dir: Path,
    include_pkuseg: bool,
) -> dict[str, Any]:
    report = validate_chatterbox_dir(chatterbox_dir)
    return {
        "name": "OfflineVoice-Models",
        "version": PACKAGE_VERSION,
        "created_for": "AYUAKSHU Audio",
        "models": [
            {
                "id": "chatterbox",
                "name": "Chatterbox Multilingual",
                "path": "tts/chatterbox",
                "required_files": list(CHATTERBOX_REQUIRED),
                "optional_files": list(CHATTERBOX_OPTIONAL),
                "size_bytes": report.size_bytes,
                "valid": report.valid,
            }
        ],
        "extras": {
            "pkuseg": include_pkuseg,
            "pkuseg_path": "extras/pkuseg" if include_pkuseg else None,
        },
        "notes": [
            "Install with AYUAKSHU Audio → Models → Install from Offline Model Package",
            "Or: python backend/scripts/install_chatterbox_model.py --from-local ./OfflineVoice-Models",
            "Do not place multi-GB weights inside the application DMG for v1",
        ],
    }
