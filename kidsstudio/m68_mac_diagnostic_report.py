"""Read-only one-shot Mac qualification report for Kids Studio.

Writes a private JSON diagnostic report. No inference, rendering, Pi access,
YouTube operations or model downloads.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .m68_mac_qualification import qualify_mac
from .m68_local_dependencies import probe


def collect(*, endpoint, first_model=None, second_model=None,
            dependency_probe=probe, qualification=qualify_mac):
    if (first_model is None) != (second_model is None):
        raise ValueError("supply both model names or neither")
    if first_model is None:
        dependencies = dependency_probe(require_ollama=True,
                                        ollama_endpoints=(endpoint,))
        return {"schema_version": 1, "status": "INVENTORY_ONLY",
                "dependencies": dependencies,
                "ready_for_manual_inference_trial": False,
                "model_inference_executed": False,
                "pi_transfer_executed": False,
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    result = qualification(first_endpoint=endpoint, first_model=first_model,
                           second_endpoint=endpoint, second_model=second_model)
    return {"schema_version": 1, **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/api/chat")
    parser.add_argument("--first-model")
    parser.add_argument("--second-model")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (not args.output.is_absolute() or args.output.is_symlink()
                or not args.output.parent.is_dir() or args.output.exists()):
            raise ValueError("new absolute report path in existing directory required")
        result = collect(endpoint=args.endpoint, first_model=args.first_model,
                         second_model=args.second_model)
        payload = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
        if len(payload) > 200_000:
            raise ValueError("diagnostic report too large")
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        print(json.dumps({"status": result["status"],
                          "report_path": str(args.output),
                          "ready_for_manual_inference_trial":
                          result["ready_for_manual_inference_trial"],
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False},
                         ensure_ascii=False))
        return 0 if result["status"] != "MAC_PREPARATION_BLOCKED" else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "MAC_DIAGNOSTIC_FAILED",
                          "error_type": type(exc).__name__,
                          "youtube_upload_authorized": False,
                          "public_release_authorized": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
