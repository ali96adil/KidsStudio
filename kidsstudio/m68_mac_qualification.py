"""Single read-only Mac qualification command for M68 educational production.

Checks installed binaries and two local Ollama model inventories. Does not
infer, render, copy files to Pi, upload or publish.
"""
from __future__ import annotations

import argparse
import json

from .m68_local_dependencies import probe
from .m68_lesson_model_readiness import qualify


def qualify_mac(*, first_endpoint, first_model, second_endpoint, second_model,
                dependency_probe=probe, model_qualifier=qualify):
    dependencies = dependency_probe(require_ollama=True,
                                    ollama_endpoints=(first_endpoint, second_endpoint))
    models = model_qualifier(first_endpoint=first_endpoint, first_model=first_model,
                             second_endpoint=second_endpoint, second_model=second_model)
    ready = not dependencies["missing"] and models["ready_for_inference_attempt"]
    return {
        "status": "MAC_READY_FOR_MANUAL_INFERENCE_TRIAL" if ready else
                  "MAC_PREPARATION_BLOCKED",
        "dependencies": dependencies,
        "educational_models": models,
        "ready_for_manual_inference_trial": ready,
        "inference_executed": False,
        "render_executed": False,
        "pi_transfer_executed": False,
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
        result = qualify_mac(
            first_endpoint=args.first_endpoint, first_model=args.first_model,
            second_endpoint=args.second_endpoint, second_model=args.second_model)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "MAC_PREPARATION_BLOCKED", "error": str(exc),
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_manual_inference_trial"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
