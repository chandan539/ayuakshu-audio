"""Audio processing utilities for OfflineVoice."""

from .chunker import ChunkPlan, TextChunk, chunk_text, parse_pause_markers
from .export import export_mp3, export_wav
from .merger import crossfade_join, join_segments
from .pipeline import AudioPipeline, PipelineResult
from .preprocess import preprocess_reference, PreprocessResult
from .validate import validate_reference_audio, ValidationReport

__all__ = [
    "AudioPipeline",
    "PipelineResult",
    "ChunkPlan",
    "TextChunk",
    "chunk_text",
    "parse_pause_markers",
    "crossfade_join",
    "join_segments",
    "export_wav",
    "export_mp3",
    "preprocess_reference",
    "PreprocessResult",
    "validate_reference_audio",
    "ValidationReport",
]
