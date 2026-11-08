"""Explicit owner-reviewed Mac colors pilot -> Pi transfer handoff.

A valid render alone is NOT enough. Only a SHA-bound, private technical
sidecar with at least one matching operator-asserted ACCEPTED_PRIVATE note
and zero matching REVISION_REQUIRED notes can enter the transfer adapter.

Preview is offline by default; the actual transfer remains a separate explicit
--execute-transfer foreground SSH action using the existing strict sender.
This is not identity authentication, YouTube upload or public approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from .mac_pilot_evidence import _private_evidence_dir
from .mac_pilot_review_shortcut import _validate_bound_pilot
from .mac_to_pi_transfer import transfer_private_video
from .optional_tool_evidence import read_private_json

_REVIEW_HEX = re.compile(r"[0-9a-f]{16}\Z")


class MacPiReviewGateError(ValueError):
    """Pilot has no trustworthy, unconflicted local private-acceptance notes."""


def inspect_reviewed_transfer_candidate(
    *, video_root: str, evidence_root: str, evidence_name: str,
) -> dict:
    """Read-only SHA-verified acceptance gate for one exact private MP4."""
    try:
        evidence = _validate_bound_pilot(
            evidence_root=evidence_root,
            evidence_name=evidence_name,
            video_root=video_root)
        root = _private_evidence_dir(evidence_root)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise MacPiReviewGateError("Source technical evidence is missing or invalid.") from exc
    prefix = evidence_name.removesuffix(".json") + ".review."
    inspected = 0
    accepted = 0
    revised = 0
    for entry in root.iterdir():
        name = entry.name
        if not name.startswith(prefix) or not name.endswith(".json"):
            continue
        # Any suspicious review-shaped item fails closed, rather than being
        # silently ignored in favor of an older positive record.
        suffix = name[len(prefix):-len(".json")]
        if not _REVIEW_HEX.fullmatch(suffix):
            raise MacPiReviewGateError("Malformed review record for selected episode.")
        inspected += 1
        if inspected > 256:
            raise MacPiReviewGateError("Too many local review records to qualify.")
        try:
            review = read_private_json(evidence_root, name)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise MacPiReviewGateError("Review note is missing or unsafe.") from exc
        if (review.get("schema_version") != 1
                or review.get("status") != "MAC_PILOT_LOCAL_REVIEW_RECORDED_UNAUTHENTICATED"
                or review.get("source_evidence_name") != evidence_name
                or review.get("episode_id") != evidence["episode_id"]
                or review.get("source_commit") != evidence["source_commit"]
                or review.get("video_sha256") != evidence["video_sha256"]
                or review.get("video_bytes") != evidence["video_bytes"]
                or review.get("review_outcome") not in (
                    "REVISION_REQUIRED", "ACCEPTED_PRIVATE")
                or type(review.get("reported_full_video_reviewed")) is not bool
                or type(review.get("reported_arabic_voice_reviewed")) is not bool
                or review.get("reviewer_identity_authenticated") is not False
                or review.get("local_acceptance_is_upload_permission") is not False
                or review.get("production_approved") is not False
                or review.get("publication_approved") is not False
                or review.get("pi_transfer_performed") is not False
                or review.get("youtube_upload_performed") is not False):
            raise MacPiReviewGateError("Contradictory or mismatched local review.")
        if review["review_outcome"] == "REVISION_REQUIRED":
            revised += 1
        elif (review["reported_full_video_reviewed"] is True
              and review["reported_arabic_voice_reviewed"] is True):
            accepted += 1
        else:
            raise MacPiReviewGateError("Incomplete local private acceptance.")
    if accepted < 1 or revised != 0:
        raise MacPiReviewGateError(
            "Selected video needs private owner acceptance without revision conflict.")
    return {
        "schema_version": 1,
        "status": "MAC_PI_PRIVATE_ACCEPTANCE_PROOF_CHECKED",
        "evidence_name": evidence_name,
        "video_name": evidence["video_name"],
        "video_sha256": evidence["video_sha256"],
        "video_bytes": evidence["video_bytes"],
        "source_commit": evidence["source_commit"],
        "matching_private_acceptances": accepted,
        "conflicting_revision_records": revised,
        "reviewer_identity_authenticated": False,
        "operator_attested_full_video_and_arabic": True,
        "source_media_sha_verified_at_check": True,
        "ssh_connection_performed": False,
        "youtube_upload_submitted": False,
        "publication_approved": False,
    }


def transfer_reviewed_mac_pilot(
    *, video_root: str, evidence_root: str, evidence_name: str,
    pi_host: str, pi_user: str, ssh_port: int = 22,
    remote_python: str = "python3", execute: bool = False,
    timeout_seconds: int = 3600,
    runner: Callable[..., Any] = subprocess.run,
) -> dict:
    """Default offline preview; real SSH only when execute=True is explicit."""
    if type(execute) is not bool:
        raise MacPiReviewGateError("Explicit boolean execution mode required.")
    proof = inspect_reviewed_transfer_candidate(
        video_root=video_root, evidence_root=evidence_root,
        evidence_name=evidence_name)
    transfer = transfer_private_video(
        video_root=video_root,
        relative_path=proof["video_name"],
        expected_sha256=proof["video_sha256"],
        destination_name=proof["video_name"],
        pi_host=pi_host, pi_user=pi_user, ssh_port=ssh_port,
        remote_python=remote_python, execute=execute,
        timeout_seconds=timeout_seconds, runner=runner,
    )
    expected_status = (
        "MAC_PI_PRIVATE_TRANSFER_VERIFIED" if execute else
        "MAC_PI_TRANSFER_PREVIEW_ONLY"
    )
    if (transfer.get("status") != expected_status
            or transfer.get("sha256") != proof["video_sha256"]
            or transfer.get("bytes") != proof["video_bytes"]
            or transfer.get("destination_name") != proof["video_name"]
            or transfer.get("publication_approved") is not False):
        raise MacPiReviewGateError("Private transfer report mismatches approved media.")
    return {
        **transfer,
        "status": ("MAC_PI_REVIEWED_PRIVATE_TRANSFER_VERIFIED" if execute
                   else "MAC_PI_REVIEWED_TRANSFER_PREVIEW_ONLY"),
        "source_evidence_name": evidence_name,
        "review_proof_check_at_start": proof["status"],
        "private_acceptance_is_not_upload_permission": True,
        "owner_identity_authenticated": False,
        "youtube_upload_submitted": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reviewed Mac colors -> Pi private SSH transfer, offline preview default")
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
        result = transfer_reviewed_mac_pilot(
            video_root=args.video_root, evidence_root=args.evidence_root,
            evidence_name=args.evidence_name,
            pi_host=args.pi_host, pi_user=args.pi_user,
            ssh_port=args.ssh_port, remote_python=args.remote_python,
            execute=args.execute_transfer)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        print(json.dumps({
            "status": "MAC_PI_REVIEWED_TRANSFER_BLOCKED_OR_UNCERTAIN",
            # On an attempted real transfer, a failure can happen AFTER
            # sending bytes; never incorrectly claim SSH was not attempted.
            "ssh_connection_performed": None if args.execute_transfer else False,
            "youtube_upload_submitted": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "MAC_PI_REVIEWED_PRIVATE_TRANSFER_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
