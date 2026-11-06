"""Offline comparison of separately collected Mac and Pi qualification reports.

This checks report consistency, not hardware identity or provenance. No network,
filesystem mutations, transfer, uploader or public-release permission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


_COMMON_CHECKS = frozenset({
    "python_3_11_plus",
    "artifact_root_exists",
    "artifact_root_outside_git",
    "artifact_root_not_symlink",
    "artifact_root_no_symlink_components",
    "artifact_root_owned_by_user",
    "artifact_root_private",
    "free_space_threshold",
    "role_matches_os_machine",
})
_DATABASE_CHECKS = frozenset({
    "database_exists",
    "database_outside_git",
    "database_no_symlink_components",
    "database_parent_private",
    "database_parent_owned_by_user",
    "database_regular_file",
    "database_private_permissions",
    "database_owned_by_user",
})
_ALLOWED_MACHINES = {
    "mac-render": ("Darwin", {"arm64", "x86_64"}),
    "pi-private-handoff": ("Linux", {"aarch64", "armv7l", "armv6l"}),
}


def _blockers(report: object, expected_role: str) -> list[str]:
    """Use fixed diagnostic codes: never echo untrusted report contents."""
    if not isinstance(report, dict):
        return ["invalid_report_object"]
    result: list[str] = []
    if type(report.get("schema_version")) is not int or report["schema_version"] != 2:
        result.append("incompatible_schema")
    if report.get("role") != expected_role:
        result.append("incorrect_role")
    system, architectures = _ALLOWED_MACHINES[expected_role]
    machine = report.get("machine")
    if report.get("host_system") != system or not isinstance(machine, str) or machine not in architectures:
        result.append("host_platform_mismatch")
    if report.get("status") != "SUPERVISED_TESTS_READY":
        result.append("offline_readiness_not_passed")
    if report.get("synthetic_review_pipeline") != "OFFLINE_REVIEW_PIPELINE_PASS":
        result.append("synthetic_review_not_passed")
    for field in ("production_approved", "publication_approved"):
        if report.get(field) is not False:
            result.append(field + "_must_be_false")
    for field in ("real_mac_pi_transfer_test", "real_youtube_upload_test"):
        if report.get(field) != "NOT_RUN":
            result.append(field + "_unexpected")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return result + ["missing_checks"]
    required = _COMMON_CHECKS | (
        {"raspberry_pi_model_confirmed"} if expected_role == "pi-private-handoff"
        else set()
    )
    missing = required.difference(checks)
    if missing:
        result.append("required_checks_missing")
    # Database checks are optional in the host command; if any are present,
    # the entire group must be present to avoid partially reported inspections.
    if _DATABASE_CHECKS.intersection(checks) and not _DATABASE_CHECKS.issubset(checks):
        result.append("incomplete_database_checks")
    if not checks or any(type(value) is not bool or not value for value in checks.values()):
        result.append("checks_not_all_true_booleans")
    return result


def compare_host_reports(mac_report: object, pi_report: object) -> dict:
    """Compare unauthenticated report contents without claiming live qualification."""
    mac_issues = _blockers(mac_report, "mac-render")
    pi_issues = _blockers(pi_report, "pi-private-handoff")
    return {
        "schema_version": 1,
        "status": (
            "OFFLINE_REPORT_PAIR_CONSISTENT_UNVERIFIED"
            if not mac_issues and not pi_issues else "OFFLINE_REPORT_PAIR_BLOCKED"
        ),
        "mac_issues": mac_issues,
        "pi_issues": pi_issues,
        "source_reports_authenticated": False,
        "same_code_revision_proven": False,
        "real_mac_pi_transfer_test": "NOT_RUN",
        "real_youtube_upload_test": "NOT_RUN",
        "production_approved": False,
        "publication_approved": False,
    }


def _read_private_report(path: str) -> tuple[object, str]:
    target = Path(os.path.abspath(os.path.expanduser(path)))
    if any(node.is_symlink() for node in (target, *target.parents)):
        raise ValueError("symlink in evidence path")
    if not target.parent.is_dir() or target.parent.stat().st_mode & 0o077:
        raise ValueError("private evidence directory required")
    if any((node / ".git").exists() for node in (target.parent, *target.parents)):
        raise ValueError("evidence must stay outside git")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or (os.name == "posix" and info.st_uid != os.getuid())
                or info.st_size > 65536):
            raise ValueError("unsafe evidence file")
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("evidence file too large")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare private offline Mac/Pi reports")
    parser.add_argument("--mac-report", required=True)
    parser.add_argument("--pi-report", required=True)
    args = parser.parse_args(argv)
    try:
        mac, mac_sha = _read_private_report(args.mac_report)
        pi, pi_sha = _read_private_report(args.pi_report)
        result = compare_host_reports(mac, pi)
        result["mac_report_sha256"] = mac_sha
        result["pi_report_sha256"] = pi_sha
    except (OSError, ValueError, UnicodeError):
        result = {
            "status": "OFFLINE_REPORT_PAIR_ERROR",
            "source_reports_authenticated": False,
            "production_approved": False,
            "publication_approved": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "OFFLINE_REPORT_PAIR_CONSISTENT_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
