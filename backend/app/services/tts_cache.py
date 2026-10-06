"""Reuse identical TTS chunks (same text + voice + mode) instead of re-inferring."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..audio.merger import wav_looks_like_speech


def chunk_cache_path(
    cache_root: Path,
    *,
    text: str,
    voice_id: str,
    language: str,
    clone_mode: str,
    ref_mtime_ns: int,
) -> Path:
    payload = "\n".join(
        [
            "cache-v2-breath-join",
            clone_mode,
            language,
            voice_id,
            str(ref_mtime_ns),
            text,
        ]
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return Path(cache_root) / "tts_chunks" / f"{digest}.wav"


def copy_if_cached(cache_file: Path, dest: Path) -> bool:
    if not cache_file.is_file() or cache_file.stat().st_size < 256:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_file, dest)
    if not wav_looks_like_speech(dest):
        dest.unlink(missing_ok=True)
        cache_file.unlink(missing_ok=True)
        return False
    return True


def store_chunk(cache_file: Path, generated: Path, *, max_files: int = 400) -> None:
    if not generated.is_file() or not wav_looks_like_speech(generated):
        return
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated, cache_file)
    _prune(cache_file.parent, max_files=max_files)


def _prune(folder: Path, *, max_files: int) -> None:
    files = sorted(folder.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    extra = len(files) - max_files
    if extra <= 0:
        return
    for stale in files[:extra]:
        stale.unlink(missing_ok=True)
