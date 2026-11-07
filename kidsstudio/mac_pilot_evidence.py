"""Mac colors pilot: immutable, private technical evidence and owner review notes.

Local-only explicit CLI. The collect step proves technical tests were invoked
against SHA-pinned local bytes; it does not attest host or reviewer identity.
The separate review step records operator assertions (never public approval).
No video transport, OAuth, queue, YouTube, external network or automation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat

from .host_qualification import qualify_host
from .mp4_playback_preflight import inspect_mp4_playback
from .optional_tool_evidence import private_evidence_file, read_private_json
from .transfer_verify import verify_staged_file

_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
_JSON_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.json\Z")
_MP4_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.mp4\Z")
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_REPORT = 64 * 1024


class MacPilotEvidenceError(ValueError):
    """A required private technical or review-evidence gate was not met."""


def _private_evidence_dir(root: str) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(str(root))))
    if (not path.is_dir()
            or any(part.is_symlink() for part in (path, *path.parents))
            or any((part / ".git").exists() for part in (path, *path.parents))):
        raise MacPilotEvidenceError("Private evidence directory outside Git required.")
    info = path.stat()
    if info.st_mode & 0o077 or (os.name == "posix" and info.st_uid != os.getuid()):
        raise MacPilotEvidenceError("Evidence directory must be private and owned.")
    return path


def _write_new_evidence(root: str, name: str, obj: dict) -> None:
    if not isinstance(name, str) or not _JSON_NAME.fullmatch(name):
        raise MacPilotEvidenceError("Invalid evidence file name.")
    parent = _private_evidence_dir(root)
    payload = (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
    if not 0 < len(payload) <= _MAX_REPORT:
        raise MacPilotEvidenceError("Evidence file is too large.")
    target = parent / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        dirfd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _video_inputs(video_name: str, expected_sha256: str) -> None:
    if (not isinstance(video_name, str) or not _MP4_NAME.fullmatch(video_name)
            or not isinstance(expected_sha256, str)
            or not _SHA.fullmatch(expected_sha256)):
        raise MacPilotEvidenceError("Exact private MP4 name and SHA256 required.")


def collect_mac_pilot_evidence(
    *, episode_id: str, video_root: str, video_name: str,
    expected_sha256: str, evidence_root: str, evidence_name: str,
    min_free_gib: float = 2.0,
) -> dict:
    """Write one non-replaceable sidecar after actual local video/host checks."""
    if not isinstance(episode_id, str) or not _EPISODE.fullmatch(episode_id):
        raise MacPilotEvidenceError("Invalid episode id.")
    _video_inputs(video_name, expected_sha256)
    _private_evidence_dir(evidence_root)
    if platform.system() != "Darwin":
        raise MacPilotEvidenceError("This collection step must run on macOS.")
    # Must be independent of the shell runner's prior printed results.
    host = qualify_host(
        role="mac-render", artifact_root=video_root,
        min_free_gib=min_free_gib,
    )
    revision = host.get("source_commit")
    if (host.get("status") != "SUPERVISED_TESTS_READY"
            or host.get("host_system") != "Darwin"
            or host.get("source_checkout_clean") is not True
            or not isinstance(revision, str) or not _COMMIT.fullmatch(revision)):
        raise MacPilotEvidenceError("Clean pinned Mac checkout and readiness required.")
    playback = inspect_mp4_playback(
        root=video_root, relative_path=video_name,
        expected_sha256=expected_sha256)
    if playback.get("status") != "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED":
        raise MacPilotEvidenceError("MP4 preflight did not pass.")
    digest = expected_sha256.lower()
    report = {
        "schema_version": 1,
        "status": "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
        "episode_id": episode_id,
        "video_name": video_name,
        "video_sha256": digest,
        "video_bytes": playback["video_bytes"],
        "duration_seconds": playback["duration_seconds"],
        "technical_preflight": playback["status"],
        "faststart_moov_before_mdat": playback["faststart_moov_before_mdat"],
        "video_samples_decoded": playback["video_samples_decoded"],
        "audio_samples_decoded": playback["audio_samples_decoded"],
        "host_role": "mac-render",
        "reported_host_system": "Darwin",
        "source_commit": revision,
        "source_checkout_clean": True,
        "host_qualification": host["status"],
        "synthetic_review_pipeline": host["synthetic_review_pipeline"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_host_identity_authenticated": False,
        "reviewer_identity_authenticated": False,
        "full_video_owner_review_pending": True,
        "arabic_voice_owner_review_pending": True,
        "real_mac_pi_transfer_test": "NOT_RUN",
        "real_youtube_upload_test": "NOT_RUN",
        "production_approved": False,
        "publication_approved": False,
    }
    _write_new_evidence(evidence_root, evidence_name, report)
    return {
        "status": report["status"],
        "evidence_name": evidence_name,
        "source_commit": revision,
        "video_sha256": digest,
        "owner_review_pending": True,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def record_mac_pilot_review(
    *, evidence_root: str, evidence_name: str, video_root: str,
    video_name: str, expected_sha256: str, review_outcome: str,
    reviewer_notes: str = "", reviewed_full_video: bool = False,
    reviewed_arabic_voice: bool = False,
) -> dict:
    """Append one operator-asserted private review file; never change pilot proof."""
    _video_inputs(video_name, expected_sha256)
    if not isinstance(evidence_name, str) or not _JSON_NAME.fullmatch(evidence_name):
        raise MacPilotEvidenceError("Invalid evidence file name.")
    if (review_outcome not in ("REVISION_REQUIRED", "ACCEPTED_PRIVATE")
            or not isinstance(reviewer_notes, str) or len(reviewer_notes) > 2000
            or type(reviewed_full_video) is not bool
            or type(reviewed_arabic_voice) is not bool):
        raise MacPilotEvidenceError("Invalid explicit review outcome or notes.")
    if (review_outcome == "ACCEPTED_PRIVATE"
            and (not reviewed_full_video or not reviewed_arabic_voice)):
        raise MacPilotEvidenceError("Full video and voice checks required for acceptance.")
    _private_evidence_dir(evidence_root)
    evidence = read_private_json(evidence_root, evidence_name)
    digest = expected_sha256.lower()
    if (evidence.get("schema_version") != 1
            or evidence.get("status") != "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING"
            or evidence.get("video_name") != video_name
            or evidence.get("video_sha256") != digest
            or evidence.get("source_checkout_clean") is not True
            or evidence.get("technical_preflight") != "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED"
            or evidence.get("publication_approved") is not False
            or not isinstance(evidence.get("source_commit"), str)
            or not _COMMIT.fullmatch(evidence["source_commit"])
            or not isinstance(evidence.get("episode_id"), str)
            or not _EPISODE.fullmatch(evidence["episode_id"])):
        raise MacPilotEvidenceError("Source pilot evidence invalid or mismatched.")
    # Recheck the actual file under a private path, never trust only metadata.
    private_evidence_file(video_root, video_name, max_bytes=20 * 1024**3)
    checked = verify_staged_file(
        root=video_root, relative_path=video_name,
        expected_sha256=expected_sha256)
    if (checked["status"] != "VERIFIED"
            or checked["bytes"] != evidence.get("video_bytes")):
        raise MacPilotEvidenceError("Video changed since qualification.")
    name = evidence_name.removesuffix(".json") + ".review." + secrets.token_hex(8) + ".json"
    report = {
        "schema_version": 1,
        "status": "MAC_PILOT_LOCAL_REVIEW_RECORDED_UNAUTHENTICATED",
        "source_evidence_name": evidence_name,
        "episode_id": evidence["episode_id"],
        "source_commit": evidence["source_commit"],
        "video_sha256": digest,
        "video_bytes": checked["bytes"],
        "review_outcome": review_outcome,
        "reviewer_notes": reviewer_notes,
        "reported_full_video_reviewed": reviewed_full_video,
        "reported_arabic_voice_reviewed": reviewed_arabic_voice,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_identity_authenticated": False,
        "local_acceptance_is_upload_permission": False,
        "production_approved": False,
        "publication_approved": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
    }
    _write_new_evidence(evidence_root, name, report)
    return {
        "status": report["status"],
        "review_evidence_name": name,
        "review_outcome": review_outcome,
        "video_sha256": digest,
        "reviewer_identity_authenticated": False,
        "publication_approved": False,
        "youtube_upload_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Mac pilot evidence and explicit private review notes")
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--episode-id", required=True)
    collect.add_argument("--min-free-gib", type=float, default=2.0)
    review = sub.add_parser("review")
    review.add_argument("--review-outcome", required=True,
                        choices=["REVISION_REQUIRED", "ACCEPTED_PRIVATE"])
    review.add_argument("--reviewer-notes", default="")
    review.add_argument("--reviewed-full-video", action="store_true")
    review.add_argument("--reviewed-arabic-voice", action="store_true")
    for command in (collect, review):
        command.add_argument("--video-root", required=True)
        command.add_argument("--video-name", required=True)
        command.add_argument("--expected-sha256", required=True)
        command.add_argument("--evidence-root", required=True)
        command.add_argument("--evidence-name", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "collect":
            report = collect_mac_pilot_evidence(
                episode_id=args.episode_id,
                min_free_gib=args.min_free_gib,
                video_root=args.video_root,
                video_name=args.video_name,
                expected_sha256=args.expected_sha256,
                evidence_root=args.evidence_root,
                evidence_name=args.evidence_name)
        else:
            report = record_mac_pilot_review(
                evidence_root=args.evidence_root,
                evidence_name=args.evidence_name,
                video_root=args.video_root,
                video_name=args.video_name,
                expected_sha256=args.expected_sha256,
                review_outcome=args.review_outcome,
                reviewer_notes=args.reviewer_notes,
                reviewed_full_video=args.reviewed_full_video,
                reviewed_arabic_voice=args.reviewed_arabic_voice)
    except (ValueError, OSError, TypeError, KeyError):
        print(json.dumps({
            "status": "MAC_PILOT_EVIDENCE_BLOCKED",
            "publication_approved": False,
            "youtube_upload_performed": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
