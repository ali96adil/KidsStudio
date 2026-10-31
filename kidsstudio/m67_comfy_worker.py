"""M67 local ComfyUI worker: submit a preconfigured workflow and fetch its PNG.

Only loopback ComfyUI is permitted. No remote inference, publication or QA.
The workflow must contain an explicit SaveImage node and be preconfigured by
the operator; arbitrary prompt interpolation is deliberately unsupported.
"""
from __future__ import annotations

import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ComfyWorkerError(RuntimeError):
    pass


def _endpoint(base):
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ComfyWorkerError("only local ComfyUI HTTP endpoint allowed")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ComfyWorkerError("invalid endpoint")
    if parsed.path not in ("", "/"):
        raise ComfyWorkerError("endpoint must not contain a path")
    return f"http://127.0.0.1:{parsed.port or 8188}"


def _request(url, *, payload=None, timeout=20):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def run_workflow(workflow, *, base="http://127.0.0.1:8188",
                 poll_seconds=2, max_wait_seconds=900):
    endpoint = _endpoint(base)
    if not isinstance(workflow, dict) or not workflow:
        raise ComfyWorkerError("API-format workflow required")
    if not any(isinstance(node, dict) and node.get("class_type") == "SaveImage"
               for node in workflow.values()):
        raise ComfyWorkerError("SaveImage node required")
    submitted = _request(endpoint + "/prompt", payload={"prompt": workflow})
    prompt_id = submitted.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise ComfyWorkerError("ComfyUI did not return prompt id")
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        history = _request(endpoint + "/history/" + prompt_id)
        record = history.get(prompt_id)
        if record:
            if record.get("status", {}).get("status_str") == "error":
                raise ComfyWorkerError("ComfyUI workflow failed")
            outputs = record.get("outputs", {})
            images = [image for node in outputs.values()
                      for image in node.get("images", [])
                      if image.get("type") == "output"]
            if images:
                return {"status": "COMFY_OUTPUT_PENDING_VALIDATION",
                        "prompt_id": prompt_id, "images": images,
                        "visual_qa": "PENDING"}
        time.sleep(poll_seconds)
    raise ComfyWorkerError("ComfyUI workflow timeout")
