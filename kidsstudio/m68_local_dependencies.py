"""Read-only local M68 dependency readiness probe; no media or network calls."""
from __future__ import annotations

import argparse
import json
import shutil
from urllib import request, error
from .local_vision_review import _endpoint


def inspect_ollama(endpoint, *, opener=None):
    """Read only Ollama tags on explicit loopback; no model execution."""
    url = _endpoint(endpoint)
    tags_url = url[:-len("/api/chat")] + "/api/tags"
    client = opener if opener is not None else request.build_opener(
        request.ProxyHandler({}))
    req = request.Request(tags_url, method="GET")
    try:
        with client.open(req, timeout=4) as response:
            raw = response.read(200001)
    except (OSError, TimeoutError, error.URLError, error.HTTPError):
        return {"reachable": False, "models": [], "error": "local_ollama_unreachable"}
    if len(raw) > 200000:
        return {"reachable": False, "models": [], "error": "response_too_large"}
    try:
        data = json.loads(raw)
        models = data["models"]
        if not isinstance(models, list) or len(models) > 500:
            raise ValueError("invalid models")
        names = [item["name"] for item in models]
        if any(not isinstance(name, str) or not 1 <= len(name) <= 120
               for name in names):
            raise ValueError("invalid model name")
    except (ValueError, TypeError, KeyError):
        return {"reachable": False, "models": [], "error": "invalid_tags_response"}
    return {"reachable": True, "models": names, "error": None}


def probe(*, require_ollama=False, ollama_endpoints=()):
    tools = {}
    for name in ("python3", "ffmpeg", "ffprobe", "godot", "ollama", "ssh", "scp"):
        path = shutil.which(name)
        tools[name] = {"available": bool(path), "path": path}
    required = ("python3", "ffmpeg", "ffprobe", "godot", "ssh", "scp")
    missing = [name for name in required if not tools[name]["available"]]
    if require_ollama and not tools["ollama"]["available"]:
        missing.append("ollama")
    services = {endpoint: inspect_ollama(endpoint)
                for endpoint in ollama_endpoints}
    for endpoint, service in services.items():
        if not service["reachable"]:
            missing.append("ollama_service:" + endpoint)
    return {
        "ollama_services": services,
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
    parser.add_argument("--ollama-endpoint", action="append", default=[])
    args = parser.parse_args(argv)
    result = probe(require_ollama=args.require_ollama,
                   ollama_endpoints=args.ollama_endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
