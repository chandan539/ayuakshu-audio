"""Async generation job queue with crash recovery."""

from __future__ import annotations

import json
import sqlite3
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from ..audio.chunker import chunk_text
from ..audio.export import export_mp3, export_wav
from ..audio.merger import join_segments
from ..config import AppPaths, recommended_max_chunk_chars
from ..security import resolve_under
from ..tts.errors import ModelNotInstalledError
from ..tts.manager import TTSManager
from ..services.ids import new_id, utc_now
from ..services.projects import ProjectService
from ..services.settings import SettingsService
from ..services.voices import VoiceService

JobStatus = str  # queued | running | completed | failed | cancelled | interrupted


class JobQueue:
    def __init__(
        self,
        conn: sqlite3.Connection,
        paths: AppPaths,
        tts: TTSManager,
        voices: VoiceService,
        projects: ProjectService,
        settings: SettingsService,
    ):
        self.conn = conn
        self.paths = paths
        self.tts = tts
        self.voices = voices
        self.projects = projects
        self.settings = settings
        self._lock = threading.RLock()
        self._cancel_flags: dict[str, threading.Event] = {}
        self._worker: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._recover_interrupted()

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._loop, name="tts-job-worker", daemon=True)
        self._worker.start()
        self._wake.set()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout)

    def _recover_interrupted(self) -> None:
        """Mark in-flight jobs as interrupted so UI can offer Resume."""
        now = utc_now()
        with self._lock:
            self.conn.execute(
                """
                UPDATE generation_jobs
                SET status = 'interrupted', stage = 'Interrupted — resume available', updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
            self.conn.commit()

    def create_job(
        self,
        *,
        text: str,
        language: str,
        voice_id: str,
        project_id: str | None = None,
        engine: str | None = None,
        max_chars: int | None = None,
        pronunciation: dict[str, str] | None = None,
        export_mp3_file: bool = True,
        clone_mode: str = "fast",
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("Text is required")
        voice = self.voices.get(voice_id)
        if not voice:
            raise KeyError(f"Voice not found: {voice_id}")

        engine_name = engine or self.settings.get("default_engine", "chatterbox")
        eng = self.tts.get_engine(engine_name)
        if not eng.is_available():
            raise ModelNotInstalledError(engine_name)

        # Cap chunk size for Apple Silicon unified memory — long chunks OOM and feel hung.
        safe_cap = recommended_max_chunk_chars()
        requested = max_chars or int(self.settings.get("max_chunk_chars", eng.default_chunk_chars))
        max_chars = max(120, min(int(requested), safe_cap))
        # Persist safer default if the old setting was too aggressive (e.g. 1000).
        stored = int(self.settings.get("max_chunk_chars", eng.default_chunk_chars))
        if stored > safe_cap:
            self.settings.update({"max_chunk_chars": safe_cap})

        plan = chunk_text(
            text,
            max_chars=max_chars,
            language=language,
            pronunciation=pronunciation,
        )

        job_id = new_id("job")
        out_dir = resolve_under(self.paths.audio_generated, job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "chunks").mkdir(parents=True, exist_ok=True)

        now = utc_now()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO generation_jobs(
                    id, project_id, voice_id, language, engine, text, status, progress,
                    current_chunk, total_chunks, stage, error, output_directory,
                    output_wav, output_mp3, max_chars, pronunciation_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, 0, ?, 'Queued', NULL, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    voice_id,
                    language,
                    engine_name,
                    text,
                    plan.total_speech_chunks,
                    str(out_dir),
                    max_chars,
                    json.dumps(
                        {
                            "map": pronunciation or {},
                            "export_mp3": export_mp3_file,
                            "clone_mode": "quality" if clone_mode == "quality" else "fast",
                        },
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                ),
            )
            for chunk in plan.chunks:
                self.conn.execute(
                    """
                    INSERT INTO generation_chunks(
                        job_id, chunk_index, kind, text, pause_seconds, audio_path, status, error
                    ) VALUES (?, ?, ?, ?, ?, NULL, 'pending', NULL)
                    """,
                    (
                        job_id,
                        chunk.index,
                        chunk.kind,
                        chunk.text,
                        chunk.pause_seconds,
                    ),
                )
            self.conn.commit()
            self._cancel_flags[job_id] = threading.Event()
            self._wake.set()
            return self._get_job_unlocked(job_id)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._get_job_unlocked(job_id)

    def list_jobs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id FROM generation_jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [self._get_job_unlocked(r["id"]) for r in rows if r]  # type: ignore[misc]

    def active_job(self) -> dict[str, Any] | None:
        """Most relevant job for UI restore (in-flight first, then last finished)."""
        with self._lock:
            row = self.conn.execute(
                """
                SELECT id FROM generation_jobs
                WHERE status IN ('queued', 'running', 'interrupted', 'failed')
                ORDER BY
                  CASE status
                    WHEN 'running' THEN 0
                    WHEN 'queued' THEN 1
                    WHEN 'interrupted' THEN 2
                    ELSE 3
                  END,
                  updated_at DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                row = self.conn.execute(
                    """
                    SELECT id FROM generation_jobs
                    WHERE status = 'completed'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ).fetchone()
            return self._get_job_unlocked(row["id"]) if row else None

    def _get_job_unlocked(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM generation_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        chunks = self.conn.execute(
            """
            SELECT chunk_index, kind, text, pause_seconds, audio_path, status, error
            FROM generation_chunks WHERE job_id = ? ORDER BY chunk_index
            """,
            (job_id,),
        ).fetchall()
        data["chunks"] = [dict(c) for c in chunks]
        if data.get("pronunciation_json"):
            try:
                data["pronunciation"] = json.loads(data["pronunciation_json"])
            except json.JSONDecodeError:
                data["pronunciation"] = {}
        return data

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if not job:
            return None
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        flag = self._cancel_flags.setdefault(job_id, threading.Event())
        flag.set()
        self._update_job(job_id, status="cancelled", stage="Cancelled", progress=job["progress"])
        return self.get_job(job_id)

    def resume(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if not job:
            return None
        if job["status"] not in {"interrupted", "failed", "cancelled"}:
            raise ValueError(f"Job cannot be resumed from status={job['status']}")
        # Reset incomplete speech chunks to pending; keep completed ones.
        with self._lock:
            self.conn.execute(
                """
                UPDATE generation_chunks
                SET status = 'pending', error = NULL
                WHERE job_id = ? AND kind = 'speech' AND status != 'done'
                """,
                (job_id,),
            )
            self.conn.commit()
        self._update_job(
            job_id,
            status="queued",
            stage="Queued for resume",
            error=None,
            progress=self._completed_progress(job_id),
        )
        self._cancel_flags[job_id] = threading.Event()
        self._wake.set()
        return self.get_job(job_id)

    def _completed_progress(self, job_id: str) -> float:
        job = self.get_job(job_id)
        if not job or not job["total_chunks"]:
            return 0.0
        done = sum(1 for c in job["chunks"] if c["kind"] == "speech" and c["status"] == "done")
        return round(100.0 * done / max(job["total_chunks"], 1), 1)

    def _update_job(self, job_id: str, **fields: Any) -> None:
        fields["updated_at"] = utc_now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self.conn.execute(
                f"UPDATE generation_jobs SET {cols} WHERE id = ?",
                (*fields.values(), job_id),
            )
            self.conn.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            job_id = self._next_queued_job_id()
            if not job_id:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                continue
            try:
                self._run_job(job_id)
            except Exception:
                self._update_job(
                    job_id,
                    status="failed",
                    stage="Failed",
                    error=traceback.format_exc()[-2000:],
                )

    def _next_queued_job_id(self) -> str | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT id FROM generation_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            return row["id"] if row else None

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        cancel = self._cancel_flags.setdefault(job_id, threading.Event())
        if cancel.is_set():
            self._update_job(job_id, status="cancelled", stage="Cancelled")
            return

        self._update_job(job_id, status="running", stage="Loading model...", progress=5)
        engine = self.tts.get_engine(job["engine"])
        if not engine.is_available():
            raise ModelNotInstalledError(job["engine"])

        already_loaded = bool(getattr(engine, "is_loaded", False))
        stop_hb = threading.Event()

        def _load_heartbeat() -> None:
            pct = 5.0
            tips = [
                "Loading AI model into memory…",
                "First load can take 1–3 minutes on this Mac…",
                "Still loading weights (this only happens once)…",
                "Almost ready — preparing neural nets…",
            ]
            tip_i = 0
            while not stop_hb.wait(2.5):
                pct = min(pct + 2.0, 18.0)
                tip_i = min(tip_i + 1, len(tips) - 1)
                self._update_job(
                    job_id,
                    status="running",
                    stage=tips[tip_i],
                    progress=round(pct, 1),
                    current_chunk=0,
                )

        if already_loaded:
            self._update_job(
                job_id,
                status="running",
                stage="Model ready — preparing voice…",
                progress=12,
                current_chunk=0,
            )
        else:
            self._update_job(
                job_id,
                status="running",
                stage="Loading AI model into memory (first time is slow)…",
                progress=5,
                current_chunk=0,
            )
            hb = threading.Thread(target=_load_heartbeat, name=f"load-hb-{job_id}", daemon=True)
            hb.start()
            try:
                engine.load()
            finally:
                stop_hb.set()

        try:
            ref = self.voices.reference_path(job["voice_id"])
        except Exception as exc:
            self._update_job(job_id, status="failed", stage="Failed", error=str(exc))
            return

        self._update_job(
            job_id,
            status="running",
            stage="Preparing voice clone…",
            progress=20,
            current_chunk=0,
        )
        prepare = getattr(engine, "prepare_voice", None)
        if callable(prepare):
            prepare(str(ref))
        else:
            # Ensure weights are resident even if prepare_voice is unavailable.
            engine.load()

        out_dir = Path(job["output_directory"])
        chunks_dir = out_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        pronunciation_blob = {}
        if job.get("pronunciation_json"):
            try:
                pronunciation_blob = json.loads(job["pronunciation_json"])
            except json.JSONDecodeError:
                pronunciation_blob = {}
        export_mp3_file = bool(pronunciation_blob.get("export_mp3", True))
        clone_mode = pronunciation_blob.get("clone_mode") or self.settings.get("clone_mode", "fast")
        if hasattr(engine, "clone_mode"):
            engine.clone_mode = "quality" if clone_mode == "quality" else "fast"
        crossfade_ms = float(self.settings.get("crossfade_ms", 40.0))
        mp3_bitrate = int(self.settings.get("mp3_bitrate", 192))

        speech_total = max(int(job["total_chunks"]), 1)
        speech_done = sum(
            1 for c in job["chunks"] if c["kind"] == "speech" and c["status"] == "done"
        )

        for chunk in job["chunks"]:
            if cancel.is_set():
                self._update_job(job_id, status="cancelled", stage="Cancelled")
                return

            if chunk["kind"] == "pause":
                with self._lock:
                    self.conn.execute(
                        """
                        UPDATE generation_chunks SET status = 'done'
                        WHERE job_id = ? AND chunk_index = ?
                        """,
                        (job_id, chunk["chunk_index"]),
                    )
                    self.conn.commit()
                continue

            if chunk["status"] == "done" and chunk.get("audio_path") and Path(chunk["audio_path"]).is_file():
                speech_done += 0  # already counted
                continue

            idx = int(chunk["chunk_index"])
            chunk_path = chunks_dir / f"chunk_{idx:04d}.wav"
            current = speech_done + 1
            pct = 10 + 70 * (speech_done / speech_total)
            self._update_job(
                job_id,
                status="running",
                stage=f"Generating chunk {current}/{speech_total}",
                current_chunk=current,
                progress=round(pct, 1),
            )
            try:
                engine.generate(
                    text=chunk["text"] or "",
                    language=job["language"],
                    reference_audio=str(ref),
                    output_path=str(chunk_path),
                )
                with self._lock:
                    self.conn.execute(
                        """
                        UPDATE generation_chunks
                        SET status = 'done', audio_path = ?, error = NULL
                        WHERE job_id = ? AND chunk_index = ?
                        """,
                        (str(chunk_path), job_id, idx),
                    )
                    self.conn.commit()
                speech_done += 1
            except Exception as exc:
                err = str(exc)
                if "out of memory" in err.lower() or "MPS backend out of memory" in err:
                    err = (
                        "GPU memory filled on this piece. Completed chunks were kept. "
                        "Click Resume to continue the same long file, close other apps first, "
                        "and keep Max chunk at 220."
                    )
                with self._lock:
                    self.conn.execute(
                        """
                        UPDATE generation_chunks
                        SET status = 'error', error = ?
                        WHERE job_id = ? AND chunk_index = ?
                        """,
                        (err, job_id, idx),
                    )
                    self.conn.commit()
                self._update_job(
                    job_id,
                    status="interrupted",
                    stage="Paused — Resume available",
                    error=err,
                    current_chunk=current,
                )
                return

        if cancel.is_set():
            self._update_job(job_id, status="cancelled", stage="Cancelled")
            return

        self._update_job(job_id, stage="Combining audio...", progress=88)
        # Reload chunks for assembly
        job = self.get_job(job_id)
        assert job is not None
        assembly: list[tuple[str, object]] = []
        for chunk in job["chunks"]:
            if chunk["kind"] == "pause":
                assembly.append(("pause", float(chunk["pause_seconds"] or 0)))
            else:
                if not chunk.get("audio_path"):
                    self._update_job(
                        job_id,
                        status="failed",
                        stage="Failed",
                        error=f"Missing audio for chunk {chunk['chunk_index']}",
                    )
                    return
                assembly.append(("speech", chunk["audio_path"]))

        audio, sr = join_segments(assembly, crossfade_ms=crossfade_ms)
        wav_out = out_dir / "final.wav"
        export_wav(audio, sr, wav_out)
        mp3_out = None
        if export_mp3_file:
            self._update_job(job_id, stage="Exporting MP3...", progress=95)
            mp3_out = export_mp3(wav_out, out_dir / "final.mp3", bitrate_kbps=mp3_bitrate)

        self._update_job(
            job_id,
            status="completed",
            stage="Complete",
            progress=100,
            current_chunk=speech_total,
            output_wav=str(wav_out),
            output_mp3=str(mp3_out) if mp3_out else None,
            error=None,
        )

        if job.get("project_id"):
            self.projects.update(
                job["project_id"],
                output_wav=str(wav_out),
                output_mp3=str(mp3_out) if mp3_out else None,
                text=job["text"],
                language=job["language"],
                voice_id=job["voice_id"],
            )
