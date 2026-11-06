"""Read-only host role qualification combining readiness and synthetic pipeline.

Produces no host-specific credentials or network activity.
"""
from __future__ import annotations

import argparse
import json

from .host_readiness import inspect_host
from .review_pipeline_qualification import run_review_pipeline_qualification

_ROLES = {"mac-render", "pi-private-handoff"}


def qualify_host(*, role: str, artifact_root: str,
                 database: str | None = None, min_free_gib: float = 2.0) -> dict:
    if role not in _ROLES:
        raise ValueError("invalid host role")
    readiness = inspect_host(
        artifact_root=artifact_root, database=database,
        min_free_gib=min_free_gib)
    synthetic = run_review_pipeline_qualification()
    return {
        "schema_version": 1,
        "status": ("SUPERVISED_TESTS_READY" if
                   readiness["ready_for_supervised_tests"] and
                   synthetic["status"] == "OFFLINE_REVIEW_PIPELINE_PASS"
                   else "SUPERVISED_TESTS_BLOCKED"),
        "role": role,
        "host_system": readiness["host_system"],
        "machine": readiness["machine"],
        "checks": readiness["checks"],
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
    except (ValueError, OSError):
        result = {"status": "QUALIFICATION_ERROR",
                  "production_approved": False,
                  "publication_approved": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "SUPERVISED_TESTS_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
