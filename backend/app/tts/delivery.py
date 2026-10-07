"""Map Stability / Similarity sliders and voice-design prompts onto local Chatterbox controls.

This does not call a cloud voice API. A designed voice still speaks with a cloned
recording; the prompt only changes delivery (how steady, how close to that recording).
"""

from __future__ import annotations

import re


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def delivery_settings(stability: float = 0.6, similarity: float = 0.75) -> dict[str, float]:
    """stability: 0 creative → 1 robust. similarity: 0 loose → 1 close to the clone."""
    s = clamp01(stability)
    sim = clamp01(similarity)
    temperature = 0.85 - 0.4 * s
    exaggeration = 0.35 + 0.7 * (1.0 - s)
    exaggeration = exaggeration + (0.5 - exaggeration) * (0.75 * sim)
    return {
        "stability": round(s, 3),
        "similarity": round(sim, 3),
        "temperature": round(temperature, 3),
        "exaggeration": round(exaggeration, 3),
        "cfg_weight": round(0.2 + 0.45 * s, 3),
        "repetition_penalty": round(1.12 + 0.28 * s, 3),
    }


PRESETS: list[dict[str, object]] = [
    {
        "id": "talk",
        "label": "Face to face",
        "prompt": "A real person explaining something to one listener. Natural, conversational, easy pace, small breaths. Sounds like the local language as people actually speak it.",
        "stability": 0.42,
        "similarity": 0.84,
    },
    {
        "id": "calm",
        "label": "Calm narrator",
        "prompt": "A calm, steady narrator. Clear diction, even pace, trustworthy and unhurried.",
        "stability": 0.82,
        "similarity": 0.88,
    },
    {
        "id": "host",
        "label": "Energetic host",
        "prompt": "An energetic show host. Quick pace, bright energy, still easy to understand.",
        "stability": 0.28,
        "similarity": 0.62,
    },
    {
        "id": "deep",
        "label": "Deep and steady",
        "prompt": "A deep, grounded voice. Slow, resonant, serious, and controlled.",
        "stability": 0.74,
        "similarity": 0.8,
    },
    {
        "id": "soft",
        "label": "Soft and close",
        "prompt": "A soft, close voice. Gentle, intimate, and consistent.",
        "stability": 0.7,
        "similarity": 0.92,
    },
    {
        "id": "news",
        "label": "News reader",
        "prompt": "A neutral news reader. Precise, robust, and highly consistent.",
        "stability": 0.9,
        "similarity": 0.7,
    },
]


def preset_by_id(preset_id: str | None) -> dict[str, object] | None:
    if not preset_id:
        return None
    for item in PRESETS:
        if item["id"] == preset_id:
            return item
    return None


def style_from_prompt(prompt: str, *, preset_id: str | None = None) -> dict[str, object]:
    """Keyword pass over a voice-design prompt. Preset wins when both are set."""
    preset = preset_by_id(preset_id)
    text = (prompt or "").strip()
    if preset and not text:
        text = str(preset["prompt"])
    low = text.lower()
    stability = 0.45
    similarity = 0.82
    if re.search(r"face.to.face|conversat|explain|one listener|natural|human", low):
        stability = min(stability, 0.45)
        similarity = max(similarity, 0.8)
    if re.search(r"calm|steady|slow|serious|controlled|narrat", low):
        stability = max(stability, 0.78)
        similarity = max(similarity, 0.8)
    if re.search(r"news|precise|neutral|robust|consistent", low):
        stability = max(stability, 0.86)
    if re.search(r"quick|excit|energet|host|theatrical|silly|maniac|burst", low):
        stability = min(stability, 0.32)
    if re.search(r"soft|whisper|gentle|intimate|close", low):
        stability = max(stability, 0.66)
        similarity = max(similarity, 0.9)
    if re.search(r"deep|boom|gravel|resonant", low):
        similarity = max(similarity, 0.78)
        stability = max(stability, 0.58)
    if preset:
        stability = float(preset["stability"])
        similarity = float(preset["similarity"])
        if not text:
            text = str(preset["prompt"])
    settings = delivery_settings(stability, similarity)
    name = str(preset["label"]) if preset else _name_from_prompt(text)
    return {
        "name": name,
        "prompt": text,
        "preset_id": preset["id"] if preset else None,
        **settings,
    }


def _name_from_prompt(prompt: str) -> str:
    words = re.findall(r"[A-Za-z\u0900-\u097F]+", prompt)
    if not words:
        return "Designed voice"
    return " ".join(words[:4])[:48]


def detect_language(text: str) -> str:
    """Auto: Devanagari-heavy text is Hindi, otherwise English."""
    devanagari = len(re.findall(r"[\u0900-\u097F]", text or ""))
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    if devanagari == 0 and latin == 0:
        return "hi"
    return "hi" if devanagari >= latin else "en"
