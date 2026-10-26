"""Opt-in, local-only ComfyUI API submission with an approved workflow.

Safety: no model downloads, no arbitrary network URLs, no secret values,
no arbitrary workflow field mutation, no automatic subscription/paid calls.
An explicit --submit action is required to queue any job.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib import request
from urllib.parse import urlparse


MODEL_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".onnx")
BANNED_CLASS_MARKERS = (
    "http", "request", "websocket", "cloud", "external", "remote",
    "openai", "anthropic", "gemini", "dalle", "falai", "replicate", "runpod",
    "shell", "exec", "pythonexec", "upload", "download", "subprocess",
)
MAX_WORKFLOW_BYTES = 2_000_000
SAFE_PREFIX_RE = re.compile(r"^[a-zA-Z0-9_./-]{1,120}$")


class ComfySafetyError(ValueError):
    """Unsafe workflow, node, model, patch, or host."""


def validate_local_base_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not (1 <= parsed.port <= 65535)
    ):
        raise ComfySafetyError("Only http://127.0.0.1:PORT local instances are allowed.")
    return f"http://127.0.0.1:{parsed.port}"


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_WORKFLOW_BYTES:
        raise ComfySafetyError("Workflow/profile exceeds permitted size.")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ComfySafetyError("JSON document must be an object.")
    return obj, raw


def _walk_model_names(inputs: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(inputs, dict):
        for value in inputs.values():
            result.update(_walk_model_names(value))
    elif isinstance(inputs, list):
        for value in inputs:
            result.update(_walk_model_names(value))
    elif isinstance(inputs, str) and inputs.lower().endswith(MODEL_SUFFIXES):
        result.add(inputs)
    return result


def prepare_submission(
    workflow_file: str | Path,
    profile_file: str | Path,
    *,
    prompt_text: str,
    filename_prefix: str,
) -> dict[str, Any]:
    workflow_path = Path(workflow_file)
    profile_path = Path(profile_file)
    workflow, raw = _load_json(workflow_path)
    profile, _ = _load_json(profile_path)

    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != profile.get("approved_workflow_sha256"):
        raise ComfySafetyError(
            "Workflow SHA-256 is not approved by the current local profile."
        )
    allowed = profile.get("allowed_node_classes")
    approved_models = profile.get("approved_model_names")
    if not isinstance(allowed, list) or not allowed or not all(
        isinstance(x, str) for x in allowed
    ):
        raise ComfySafetyError("Specify allowed_node_classes explicitly.")
    if not isinstance(approved_models, list) or not all(
        isinstance(x, str) for x in approved_models
    ):
        raise ComfySafetyError("Specify approved_model_names explicitly.")
    if len(workflow) > 160:
        raise ComfySafetyError("Workflow node count exceeds local profile limit.")

    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise ComfySafetyError("Invalid node in API-format workflow.")
        cls = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(cls, str) or not isinstance(inputs, dict):
            raise ComfySafetyError(f"Node {node_id} is not API-format.")
        if any(marker in cls.lower() for marker in BANNED_CLASS_MARKERS):
            raise ComfySafetyError(f"Disallowed external/executable node: {cls}")
        if cls not in allowed:
            raise ComfySafetyError(f"Unapproved node class: {cls}")
        unknown_models = _walk_model_names(inputs) - set(approved_models)
        if unknown_models:
            raise ComfySafetyError(
                f"Unapproved model at node {node_id}: {sorted(unknown_models)}"
            )

    prompt_node = profile.get("prompt_node_id")
    prefix_node = profile.get("filename_node_id")
    if not isinstance(prompt_node, str) or prompt_node not in workflow:
        raise ComfySafetyError("Invalid prompt_node_id.")
    if not isinstance(prefix_node, str) or prefix_node not in workflow:
        raise ComfySafetyError("Invalid filename_node_id.")
    if workflow[prompt_node]["class_type"] != "CLIPTextEncode":
        raise ComfySafetyError("Prompt node must be a standard CLIPTextEncode.")
    if workflow[prefix_node]["class_type"] != "SaveImage":
        raise ComfySafetyError("Output node must be a standard SaveImage.")
    if not isinstance(prompt_text, str) or not (1 <= len(prompt_text) <= 6000):
        raise ComfySafetyError("Prompt must be 1–6000 characters.")
    if (
        not isinstance(filename_prefix, str)
        or not SAFE_PREFIX_RE.fullmatch(filename_prefix)
        or ".." in filename_prefix.split("/")
        or filename_prefix.startswith("/")
    ):
        raise ComfySafetyError("Unsafe output filename prefix.")

    result = copy.deepcopy(workflow)
    result[prompt_node]["inputs"]["text"] = prompt_text
    result[prefix_node]["inputs"]["filename_prefix"] = filename_prefix
    return {
        "status": "READY_NOT_SUBMITTED",
        "workflow_sha256": checksum,
        "node_count": len(result),
        "models": sorted(set().union(*[
            _walk_model_names(node["inputs"]) for node in result.values()
        ])),
        "prompt": result,
    }


def queue_on_local_comfy(
    prepared: dict[str, Any], *, base_url: str = "http://127.0.0.1:8188"
) -> dict[str, Any]:
    """An intentional network operation; caller must explicitly opt in."""
    base = validate_local_base_url(base_url)
    if prepared.get("status") != "READY_NOT_SUBMITTED":
        raise ComfySafetyError("Submit only a validated, prepared workflow.")
    data = json.dumps({"prompt": prepared["prompt"]}).encode("utf-8")
    req = request.Request(
        base + "/prompt", data=data, headers={"Content-Type": "application/json"},
        method="POST"
    )
    with request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read(MAX_WORKFLOW_BYTES + 1))
    if not isinstance(result, dict) or not isinstance(result.get("prompt_id"), str):
        raise RuntimeError("ComfyUI did not return a prompt_id.")
    return {"status": "QUEUED", "prompt_id": result["prompt_id"]}
