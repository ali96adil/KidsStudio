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
import sys

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


def _interactive_terminal() -> bool:
    """No piped responses, unattended approvals or background sessions."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _guided_cancelled() -> dict:
    return {
        "status": "MAC_PILOT_GUIDED_REVIEW_CANCELLED_NO_WRITE",
        "review_recorded": False,
        "publication_approved": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
    }


def guided_mac_pilot_review(*, video_root: str, evidence_root: str,
                            limit: int = 10) -> dict:
    """TTY-only explicit selection and local private review of one pilot.

    Video checks/approval are assertions made by the operator, not checks
    performed by this prompt. No default selection or unattended mode.
    """
    if not _interactive_terminal():
        raise MacPilotShortcutError("A real interactive terminal is required.")
    choices = list_mac_pilot_evidence(
        video_root=video_root, evidence_root=evidence_root, limit=limit)["pilots"]
    if not choices:
        return {
            **_guided_cancelled(),
            "status": "MAC_PILOT_GUIDED_NO_VALID_PRIVATE_PILOTS",
        }

    print("KidsStudio — اختيار حلقة للمراجعة المحلية فقط")
    print("الأرقام للاختيار، ولا توجد موافقة أو رفع تلقائي.")
    for number, item in enumerate(choices, 1):
        print(f"{number}) {item['video_name']} "
              f"({item['duration_seconds']}s, SHA {item['video_sha256'][:12]}...)")
    try:
        number_text = input("رقم الحلقة المطلوب مراجعتها (0 للإلغاء): ").strip()
        if not number_text.isascii() or not number_text.isdigit():
            return _guided_cancelled()
        number = int(number_text)
        if not 1 <= number <= len(choices):
            return _guided_cancelled()
        selected = choices[number - 1]
        print(f"الفيديو المختار: {selected['video_name']}")
        print("شاهد كل الفيديو واستمع لكل الجمل العربية قبل القبول.")
        decision = input("اكتب R إذا تحتاج تعديل، أو A لقبول محلي خاص، أو C للإلغاء: ").strip().upper()
        if decision not in ("R", "A"):
            return _guided_cancelled()
        notes = input("الملاحظات (حتى 2000 حرف): ").strip()
        if len(notes) > 2000 or (decision == "R" and not notes):
            return _guided_cancelled()
        accepted = decision == "A"
        if accepted:
            if input("هل شاهدت الفيديو كاملاً؟ اكتب YES فقط إن كان صحيحاً: ").strip() != "YES":
                return _guided_cancelled()
            if input("هل راجعت الاستماع لكل الصوت العربي؟ اكتب YES فقط إن كان صحيحاً: ").strip() != "YES":
                return _guided_cancelled()
        print("هذا يحفظ ملاحظة محلية فقط. لا ينقل أو يرفع أو ينشر الفيديو.")
        if input("لتسجيل القرار المحدد على هذا الملف فقط اكتب SAVE: ").strip() != "SAVE":
            return _guided_cancelled()
    except (EOFError, KeyboardInterrupt):
        return _guided_cancelled()

    # Re-validate sidecar and actual bytes AFTER all prompts: a file change
    # between selection and commit MUST block recording.
    return record_mac_pilot_review_shortcut(
        video_root=video_root,
        evidence_root=evidence_root,
        evidence_name=selected["evidence_name"],
        review_outcome="ACCEPTED_PRIVATE" if accepted else "REVISION_REQUIRED",
        reviewer_notes=notes,
        reviewed_full_video=accepted,
        reviewed_arabic_voice=accepted,
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
    guided = sub.add_parser("guided",
                            help="Interactive TTY-only exact-video selection and private review")
    guided.add_argument("--limit", type=int, default=10)
    for selected in (listing, record, guided):
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
        elif args.action == "guided":
            result = guided_mac_pilot_review(
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
