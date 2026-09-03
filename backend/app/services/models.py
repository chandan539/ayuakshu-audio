"""Local model status, validation, and offline package installation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import AppPaths
from ..stt.whisper_engine import WhisperEngine, validate_whisper_dir
from ..tts.chatterbox_engine import ChatterboxEngine
from ..tts.manager import TTSManager
from .model_package import (
    build_manifest,
    install_chatterbox_from_package,
    install_pkuseg_from_package,
    validate_chatterbox_dir,
    validate_offline_package,
)
from .settings import SettingsService


class ModelService:
    def __init__(
        self,
        paths: AppPaths,
        tts: TTSManager,
        models_root: Path | None = None,
        settings: SettingsService | None = None,
        whisper: WhisperEngine | None = None,
    ):
        self.paths = paths
        self.tts = tts
        self.settings = settings
        self.models_root = Path(models_root).resolve() if models_root else paths.models.resolve()
        self.whisper = whisper or WhisperEngine(self.models_root / "whisper")

    @property
    def chatterbox_dir(self) -> Path:
        return self.models_root / "tts" / "chatterbox"

    @property
    def whisper_dir(self) -> Path:
        return self.models_root / "whisper"

    def list_models(self) -> list[dict[str, Any]]:
        cb = validate_chatterbox_dir(self.chatterbox_dir)
        engine = self.tts.get_engine("chatterbox")
        installed = cb.valid and engine.is_available()
        wh = validate_whisper_dir(self.whisper_dir)
        return [
            {
                "id": "chatterbox",
                "name": "Chatterbox Multilingual",
                "kind": "tts",
                "installed": installed,
                "ready_offline": installed,
                "path": cb.path,
                "size_bytes": cb.size_bytes,
                "status": "Installed" if installed else "Not Installed",
                "message": cb.message,
                "missing_required": cb.missing_required,
                "files": [f.__dict__ for f in cb.files],
            },
            {
                "id": "whisper",
                "name": "Whisper",
                "kind": "stt",
                "installed": wh.installed,
                "ready_offline": wh.installed,
                "path": wh.path,
                "size_bytes": wh.size_bytes,
                "status": "Installed" if wh.installed else "Not Installed",
                "message": wh.message,
                "missing_required": [] if wh.installed else ["small.pt"],
                "files": (
                    [{"name": wh.model_file, "present": True, "required": True}]
                    if wh.model_file
                    else []
                ),
            },
        ]

    def get(self, model_id: str) -> dict[str, Any] | None:
        for item in self.list_models():
            if item["id"] == model_id:
                return item
        return None

    def validate(self, model_id: str = "chatterbox") -> dict[str, Any]:
        if model_id == "whisper":
            report = validate_whisper_dir(self.whisper_dir)
            data = report.to_dict()
            data["model_id"] = "whisper"
            data["valid"] = report.installed
            data["ready_offline"] = report.installed
            data["engine_available"] = self.whisper.is_available()
            return data
        if model_id != "chatterbox":
            return {
                "model_id": model_id,
                "valid": False,
                "message": f"Unknown model id: {model_id}",
            }
        report = validate_chatterbox_dir(self.chatterbox_dir)
        data = report.to_dict()
        data["engine_available"] = self.tts.get_engine("chatterbox").is_available()
        return data

    def validate_package(self, package_dir: str | Path) -> dict[str, Any]:
        return validate_offline_package(Path(package_dir))

    def install_from_local(self, package_dir: str | Path) -> dict[str, Any]:
        """Install from OfflineVoice-Models package. Never contacts the network."""
        package_dir = Path(package_dir)
        dest = self.paths.models / "tts" / "chatterbox"
        report = install_chatterbox_from_package(package_dir, dest)
        if not report.valid:
            raise ValueError(report.message)

        pkuseg_dest = install_pkuseg_from_package(package_dir, self.paths.models)

        pkg_whisper = package_dir / "whisper"
        if not pkg_whisper.is_dir():
            pkg_whisper = package_dir / "stt" / "whisper"
        whisper_dest = None
        if pkg_whisper.is_dir() and any(pkg_whisper.glob("*.pt")):
            import shutil

            whisper_dest = self.paths.models / "whisper"
            whisper_dest.mkdir(parents=True, exist_ok=True)
            for pt in pkg_whisper.glob("*.pt"):
                shutil.copy2(pt, whisper_dest / pt.name)
            self.whisper = WhisperEngine(whisper_dest)

        self.models_root = self.paths.models.resolve()
        self.tts.models_root = self.models_root
        self.tts._engines["chatterbox"] = ChatterboxEngine(dest)
        try:
            self.tts.get_engine("chatterbox").unload()
        except Exception:
            pass

        if self.settings is not None:
            self.settings.update({"setup_completed": True, "setup_skipped": False})

        model = self.get("chatterbox")
        assert model is not None
        return {
            "ok": True,
            "message": (
                "Offline AI setup complete. "
                "You can now disconnect from the Internet. "
                "All speech generation happens locally."
            ),
            "model": model,
            "whisper": self.get("whisper"),
            "validation": report.to_dict(),
            "pkuseg_path": str(pkuseg_dest) if pkuseg_dest else None,
            "whisper_path": str(whisper_dest) if whisper_dest else None,
            "install_path": str(dest),
        }

    def setup_status(self) -> dict[str, Any]:
        model = self.get("chatterbox") or {}
        completed = False
        skipped = False
        if self.settings is not None:
            completed = bool(self.settings.get("setup_completed", False))
            skipped = bool(self.settings.get("setup_skipped", False))
        needs_setup = not bool(model.get("installed"))
        return {
            "needs_setup": needs_setup and not skipped,
            "setup_completed": completed or bool(model.get("installed")),
            "setup_skipped": skipped,
            "model_ready": bool(model.get("installed")),
            "model": model,
            "whisper": self.get("whisper"),
            "recommended_package_layout": {
                "OfflineVoice-Models": {
                    "manifest.json": "...",
                    "tts": {"chatterbox": ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "..."]},
                    "whisper": ["small.pt"],
                    "extras": {"pkuseg": ["spacy_ontonotes/", "..."]},
                }
            },
        }

    def mark_setup_skipped(self) -> dict[str, Any]:
        if self.settings is not None:
            self.settings.update({"setup_skipped": True})
        return self.setup_status()

    def mark_setup_completed(self) -> dict[str, Any]:
        if self.settings is not None:
            self.settings.update({"setup_completed": True, "setup_skipped": False})
        return self.setup_status()

    def export_package_preview(self) -> dict[str, Any]:
        include_pkuseg = (Path.home() / ".pkuseg").is_dir() or (
            self.paths.models / "extras" / "pkuseg"
        ).is_dir()
        return build_manifest(
            chatterbox_dir=self.chatterbox_dir,
            include_pkuseg=include_pkuseg,
        )
