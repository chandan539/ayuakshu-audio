"""Sentence-aware text chunking + pause marker parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

PAUSE_RE = re.compile(r"\[pause\s*:\s*([0-9]*\.?[0-9]+)\s*s?\]", re.IGNORECASE)

# Sentence enders for English + Devanagari danda.
SENTENCE_END_RE = re.compile(r"(?<=[.!?…।॥])\s+")

CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:—–])\s+")


@dataclass
class TextChunk:
    index: int
    kind: Literal["speech", "pause"]
    text: str = ""
    pause_seconds: float = 0.0
    # Character span in the normalized source (approx).
    start_char: int = 0
    end_char: int = 0

    @property
    def is_speech(self) -> bool:
        return self.kind == "speech"


@dataclass
class ChunkPlan:
    chunks: list[TextChunk] = field(default_factory=list)
    max_chars: int = 1000
    language: str = "en"

    @property
    def speech_chunks(self) -> list[TextChunk]:
        return [c for c in self.chunks if c.is_speech]

    @property
    def total_speech_chunks(self) -> int:
        return len(self.speech_chunks)


def apply_pronunciation_dictionary(text: str, mapping: dict[str, str] | None) -> str:
    """Simple whole-token / phrase replacement (future-ready)."""
    if not mapping:
        return text
    # Longer keys first to avoid partial overlaps.
    out = text
    for original, replacement in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        if not original:
            continue
        out = out.replace(original, replacement)
    return out


def normalize_text(text: str) -> str:
    # Preserve Unicode (Devanagari). Normalize newlines; collapse excessive spaces.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip common script markup that is not meant to be spoken.
    text = re.sub(r"\*\*\[/?WHISPER\]\*\*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[/?WHISPER\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[(?:MUSIC|SFX|SOUND|NOISE)[^\]]*\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pause_markers(text: str) -> list[tuple[Literal["speech", "pause"], str | float]]:
    """
    Split text into alternating speech strings and pause durations.

    Example:
      "Hello...[pause:1s]Today we talk."
      → [("speech","Hello..."), ("pause",1.0), ("speech","Today we talk.")]
    """
    parts: list[tuple[Literal["speech", "pause"], str | float]] = []
    last = 0
    for match in PAUSE_RE.finditer(text):
        before = text[last : match.start()]
        if before.strip():
            parts.append(("speech", before))
        parts.append(("pause", float(match.group(1))))
        last = match.end()
    tail = text[last:]
    if tail.strip():
        parts.append(("speech", tail))
    return parts


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    parts = SENTENCE_END_RE.split(paragraph.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_clauses(sentence: str) -> list[str]:
    parts = CLAUSE_SPLIT_RE.split(sentence.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_words(text: str) -> list[str]:
    # Unicode-aware-ish: split on whitespace, keep punctuation attached.
    return [w for w in text.split(" ") if w]


def _pack_units(units: list[str], max_chars: int, joiner: str = " ") -> list[str]:
    """Greedily pack units without exceeding max_chars (unless a single unit is longer)."""
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    packed: list[str] = []
    buf = ""
    for unit in units:
        if not unit:
            continue
        if len(unit) > max_chars:
            # Flush buffer, then hard-split oversized unit at word/char boundaries.
            if buf:
                packed.append(buf)
                buf = ""
            if " " not in unit and "\n" not in unit:
                packed.extend(unit[i : i + max_chars] for i in range(0, len(unit), max_chars))
            else:
                packed.extend(_hard_split(unit, max_chars))
            continue
        candidate = unit if not buf else f"{buf}{joiner}{unit}"
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            packed.append(buf)
            buf = unit
    if buf:
        packed.append(buf)
    return packed


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last resort: split on words, then characters — never mid-codepoint."""
    if not text:
        return []
    words = _split_words(text)
    # Single unbroken token (common with long Devanagari lines) → char slices.
    if len(words) <= 1:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    packed = _pack_units(words, max_chars, joiner=" ")
    out: list[str] = []
    for part in packed:
        if len(part) <= max_chars:
            out.append(part)
        else:
            out.extend(part[i : i + max_chars] for i in range(0, len(part), max_chars))
    return out


def chunk_speech_text(text: str, max_chars: int) -> list[str]:
    """
    Hierarchical chunking:
      paragraph → sentence → clause → word → character
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = _split_paragraphs(text)
    if len(paragraphs) > 1:
        return _pack_units(
            [c for p in paragraphs for c in chunk_speech_text(p, max_chars)],
            max_chars,
            joiner="\n\n",
        )

    sentences = _split_sentences(text)
    if len(sentences) > 1:
        return _pack_units(sentences, max_chars, joiner=" ")

    clauses = _split_clauses(text)
    if len(clauses) > 1:
        return _pack_units(clauses, max_chars, joiner=" ")

    words = _split_words(text)
    if len(words) > 1:
        return _pack_units(words, max_chars, joiner=" ")

    return _hard_split(text, max_chars)


def chunk_text(
    text: str,
    *,
    max_chars: int = 1000,
    language: str = "en",
    pronunciation: dict[str, str] | None = None,
) -> ChunkPlan:
    """
    Build a full generation plan including pause segments.

    Pause markers are removed from TTS input and become silence during assembly.
    """
    normalized = normalize_text(text)
    normalized = apply_pronunciation_dictionary(normalized, pronunciation)
    plan = ChunkPlan(max_chars=max_chars, language=language)
    if not normalized:
        return plan

    cursor = 0
    idx = 0
    for kind, payload in parse_pause_markers(normalized):
        if kind == "pause":
            plan.chunks.append(
                TextChunk(
                    index=idx,
                    kind="pause",
                    pause_seconds=float(payload),
                    start_char=cursor,
                    end_char=cursor,
                )
            )
            idx += 1
            continue

        speech = str(payload).strip()
        if not speech:
            continue
        pieces = chunk_speech_text(speech, max_chars=max_chars)
        for piece in pieces:
            start = normalized.find(piece, cursor)
            if start < 0:
                start = cursor
            end = start + len(piece)
            plan.chunks.append(
                TextChunk(
                    index=idx,
                    kind="speech",
                    text=piece,
                    start_char=start,
                    end_char=end,
                )
            )
            idx += 1
            cursor = end
    return plan
