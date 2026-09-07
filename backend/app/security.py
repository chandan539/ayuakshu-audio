"""Path safety: keep all file access inside approved app directories."""

from __future__ import annotations

import os
import re
from pathlib import Path

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


class PathSecurityError(ValueError):
    pass


def sanitize_filename(name: str, *, default: str = "file") -> str:
    base = Path(name).name.strip()
    base = SAFE_NAME_RE.sub("_", base).strip("._")
    if not base:
        base = default
    return base[:180]


def sanitize_id(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", value.strip())
    if not cleaned:
        raise PathSecurityError("Empty identifier")
    return cleaned[:64]


def resolve_under(root: Path, *parts: str) -> Path:
    """
    Join path parts under root and reject traversal outside root.
    """
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError(f"Path escapes approved directory: {candidate}") from exc
    return candidate


def ensure_within(path: Path, *allowed_roots: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    for root in allowed_roots:
        root = root.resolve()
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PathSecurityError(f"Path not in approved directories: {resolved}")


def export_allowed_roots() -> list[Path]:
    """Places a user may save exported WAV/MP3 (Desktop, USB, test dirs)."""
    roots: list[Path] = [Path.home()]
    for extra in (
        Path("/Volumes"),
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/private/var/folders"),
        Path("/var/folders"),
        Path("/var/tmp"),
    ):
        if extra.exists():
            roots.append(extra)
    for env_key in ("OFFLINEVOICE_EXPORT_ROOT", "OFFLINEVOICE_DATA_DIR"):
        raw = os.environ.get(env_key)
        if raw:
            roots.append(Path(raw).expanduser())
    return roots


def ensure_export_destination(path: Path) -> Path:
    """Allow writing exports under Home, USB volumes, or temp (tests)."""
    resolved = Path(path).expanduser().resolve()
    if any(part.endswith(".app") for part in resolved.parts):
        raise PathSecurityError("Cannot export into an application bundle")
    blocked = (
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/etc"),
        Path("/Library"),
        Path("/Applications"),
    )
    for root in blocked:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise PathSecurityError(f"Cannot export to system location: {resolved}")
    return ensure_within(resolved, *export_allowed_roots())
