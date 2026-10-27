"""Single-command, read-only Mac art-station qualification report.

This tool never submits ComfyUI prompts, changes models, uploads artwork,
installs software, or talks to paid AI services. Optional network requests
are GET requests to explicit loopback ComfyUI and Ollama endpoints only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any
from urllib import error, request

from PIL import Image, UnidentifiedImageError

from .comfy import validate_local_base_url
from .comfy_inspector import inspect_mac_comfy
from .factory import inspect_reference_image
from .planner import make_rig_plan
from .reviewer import MODEL_RE

MAX_TAGS_BYTES = 2_000_000
SAFE_BINARY = re.compile(r"^(?:godot|godot4|ffmpeg)$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+~-]{0,90}$")


class MacDoctorError(ValueError):
    """Invalid or unsafe local station inspection request."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _local_get_json(url: str, *, opener: Any, limit: int) -> Any:
    with opener.open(request.Request(url, method="GET"), timeout=12) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise MacDoctorError("Local metadata response exceeded limit.")
    return json.loads(raw)


def _godot_path(explicit: str | None = None) -> str | None:
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return None
        return str(candidate)
    # These paths refer to the official macOS application bundle, not any
    # executable discovered by scanning a user's private directories.
    found = shutil.which("godot") or shutil.which("godot4")
    if found:
        return found
    for candidate in (
        Path("/Applications/Godot.app/Contents/MacOS/Godot"),
        Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _tool_info(tool: str, binary: str | None) -> dict[str, Any]:
    if tool not in {"godot", "ffmpeg"}:
        raise MacDoctorError("Unsupported local diagnostic executable.")
    path = _godot_path(binary) if tool == "godot" else (
        str(Path(binary).expanduser().resolve()) if binary else shutil.which("ffmpeg")
    )
    if not path:
        return {"state": "MISSING", "version": None}
    if tool == "ffmpeg" and not Path(path).is_file():
        return {"state": "MISSING", "version": None}
    args = [path, "--version" if tool == "godot" else "-version"]
    try:
        proc = subprocess.run(
            args, check=False, capture_output=True, text=True,
            errors="replace", timeout=8,
        )
        # Never preserve raw binary output: it may contain personal paths.
        line = proc.stdout.splitlines()[0].strip() if proc.stdout else ""
        if tool == "ffmpeg":
            match = re.match(r"^ffmpeg version (\S+)", line)
            version = match.group(1) if match else None
        else:
            version = line.split()[0] if line else None
        if version is not None and not VERSION.fullmatch(version):
            version = None
        return {
            "state": "FOUND" if proc.returncode == 0 and version else "UNVERIFIED",
            "version": version,
        }
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"state": "UNAVAILABLE", "version": None}


def _reference_info(reference_file: str | Path) -> dict[str, Any]:
    try:
        payload, _, digest = inspect_reference_image(reference_file)
        with Image.open(Path(reference_file).expanduser()) as source:
            source.load()
            dims = [source.width, source.height]
            rgb = source.mode
    except (OSError, ValueError, UnidentifiedImageError):
        return {"state": "BLOCKED", "issue": "CANONICAL_REFERENCE_INVALID"}
    return {
        "state": "PASS", "sha256": digest,
        "dimensions": dims, "mode": rgb,
        "byte_count": len(payload),
    }


