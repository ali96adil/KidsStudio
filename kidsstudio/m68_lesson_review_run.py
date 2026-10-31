"""One-command local M68 lesson readiness + actual two-model review.

Read-only source inspection and local Ollama inference. No upload or publish.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m68_lesson_model_readiness import qualify
from .m68_local_lesson_review import OllamaLesson, review_lesson


def run(handoff, *, script_path, lesson_path, first_endpoint, first_model,
        second_endpoint, second_model, inspector=None, reviewer_factory=OllamaLesson):
    kwargs = dict(first_endpoint=first_endpoint, first_model=first_model,
                  second_endpoint=second_endpoint, second_model=second_model)
    if inspector is not None:
        kwargs["inspector"] = inspector
    readiness = qualify(**kwargs)
    if not readiness["ready_for_inference_attempt"]:
        return {"status": "LESSON_REVIEW_BLOCKED_MODELS_NOT_READY",
                "readiness": readiness, "review": None,
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    review = review_lesson(
        handoff, script_path=script_path, lesson_path=lesson_path,
        first=reviewer_factory(first_endpoint, first_model),
        second=reviewer_factory(second_endpoint, second_model))
    checks = review.get("checks", {})
    passed = (isinstance(checks, dict) and
              set(checks) == {"pedagogy", "source_consistency"} and
              all(value is True for value in checks.values()))
    return {"status": ("LESSON_REVIEW_MODEL_PASS_RECORDED" if passed else
                       "LESSON_REVIEW_NEEDS_FIX"),
            "readiness": readiness, "review": review,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--lesson-plan", type=Path, required=True)
    for label in ("first", "second"):
        parser.add_argument("--" + label + "-endpoint", required=True)
        parser.add_argument("--" + label + "-model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists")
    try:
        if (not args.handoff.is_absolute() or args.handoff.is_symlink()
                or not args.handoff.is_file()
                or not 1 <= args.handoff.stat().st_size <= 200000):
            raise ValueError("bounded absolute handoff required")
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        if not isinstance(handoff, dict):
            raise ValueError("handoff object required")
        result = run(
            handoff, script_path=args.script, lesson_path=args.lesson_plan,
            first_endpoint=args.first_endpoint, first_model=args.first_model,
            second_endpoint=args.second_endpoint, second_model=args.second_model)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "LESSON_REVIEW_FAILED",
                          "error": str(exc),
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False}))
        return 2
    if result["review"] is not None:
        try:
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result["review"], handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except OSError as exc:
            print(json.dumps({"status": "LESSON_REVIEW_OUTPUT_FAILED",
                              "error": str(exc),
                              "youtube_upload_authorized": False,
                              "public_release_authorized": False}))
            return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "LESSON_REVIEW_MODEL_PASS_RECORDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
