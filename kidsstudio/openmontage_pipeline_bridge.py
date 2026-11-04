"""Kids Studio pipeline selection inspired by OpenMontage's manifest-first architecture.

Original implementation, not copied from OpenMontage. Planning only: no network,
render, uploads, filesystem writes or subprocess execution.
"""
from __future__ import annotations

from typing import Any

PIPELINES: dict[str, dict[str, Any]] = {
    "animated_explainer": {
        "description": "Child-friendly animated lesson with recurring characters",
        "stages": ["curriculum", "script", "child_safety_review", "storyboard",
                   "character_consistency", "assets", "godot_render", "audio",
                   "automated_quality", "private_owner_review"],
        "engines": ["godot", "comfyui", "ffmpeg"],
    },
    "bilingual_localization": {
        "description": "Adapt an approved episode into a second language",
        "stages": ["source_review", "translation", "language_quality",
                   "timing", "voice", "subtitle", "render",
                   "automated_quality", "private_owner_review"],
        "engines": ["local_tts", "ffmpeg", "godot"],
    },
    "coloring_companion": {
        "description": "Printable educational companion for an approved episode",
        "stages": ["curriculum", "asset_rights", "line_art",
                   "print_quality", "private_owner_review"],
        "engines": ["vector", "pdf"],
    },
}


def plan_episode(*, episode_id: str, topic: str, language: str = "ar",
                 kind: str = "animated_explainer",
                 available_engines: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(episode_id, str) or not episode_id or len(episode_id) > 128:
        raise ValueError("invalid episode_id")
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 500:
        raise ValueError("invalid topic")
    if language not in ("ar", "en"):
        raise ValueError("supported languages: ar, en")
    if kind not in PIPELINES:
        raise ValueError("unknown pipeline")
    if available_engines is None:
        available_engines = []
    if (not isinstance(available_engines, list) or
            any(not isinstance(x, str) for x in available_engines)):
        raise ValueError("available_engines must be string list")
    pipeline = PIPELINES[kind]
    return {
        "status": "PLAN_ONLY_NOT_EXECUTED",
        "episode_id": episode_id,
        "topic": topic.strip(),
        "language": language,
        "pipeline": kind,
        "description": pipeline["description"],
        "stages": list(pipeline["stages"]),
        "recommended_engines": list(pipeline["engines"]),
        "available_recommended_engines": [
            x for x in pipeline["engines"] if x in available_engines],
        "missing_engines": [x for x in pipeline["engines"]
                            if x not in available_engines],
        "review_gates": ["automated_child_safety", "owner_private_review",
                         "explicit_owner_public_release"],
        "youtube_uploaded": False,
        "public_release_authorized": False,
        "source_inspiration": "OpenMontage manifest-first pipeline architecture",
        "source_url": "https://github.com/calesthio/OpenMontage",
        "implementation": "original KidsStudio code; no OpenMontage code vendored",
    }
