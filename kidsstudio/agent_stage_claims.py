"""Local cooperative stage ownership with expiring leases.

No remote execution, stage mutation, YouTube upload or public publishing.
Claims are advisory: workers must call claim_stage before doing stage work.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .episode_stage_checkpoints import _path, status
from .openmontage_pipeline_bridge import PIPELINES

AGENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
MAX_LEASE_SECONDS = 3600


def _claim_path(root: str | Path, episode_id: str) -> Path:
    return _path(root, episode_id).with_suffix(".claims.json")


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("symlink claim file rejected")
    if not path.exists():
        return {}
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        if os.fstat(handle.fileno()).st_size > 1024 * 1024:
            raise ValueError("oversized claim file")
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("invalid claims")
    return value


def _save(path: Path, value: dict) -> None:
    fd, temp = tempfile.mkstemp(prefix=".claim-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise ValueError("symlink claim file rejected")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _with_lock(root: str | Path, episode_id: str, callback):
    path = _claim_path(root, episode_id)
    lock = path.with_name(path.name + ".lock")
    if lock.is_symlink():
        raise ValueError("symlink claim lock rejected")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return callback(path)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def claim_stage(root: str | Path, episode_id: str, stage: str, agent_id: str,
                lease_seconds: int = 900) -> dict:
    if not isinstance(agent_id, str) or not AGENT_RE.fullmatch(agent_id):
        raise ValueError("invalid agent_id")
    if type(lease_seconds) is not int or not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
        raise ValueError("invalid lease duration")

    def update(path):
        checkpoint = status(root, episode_id)
        stages = checkpoint["stages"]
        if stage not in stages:
            raise ValueError("unknown stage")
        order = PIPELINES[checkpoint["pipeline"]]["stages"]
        if stages[stage] == "passed" or any(stages[s] != "passed" for s in order[:order.index(stage)]):
            raise ValueError("stage not ready")
        claims = _read(path)
        now = datetime.now(timezone.utc)
        existing = claims.get(stage)
        if existing is not None:
            if not isinstance(existing, dict):
                raise ValueError("invalid existing claim")
            try:
                expiry = datetime.fromisoformat(existing["expires_at"])
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("invalid claim expiry") from exc
            if expiry.tzinfo is None:
                raise ValueError("naive claim expiry")
            if expiry > now:
                raise ValueError("stage already claimed")
        claim = {"agent_id": agent_id, "expires_at": (now + timedelta(seconds=lease_seconds)).isoformat(), "fencing_token": secrets.token_hex(16)}
        claims[stage] = claim
        _save(path, claims)
        return {"episode_id": episode_id, "stage": stage, **claim,
                "youtube_uploaded": False, "public_release_authorized": False}
    return _with_lock(root, episode_id, update)


def release_stage(root: str | Path, episode_id: str, stage: str, agent_id: str) -> bool:
    if not isinstance(agent_id, str) or not AGENT_RE.fullmatch(agent_id):
        raise ValueError("invalid agent_id")
    def update(path):
        status(root, episode_id)
        claims = _read(path)
        existing = claims.get(stage)
        if not isinstance(existing, dict) or existing.get("agent_id") != agent_id:
            raise ValueError("stage not claimed by agent")
        del claims[stage]
        _save(path, claims)
        return True
    return _with_lock(root, episode_id, update)


def read_claims(root: str | Path, episode_id: str) -> dict:
    checkpoint = status(root, episode_id)
    claims = _read(_claim_path(root, episode_id))
    if any(stage not in checkpoint["stages"] for stage in claims):
        raise ValueError("unknown claimed stage")
    return {"episode_id": episode_id, "claims": claims, "read_only": True,
            "youtube_uploaded": False, "public_release_authorized": False}


def validate_claim(root: str | Path, episode_id: str, stage: str,
                   agent_id: str, fencing_token: str) -> bool:
    """Verify a worker still owns an unexpired lease before accepting outputs."""
    if not isinstance(agent_id, str) or not AGENT_RE.fullmatch(agent_id):
        raise ValueError("invalid agent_id")
    if not isinstance(fencing_token, str) or not re.fullmatch(r"[0-9a-f]{32}", fencing_token):
        raise ValueError("invalid fencing token")
    def check(path):
        checkpoint = status(root, episode_id)
        if stage not in checkpoint["stages"] or checkpoint["stages"][stage] == "passed":
            raise ValueError("stage not active")
        claim = _read(path).get(stage)
        if not isinstance(claim, dict):
            raise ValueError("stage not claimed")
        if claim.get("agent_id") != agent_id or claim.get("fencing_token") != fencing_token:
            raise ValueError("stale or foreign stage claim")
        try:
            expires = datetime.fromisoformat(claim["expires_at"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("invalid claim expiry") from exc
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise ValueError("expired stage claim")
        return True
    return _with_lock(root, episode_id, check)


def renew_claim(root: str | Path, episode_id: str, stage: str, agent_id: str,
                fencing_token: str, lease_seconds: int = 900) -> dict:
    """Extend a valid claim; never resurrect an expired or superseded lease."""
    if type(lease_seconds) is not int or not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
        raise ValueError("invalid lease duration")
    def update(path):
        checkpoint = status(root, episode_id)
        if stage not in checkpoint["stages"] or checkpoint["stages"][stage] == "passed":
            raise ValueError("stage not active")
        claims = _read(path)
        claim = claims.get(stage)
        if not isinstance(claim, dict) or claim.get("agent_id") != agent_id or claim.get("fencing_token") != fencing_token:
            raise ValueError("stale or foreign stage claim")
        try:
            expires = datetime.fromisoformat(claim["expires_at"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("invalid claim expiry") from exc
        now = datetime.now(timezone.utc)
        if expires.tzinfo is None or expires <= now:
            raise ValueError("expired stage claim")
        claim["expires_at"] = (now + timedelta(seconds=lease_seconds)).isoformat()
        _save(path, claims)
        return {"episode_id": episode_id, "stage": stage, **claim}
    return _with_lock(root, episode_id, update)
