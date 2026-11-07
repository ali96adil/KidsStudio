"""Offline, read-only comparison of two actual private export files.

Calls the existing SHA + ffprobe gate for both files, then compares technical
metadata. It does not compare frame content, listen to audio, or validate editor
provenance. Nothing is written and no publishing decision is possible.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import subprocess
from typing import Any, Callable

from .filmcraft_export_check import qualify_filmcraft_export
from .optional_tool_evidence import ToolEvidenceError


def compare_filmcraft_baseline(
    *, evidence_root: str, baseline_relative_path: str,
    baseline_sha256: str, candidate_relative_path: str,
    candidate_sha256: str, runner: Callable[..., Any] = subprocess.run,
) -> dict:
    if baseline_relative_path == candidate_relative_path:
        raise ToolEvidenceError("Baseline and candidate paths must differ.")
    baseline = qualify_filmcraft_export(
        evidence_root=evidence_root, relative_path=baseline_relative_path,
        expected_sha256=baseline_sha256, runner=runner)
    candidate = qualify_filmcraft_export(
        evidence_root=evidence_root, relative_path=candidate_relative_path,
        expected_sha256=candidate_sha256, runner=runner)
    base = baseline["technical_profile"]
    other = candidate["technical_profile"]
    profiles_ok = base is not None and other is not None
    fps_equal = (
        profiles_ok and
        Fraction(base["fps_numerator"], base["fps_denominator"])
        == Fraction(other["fps_numerator"], other["fps_denominator"])
    )
    duration_delta = (
        round(abs(base["duration_seconds"] - other["duration_seconds"]), 6)
        if profiles_ok else None)
    checks = {
        "both_independently_technically_pass": bool(profiles_ok),
        "different_content_sha256": baseline["file_sha256"] != candidate["file_sha256"],
        "same_frame_rate": bool(fps_equal),
        "duration_delta_at_most_0_10_seconds": (
            duration_delta is not None and duration_delta <= 0.10),
    }
    return {
        "schema_version": 1,
        "status": (
            "FILMCRAFT_BASELINE_TECHNICALLY_COMPARABLE_UNREVIEWED"
            if all(checks.values()) else "FILMCRAFT_BASELINE_COMPARISON_BLOCKED"
        ),
        "checks": checks,
        "duration_delta_seconds": duration_delta,
        "baseline_bytes": baseline["file_bytes"],
        "candidate_bytes": candidate["file_bytes"],
        "candidate_to_baseline_bytes_ratio": round(
            candidate["file_bytes"] / baseline["file_bytes"], 5
        ) if baseline["file_bytes"] else None,
        "baseline_sha256": baseline["file_sha256"],
        "candidate_sha256": candidate["file_sha256"],
        "exact_frame_content_compared": False,
        "audio_perceptual_quality_compared": False,
        "arabic_captions_compared": False,
        "same_underlying_episode_verified": False,
        "godot_origin_authenticated": False,
        "filmcraft_origin_authenticated": False,
        "local_files_checked_at_report_time": True,
        "real_mac_filmcraft_run": "NOT_RUN",
        "media_files_mutated": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only FilmCraft vs Godot final-delivery technical comparison")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--baseline-relative-path", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--candidate-relative-path", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        report = compare_filmcraft_baseline(
            evidence_root=args.evidence_root,
            baseline_relative_path=args.baseline_relative_path,
            baseline_sha256=args.baseline_sha256,
            candidate_relative_path=args.candidate_relative_path,
            candidate_sha256=args.candidate_sha256,
        )
    except (ToolEvidenceError, ValueError, OSError, TypeError, KeyError, ZeroDivisionError):
        print(json.dumps({"status": "FILMCRAFT_BASELINE_COMPARISON_ERROR",
                          "media_files_mutated": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "FILMCRAFT_BASELINE_TECHNICALLY_COMPARABLE_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
