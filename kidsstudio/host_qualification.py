"""Read-only host role qualification combining readiness and synthetic pipeline.

No production actions, external network calls, or host credential reads.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from .host_readiness import inspect_host
from .review_pipeline_qualification import run_review_pipeline_qualification

_ROLES = {"mac-render", "pi-private-handoff"}


def _raspberry_pi_model_present() -> bool:
    """A Linux ARM machine alone is not proof of Raspberry Pi hardware."""
    try:
        model = Path("/proc/device-tree/model").read_bytes()[:256]
    except OSError:
        return False
    return b"raspberry pi" in model.lower()


def _source_checkout() -> tuple[str | None, bool]:
    """Read checkout revision, without network access or branch mutations."""
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        return None, False
    try:
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            capture_output=True, text=True, check=False, timeout=5)
        # Inspect the ENTIRE checkout, including scripts, docs, workflows
        # and untracked (non-ignored) files. Never print local filenames.
        # This is a consistency signal, not host or build attestation.
        changes = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1",
             "--untracked-files=all"],
            capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    revision = sha.stdout.strip()
    if (sha.returncode != 0 or
            not re.fullmatch(r"[a-fA-F0-9]{40}", revision)):
        return None, False
    return revision.lower(), (
        changes.returncode == 0 and not changes.stdout.strip())


def qualify_host(*, role: str, artifact_root: str,
                 database: str | None = None, min_free_gib: float = 2.0) -> dict:
    if role not in _ROLES:
        raise ValueError("invalid host role")
    readiness = inspect_host(
        artifact_root=artifact_root, database=database,
        min_free_gib=min_free_gib)
    system = readiness["host_system"]
    machine = readiness["machine"].lower()
    checks = dict(readiness["checks"])
    if role == "mac-render":
        checks["role_matches_os_machine"] = (
            system == "Darwin" and machine in {"arm64", "x86_64"})
    else:
        checks["role_matches_os_machine"] = (
            system == "Linux" and machine in {"aarch64", "armv7l", "armv6l"})
        checks["raspberry_pi_model_confirmed"] = (
            checks["role_matches_os_machine"] and _raspberry_pi_model_present())
    synthetic = run_review_pipeline_qualification()
    revision, clean = _source_checkout()
    ready = (
        readiness["ready_for_supervised_tests"]
        and all(checks.values())
        and synthetic["status"] == "OFFLINE_REVIEW_PIPELINE_PASS"
    )
    return {
        "schema_version": 3,
        "status": "SUPERVISED_TESTS_READY" if ready else "SUPERVISED_TESTS_BLOCKED",
        "role": role,
        "host_system": system,
        "machine": readiness["machine"],
        "source_commit": revision,
        "source_checkout_clean": clean,
        "checks": checks,
        "synthetic_review_pipeline": synthetic["status"],
        "real_mac_pi_transfer_test": "NOT_RUN",
        "real_youtube_upload_test": "NOT_RUN",
        "production_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline KidsStudio Mac/Pi host qualification")
    parser.add_argument("--role", choices=sorted(_ROLES), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--db")
    parser.add_argument("--min-free-gib", type=float, default=2.0)
    args = parser.parse_args(argv)
    try:
        result = qualify_host(
            role=args.role, artifact_root=args.artifact_root,
            database=args.db, min_free_gib=args.min_free_gib)
    except (ValueError, OSError, AssertionError):
        result = {"status": "QUALIFICATION_ERROR",
                  "production_approved": False,
                  "publication_approved": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "SUPERVISED_TESTS_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
