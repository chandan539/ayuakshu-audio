"""End-to-end local TTS audio pipeline (Phase 2).

Long text → normalize → chunk → generate each chunk → crossfade/join → WAV/MP3
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..tts.base import TTSEngine
from ..tts.errors import ModelNotInstalledError
from .chunker import ChunkPlan, TextChunk, chunk_text
from .export import export_mp3, export_wav
from .merger import join_segments
from .preprocess import preprocess_reference


ProgressCallback = Callable[[str, float, dict], None]


@dataclass
class ChunkArtifact:
    index: int
    kind: str
    text: str
    pause_seconds: float
    path: str | None
    status: str  # pending | done | skipped | error
    error: str | None = None


@dataclass
class PipelineResult:
    output_wav: str
    output_mp3: str | None
    language: str
    reference_audio: str
    max_chars: int
    total_chunks: int
    speech_chunks: int
    duration_sec: float
    sample_rate: int
    artifacts: list[ChunkArtifact] = field(default_factory=list)
    work_dir: str = ""
    elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class AudioPipeline:
    def __init__(
        self,
        engine: TTSEngine,
        *,
        work_dir: str | Path,
        max_chars: int | None = None,
        crossfade_ms: float = 40.0,
        mp3_bitrate: int = 192,
    ):
        self.engine = engine
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.max_chars = max_chars or getattr(engine, "default_chunk_chars", 1000)
        self.crossfade_ms = crossfade_ms
        self.mp3_bitrate = mp3_bitrate

    def prepare_reference(self, reference_audio: str | Path) -> Path:
        voices_dir = self.work_dir / "reference"
        voices_dir.mkdir(parents=True, exist_ok=True)
        out = voices_dir / "reference.wav"
        result = preprocess_reference(reference_audio, out)
        if not result.validation.usable:
            # Spec: allow imperfect but usable; block only unusable.
            raise ValueError(
                "Reference audio is not usable: "
                + "; ".join(result.validation.warnings or ["unknown issue"])
            )
        return Path(result.output_path)

    def plan(
        self,
        text: str,
        language: str,
        *,
        pronunciation: dict[str, str] | None = None,
        max_chars: int | None = None,
    ) -> ChunkPlan:
        return chunk_text(
            text,
            max_chars=max_chars or self.max_chars,
            language=language,
            pronunciation=pronunciation,
        )

    def generate(
        self,
        text: str,
        language: str,
        reference_audio: str | Path,
        *,
        output_basename: str = "final",
        pronunciation: dict[str, str] | None = None,
        max_chars: int | None = None,
        export_mp3_file: bool = True,
        regenerate_indices: set[int] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        """
        Run full pipeline. Model must already be installed locally.

        regenerate_indices: if set, only regenerate those speech chunk indices
        and reuse other existing chunk WAV files from work_dir/chunks/.
        """
        t0 = time.time()
        if not self.engine.is_available():
            raise ModelNotInstalledError(self.engine.name)

        def progress(stage: str, pct: float, **extra: object) -> None:
            if on_progress:
                on_progress(stage, pct, extra)

        progress("Preparing...", 1)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir = self.work_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        progress("Preparing reference voice...", 5)
        ref_path = self.prepare_reference(reference_audio)

        progress("Chunking text...", 10)
        plan = self.plan(
            text,
            language,
            pronunciation=pronunciation,
            max_chars=max_chars,
        )
        speech_total = plan.total_speech_chunks
        artifacts: list[ChunkArtifact] = []
        assembly: list[tuple[str, object]] = []

        progress("Loading model...", 15)
        self.engine.load()
        progress("AI model ready.", 20)

        speech_done = 0
        for chunk in plan.chunks:
            if chunk.kind == "pause":
                artifacts.append(
                    ChunkArtifact(
                        index=chunk.index,
                        kind="pause",
                        text="",
                        pause_seconds=chunk.pause_seconds,
                        path=None,
                        status="done",
                    )
                )
                assembly.append(("pause", chunk.pause_seconds))
                continue

            chunk_path = chunks_dir / f"chunk_{chunk.index:04d}.wav"
            reuse = (
                regenerate_indices is not None
                and chunk.index not in regenerate_indices
                and chunk_path.is_file()
            )

            if reuse:
                artifacts.append(
                    ChunkArtifact(
                        index=chunk.index,
                        kind="speech",
                        text=chunk.text,
                        pause_seconds=0.0,
                        path=str(chunk_path),
                        status="done",
                    )
                )
                assembly.append(("speech", chunk_path))
                speech_done += 1
                pct = 20 + 60 * (speech_done / max(speech_total, 1))
                progress(
                    f"Reusing chunk {speech_done}/{speech_total}",
                    pct,
                    current_chunk=speech_done,
                    total_chunks=speech_total,
                )
                continue

            pct = 20 + 60 * (speech_done / max(speech_total, 1))
            progress(
                f"Generating chunk {speech_done + 1}/{speech_total}",
                pct,
                current_chunk=speech_done + 1,
                total_chunks=speech_total,
                text_preview=chunk.text[:80],
            )
            try:
                self.engine.generate(
                    text=chunk.text,
                    language=language,
                    reference_audio=str(ref_path),
                    output_path=str(chunk_path),
                )
                artifacts.append(
                    ChunkArtifact(
                        index=chunk.index,
                        kind="speech",
                        text=chunk.text,
                        pause_seconds=0.0,
                        path=str(chunk_path),
                        status="done",
                    )
                )
                assembly.append(("speech", chunk_path))
            except Exception as exc:  # keep other chunks; surface error on artifact
                artifacts.append(
                    ChunkArtifact(
                        index=chunk.index,
                        kind="speech",
                        text=chunk.text,
                        pause_seconds=0.0,
                        path=None,
                        status="error",
                        error=str(exc),
                    )
                )
                raise
            speech_done += 1

        progress("Combining audio...", 85)
        audio, sr = join_segments(assembly, crossfade_ms=self.crossfade_ms)

        progress("Finalizing...", 92)
        wav_out = self.work_dir / f"{output_basename}.wav"
        export_wav(audio, sr, wav_out)

        mp3_out: Optional[Path] = None
        if export_mp3_file:
            mp3_path = self.work_dir / f"{output_basename}.mp3"
            mp3_out = export_mp3(wav_out, mp3_path, bitrate_kbps=self.mp3_bitrate)

        # Persist plan for crash recovery / sentence regeneration.
        meta = {
            "language": language,
            "reference_audio": str(ref_path),
            "max_chars": max_chars or self.max_chars,
            "chunks": [asdict(a) for a in artifacts],
            "output_wav": str(wav_out),
            "output_mp3": str(mp3_out) if mp3_out else None,
        }
        (self.work_dir / "pipeline_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        progress("Complete", 100)
        duration = float(len(audio) / sr) if sr else 0.0
        return PipelineResult(
            output_wav=str(wav_out),
            output_mp3=str(mp3_out) if mp3_out else None,
            language=language,
            reference_audio=str(ref_path),
            max_chars=max_chars or self.max_chars,
            total_chunks=len(plan.chunks),
            speech_chunks=speech_total,
            duration_sec=duration,
            sample_rate=sr,
            artifacts=artifacts,
            work_dir=str(self.work_dir),
            elapsed_sec=time.time() - t0,
        )

    def regenerate_chunk(
        self,
        chunk_index: int,
        text: str,
        language: str,
        reference_audio: str | Path,
        *,
        output_basename: str = "final",
        pronunciation: dict[str, str] | None = None,
        export_mp3_file: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Regenerate a single speech chunk, then rebuild the final audio."""
        return self.generate(
            text=text,
            language=language,
            reference_audio=reference_audio,
            output_basename=output_basename,
            pronunciation=pronunciation,
            export_mp3_file=export_mp3_file,
            regenerate_indices={chunk_index},
            on_progress=on_progress,
        )
