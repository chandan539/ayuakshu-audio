"""Copy generated audio to a user-chosen folder (Desktop, USB, etc.)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..security import PathSecurityError, ensure_export_destination, sanitize_filename


def _copy_file(src: Path, dest: Path) -> Path:
    dest = ensure_export_destination(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return dest
    shutil.copy2(src, dest)
    return dest


def reveal_in_finder(path: Path) -> None:
    """Show the file in Finder on macOS. No-op on other platforms."""
    if not path.exists():
        return
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)


def export_job_files(
    job: dict[str, Any],
    *,
    fmt: str,
    destination: str,
    reveal: bool = True,
) -> dict[str, Any]:
    fmt = (fmt or "wav").strip().lower()
    if fmt not in {"wav", "mp3", "both"}:
        raise ValueError("format must be wav, mp3, or both")

    dest = Path(destination).expanduser()
    copied: list[dict[str, str]] = []

    wav_src = Path(job["output_wav"]) if job.get("output_wav") else None
    mp3_src = Path(job["output_mp3"]) if job.get("output_mp3") else None

    if fmt in {"wav", "both"} and (not wav_src or not wav_src.is_file()):
        raise FileNotFoundError("WAV is not ready to export yet")
    if fmt in {"mp3", "both"} and (not mp3_src or not mp3_src.is_file()):
        raise FileNotFoundError("MP3 is not ready to export yet")

    if fmt == "both":
        folder = dest if dest.suffix.lower() not in {".wav", ".mp3"} else dest.parent
        folder = ensure_export_destination(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stem = sanitize_filename(dest.stem if dest.suffix.lower() in {".wav", ".mp3"} else "AYUAKSHU-Audio")
        wav_out = _copy_file(wav_src, folder / f"{stem}.wav")  # type: ignore[arg-type]
        copied.append({"format": "wav", "path": str(wav_out)})
        mp3_out = _copy_file(mp3_src, folder / f"{stem}.mp3")  # type: ignore[arg-type]
        copied.append({"format": "mp3", "path": str(mp3_out)})
        reveal_path = wav_out
        folder_out = folder
    else:
        src = wav_src if fmt == "wav" else mp3_src
        suffix = ".wav" if fmt == "wav" else ".mp3"
        if dest.suffix.lower() != suffix:
            dest = dest.with_suffix(suffix)
        out = _copy_file(src, dest)  # type: ignore[arg-type]
        copied.append({"format": fmt, "path": str(out)})
        reveal_path = out
        folder_out = out.parent

    if reveal:
        reveal_in_finder(reveal_path)

    return {
        "ok": True,
        "copied": copied,
        "folder": str(folder_out),
        "message": f"Saved to {folder_out}",
    }


def reveal_job_file(job: dict[str, Any], fmt: str = "wav") -> dict[str, Any]:
    key = "output_mp3" if fmt == "mp3" else "output_wav"
    raw = job.get(key) or job.get("output_wav") or job.get("output_mp3")
    if not raw:
        raise FileNotFoundError("No generated audio to show yet")
    path = Path(raw)
    if not path.exists():
        raise FileNotFoundError(f"File missing on disk: {path}")
    reveal_in_finder(path)
    return {"ok": True, "path": str(path), "folder": str(path.parent)}
