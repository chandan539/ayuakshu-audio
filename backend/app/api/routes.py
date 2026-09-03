"""FastAPI routers."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..config import detect_system_info
from ..tts.errors import ModelNotInstalledError
from .schemas import (
    GenerateRequest,
    HealthResponse,
    InstallModelRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    SettingsUpdateRequest,
    TranscribeRequest,
    VoiceCreateRequest,
)


def get_state(request: Request):
    return request.app.state.state


def sanitize_upload_id() -> str:
    return uuid.uuid4().hex[:12]


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    state = get_state(request)
    engine = state.tts.get_engine(state.settings.get("default_engine", "chatterbox"))
    return HealthResponse(
        status="ok",
        offline_mode=bool(state.settings.get("offline_mode", True)),
        bind=f"{state.host}:{state.port}",
        model_ready=engine.is_available(),
        model_loaded=bool(getattr(engine, "is_loaded", False)),
        model_warming=bool(
            getattr(engine, "is_loading", False)
            or (getattr(engine, "is_loaded", False) and not getattr(engine, "is_warmed", True))
        ),
        app_data=str(state.paths.root),
    )


@router.get("/system")
def system_info():
    return detect_system_info()


@router.get("/settings")
def get_settings(request: Request):
    return get_state(request).settings.get_all()


@router.put("/settings")
def update_settings(body: SettingsUpdateRequest, request: Request):
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    return get_state(request).settings.update(values)


@router.post("/storage/clear-temporary")
def clear_temporary(request: Request):
    removed = get_state(request).paths.clear_temporary()
    return {"removed": removed}


@router.get("/models")
def list_models(request: Request):
    return {"models": get_state(request).models.list_models()}


@router.get("/models/package/manifest")
def package_manifest(request: Request):
    return get_state(request).models.export_package_preview()


@router.get("/models/{model_id}")
def get_model(model_id: str, request: Request):
    item = get_state(request).models.get(model_id)
    if not item:
        raise HTTPException(404, "Model not found")
    return item


@router.get("/models/{model_id}/validate")
def validate_model(model_id: str, request: Request):
    return get_state(request).models.validate(model_id)


@router.post("/models/validate-package")
def validate_package(body: InstallModelRequest, request: Request):
    if not body.from_local:
        raise HTTPException(400, "from_local path is required")
    try:
        return get_state(request).models.validate_package(body.from_local)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/models/install")
def install_model(body: InstallModelRequest, request: Request):
    """
    Install from a local Offline Model Package.
    Network install is never triggered from the API.
    """
    state = get_state(request)
    offline = bool(state.settings.get("offline_mode", True))
    if not body.from_local:
        if offline:
            raise HTTPException(
                400,
                "Internet is unavailable / Offline Mode is ON. "
                "You can install the model from a local model package.",
            )
        raise HTTPException(
            400,
            "Network model download is not exposed via API. "
            "Use backend/scripts/install_chatterbox_model.py on a connected machine, "
            "or pass from_local=/path/to/OfflineVoice-Models.",
        )
    if body.model_id != "chatterbox":
        raise HTTPException(400, "Only chatterbox install is supported in MVP")
    try:
        return state.models.install_from_local(body.from_local)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/setup/status")
def setup_status(request: Request):
    return get_state(request).models.setup_status()


@router.post("/setup/skip")
def setup_skip(request: Request):
    return get_state(request).models.mark_setup_skipped()


@router.post("/setup/complete")
def setup_complete(request: Request):
    return get_state(request).models.mark_setup_completed()


@router.get("/voices")
def list_voices(request: Request):
    return {"voices": get_state(request).voices.list()}


@router.post("/voices")
def create_voice(body: VoiceCreateRequest, request: Request):
    try:
        voice = get_state(request).voices.create(
            name=body.name,
            source_audio=body.source_audio,
            language=body.language,
            engine=body.engine,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return voice


@router.post("/voices/upload")
async def upload_voice(
    request: Request,
    name: str = Form("My Voice"),
    language: str = Form("hi"),
    engine: str = Form("chatterbox"),
    file: UploadFile = File(...),
):
    """Create a voice from an uploaded recording (Record Voice)."""
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "recording.wav").suffix or ".wav"
    if suffix.lower() not in {".wav", ".mp3", ".m4a", ".flac", ".aiff", ".aif", ".webm", ".ogg"}:
        suffix = ".wav"

    state = get_state(request)
    tmp_dir = state.paths.cache / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"upload_{sanitize_upload_id()}{suffix}"
    try:
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty recording")
        tmp_path.write_bytes(data)
        voice = state.voices.create(
            name=name,
            source_audio=tmp_path,
            language=language,
            engine=engine,
        )
        return voice
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


@router.get("/voices/{voice_id}")
def get_voice(voice_id: str, request: Request):
    voice = get_state(request).voices.get(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found")
    return voice


@router.get("/voices/{voice_id}/audio")
def voice_audio(voice_id: str, request: Request):
    """Stream the stored reference WAV for playback in the Voices tab."""
    from fastapi.responses import FileResponse

    try:
        path = get_state(request).voices.reference_path(voice_id)
    except KeyError as exc:
        raise HTTPException(404, "Voice not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "Reference audio missing on disk") from exc
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{voice_id}.wav",
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/voices/{voice_id}")
def delete_voice(voice_id: str, request: Request):
    ok = get_state(request).voices.delete(voice_id)
    if not ok:
        raise HTTPException(404, "Voice not found")
    return {"deleted": True, "id": voice_id}


@router.get("/projects")
def list_projects(request: Request):
    return {"projects": get_state(request).projects.list()}


@router.post("/projects")
def create_project(body: ProjectCreateRequest, request: Request):
    return get_state(request).projects.create(
        title=body.title,
        text=body.text,
        voice_id=body.voice_id,
        language=body.language,
        settings=body.settings,
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request):
    project = get_state(request).projects.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdateRequest, request: Request):
    project = get_state(request).projects.update(
        project_id, **{k: v for k, v in body.model_dump().items() if v is not None}
    )
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, request: Request):
    ok = get_state(request).projects.delete(project_id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"deleted": True, "id": project_id}


@router.post("/generate")
def generate(body: GenerateRequest, request: Request):
    state = get_state(request)
    try:
        job = state.jobs.create_job(
            text=body.text,
            language=body.language,
            voice_id=body.voice_id,
            project_id=body.project_id,
            engine=body.engine,
            max_chars=body.max_chars,
            pronunciation=body.pronunciation or None,
            export_mp3_file=body.export_mp3,
            clone_mode=body.clone_mode or "fast",
        )
    except ModelNotInstalledError as exc:
        raise HTTPException(
            409,
            {
                "code": "MODEL_NOT_INSTALLED",
                "message": str(exc),
                "hint": "Open Settings → AI Models to install it.",
            },
        ) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"job_id": job["id"], "job": job}


@router.get("/jobs")
def list_jobs(request: Request, limit: int = 20):
    jobs = get_state(request).jobs.list_jobs(limit=limit)
    return {
        "jobs": [
            {
                "id": j["id"],
                "status": j["status"],
                "progress": j["progress"],
                "current_chunk": j["current_chunk"],
                "total_chunks": j["total_chunks"],
                "stage": j["stage"],
                "error": j["error"],
                "output_wav": j["output_wav"],
                "output_mp3": j["output_mp3"],
                "project_id": j.get("project_id"),
                "voice_id": j.get("voice_id"),
                "language": j.get("language"),
                "text": j.get("text"),
            }
            for j in jobs
            if j
        ]
    }


@router.get("/jobs/active")
def active_job(request: Request):
    job = get_state(request).jobs.active_job()
    if not job:
        return {"job": None}
    return {
        "job": {
            "id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "current_chunk": job["current_chunk"],
            "total_chunks": job["total_chunks"],
            "stage": job["stage"],
            "error": job["error"],
            "output_wav": job["output_wav"],
            "output_mp3": job["output_mp3"],
            "project_id": job.get("project_id"),
            "voice_id": job.get("voice_id"),
            "language": job.get("language"),
            "text": job.get("text"),
        }
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = get_state(request).jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "current_chunk": job["current_chunk"],
        "total_chunks": job["total_chunks"],
        "stage": job["stage"],
        "error": job["error"],
        "output_wav": job["output_wav"],
        "output_mp3": job["output_mp3"],
        "chunks": job.get("chunks", []),
        "project_id": job.get("project_id"),
        "voice_id": job.get("voice_id"),
        "language": job.get("language"),
        "text": job.get("text"),
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    job = get_state(request).jobs.cancel(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, request: Request):
    try:
        job = get_state(request).jobs.resume(job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job["id"], "job": job}


@router.get("/jobs/{job_id}/audio.wav")
def job_audio_wav(job_id: str, request: Request):
    from fastapi.responses import FileResponse

    job = get_state(request).jobs.get_job(job_id)
    if not job or not job.get("output_wav"):
        raise HTTPException(404, "WAV not found")
    path = Path(job["output_wav"])
    if not path.is_file():
        raise HTTPException(404, "WAV missing on disk")
    return FileResponse(path, media_type="audio/wav", filename="output.wav")


@router.get("/jobs/{job_id}/audio.mp3")
def job_audio_mp3(job_id: str, request: Request):
    from fastapi.responses import FileResponse

    job = get_state(request).jobs.get_job(job_id)
    if not job or not job.get("output_mp3"):
        raise HTTPException(404, "MP3 not found")
    path = Path(job["output_mp3"])
    if not path.is_file():
        raise HTTPException(404, "MP3 missing on disk")
    return FileResponse(path, media_type="audio/mpeg", filename="output.mp3")


@router.post("/transcribe")
def transcribe(body: TranscribeRequest, request: Request):
    state = get_state(request)
    whisper = state.whisper
    if whisper is None or not whisper.is_available():
        raise HTTPException(
            503,
            {
                "code": "MODEL_NOT_INSTALLED",
                "message": "Whisper is not installed. Run backend/scripts/install_whisper_model.py",
            },
        )
    path = Path(body.audio_path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(404, f"Audio not found: {path}")
    try:
        return whisper.transcribe(path, language=body.language)
    except ModelNotInstalledError as exc:
        raise HTTPException(503, {"code": "MODEL_NOT_INSTALLED", "message": str(exc)}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@router.post("/transcribe/upload")
async def transcribe_upload(
    request: Request,
    language: str | None = Form(None),
    file: UploadFile = File(...),
):
    """Transcribe an uploaded audio clip with local Whisper."""
    state = get_state(request)
    whisper = state.whisper
    if whisper is None or not whisper.is_available():
        raise HTTPException(
            503,
            {
                "code": "MODEL_NOT_INSTALLED",
                "message": "Whisper is not installed. Run backend/scripts/install_whisper_model.py",
            },
        )
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    tmp_dir = state.paths.cache / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"stt_{sanitize_upload_id()}{suffix}"
    try:
        tmp_path.write_bytes(await file.read())
        return whisper.transcribe(tmp_path, language=language or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
