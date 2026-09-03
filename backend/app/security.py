"""Path safety: keep all file access inside approved app directories."""

from __future__ import annotations

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
