"""M68 local preflight: one read-only command summarizing review readiness.

Does not run inference, media rendering, transfer, YouTube or network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m68_consolidated_review import audit


def preflight(*, root, handoff_path, vision_path=None, audio_path=None,
              rights_path=None, script_path=None, lesson_path=None,
              lesson_model_path=None):
    def read_json(path):
        item = Path(path)
        if (not item.is_absolute() or item.is_symlink()
                or not item.is_file() or not 1 <= item.stat().st_size <= 200_000):
            raise ValueError("absolute regular bounded JSON evidence required")
        data = json.loads(item.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON evidence must be an object")
        return data

    handoff = read_json(handoff_path)

    def read_optional(path):
        return read_json(path) if path else None

    report = audit(
        root, handoff,
        vision_receipt=read_optional(vision_path),
        audio_receipt=read_optional(audio_path),
        rights_manifest=rights_path,
        script_path=script_path, lesson_path=lesson_path,
        lesson_model_receipt=read_optional(lesson_model_path),
    )
    report["preflight_mode"] = "READ_ONLY_NO_NETWORK_NO_UPLOAD"
    report["model_inference_executed"] = False
    report["mac_pi_hardware_verified"] = False
    report["next_action"] = (
        "Complete missing independent evidence and physical Mac/Pi qualification; "
        "do not upload or publish from this preflight."
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--vision", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--rights", type=Path)
    parser.add_argument("--script", type=Path)
    parser.add_argument("--lesson", type=Path)
    parser.add_argument("--lesson-model", type=Path)
    args = parser.parse_args(argv)
    try:
        result = preflight(
            root=args.root, handoff_path=args.handoff,
            vision_path=args.vision, audio_path=args.audio,
            rights_path=args.rights, script_path=args.script,
            lesson_path=args.lesson, lesson_model_path=args.lesson_model)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({
            "status": "M68_PREFLIGHT_INVALID",
            "error": str(exc),
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
