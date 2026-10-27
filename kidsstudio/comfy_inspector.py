"""Read-only Mac ComfyUI readiness diagnostic for original character rigs.

Never submits GPU jobs, uploads a reference image, changes models, downloads
checkpoints, reads arbitrary model weights or calls a paid AI service.
Workflow values and local machine details never enter source-control reports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib import error, request

from .comfy import (
    ComfySafetyError, MAX_WORKFLOW_BYTES, BANNED_CLASS_MARKERS,
    _walk_model_names, validate_local_base_url,
)
from .workflow_audit import audit_character_workflow

MAX_OBJECT_INFO_BYTES = 24_000_000
MAX_STATS_BYTES = 150_000
ROLE_HINTS = {
    "identity_conditioning": ("ipadapter", "reference", "kontext", "pulid", "instantid", "identity", "conditioning"),
    "sampler": ("sampler", "samplecustom", "ksampler"),
    "alpha_matte": ("matte", "removebg", "backgroundremove", "transparent", "rmbg", "alpha"),
}


class ReadinessError(ValueError):
    """Invalid diagnostic input; no workflow submission was attempted."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _load_workflow(file: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(file).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > MAX_WORKFLOW_BYTES:
        raise ReadinessError("API workflow missing or larger than 2 MB.")
    raw = source.read_bytes()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ReadinessError("Workflow is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ReadinessError("ComfyUI workflow must be a JSON object.")
    return data, hashlib.sha256(raw).hexdigest()


def _class_ids(workflow: dict[str, Any], cls: str) -> list[str]:
    return sorted(i for i, node in workflow.items()
                  if node["class_type"] == cls)


def _hint_ids(workflow: dict[str, Any], role: str) -> list[str]:
    markers = ROLE_HINTS[role]
    return sorted(i for i, node in workflow.items()
                  if any(t in node["class_type"].lower() for t in markers))


def _check_graph_format(workflow: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if isinstance(workflow.get("nodes"), list):
        return ["EDITOR_FORMAT_NOT_API"]
    if not workflow or len(workflow) > 160:
        return ["INVALID_NODE_COUNT"]
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            return ["INVALID_API_NODE"]
        cls = node.get("class_type")
        if not isinstance(cls, str) or not isinstance(node.get("inputs"), dict):
            return ["EDITOR_FORMAT_NOT_API"]
        if any(marker in cls.lower() for marker in BANNED_CLASS_MARKERS):
            issues.append("UNSAFE_EXTERNAL_OR_EXECUTABLE_NODE")
    return sorted(set(issues))


def _candidates(workflow: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "prompt_node_id": _class_ids(workflow, "CLIPTextEncode"),
        "reference_node_id": _class_ids(workflow, "LoadImage"),
        "filename_node_id": _class_ids(workflow, "SaveImage"),
        "conditioning_node_id": _hint_ids(workflow, "identity_conditioning"),
        "sampler_node_id": _hint_ids(workflow, "sampler"),
        "matting_node_id": _hint_ids(workflow, "alpha_matte"),
    }


def draft_profile(workflow: dict[str, Any], sha: str) -> dict[str, Any]:
    """Unapproved configuration skeleton. Deliberately unusable as a permit."""
    choices = _candidates(workflow)
    def proposed(key: str) -> str:
        ids = choices[key]
        return ids[0] if len(ids) == 1 else "REQUIRES_HUMAN_NODE_SELECTION"
    return {
        "approved_workflow_sha256": "OWNER_MUST_APPROVE_" + sha,
        "allowed_node_classes": sorted({
            node["class_type"] for node in workflow.values()
        }),
        "approved_model_names": sorted({
            name for node in workflow.values()
            for name in _walk_model_names(node["inputs"])
        }),
        "prompt_node_id": proposed("prompt_node_id"),
        "reference_node_id": proposed("reference_node_id"),
        "filename_node_id": proposed("filename_node_id"),
        "production_contract": {
            "conditioning_node_id": "REQUIRES_HUMAN_GRAPH_INSPECTION",
            "sampler_node_id": "REQUIRES_HUMAN_GRAPH_INSPECTION",
            "matting_node_id": "REQUIRES_HUMAN_GRAPH_INSPECTION",
        },
        "_note": (
            "Unapproved planning draft; inspect actual API graph, node semantics, "
            "model names and outputs. Remove _note and fill all fields. The "
            "workflow hash MUST only be approved by the local owner, not auto."
        ),
    }


def _get_local_json(base: str, endpoint: str, *, opener: Any,
                    limit: int) -> Any:
    if endpoint not in ("/object_info", "/system_stats"):
        raise ReadinessError("Only read-only diagnostic endpoints are allowed.")
    req = request.Request(base + endpoint, method="GET")
    with opener.open(req, timeout=12) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ReadinessError("Local ComfyUI diagnostic response exceeded cap.")
    return json.loads(raw)


def _model_registration(
    workflow: dict[str, Any],
    available: dict[str, Any],
) -> list[dict[str, Any]]:
    """Verify selected model dropdown values only when server exposes choices."""
    checks: list[dict[str, Any]] = []
    for node_id, node in workflow.items():
        class_info = available.get(node["class_type"])
        if not isinstance(class_info, dict):
            continue
        inputs_schema = class_info.get("input", {})
        if not isinstance(inputs_schema, dict):
            continue
        for field, value in node["inputs"].items():
            if not isinstance(value, str) or not value.lower().endswith(
                (".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".onnx")
            ):
                continue
            schema = None
            for scope in ("required", "optional"):
                candidate = inputs_schema.get(scope, {})
                if isinstance(candidate, dict) and field in candidate:
                    schema = candidate[field]
                    break
            choices = schema[0] if isinstance(schema, list) and schema else None
            # Some loaders use dynamic values or custom free text; do not
            # make a false assertion that model files exist on disk.
            if isinstance(choices, list) and all(isinstance(c, str) for c in choices):
                result = "AVAILABLE_IN_NODE_CHOICES" if value in choices else "NOT_IN_NODE_CHOICES"
            else:
                result = "UNVERIFIED_DYNAMIC_MODEL_INPUT"
            checks.append({
                "node_id": node_id, "input_name": field,
                "status": result,
                "model_name": Path(value).name,
            })
    return checks


def inspect_mac_comfy(
    workflow_file: str | Path,
    *, base_url: str = "http://127.0.0.1:8188",
    connect: bool = False,
    profile_file: str | Path | None = None,
    blueprint_file: str | Path | None = None,
    reference_file: str | Path | None = None,
    opener: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Analyze actual workflow and optionally registered *local* ComfyUI nodes.

    Returns redacted diagnostic report and an unapproved candidate profile,
    never full workflow source nor local prompt values.
    """
    if type(connect) is not bool:
        raise ReadinessError("connect must be an explicit boolean.")
    data, workflow_sha = _load_workflow(workflow_file)
    errors = _check_graph_format(data)
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "BLOCKED" if errors else "NEEDS_OWNER_WORKFLOW_APPROVAL",
        "workflow_sha256": workflow_sha,
        "format": "EDITOR_FORMAT" if "EDITOR_FORMAT_NOT_API" in errors else "API_FORMAT",
        "node_count": len(data),
        "checks": {"api_format": "FAIL" if errors else "PASS"},
        "issues": list(errors),
        "candidates": {},
        "live_comfy_connection_requested": connect,
        "production_approved": False,
        "generation_submitted": False,
        "api_tokens_or_original_art_uploaded": False,
    }
    if errors:
        result["next_action"] = (
            "Open the workflow in ComfyUI; use File > Export Workflow (API), "
            "remove prohibited execution/network nodes, and inspect again."
        )
        return result, None

    candidates = _candidates(data)
    result["candidates"] = candidates
    if not candidates["prompt_node_id"]:
        result["issues"].append("MISSING_STANDARD_CLIP_TEXT_ENCODE")
    if not candidates["reference_node_id"]:
        result["issues"].append("MISSING_LOAD_IMAGE")
    if not candidates["filename_node_id"]:
        result["issues"].append("MISSING_SAVE_IMAGE")
    for key in ("conditioning_node_id", "sampler_node_id", "matting_node_id"):
        if not candidates[key]:
            result["issues"].append("NO_OBVIOUS_" + key.upper())
    draft = draft_profile(data, workflow_sha)

    if connect:
        base = validate_local_base_url(base_url)
        active = opener if opener is not None else request.build_opener(
            request.ProxyHandler({}), _NoRedirect(),
        )
        try:
            nodes = _get_local_json(
                base, "/object_info", opener=active,
                limit=MAX_OBJECT_INFO_BYTES,
            )
            if not isinstance(nodes, dict):
                raise ReadinessError("ComfyUI node registry is malformed.")
            missing = sorted({
                node["class_type"] for node in data.values()
            } - set(nodes))
            result["checks"]["local_registry"] = "PASS" if not missing else "FAIL"
            result["unregistered_node_classes"] = missing
            if missing:
                result["issues"].append("WORKFLOW_HAS_MISSING_NODES")
            model_checks = _model_registration(data, nodes)
            result["model_registration"] = model_checks
            if any(x["status"] == "NOT_IN_NODE_CHOICES" for x in model_checks):
                result["issues"].append("SELECTED_MODEL_NOT_AVAILABLE")
            if any(x["status"] == "UNVERIFIED_DYNAMIC_MODEL_INPUT"
                   for x in model_checks):
                result["issues"].append("MODEL_INSTALLATION_NOT_PROVEN")
            result["live_nodes_registered"] = len(nodes)
        except (error.URLError, OSError, ValueError, UnicodeError,
                ReadinessError, TimeoutError, TypeError):
            result["checks"]["local_registry"] = "UNAVAILABLE"
            result["issues"].append("LOCAL_COMFYUI_UNAVAILABLE")
        # System stats are informational only; missing stats must not prove
        # that GPU support is or isn't available.
        if result["checks"].get("local_registry") == "PASS":
            try:
                stats = _get_local_json(
                    base, "/system_stats", opener=active,
                    limit=MAX_STATS_BYTES,
                )
                if isinstance(stats, dict):
                    result["checks"]["system_stats"] = "RECEIVED"
                    result["device_count"] = len(stats.get("devices", [])) if (
                        isinstance(stats.get("devices", []), list)
                    ) else None
                else:
                    result["checks"]["system_stats"] = "UNAVAILABLE"
            except (error.URLError, OSError, ValueError, UnicodeError,
                    ReadinessError, TimeoutError, TypeError):
                result["checks"]["system_stats"] = "UNAVAILABLE"

    requested = (profile_file, blueprint_file, reference_file)
    if any(item is not None for item in requested):
        if not all(item is not None for item in requested):
            result["issues"].append("NEED_PROFILE_BLUEPRINT_AND_REFERENCE_TOGETHER")
        else:
            try:
                audit = audit_character_workflow(
                    blueprint_file, workflow_file, profile_file, reference_file,
                )
                result["checks"]["approved_graph"] = "PASS"
                result["approved_graph_sha256"] = audit["workflow_sha256"]
            except (ComfySafetyError, ValueError, OSError, KeyError,
                    TypeError, json.JSONDecodeError):
                result["checks"]["approved_graph"] = "FAIL"
                result["issues"].append("APPROVED_GRAPH_AUDIT_FAILED")
    else:
        result["checks"]["approved_graph"] = "NOT_RUN"

    result["issues"] = sorted(set(result["issues"]))
    critical = {
        "WORKFLOW_HAS_MISSING_NODES", "LOCAL_COMFYUI_UNAVAILABLE",
        "SELECTED_MODEL_NOT_AVAILABLE", "APPROVED_GRAPH_AUDIT_FAILED",
        "NEED_PROFILE_BLUEPRINT_AND_REFERENCE_TOGETHER",
        "MISSING_STANDARD_CLIP_TEXT_ENCODE", "MISSING_LOAD_IMAGE",
        "MISSING_SAVE_IMAGE",
    }
    if any(issue in critical for issue in result["issues"]):
        result["status"] = "BLOCKED"
    elif (result["checks"]["approved_graph"] == "PASS"
          and connect and result["checks"].get("local_registry") == "PASS"
          and "MODEL_INSTALLATION_NOT_PROVEN" not in result["issues"]):
        result["status"] = "READY_FOR_TWO_PART_PROBE_NOT_GENERATED"
    else:
        result["status"] = "NEEDS_OWNER_WORKFLOW_APPROVAL"
    result["next_action"] = {
        "BLOCKED": "Fix missing nodes/models or obtain a correct API-format, approved workflow.",
        "READY_FOR_TWO_PART_PROBE_NOT_GENERATED": (
            "Graph and live node registry pass; operator may explicitly opt "
            "into the separate two-part generation probe. Art is NOT proven."
        ),
        "NEEDS_OWNER_WORKFLOW_APPROVAL": (
            "Inspect proposed node IDs and the ComfyUI graph, create a private "
            "reviewed profile, run the approved-graph audit, then inspect --connect."
        ),
    }[result["status"]]
    return result, draft