def _ollama_info(
    *, model: str | None, connect: bool, opener: Any | None,
) -> dict[str, Any]:
    if model is None:
        return {"state": "NOT_SELECTED", "model_registered": None,
                "vision_capability_verified": False}
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise MacDoctorError("Invalid selected local Ollama model name.")
    if not connect:
        return {"state": "NOT_CHECKED_OFFLINE", "model_registered": None,
                "vision_capability_verified": False}
    active = opener if opener is not None else request.build_opener(
        request.ProxyHandler({}), _NoRedirect(),
    )
    try:
        tags = _local_get_json(
            "http://127.0.0.1:11434/api/tags",
            opener=active, limit=MAX_TAGS_BYTES,
        )
        names = {
            item.get("name") for item in tags.get("models", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        return {
            "state": "FOUND" if model in names else "MISSING",
            "model_registered": model in names,
            "vision_capability_verified": False,
        }
    except (error.URLError, OSError, ValueError, TypeError, TimeoutError,
            KeyError, AttributeError):
        return {"state": "UNAVAILABLE", "model_registered": None,
                "vision_capability_verified": False}


def _disk_info(output_root: str | Path | None, min_free_gb: int) -> dict[str, Any]:
    if type(min_free_gb) is not int or not 1 <= min_free_gb <= 100:
        raise MacDoctorError("min_free_gb must be an integer 1..100.")
    if output_root is None:
        return {"state": "NOT_CHECKED", "minimum_free_gb": min_free_gb}
    directory = Path(output_root).expanduser().resolve()
    if not directory.is_dir():
        return {"state": "MISSING", "minimum_free_gb": min_free_gb}
    if any((p / ".git").exists() for p in (directory, *directory.parents)):
        return {"state": "BLOCKED_GIT_OUTPUT_ROOT", "minimum_free_gb": min_free_gb}
    try:
        free = shutil.disk_usage(directory).free // (1024 ** 3)
    except OSError:
        return {"state": "UNAVAILABLE", "minimum_free_gb": min_free_gb}
    return {
        "state": "PASS" if free >= min_free_gb else "LOW_FREE_SPACE",
        "free_gb_floor": free, "minimum_free_gb": min_free_gb,
    }


def inspect_mac_station(
    *, workflow_file: str | Path,
    reference_file: str | Path,
    blueprint_file: str | Path | None = None,
    profile_file: str | Path | None = None,
    connect: bool = False,
    comfy_url: str = "http://127.0.0.1:8188",
    ollama_model: str | None = None,
    output_root: str | Path | None = None,
    min_free_gb: int = 10,
    godot_binary: str | None = None,
    ffmpeg_binary: str | None = None,
    comfy_opener: Any | None = None,
    ollama_opener: Any | None = None,
) -> dict[str, Any]:
    """Produce one redacted, reproducible status; never approve artwork.

    ready=True requires explicit real ComfyUI registry and owner-pinned
    graph, registered reviewer model, available render tools, sound
    reference art and adequate disk. It NEVER authorizes generation.
    """
    if type(connect) is not bool:
        raise MacDoctorError("connect must be a boolean.")
    # Validate loopback before any network access.
    validate_local_base_url(comfy_url)
    if (profile_file is None) != (blueprint_file is None):
        raise MacDoctorError("Approved profile and blueprint must be supplied together.")
    reference = _reference_info(reference_file)
    work = inspect_mac_comfy(
        workflow_file, connect=connect, base_url=comfy_url,
        profile_file=profile_file, blueprint_file=blueprint_file,
        reference_file=reference_file if profile_file is not None else None,
        opener=comfy_opener,
    )[0]
    if blueprint_file is not None:
        try:
            blueprint = make_rig_plan(blueprint_file)
            canvas = blueprint["canvas"]
            blueprint_status: dict[str, Any] = {
                "state": "PASS", "canvas": [
                    canvas["width"], canvas["height"]
                ], "character_id": blueprint["character_id"],
            }
        except (OSError, ValueError, KeyError, TypeError):
            blueprint_status = {"state": "BLOCKED"}
    else:
        blueprint_status = {"state": "NOT_PROVIDED"}
    tools = {
        "godot": _tool_info("godot", godot_binary),
        "ffmpeg": _tool_info("ffmpeg", ffmpeg_binary),
    }
    vision = _ollama_info(
        model=ollama_model, connect=connect, opener=ollama_opener,
    )
    disk = _disk_info(output_root, min_free_gb)
    blockers: list[str] = []
    if work["status"] == "BLOCKED":
        blockers.append("COMFY_WORKFLOW_OR_INSTALLED_NODES")
    if reference["state"] != "PASS":
        blockers.append("CANONICAL_REFERENCE")
    if blueprint_status["state"] == "BLOCKED":
        blockers.append("BLUEPRINT")
    for name in ("godot", "ffmpeg"):
        if tools[name]["state"] != "FOUND":
            blockers.append(name.upper() + "_NOT_VERIFIED")
    if vision["state"] in ("MISSING", "UNAVAILABLE"):
        blockers.append("LOCAL_VISION_MODEL_UNAVAILABLE")
    if disk["state"] in ("LOW_FREE_SPACE", "MISSING", "UNAVAILABLE",
                         "BLOCKED_GIT_OUTPUT_ROOT"):
        blockers.append("PRIVATE_OUTPUT_DISK")
    ready = (
        not blockers
        and connect
        and work["status"] == "READY_FOR_TWO_PART_PROBE_NOT_GENERATED"
        and vision["state"] == "FOUND"
        and disk["state"] == "PASS"
        and blueprint_status["state"] == "PASS"
    )
    state = (
        "READY_TO_REQUEST_MANUAL_TWO_PART_PROBE" if ready
        else "BLOCKED" if blockers
        else "NEEDS_LOCAL_PROVISIONING_OR_OWNER_APPROVAL"
    )
    return {
        "schema_version": 1,
        "status": state,
        "operating_system": platform.system(),
        "comfy": work,
        "canonical_reference": reference,
        "blueprint": blueprint_status,
        "installed_tools": tools,
        "local_vision_model": vision,
        "private_output_disk": disk,
        "blockers": sorted(set(blockers)),
        "no_generation_submitted": True,
        "no_image_uploaded": True,
        "no_paid_ai_called": True,
        "full_rig_production_authorized": False,
        "public_release_authorized": False,
        "next_action": (
            "Operator may explicitly run the separate two-part art probe."
            if ready else
            "Resolve the reported local blockers and approved workflow graph; "
            "no automatic generation will start."
        ),
    }
