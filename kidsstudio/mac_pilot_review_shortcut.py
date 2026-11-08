"""Local-only helper for exact Mac pilot evidence lookup and SHA-bound review.

No implicit approval: the operator selects an exact evidence filename and
explicit review outcome. All video/commit digests come from the validated
private technical sidecar, never from manually retyped SHA strings.
No socket, SSH, upload, YouTube, publication, or background processing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .mac_pilot_evidence import record_mac_pilot_review, _private_evidence_dir
from .optional_tool_evidence import read_private_json, private_evidence_file
from .transfer_verify import verify_staged_file

_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}\Z")
_EVIDENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.evidence\.json\Z")
_VIDEO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.mp4\Z")
_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


class MacPilotShortcutError(ValueError):
    """Pilot sidecar, video or review selection is invalid."""


def _validate_bound_pilot(*, evidence_root: str, evidence_name: str,
                          video_root: str) -> dict:
    """Validate exact immutable-style sidecar and current private MP4 bytes."""
    if not isinstance(evidence_name, str) or not _EVIDENCE.fullmatch(evidence_name):
        raise MacPilotShortcutError("Exact pilot evidence filename required.")
    _private_evidence_dir(evidence_root)
    item = read_private_json(evidence_root, evidence_name)
    name = item.get("video_name")
    digest = item.get("video_sha256")
    if (item.get("schema_version") != 1
            or item.get("status") != "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING"
            or item.get("episode_id") != "colors_ar_01"
            or not isinstance(name, str) or not _VIDEO.fullmatch(name)
            or not isinstance(digest, str) or not _SHA.fullmatch(digest)
            or item.get("source_checkout_clean") is not True
            or not isinstance(item.get("source_commit"), str)
            or not _COMMIT.fullmatch(item["source_commit"])
            or item.get("technical_preflight") != "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED"
            or item.get("publication_approved") is not False
            or item.get("production_approved") is not False
            or item.get("real_mac_pi_transfer_test") != "NOT_RUN"
            or item.get("real_youtube_upload_test") != "NOT_RUN"):
        raise MacPilotShortcutError("Technical evidence failed validation.")
    # The collector's naming is deterministic. Do not allow an arbitrary
    # sidecar to be re-labelled as a different output filename.
    if evidence_name != name.removesuffix(".mp4") + ".evidence.json":
        raise MacPilotShortcutError("Evidence and video filenames disagree.")
    private_evidence_file(video_root, name, max_bytes=20 * 1024**3)
    verified = verify_staged_file(
        root=video_root, relative_path=name, expected_sha256=digest)
    if (verified["status"] != "VERIFIED"
            or verified["bytes"] != item.get("video_bytes")):
        raise MacPilotShortcutError("The private MP4 changed after evidence capture.")
    return item


def list_mac_pilot_evidence(*, video_root: str, evidence_root: str,
                            limit: int = 10) -> dict:
    """List only SHA-verified original pilot files; do not list arbitrary JSON."""
    if type(limit) is not int or not 1 <= limit <= 20:
        raise MacPilotShortcutError("Limit must be 1–20.")
    root = _private_evidence_dir(evidence_root)
    candidates = []
    for entry in root.iterdir():
        # Avoid following links, even if a malicious file has the right name.
        if not entry.is_symlink() and entry.is_file() and _EVIDENCE.fullmatch(entry.name):
            candidates.append(entry)
    candidates.sort(key=lambda entry: (entry.stat().st_mtime_ns, entry.name),
                    reverse=True)
    found = []
    for candidate in candidates:
        try:
            item = _validate_bound_pilot(
                evidence_root=evidence_root, evidence_name=candidate.name,
                video_root=video_root)
        except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
            # An invalid sidecar must not appear selectable as a valid pilot.
            continue
        found.append({
            "evidence_name": candidate.name,
            "video_name": item["video_name"],
            "episode_id": item["episode_id"],
            "video_sha256": item["video_sha256"],
            "source_commit": item["source_commit"],
            "video_bytes": item["video_bytes"],
            "duration_seconds": item["duration_seconds"],
            "technical_evidence_verified": True,
            "owner_review_recorded_by_this_command": False,
        })
        if len(found) >= limit:
            break
    return {
        "schema_version": 1,
        "status": "MAC_PILOT_REVIEW_CHOICES_READ_ONLY",
        "pilots": found,
        "publication_approved": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
    }


def record_mac_pilot_review_shortcut(
    *, video_root: str, evidence_root: str, evidence_name: str,
    review_outcome: str, reviewer_notes: str = "",
    reviewed_full_video: bool = False,
    reviewed_arabic_voice: bool = False,
) -> dict:
    """Write a distinct review note; never select a video by timestamp/latest."""
    if review_outcome not in ("REVISION_REQUIRED", "ACCEPTED_PRIVATE"):
        raise MacPilotShortcutError("Explicit local review decision required.")
    item = _validate_bound_pilot(
        evidence_root=evidence_root, evidence_name=evidence_name,
        video_root=video_root)
    # Underlying implementation does all gating again, then re-hashes MP4.
    return record_mac_pilot_review(
        evidence_root=evidence_root,
        evidence_name=evidence_name,
        video_root=video_root,
        video_name=item["video_name"],
        expected_sha256=item["video_sha256"],
        review_outcome=review_outcome,
        reviewer_notes=reviewer_notes,
        reviewed_full_video=reviewed_full_video,
        reviewed_arabic_voice=reviewed_arabic_voice,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Mac colors pilot review without manually copying SHA256")
    sub = parser.add_subparsers(dest="action", required=True)
    listing = sub.add_parser("list", help="Show up to 10 valid local pilots; no writes")
    listing.add_argument("--limit", type=int, default=10)
    record = sub.add_parser("record", help="Explicit review of one evidence filename")
    record.add_argument("--evidence-name", required=True)
    record.add_argument("--review-outcome", required=True,
                        choices=["REVISION_REQUIRED", "ACCEPTED_PRIVATE"])
    record.add_argument("--reviewer-notes", default="")
    record.add_argument("--reviewed-full-video", action="store_true")
    record.add_argument("--reviewed-arabic-voice", action="store_true")
    for selected in (listing, record):
        selected.add_argument("--video-root", default=str(
            Path.home() / "kidsstudio-private" / "ready"))
        selected.add_argument("--evidence-root", default=str(
            Path.home() / "kidsstudio-private" / "qualification"))
    args = parser.parse_args(argv)
    try:
        if args.action == "list":
            result = list_mac_pilot_evidence(
                video_root=args.video_root,
                evidence_root=args.evidence_root,
                limit=args.limit)
        else:
            result = record_mac_pilot_review_shortcut(
                video_root=args.video_root,
                evidence_root=args.evidence_root,
                evidence_name=args.evidence_name,
                review_outcome=args.review_outcome,
                reviewer_notes=args.reviewer_notes,
                reviewed_full_video=args.reviewed_full_video,
                reviewed_arabic_voice=args.reviewed_arabic_voice)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        print(json.dumps({
            "status": "MAC_PILOT_REVIEW_SHORTCUT_BLOCKED",
            "publication_approved": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
