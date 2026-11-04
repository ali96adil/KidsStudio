"""Durable private stage checkpoints for KidsStudio episode pipelines.

No render, network, queue or publishing. Uses atomic replace and rejects symlinks.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .openmontage_pipeline_bridge import PIPELINES

EPISODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
STATES = {"pending", "running", "passed", "failed"}
MAX_BYTES = 1024 * 1024


def _path(root: str | Path, episode_id: str) -> Path:
    if not isinstance(episode_id, str) or not EPISODE_RE.fullmatch(episode_id):
        raise ValueError("unsafe episode_id")
    return Path(root) / (episode_id + ".checkpoints.json")


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("symlink checkpoint rejected")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if os.fstat(fd).st_size > MAX_BYTES:
            raise ValueError("checkpoint too large")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    if not isinstance(data, dict) or data.get("pipeline") not in PIPELINES:
        raise ValueError("invalid checkpoint")
    expected = PIPELINES[data["pipeline"]]["stages"]
    if data.get("stages") != {stage: "pending" for stage in expected} and (
            not isinstance(data.get("stages"), dict)
            or list(data["stages"]) != expected
            or any(state not in STATES for state in data["stages"].values())):
        raise ValueError("invalid stage states")
    return data


def initialize(root: str | Path, episode_id: str, pipeline: str) -> dict:
    if pipeline not in PIPELINES:
        raise ValueError("unknown pipeline")
    path = _path(root, episode_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError("checkpoint already exists")
    data = {"schema_version": 1, "episode_id": episode_id,
            "pipeline": pipeline,
            "stages": {stage: "pending" for stage in PIPELINES[pipeline]["stages"]},
            "youtube_uploaded": False, "public_release_authorized": False}
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())
    return data


def status(root: str | Path, episode_id: str) -> dict:
    data = _read(_path(root, episode_id))
    if data.get("episode_id") != episode_id or data.get("schema_version") != 1:
        raise ValueError("checkpoint identity mismatch")
    if data.get("youtube_uploaded") is not False or data.get("public_release_authorized") is not False:
        raise ValueError("unsafe checkpoint flags")
    stages = data["stages"]
    remaining = [stage for stage, state in stages.items() if state != "passed"]
    return {**data, "next_stage": remaining[0] if remaining else None,
            "completed": not remaining, "read_only": True}


def transition(root: str | Path, episode_id: str, stage: str, new_state: str) -> dict:
    if new_state not in {"running", "passed", "failed"}:
        raise ValueError("unsupported transition")
    path = _path(root, episode_id)
    data = status(root, episode_id)
    stages = data["stages"]
    if stage not in stages:
        raise ValueError("unknown stage")
    order = list(stages)
    if any(stages[previous] != "passed" for previous in order[:order.index(stage)]):
        raise ValueError("previous stage not passed")
    current = stages[stage]
    allowed = {"pending": {"running"}, "running": {"passed", "failed"},
               "failed": {"running"}, "passed": set()}
    if new_state not in allowed[current]:
        raise ValueError("invalid stage transition")
    stages[stage] = new_state
    data.pop("next_stage", None)
    data.pop("completed", None)
    data.pop("read_only", None)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("checkpoint too large")
    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        # Caller must serialize concurrent writers; do not use for multi-writer deployments.
        if path.is_symlink():
            raise ValueError("symlink checkpoint rejected")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return status(root, episode_id)
