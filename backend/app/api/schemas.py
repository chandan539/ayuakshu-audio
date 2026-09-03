"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    offline_mode: bool
    bind: str
    model_ready: bool
    model_loaded: bool = False
    model_warming: bool = False
    app_data: str


class VoiceCreateRequest(BaseModel):
    name: str = "My Voice"
    language: str = "hi"
    engine: str = "chatterbox"
    # Absolute path on the local machine (Tauri will pass a local file path).
    source_audio: str


class ProjectCreateRequest(BaseModel):
    title: str = "Untitled Project"
    text: str = ""
    voice_id: Optional[str] = None
    language: str = "hi"
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class GenerateRequest(BaseModel):
    text: str
    language: str = "hi"
    voice_id: str
    project_id: Optional[str] = None
    engine: Optional[str] = None
    max_chars: Optional[int] = None
    pronunciation: dict[str, str] = Field(default_factory=dict)
    export_mp3: bool = True
    clone_mode: Optional[str] = "fast"


class SettingsUpdateRequest(BaseModel):
    offline_mode: Optional[bool] = None
    default_language: Optional[str] = None
    default_engine: Optional[str] = None
    max_chunk_chars: Optional[int] = None
    mp3_bitrate: Optional[int] = None
    crossfade_ms: Optional[float] = None
    unload_model_after_inactivity: Optional[bool] = None
    clone_mode: Optional[str] = None


class InstallModelRequest(BaseModel):
    model_id: str = "chatterbox"
    # Local offline package path (no network).
    from_local: Optional[str] = None


class TranscribeRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
