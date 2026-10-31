"""Read-only local M68 dependency readiness probe; no media or network calls."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def probe(*, require_ollama=False):
    tools = {}
    for name in ("python3", "ffmpeg", "ffprobe", "godot", "ollama", "ssh", "scp"):
        path = shutil.which(name)
        tools[name] = {"available": bool(path), "path": path}
    required = ("python3", "ffmpeg", "ffprobe", "godot", "ssh", "scp")
    missing = [name for name in required if not tools[name]["available"]]
    if require_ollama and not tools["ollama"]["available"]:
        missing.append("ollama")
    return {
        "status": "LOCAL_DEPENDENCIES_PRESENT_NOT_RUNTIME_VERIFIED"
                  if not missing else "LOCAL_DEPENDENCIES_MISSING",
        "tools": tools, "missing": missing,
        "model_inference_executed": False,
        "pi_connection_tested": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ollama", action="store_true")
    args = parser.parse_args(argv)
    result = probe(require_ollama=args.require_ollama)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
