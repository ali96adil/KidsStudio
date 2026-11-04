"""M68 Pi-local short import through the existing M65 ordinary inbox.

This module never calls YouTube. It requires a verified short transfer,
matching M65 plan/readiness receipts, and the existing M65 policy database.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_queue import StudioQueue
from .m67_pi_ordinary_import import import_transferred
from .m68_pi_import_preflight import assess_short_import


def import_short(queue, inbox_root, *, transfer_receipt, transferred_master,
                 plan_file, readiness_file, render_job_id,
                 importer=import_transferred):
    preflight = assess_short_import(
        transfer_receipt, master=transferred_master, plan=plan_file,
        readiness=readiness_file, render_job_id=render_job_id)
    if preflight["status"] != "M68_SHORT_READY_FOR_EXISTING_M65_IMPORT":
        raise RuntimeError("short not ready for M65 import")
    result = importer(
        queue, inbox_root, render_job_id=render_job_id,
        transferred_master=transferred_master, plan_file=plan_file,
        readiness_file=readiness_file,
        expected_sha256=transfer_receipt["sha256"])
    if result.get("status") != "M67_IMPORTED_VIA_M65_ORDINARY_INBOX":
        raise RuntimeError("M65 inbox did not accept short")
    if result.get("master_sha256") != transfer_receipt["sha256"]:
        raise RuntimeError("M65 accepted unexpected video digest")
    return {"status": "M68_SHORT_ACCEPTED_IN_M65_INBOX_NOT_UPLOADED",
            "short_id": transfer_receipt["short_id"],
            "source_episode_id": transfer_receipt["source_episode_id"],
            "render_job_id": render_job_id,
            "master_sha256": result["master_sha256"],
            "youtube_uploaded": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--inbox-root", type=Path, required=True)
    p.add_argument("--transfer-receipt", type=Path, required=True)
    p.add_argument("--transferred-master", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--readiness", type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    args = p.parse_args(argv)
    receipt = json.loads(args.transfer_receipt.read_text(encoding="utf-8"))
    result = import_short(
        StudioQueue(args.db), args.inbox_root,
        transfer_receipt=receipt, transferred_master=args.transferred_master,
        plan_file=args.plan, readiness_file=args.readiness,
        render_job_id=args.render_job_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
