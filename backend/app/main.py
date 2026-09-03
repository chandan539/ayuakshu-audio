"""AYUAKSHU Audio local FastAPI backend.

Binds to 127.0.0.1 only. No cloud calls during normal operation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import DEFAULT_HOST, AppPaths, default_app_support_dir
from .database import init_db
from .jobs.queue import JobQueue
from .services.models import ModelService
from .services.projects import ProjectService
from .services.settings import SettingsService
from .services.voices import VoiceService
from .state import AppState
from .stt.whisper_engine import WhisperEngine
from .tts.chatterbox_engine import ChatterboxEngine
from .tts.manager import TTSManager
from .tts.xtts_engine import XTTSEngine


def _pick_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def resolve_models_root(paths: AppPaths) -> Path:
    """
    Prefer OFFLINEVOICE_MODELS_DIR, then app-support models if installed,
    else the repo ./models directory for development.
    """
    env = os.environ.get("OFFLINEVOICE_MODELS_DIR")
    if env:
        return Path(env).expanduser().resolve()

    app_cb = paths.models / "tts" / "chatterbox"
    if (app_cb / "ve.pt").exists() and (
        any(app_cb.glob("t3_mtl*.safetensors")) or any(app_cb.glob("t3*.safetensors"))
    ):
        return paths.models.resolve()

    repo_models = Path(__file__).resolve().parents[2] / "models"
    if (repo_models / "tts" / "chatterbox" / "ve.pt").exists():
        return repo_models.resolve()

    return paths.models.resolve()


def create_app(
    *,
    data_dir: str | Path | None = None,
    host: str = DEFAULT_HOST,
    port: int = 0,
) -> FastAPI:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Backend must bind to 127.0.0.1 for local-only security")

    paths = AppPaths(Path(data_dir) if data_dir else default_app_support_dir()).ensure()
    # librosa/numba needs a writable cache dir (venv site-packages is not always usable).
    numba_cache = paths.cache / "numba"
    numba_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(numba_cache))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    # Allow MPS to use more unified memory before hard-failing (still not unlimited).
    # Combined with short chunk sizes this avoids the common 20 GiB ceiling crash.
    os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
    os.environ.setdefault("TQDM_DISABLE", "1")

    models_root = resolve_models_root(paths)

    conn = init_db(paths.database_file)
    settings = SettingsService(conn)
    if settings.get("offline_mode", True):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    tts = TTSManager(models_root)
    # Ensure engines point at resolved model dirs even if AppPaths.models differs.
    tts._engines["chatterbox"] = ChatterboxEngine(models_root / "tts" / "chatterbox")
    tts._engines["xtts"] = XTTSEngine(models_root / "tts" / "xtts")
    whisper = WhisperEngine(models_root / "whisper")

    voices = VoiceService(conn, paths)
    projects = ProjectService(conn, paths)
    models = ModelService(
        paths, tts, models_root=models_root, settings=settings, whisper=whisper
    )
    if models.get("chatterbox") and models.get("chatterbox").get("installed"):
        settings.update({"setup_completed": True})

    jobs = JobQueue(conn, paths, tts, voices, projects, settings)
    resolved_port = port if port > 0 else _pick_free_port(host)
    state = AppState(
        paths=paths,
        conn=conn,
        settings=settings,
        voices=voices,
        projects=projects,
        models=models,
        tts=tts,
        jobs=jobs,
        whisper=whisper,
        host=host,
        port=resolved_port,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.state = state
        state.jobs.start()
        endpoint = {
            "host": state.host,
            "port": state.port,
            "base_url": f"http://{state.host}:{state.port}",
        }
        (paths.cache / "backend_port.txt").write_text(str(state.port), encoding="utf-8")
        (paths.cache / "backend_endpoint.json").write_text(
            json.dumps(endpoint) + "\n", encoding="utf-8"
        )

        def _warmup_tts() -> None:
            try:
                logger.info("Background TTS warm-up starting…")
                state.tts.warm_default()
                logger.info("Background TTS warm-up finished")
            except Exception:
                logger.exception("Background TTS warm-up failed")

        # Load + tiny inference in the background so Generate is not stuck at 5%.
        # Tests / CI can disable with OFFLINEVOICE_SKIP_WARMUP=1.
        if os.environ.get("OFFLINEVOICE_SKIP_WARMUP", "").strip() not in {"1", "true", "yes"}:
            threading.Thread(target=_warmup_tts, name="tts-warmup", daemon=True).start()

        yield
        state.jobs.stop()
        state.conn.close()

    app = FastAPI(title="AYUAKSHU Audio Local API", version="0.6.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.state.state = state
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AYUAKSHU Audio local backend")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=0, help="0 = ephemeral port")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing to bind non-local host. Use 127.0.0.1")

    app = create_app(data_dir=args.data_dir, host=args.host, port=args.port)
    state: AppState = app.state.state
    print(f"AYUAKSHU Audio backend listening on http://{state.host}:{state.port}")
    print(f"App data: {state.paths.root}")
    print(f"Models: {state.tts.models_root}")
    print("Offline Mode: ON" if state.settings.get("offline_mode", True) else "Offline Mode: OFF")
    uvicorn.run(app, host=state.host, port=state.port, log_level="info")


if __name__ == "__main__":
    main()
