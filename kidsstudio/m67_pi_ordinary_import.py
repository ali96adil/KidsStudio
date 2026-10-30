"""M67 Pi-local import of an already transferred MP4 into M65 ordinary inbox.

Only an approved M65 render job and its existing M25 plan/readiness receipts
may be accepted. The transferred master is copied to a staged .part file;
the existing PiOrdinaryInbox.accept performs final policy and hash checks.
No YouTube call, no arbitrary upload authorization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import re

from .studio_queue import StudioQueue
from .pi_ordinary_inbox import PiOrdinaryInbox
from .youtube_private_upload import file_sha256
from .m67_pi_receipts_preflight import preflight


class PiImportError(RuntimeError):
    pass


def import_transferred(queue, inbox_root, *, render_job_id, transferred_master,
                       plan_file, readiness_file, expected_sha256):
    inbox = PiOrdinaryInbox(queue, inbox_root)
    source = Path(transferred_master)
    plan = Path(plan_file)
    readiness = Path(readiness_file)
    for item in (source, plan, readiness):
        if item.is_symlink() or not item.is_file():
            raise PiImportError("regular existing source files required")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PiImportError("exact master SHA256 required")
    if file_sha256(source) != expected_sha256:
        raise PiImportError("transferred MP4 hash mismatch")
    receipt_check = preflight(master=source, plan=plan, readiness=readiness,
                              render_job_id=render_job_id,
                              expected_sha256=expected_sha256)
    if receipt_check["status"] != "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL":
        raise PiImportError("M65 upload plan or readiness receipt mismatch")
    inbox.prepare(render_job_id)
    video_target, plan_target, ready_target = inbox._files(render_job_id, True)
    for target in (video_target, plan_target, ready_target):
        if target.exists() or target.is_symlink():
            raise PiImportError("existing staged files require reconciliation")
    # Never move the raw inbox source; preserve the original LAN delivery.
    created = []
    try:
        for original, target in ((source, video_target), (plan, plan_target),
                                 (readiness, ready_target)):
            with original.open("rb") as reader, target.open("xb") as writer:
                created.append(target)
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
        if file_sha256(video_target) != expected_sha256:
            raise PiImportError("staged master changed during copy")
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    try:
        result = inbox.accept(render_job_id)
    except Exception as exc:
        raise PiImportError("M65 acceptance failed; inspect staged files") from exc
    if result["master_sha256"] != expected_sha256:
        raise PiImportError("accepted master digest mismatch")
    return {"status": "M67_IMPORTED_VIA_M65_ORDINARY_INBOX",
            "render_job_id": render_job_id,
            "master_sha256": expected_sha256,
            "youtube_uploaded": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--inbox-root", type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    p.add_argument("--transferred-master", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--readiness", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    args = p.parse_args(argv)
    result = import_transferred(
        StudioQueue(args.db), args.inbox_root,
        render_job_id=args.render_job_id,
        transferred_master=args.transferred_master,
        plan_file=args.plan, readiness_file=args.readiness,
        expected_sha256=args.sha256)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
