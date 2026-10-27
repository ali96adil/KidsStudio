"""Owner-invoked first real bunny production trial: single bounded command.

One approved private config -> local read-only preflight -> exactly TWO ComfyUI
part generations -> alpha/shoulder QA -> one local vision assessment.
No scheduling, retries, paid provider, remote execution, full rig approval
or YouTube publication. Every outcome leaves a private resumable-*report*;
uncertain GPU executions must NEVER be automatically replayed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from .factory import LocalComfyClient
from .mac_doctor import inspect_mac_station
from .part_probe import run_two_part_probe
from .probe_review import review_two_part_probe
from .reviewer import LocalVisionClient, MODEL_RE

CONFIG_KEYS = frozenset({
    "schema_version", "workflow", "profile", "reference", "blueprint",
    "review_model", "comfy_url", "output_root", "timeout_seconds",
    "min_free_gb", "godot_binary", "ffmpeg_binary",
})
REQUIRED = frozenset({
    "schema_version", "workflow", "profile", "reference", "blueprint",
    "review_model", "output_root",
})
MAX_CONFIG_BYTES = 24_000
OUTPUT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,80}$")


class FirstRunError(ValueError):
    """Local owner-only configuration or workspace validation failure."""


def _outside_git(path: Path) -> bool:
    return not any((parent / ".git").exists() for parent in (path, *path.parents))


def load_first_run_config(source: str | Path) -> dict[str, Any]:
    path = Path(source).expanduser().resolve()
    if not path.is_file() or not 1 <= path.stat().st_size <= MAX_CONFIG_BYTES:
        raise FirstRunError("Private first-run config missing or oversized.")
    if not _outside_git(path):
        raise FirstRunError("Private setup configuration must not live in public Git.")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise FirstRunError("Private station config is not valid JSON.") from exc
    if (not isinstance(config, dict) or set(config) - CONFIG_KEYS or
            not REQUIRED.issubset(config) or config.get("schema_version") != 1):
        raise FirstRunError("Unsupported or incomplete owner station config.")
    for key in ("workflow", "profile", "reference", "blueprint", "output_root"):
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise FirstRunError(f"{key} must be an absolute local path.")
    for key in ("workflow", "profile", "reference"):
        if not _outside_git(Path(config[key]).resolve()):
            raise FirstRunError(f"{key} cannot be stored inside public Git.")
    root = Path(config["output_root"]).resolve()
    if not root.is_dir() or not _outside_git(root):
        raise FirstRunError("Private output root must already exist outside Git.")
    model = config["review_model"]
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise FirstRunError("Invalid installed local vision model name.")
    for key, low, high, default in (
        ("timeout_seconds", 30, 3600, 900),
        ("min_free_gb", 1, 100, 10),
    ):
        value = config.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise FirstRunError(f"Invalid {key} budget.")
        config[key] = value
    for key in ("godot_binary", "ffmpeg_binary"):
        if key in config and (
            not isinstance(config[key], str)
            or not Path(config[key]).is_absolute()
        ):
            raise FirstRunError(f"{key} must be an absolute executable path.")
    return config


def _journal(file: Path, result: dict[str, Any]) -> None:
    """Atomic private report update. No raw prompts/art or OS exception text."""
    temporary = file.with_name("first_run_pending.tmp")
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
    finally:
        temporary.unlink(missing_ok=True)


def first_bunny_run(
    config_file: str | Path,
    run_name: str,
    *,
    execute: bool = False,
    doctor: Callable[..., dict[str, Any]] | None = None,
    part_generator: Callable[..., dict[str, Any]] | None = None,
    vision_reviewer: Callable[..., dict[str, Any]] | None = None,
    comfy_client: Any | None = None,
    vision_client: Any | None = None,
) -> dict[str, Any]:
    """Run once. No retries even when generation or network ACK is uncertain."""
    if execute is not True:
        raise FirstRunError("Explicit --execute is required for GPU generation.")
    if not isinstance(run_name, str) or not OUTPUT_NAME.fullmatch(run_name):
        raise FirstRunError("Use a new short versioned run name (letters/digits/_/-).")
    cfg = load_first_run_config(config_file)
    root = Path(cfg["output_root"]).resolve()
    destination = root / run_name
    if destination.exists():
        raise FileExistsError("This qualification version exists; never overwrite/retry.")
    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    report_path = destination / "first_run.json"
    info: dict[str, Any] = {
        "schema_version": 1,
        "status": "PREFLIGHT_IN_PROGRESS",
        "config_sha256": hashlib.sha256(
            Path(config_file).expanduser().resolve().read_bytes()
        ).hexdigest(),
        "run_name": run_name,
        "workflow_approved_for_probe": False,
        "local_gpu_part_budget": 2,
        "parts_planned": ["body", "arm_right"],
        "local_vision_review_attempted": False,
        "full_rig_generation_authorized": False,
        "public_release_authorized": False,
        "owner_visual_signoff_required": True,
    }
    _journal(report_path, info)
    try:
        inspection = (doctor or inspect_mac_station)(
            workflow_file=cfg["workflow"],
            reference_file=cfg["reference"],
            profile_file=cfg["profile"],
            blueprint_file=cfg["blueprint"],
            connect=True, comfy_url=cfg.get("comfy_url", "http://127.0.0.1:8188"),
            ollama_model=cfg["review_model"],
            output_root=cfg["output_root"],
            min_free_gb=cfg["min_free_gb"],
            godot_binary=cfg.get("godot_binary"),
            ffmpeg_binary=cfg.get("ffmpeg_binary"),
        )
        info["station_status"] = inspection["status"]
        info["preflight"] = inspection  # already redacted by Mac Doctor
        if inspection["status"] != "READY_TO_REQUEST_MANUAL_TWO_PART_PROBE":
            info["status"] = "BLOCKED_AT_PREFLIGHT"
            _journal(report_path, info)
            return info

        info["workflow_approved_for_probe"] = True
        info["status"] = "GENERATION_IN_PROGRESS"
        _journal(report_path, info)
        active_comfy = comfy_client if comfy_client is not None else LocalComfyClient(
            base_url=cfg.get("comfy_url", "http://127.0.0.1:8188")
        )
        probe = (part_generator or run_two_part_probe)(
            cfg["blueprint"], cfg["workflow"], cfg["profile"],
            cfg["reference"], destination / "probe",
            client=active_comfy, timeout_seconds=cfg["timeout_seconds"],
        )
        info["probe_status"] = probe["status"]
        if probe["status"] != "PROBE_READY_FOR_VISUAL_INSPECTION":
            info["status"] = "BLOCKED_AT_GEOMETRY"
            _journal(report_path, info)
            return info

        info["status"] = "VISION_REVIEW_IN_PROGRESS"
        info["local_vision_review_attempted"] = True
        _journal(report_path, info)
        active_vision = vision_client if vision_client is not None else LocalVisionClient()
        reviewed = (vision_reviewer or review_two_part_probe)(
            destination / "probe", cfg["reference"],
            model=cfg["review_model"], client=active_vision,
        )
        info["review_status"] = reviewed["status"]
        info["review_verdict"] = reviewed["verdict"]
        info["status"] = {
            "PROBE_PRELIMINARY_ART_PASS": "PRELIMINARY_ART_PASS_NEEDS_OWNER",
            "PROBE_ART_REVISION_REQUIRED": "ART_REVISION_REQUIRED",
            "PROBE_ART_REJECTED": "ART_REJECTED",
        }.get(reviewed["status"], "VISION_RESULT_UNRECOGNIZED")
    except Exception as exc:
        # Never leak internal paths or local-model HTTP errors into archive.
        info["failed_stage"] = info["status"]
        info["status"] = "STOPPED_UNCERTAIN_NO_AUTORETRY"
        info["failure_class"] = type(exc).__name__
    _journal(report_path, info)
    return info
