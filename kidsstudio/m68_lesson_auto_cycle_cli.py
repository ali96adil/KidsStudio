"""CLI for the bounded local M68 two-model lesson repair cycle.

Never uploads or publishes. Existing output directory must be supplied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m68_lesson_auto_cycle import run_cycle
from .m68_local_lesson_review import OllamaLesson
from .m68_local_script_rewriter import OllamaScriptRewriter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--lesson-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--first-endpoint", required=True)
    parser.add_argument("--first-model", required=True)
    parser.add_argument("--second-endpoint", required=True)
    parser.add_argument("--second-model", required=True)
    parser.add_argument("--rewriter-endpoint", required=True)
    parser.add_argument("--rewriter-model", required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if (not args.handoff.is_absolute() or args.handoff.is_symlink()
                or not args.handoff.is_file()
                or not 1 <= args.handoff.stat().st_size <= 200000):
            raise ValueError("absolute bounded handoff file required")
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        if not isinstance(handoff, dict):
            raise ValueError("handoff object required")
        first = OllamaLesson(args.first_endpoint, args.first_model)
        second = OllamaLesson(args.second_endpoint, args.second_model)
        rewriter = OllamaScriptRewriter(args.rewriter_endpoint,
                                       args.rewriter_model)
        result = run_cycle(
            handoff, script_path=args.script, lesson_path=args.lesson_plan,
            output_dir=args.output_dir, first=first, second=second,
            rewriter=rewriter, max_attempts=args.max_attempts)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "LESSON_AUTO_CYCLE_FAILED",
                          "error": str(exc),
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
