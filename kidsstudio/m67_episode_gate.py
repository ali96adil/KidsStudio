"""M67 educational episode storyboard gate (no rendering or publication)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class EpisodeGateError(ValueError):
    pass


def validate_episode(data: dict) -> dict:
    if not isinstance(data, dict):
        raise EpisodeGateError("episode must be an object")
    if data.get("schema_version") != 1:
        raise EpisodeGateError("unsupported schema")
    if data.get("youtube_visibility") != "PRIVATE_ONLY":
        raise EpisodeGateError("episode must remain private")
    if data.get("review_state") != "DRAFT_NOT_APPROVED":
        raise EpisodeGateError("only draft storyboard admitted by this gate")
    if data.get("language") != "ar-IQ":
        raise EpisodeGateError("unexpected narration language")
    duration = data.get("duration_seconds")
    if type(duration) is not int or not 30 <= duration <= 180:
        raise EpisodeGateError("invalid duration")
    beats = data.get("beats")
    if not isinstance(beats, list) or not 3 <= len(beats) <= 15:
        raise EpisodeGateError("expected bounded storyboard")
    cursor = 0
    purposes = set()
    for beat in beats:
        if not isinstance(beat, dict):
            raise EpisodeGateError("invalid beat")
        start, end = beat.get("start"), beat.get("end")
        if type(start) is not int or type(end) is not int:
            raise EpisodeGateError("integer timeline required")
        if start != cursor or end <= start or end > duration:
            raise EpisodeGateError("gapped, overlapping or invalid timeline")
        for key in ("visual", "narration", "purpose"):
            if not isinstance(beat.get(key), str) or not beat[key].strip():
                raise EpisodeGateError("missing beat content")
        purposes.add(beat["purpose"])
        cursor = end
    if cursor != duration or not {"teach", "recall"}.issubset(purposes):
        raise EpisodeGateError("educational coverage incomplete")
    qa = data.get("qa_requirements")
    if not isinstance(qa, dict) or qa.get("single_primary_concept") is not True:
        raise EpisodeGateError("single learning objective required")
    if qa.get("no_flashing") is not True or qa.get("no_external_links_or_qr") is not True:
        raise EpisodeGateError("child-safe presentation requirements missing")
    return {"status": "STORYBOARD_VALID_DRAFT_ONLY",
            "beats": len(beats), "duration_seconds": duration,
            "render_authorized": False, "upload_authorized": False,
            "public_release_authorized": False}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("storyboard", type=Path)
    args = p.parse_args(argv)
    try:
        if args.storyboard.is_symlink() or not args.storyboard.is_file():
            raise EpisodeGateError("regular storyboard file required")
        result = validate_episode(json.loads(
            args.storyboard.read_text(encoding="utf-8")))
        code = 0
    except (EpisodeGateError, OSError, ValueError) as exc:
        result = {"status": "STORYBOARD_REJECTED", "reason": str(exc)}
        code = 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
