"""Offline Pi PRIVATE draft review queue, assembled from existing evidence.

Read-only by design: scans owner-private upload journals and review notes,
checks every currently present original MP4's SHA/size before categorizing it.
It does NOT contact Google, open SSH, invoke OAuth, start or resume uploads,
create files, publish, or pretend a local journal proves current privacy.

Only locally recorded historical status is displayed. A conflicted or unsafe
journal/review never becomes accepted or ready merely because older evidence
looked good. Reviewer identity is NOT authenticated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .optional_tool_evidence import read_private_json
from .pi_private_draft_review import (
    _existing_review_outcomes,
    _private_review_root,
    inspect_uploaded_private_draft,
)

_JOURNAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.json\Z")
_STATES = frozenset({
    "INITIATION_UNCERTAIN",
    "SESSION_ACTIVE",
    "REMOTE_COMPLETED_UNVERIFIED",
    "PRIVATE_UPLOAD_CONFIRMED",
})
_MAX_JOURNALS = 256


class PrivateDraftInboxError(ValueError):
    """Local inbox directory is unsafe or has too many upload records."""


def build_private_draft_inbox(
    *, journal_root: str, private_root: str, review_root: str,
    show_video_ids: bool = False,
) -> dict:
    """Offline status per uploaded version, conservative under any ambiguity."""
    if type(show_video_ids) is not bool:
        raise PrivateDraftInboxError("Only explicit display preferences allowed.")
    try:
        journals = _private_review_root(journal_root)
        reviews = _private_review_root(review_root)
        # Verify even with no journals: missing/public/symlinked Pi inbox must
        # never yield the appearance of an empty healthy system.
        _private_review_root(private_root)
    except (ValueError, OSError, TypeError) as exc:
        raise PrivateDraftInboxError(
            "Private Pi journals, inbox or reviews directory is unsafe.") from exc
    names = sorted(
        child.name for child in journals.iterdir()
        if child.name.endswith(".json")
    )
    if len(names) > _MAX_JOURNALS:
        raise PrivateDraftInboxError("Too many journals for one bounded read.")
    items: list[dict] = []
    counts = {
        "NEEDS_OWNER_REVIEW_PRIVATE": 0,
        "REVISION_REQUIRED_PRIVATE": 0,
        "ACCEPTED_PRIVATE_ONLY": 0,
        "UPLOAD_UNCONFIRMED": 0,
        "BLOCKED_LOCAL_EVIDENCE": 0,
    }
    for name in names:
        row: dict = {
            "journal_name": name if _JOURNAL.fullmatch(name) else None,
            "status": "BLOCKED_LOCAL_EVIDENCE",
            "episode_id": None,
            "video_name": None,
            "youtube_video_id": None,
            "matching_acceptance_notes": 0,
            "matching_revision_notes": 0,
            "local_video_sha_verified": False,
        }
        try:
            if not _JOURNAL.fullmatch(name):
                raise PrivateDraftInboxError("Unsafe journal filename.")
            journal = read_private_json(str(journals), name)
            if journal.get("schema_version") != 1:
                raise PrivateDraftInboxError("Unsupported journal schema.")
            state = journal.get("state")
            if state not in _STATES:
                raise PrivateDraftInboxError("Invalid private upload state.")
            # A pending upload is NEVER owner-review-ready. We do not read
            # its sensitive session URL or claim it is safe to retry.
            if state != "PRIVATE_UPLOAD_CONFIRMED":
                row["status"] = "UPLOAD_UNCONFIRMED"
            else:
                proof = inspect_uploaded_private_draft(
                    private_root=private_root,
                    relative_path=journal.get("media_name"),
                    expected_sha256=journal.get("media_sha256"),
                    episode_id=journal.get("episode_id"),
                    journal_file=str(journals / name),
                    video_id=journal.get("video_id"),
                )
                prefix = (
                    f"private_draft_{proof['youtube_video_id']}_"
                    f"{proof['video_sha256'][:16]}.review."
                )
                accepted, revision = _existing_review_outcomes(
                    root=reviews, prefix=prefix, expected=proof)
                row.update({
                    "episode_id": proof["episode_id"],
                    "video_name": proof["video_name"],
                    "youtube_video_id": (
                        proof["youtube_video_id"] if show_video_ids else None
                    ),
                    "matching_acceptance_notes": accepted,
                    "matching_revision_notes": revision,
                    "local_video_sha_verified": True,
                    "status": (
                        "REVISION_REQUIRED_PRIVATE" if revision
                        else "ACCEPTED_PRIVATE_ONLY" if accepted
                        else "NEEDS_OWNER_REVIEW_PRIVATE"
                    ),
                })
        except (ValueError, OSError, TypeError, KeyError):
            # No false positive, no raw paths/tokens/notes in printed output.
            row["status"] = "BLOCKED_LOCAL_EVIDENCE"
            row["episode_id"] = None
            row["video_name"] = None
            row["youtube_video_id"] = None
            row["matching_acceptance_notes"] = 0
            row["matching_revision_notes"] = 0
            row["local_video_sha_verified"] = False
        counts[row["status"]] += 1
        items.append(row)
    return {
        "schema_version": 1,
        "status": "PI_PRIVATE_DRAFT_INBOX_READ_ONLY",
        "scanned_journals": len(items),
        "counts": counts,
        "items": items,
        "youtube_private_historically_confirmed_only": True,
        "youtube_current_privacy_live_rechecked": False,
        "owner_review_attestations_not_authenticated": True,
        "no_automatic_reupload_or_publication": True,
        "ssh_or_google_network_called": False,
        "files_created_or_modified": False,
        "publication_approved": False,
    }


def format_inbox_table(report: dict) -> str:
    """Compact terminal view; never includes review note text or OAuth URLs."""
    labels = {
        "NEEDS_OWNER_REVIEW_PRIVATE": "NEEDS REVIEW",
        "REVISION_REQUIRED_PRIVATE": "REVISION",
        "ACCEPTED_PRIVATE_ONLY": "ACCEPTED PRIVATE",
        "UPLOAD_UNCONFIRMED": "UPLOAD UNCERTAIN",
        "BLOCKED_LOCAL_EVIDENCE": "BLOCKED",
    }
    lines = [
        "KidsStudio | PRIVATE draft review inbox (LOCAL ONLY)",
        "Journal | Episode | Status | Accept / Revision",
        "-" * 70,
    ]
    for row in report["items"]:
        lines.append(
            f"{row['journal_name'] or '[unsafe]'} | "
            f"{row['episode_id'] or '-'} | "
            f"{labels[row['status']]} | "
            f"{row['matching_acceptance_notes']} / "
            f"{row['matching_revision_notes']}"
        )
    totals = report["counts"]
    lines.append(
        f"TOTAL={report['scanned_journals']}  NEEDS_REVIEW="
        f"{totals['NEEDS_OWNER_REVIEW_PRIVATE']}  REVISION="
        f"{totals['REVISION_REQUIRED_PRIVATE']}  ACCEPTED_PRIVATE="
        f"{totals['ACCEPTED_PRIVATE_ONLY']}  BLOCKED="
        f"{totals['BLOCKED_LOCAL_EVIDENCE']}  UPLOAD_UNCONFIRMED="
        f"{totals['UPLOAD_UNCONFIRMED']}"
    )
    lines.append(
        "PRIVATE is historical local journal status only; check current "
        "YouTube Studio privacy yourself. NEVER publication approval."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Pi PRIVATE draft/owner-note inbox (read-only)")
    parser.add_argument("--journal-root", default=str(
        Path.home() / "kidsstudio-private" / "journals"))
    parser.add_argument("--private-root", default=str(
        Path.home() / "kidsstudio-private" / "inbox"))
    parser.add_argument("--review-root", default=str(
        Path.home() / "kidsstudio-private" / "reviews"))
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--show-video-ids", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_private_draft_inbox(
            journal_root=args.journal_root, private_root=args.private_root,
            review_root=args.review_root, show_video_ids=args.show_video_ids)
    except (ValueError, OSError, TypeError, KeyError):
        print(json.dumps({
            "status": "PI_PRIVATE_DRAFT_INBOX_BLOCKED",
            "ssh_or_google_network_called": False,
            "files_created_or_modified": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_inbox_table(report))
    return 0 if report["counts"]["BLOCKED_LOCAL_EVIDENCE"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
