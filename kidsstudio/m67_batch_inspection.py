"""Check Godot batch report against episode manifest without changing approval."""
from __future__ import annotations

from pathlib import Path

from .m67_production_handoff import _safe_file, _sha


def inspect_batch(manifest, batch, root, workspace):
    items = manifest.get("assets", [])
    beats = batch.get("beats", [])
    if batch.get("status") != "ALL_BEATS_RENDERED_PENDING_QA":
        return {"status": "BLOCKED", "reason": "batch incomplete"}
    if manifest.get("episode_id") != batch.get("episode_id"):
        return {"status": "BLOCKED", "reason": "episode mismatch"}
    if not items or len(items) != len(beats):
        return {"status": "BLOCKED", "reason": "beat count mismatch"}
    verified = []
    for number, (item, beat) in enumerate(zip(items, beats), 1):
        if item.get("beat") != number or beat.get("beat") != number:
            return {"status": "BLOCKED", "reason": "beat order mismatch"}
        if beat.get("status") != "RENDERED_PENDING_QA":
            return {"status": "BLOCKED", "reason": "beat not rendered"}
        try:
            video = _safe_file(Path(workspace), beat["video"])
            if _sha(video) != beat.get("sha256"):
                return {"status": "BLOCKED", "reason": "video changed"}
            if not video.resolve().is_relative_to(Path(root).resolve()):
                return {"status": "BLOCKED", "reason": "video outside episode"}
        except (OSError, KeyError, ValueError):
            return {"status": "BLOCKED", "reason": "video unavailable"}
        verified.append({"beat": number,
                         "path": str(video.relative_to(Path(root).resolve())),
                         "sha256": beat["sha256"], "qa": "PENDING"})
    return {"status": "RENDERS_VERIFIED_PENDING_QA",
            "videos": verified, "upload_authorized": False,
            "public_release_authorized": False}
