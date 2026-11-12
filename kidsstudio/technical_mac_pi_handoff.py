"""Mac colors technical QA -> Pi PRIVATE staging, WITHOUT pre-upload human review.

Owner workflow: locally generate and technically verify the MP4; transfer the
exact SHA-bound file to the Pi for a separately authorized PRIVATE upload;
only AFTER YouTube PRIVATE draft exists does the owner watch and accept/revise.

This command never uploads to YouTube and never approves public release.
A sidecar is a local technical assertion, not authenticated source/identity.
Preview is NO SSH by default; --execute-transfer is an explicit physical action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from .mac_pilot_review_shortcut import _validate_bound_pilot
from .mac_to_pi_transfer import transfer_private_video


class TechnicalPrivateHandoffError(ValueError):
    """Pilot technical evidence is missing, mismatched or incomplete."""


def inspect_technical_private_candidate(
    *, video_root: str, evidence_root: str, evidence_name: str,
) -> dict:
    """Read-only inspect one technically verified MP4; NO owner review required."""
    try:
        proof = _validate_bound_pilot(
            video_root=video_root, evidence_root=evidence_root,
            evidence_name=evidence_name)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise TechnicalPrivateHandoffError(
            "Selected local MP4 has no valid private technical proof.") from exc

    # These are exact fields the actual collect_mac_pilot_evidence() writes.
    # Do not qualify an ad hoc SHA-only file or a previously self-declared
    # human-approved/public artifact as a private review-pending pilot.
    if (proof.get("host_role") != "mac-render"
            or proof.get("reported_host_system") != "Darwin"
            or proof.get("host_qualification") != "SUPERVISED_TESTS_READY"
            or proof.get("faststart_moov_before_mdat") is not True
            or proof.get("video_samples_decoded") != 3
            or proof.get("audio_samples_decoded") != 2
            or proof.get("full_video_owner_review_pending") is not True
            or proof.get("arabic_voice_owner_review_pending") is not True
            or proof.get("reviewer_identity_authenticated") is not False
            or proof.get("actual_host_identity_authenticated") is not False
            or type(proof.get("video_bytes")) is not int
            or proof["video_bytes"] <= 0):
        raise TechnicalPrivateHandoffError(
            "Mac technical qualification or review-pending state is incomplete.")
    return {
        "schema_version": 1,
        "status": "MAC_PI_TECHNICAL_QA_VERIFIED_OWNER_REVIEW_PENDING",
        "source_evidence_name": evidence_name,
        "video_name": proof["video_name"],
        "video_sha256": proof["video_sha256"],
        "video_bytes": proof["video_bytes"],
        "source_commit": proof["source_commit"],
        "technical_checks_passed_at_capture": True,
        "current_video_sha_verified": True,
        "owner_full_video_review_pending": True,
        "owner_arabic_voice_review_pending": True,
        "operator_identity_authenticated": False,
        "ssh_connection_performed": False,
        "youtube_upload_submitted": False,
        "publication_approved": False,
    }


def transfer_technical_private_pilot(
    *, video_root: str, evidence_root: str, evidence_name: str,
    pi_host: str, pi_user: str, ssh_port: int = 22,
    remote_python: str = "python3", execute: bool = False,
    timeout_seconds: int = 3600,
    runner: Callable[..., Any] = subprocess.run,
) -> dict:
    """Preview first; explicit execute invokes existing strict SHA-pinned SSH."""
    if type(execute) is not bool:
        raise TechnicalPrivateHandoffError("Explicit boolean execute mode required.")
    proof = inspect_technical_private_candidate(
        video_root=video_root, evidence_root=evidence_root,
        evidence_name=evidence_name)
    # Existing sender checks private file, source SHA and Pi host key; its
    # receiver atomically verifies bytes and creates a private inbox MP4.
    result = transfer_private_video(
        video_root=video_root,
        relative_path=proof["video_name"],
        expected_sha256=proof["video_sha256"],
        destination_name=proof["video_name"],
        pi_host=pi_host, pi_user=pi_user, ssh_port=ssh_port,
        remote_python=remote_python, execute=execute,
        timeout_seconds=timeout_seconds, runner=runner)
    expected = ("MAC_PI_PRIVATE_TRANSFER_VERIFIED" if execute
                else "MAC_PI_TRANSFER_PREVIEW_ONLY")
    if (result.get("status") != expected
            or result.get("sha256") != proof["video_sha256"]
            or result.get("destination_name") != proof["video_name"]
            or result.get("bytes") != proof["video_bytes"]
            or result.get("publication_approved") is not False
            or result.get("youtube_upload_submitted") is not False):
        raise TechnicalPrivateHandoffError(
            "Pi private transfer report does not match Mac technical proof.")
    return {
        **result,
        "status": ("MAC_PI_QA_ONLY_PRIVATE_TRANSFER_VERIFIED" if execute
                   else "MAC_PI_QA_ONLY_TRANSFER_PREVIEW_NO_SSH"),
        "source_evidence_name": evidence_name,
        "owner_review_pending_until_youtube_private_draft": True,
        "local_acceptance_required_before_private_transfer": False,
        "private_transfer_is_not_upload_or_publication_permission": True,
        "publication_approved": False,
        "youtube_upload_submitted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verified Mac colors QA -> Pi PRIVATE staging, no human review required")
    parser.add_argument("--video-root", default=str(
        Path.home() / "kidsstudio-private" / "ready"))
    parser.add_argument("--evidence-root", default=str(
        Path.home() / "kidsstudio-private" / "qualification"))
    parser.add_argument("--evidence-name", required=True)
    parser.add_argument("--pi-host", required=True)
    parser.add_argument("--pi-user", required=True)
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--remote-python", default="python3")
    parser.add_argument("--execute-transfer", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = transfer_technical_private_pilot(
            video_root=args.video_root, evidence_root=args.evidence_root,
            evidence_name=args.evidence_name, pi_host=args.pi_host,
            pi_user=args.pi_user, ssh_port=args.ssh_port,
            remote_python=args.remote_python, execute=args.execute_transfer)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        # For execute=True the outcome may be uncertain AFTER SSH starts.
        # Do not falsely state it never contacted the Pi.
        print(json.dumps({
            "status": "MAC_PI_QA_ONLY_TRANSFER_BLOCKED_OR_UNCERTAIN",
            "ssh_connection_performed": None if args.execute_transfer else False,
            "youtube_upload_submitted": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "MAC_PI_QA_ONLY_PRIVATE_TRANSFER_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
