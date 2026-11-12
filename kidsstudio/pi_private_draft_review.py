"""Offline review note for an existing YouTube PRIVATE draft.

Intended sequence: Mac render/technical QA -> Pi SHA transfer -> separate
owner-authorized PRIVATE upload -> owner watches the PRIVATE YouTube draft ->
explicit accept-private or revision note, bound to the Pi bytes and journal.

The local journal is historical, unauthenticated evidence. We DO NOT re-check
current Google privacy or identify the reviewer. No OAuth, HTTP, SSH, uploads,
YouTube publish/change requests, background tasks or source-file deletion.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets

from .optional_tool_evidence import private_evidence_file, read_private_json
from .pi_youtube_private_upload import _load_journal, _private_journal_path
from .transfer_verify import verify_staged_file

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{8,32}\Z")
_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
_MP4_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.mp4\Z")
_INTERNAL_CANDIDATE = "verified-candidate.mp4"
_NOTE_SUFFIX = re.compile(r"[0-9a-f]{16}\.json\Z")


class PrivateDraftReviewError(ValueError):
    """Private uploaded-video evidence or explicit review input is invalid."""


def _private_review_root(path: str) -> Path:
    root = Path(os.path.abspath(os.path.expanduser(path)))
    if (not root.is_dir()
            or any(p.is_symlink() or (p / ".git").exists()
                   for p in (root, *root.parents))):
        raise PrivateDraftReviewError(
            "Existing owner-private review directory outside Git required.")
    info = root.stat()
    if info.st_mode & 0o077 or (
        os.name == "posix" and info.st_uid != os.getuid()
    ):
        raise PrivateDraftReviewError("Review directory must be mode 0700, owner only.")
    return root


def inspect_uploaded_private_draft(
    *, private_root: str, relative_path: str,
    expected_sha256: str, episode_id: str,
    journal_file: str, video_id: str,
) -> dict:
    """Require journal CONFIRMED and actual Pi MP4 bytes, with no network.

    No claim that the video remains PRIVATE *now*; the actual owner must
    check current channel/video status in YouTube Studio themselves.
    """
    if (not isinstance(relative_path, str)
            or not _MP4_NAME.fullmatch(relative_path)
            or relative_path == _INTERNAL_CANDIDATE
            or not isinstance(expected_sha256, str)
            or not _SHA.fullmatch(expected_sha256)
            or not isinstance(video_id, str)
            or not _VIDEO_ID.fullmatch(video_id)
            or not isinstance(episode_id, str)
            or not _EPISODE.fullmatch(episode_id)):
        raise PrivateDraftReviewError("Exact MP4, SHA, video ID and episode required.")
    journal = _load_journal(_private_journal_path(journal_file))
    if (journal.get("schema_version") != 1
            or journal.get("state") != "PRIVATE_UPLOAD_CONFIRMED"
            or journal.get("media_sha256") != expected_sha256
            or journal.get("media_name") != relative_path
            or journal.get("episode_id") != episode_id
            or type(journal.get("media_bytes")) is not int
            or not 1 <= journal["media_bytes"] <= 20 * 1024**3
            or journal.get("video_id") != video_id
            or not isinstance(journal.get("intent_sha256"), str)
            or not _SHA.fullmatch(journal["intent_sha256"])
            or "session_url" in journal):
        raise PrivateDraftReviewError(
            "Journal is not a confirmed PRIVATE upload for this exact version.")
    # Pi inbox must remain mode 0700 and the MP4 regular, owned, mode 0600.
    # Generic digest verification alone does not enforce private path safety.
    private_evidence_file(private_root, relative_path, max_bytes=20 * 1024**3)
    verified = verify_staged_file(
        root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256)
    if (verified.get("status") != "VERIFIED"
            or verified.get("bytes") != journal["media_bytes"]):
        raise PrivateDraftReviewError(
            "Local Pi MP4 changed or does not match the confirmed upload journal.")
    return {
        "schema_version": 1,
        "status": "PI_PRIVATE_DRAFT_REVIEW_ELIGIBLE_OFFLINE",
        "episode_id": episode_id,
        "video_name": relative_path,
        "video_sha256": expected_sha256,
        "video_bytes": verified["bytes"],
        "youtube_video_id": video_id,
        "upload_intent_sha256": journal["intent_sha256"],
        "youtube_private_historically_confirmed_in_local_journal": True,
        "youtube_current_privacy_live_rechecked": False,
        "owner_review_completed": False,
        "reviewer_identity_authenticated": False,
        "youtube_network_called": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def _existing_review_outcomes(*, root: Path, prefix: str,
                              expected: dict) -> tuple[int, int]:
    accepted = 0
    revision = 0
    for file in root.iterdir():
        if not file.name.startswith(prefix):
            continue
        suffix = file.name[len(prefix):]
        if not _NOTE_SUFFIX.fullmatch(suffix):
            raise PrivateDraftReviewError("Malformed review-shaped record.")
        note = read_private_json(str(root), file.name)
        if (note.get("schema_version") != 1
                or note.get("status") != "PI_PRIVATE_DRAFT_REVIEW_RECORDED"
                or note.get("episode_id") != expected["episode_id"]
                or note.get("video_name") != expected["video_name"]
                or note.get("video_sha256") != expected["video_sha256"]
                or note.get("video_bytes") != expected["video_bytes"]
                or note.get("youtube_video_id") != expected["youtube_video_id"]
                or note.get("upload_intent_sha256") != expected["upload_intent_sha256"]
                or note.get("publication_approved") is not False
                or note.get("reviewer_identity_authenticated") is not False
                or note.get("youtube_current_privacy_live_rechecked") is not False
                or note.get("review_outcome") not in (
                    "REVISION_REQUIRED", "ACCEPTED_PRIVATE")):
            raise PrivateDraftReviewError("Contradictory or unsafe past review.")
        if note["review_outcome"] == "REVISION_REQUIRED":
            revision += 1
        else:
            if (note.get("reported_full_video_reviewed") is not True
                    or note.get("reported_arabic_voice_reviewed") is not True):
                raise PrivateDraftReviewError("Incomplete historical acceptance.")
            accepted += 1
        if accepted + revision > 256:
            raise PrivateDraftReviewError("Too many review notes for same draft.")
    return accepted, revision


def record_post_private_draft_review(
    *, private_root: str, relative_path: str,
    expected_sha256: str, episode_id: str, journal_file: str,
    video_id: str, review_root: str, review_outcome: str,
    reviewer_notes: str, reviewed_private_youtube_draft: bool,
    reviewed_full_video: bool = False,
    reviewed_arabic_voice: bool = False,
    save_review: bool = False,
) -> dict:
    if (review_outcome not in ("REVISION_REQUIRED", "ACCEPTED_PRIVATE")
            or not isinstance(reviewer_notes, str)
            or not 0 <= len(reviewer_notes) <= 2000
            or type(reviewed_private_youtube_draft) is not bool
            or type(reviewed_full_video) is not bool
            or type(reviewed_arabic_voice) is not bool
            or type(save_review) is not bool):
        raise PrivateDraftReviewError("Invalid private owner review parameters.")
    if not save_review:
        raise PrivateDraftReviewError("Explicit --save-review is required.")
    if not reviewed_private_youtube_draft:
        raise PrivateDraftReviewError("Must explicitly review the YouTube PRIVATE draft.")
    if review_outcome == "REVISION_REQUIRED" and not reviewer_notes.strip():
        raise PrivateDraftReviewError("Revision request requires a written note.")
    if (review_outcome == "ACCEPTED_PRIVATE"
            and not (reviewed_full_video and reviewed_arabic_voice)):
        raise PrivateDraftReviewError("Accept requires full video and Arabic listening.")
    root = _private_review_root(review_root)
    proof = inspect_uploaded_private_draft(
        private_root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256, episode_id=episode_id,
        journal_file=journal_file, video_id=video_id)
    prefix = f"private_draft_{video_id}_{expected_sha256[:16]}.review."
    _, revision_count = _existing_review_outcomes(
        root=root, prefix=prefix, expected=proof)
    if review_outcome == "ACCEPTED_PRIVATE" and revision_count:
        raise PrivateDraftReviewError(
            "This exact private draft has a revision request; review a new version.")

    # Re-check source bytes/journal immediately before appending evidence.
    if inspect_uploaded_private_draft(
        private_root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256, episode_id=episode_id,
        journal_file=journal_file, video_id=video_id) != proof:
        raise PrivateDraftReviewError("Private draft source changed before review save.")

    name = prefix + secrets.token_hex(8) + ".json"
    review = {
        "schema_version": 1,
        "status": "PI_PRIVATE_DRAFT_REVIEW_RECORDED",
        "episode_id": episode_id,
        "video_name": relative_path,
        "video_sha256": expected_sha256,
        "video_bytes": proof["video_bytes"],
        "youtube_video_id": video_id,
        "upload_intent_sha256": proof["upload_intent_sha256"],
        "review_outcome": review_outcome,
        "reviewer_notes": reviewer_notes,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "reported_youtube_private_draft_reviewed": True,
        "reported_full_video_reviewed": reviewed_full_video,
        "reported_arabic_voice_reviewed": reviewed_arabic_voice,
        "youtube_private_historically_confirmed_in_local_journal": True,
        "youtube_current_privacy_live_rechecked": False,
        "reviewer_identity_authenticated": False,
        "local_acceptance_is_publication_permission": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }
    raw = (json.dumps(review, ensure_ascii=False, sort_keys=True) + "\n").encode()
    if len(raw) > 16 * 1024:
        raise PrivateDraftReviewError("Review record too large.")
    target = root / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        parent_fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        "status": "PI_PRIVATE_DRAFT_REVIEW_RECORDED",
        "review_evidence_name": name,
        "youtube_video_id": video_id,
        "video_sha256": expected_sha256,
        "review_outcome": review_outcome,
        "reviewer_identity_authenticated": False,
        "youtube_current_privacy_live_rechecked": False,
        "youtube_network_called": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline post-YouTube-PRIVATE review, exact journal+SHA bound")
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--video-id", required=True,
                        help="Exact ID copied from the PRIVATE video opened in Studio")
    parser.add_argument("--review-root", default=str(
        Path.home() / "kidsstudio-private" / "reviews"))
    parser.add_argument("--review-outcome",
                        choices=["REVISION_REQUIRED", "ACCEPTED_PRIVATE"])
    parser.add_argument("--reviewer-notes", default="")
    parser.add_argument("--reviewed-private-draft", action="store_true")
    parser.add_argument("--reviewed-full-video", action="store_true")
    parser.add_argument("--reviewed-arabic-voice", action="store_true")
    parser.add_argument("--save-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.save_review:
            result = record_post_private_draft_review(
                private_root=args.private_root,
                relative_path=args.relative_path,
                expected_sha256=args.expected_sha256,
                episode_id=args.episode_id,
                journal_file=args.journal,
                video_id=args.video_id,
                review_root=args.review_root,
                review_outcome=args.review_outcome,
                reviewer_notes=args.reviewer_notes,
                reviewed_private_youtube_draft=args.reviewed_private_draft,
                reviewed_full_video=args.reviewed_full_video,
                reviewed_arabic_voice=args.reviewed_arabic_voice,
                save_review=True)
        else:
            result = inspect_uploaded_private_draft(
                private_root=args.private_root,
                relative_path=args.relative_path,
                expected_sha256=args.expected_sha256,
                episode_id=args.episode_id,
                journal_file=args.journal,
                video_id=args.video_id)
    except (ValueError, TypeError, KeyError, OSError, OverflowError):
        print(json.dumps({
            "status": "PI_PRIVATE_DRAFT_REVIEW_BLOCKED",
            "youtube_network_called": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if args.save_review else 1


if __name__ == "__main__":
    raise SystemExit(main())
