"""Read-only qualification of two distinct locally installed lesson models.

No model downloads, inference, media rendering, Pi access, or YouTube calls.
"""
from __future__ import annotations

import argparse
import json

from .local_vision_review import MODEL
from .m68_local_dependencies import inspect_ollama


def qualify(*, first_endpoint, first_model, second_endpoint, second_model,
            inspector=inspect_ollama):
    pairs = ((first_endpoint, first_model), (second_endpoint, second_model))
    if (first_endpoint == second_endpoint or first_model == second_model):
        raise ValueError("two distinct endpoints and model names required")
    for endpoint, model in pairs:
        if not isinstance(model, str) or not MODEL.fullmatch(model):
            raise ValueError("invalid model name")
    reports = []
    for endpoint, model in pairs:
        info = inspector(endpoint)
        if not isinstance(info, dict) or not isinstance(info.get("models"), list):
            raise ValueError("invalid local model inventory")
        reports.append({
            "endpoint": endpoint, "model": model,
            "reachable": info.get("reachable") is True,
            "installed": info.get("reachable") is True
                         and model in info["models"],
        })
    ready = all(row["reachable"] and row["installed"] for row in reports)
    return {
        "status": ("LESSON_MODELS_INSTALLED_NOT_INFERENCE_TESTED" if ready
                   else "LESSON_MODELS_NOT_READY"),
        "models": reports, "ready_for_inference_attempt": ready,
        "model_inference_executed": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("first", "second"):
        parser.add_argument("--" + label + "-endpoint", required=True)
        parser.add_argument("--" + label + "-model", required=True)
    args = parser.parse_args(argv)
    try:
        result = qualify(
            first_endpoint=args.first_endpoint, first_model=args.first_model,
            second_endpoint=args.second_endpoint, second_model=args.second_model)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "LESSON_MODELS_INVALID",
                          "error": str(exc),
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_inference_attempt"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
