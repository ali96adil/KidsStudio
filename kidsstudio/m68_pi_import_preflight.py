"""M68 Pi-side preflight for an individual short and M65 upload receipts.

A transferred MP4 alone is never an M65 upload job. This module checks the
independent short identity and existing M65 plan/readiness before import.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_pi_receipts_preflight import preflight


class ShortImportPreflightError(RuntimeError):
    pass


def assess_short_import(transfer_receipt, *, master, plan, readiness, render_job_id):
    if transfer_receipt.get("status") != "SHORT_ON_PI_PENDING_PRIVATE_UPLOAD":
        raise ShortImportPreflightError("verified M68 transfer receipt required")
    short_id = transfer_receipt.get("short_id")
    if not isinstance(short_id, str) or not short_id:
        raise ShortImportPreflightError("short id required")
    if transfer_receipt.get("public_release_authorized") is not False:
        raise ShortImportPreflightError("public release prohibited")
    if transfer_receipt.get("youtube_upload_authorized") is not False:
        raise ShortImportPreflightError("unexpected upload authorization")
    digest = transfer_receipt.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ShortImportPreflightError("transfer SHA256 required")
    if render_job_id == transfer_receipt.get("source_episode_id"):
        raise ShortImportPreflightError("short cannot reuse parent episode identity")
    result = preflight(master=Path(master), plan=Path(plan),
                       readiness=Path(readiness), render_job_id=render_job_id,
                       expected_sha256=digest)
    if result.get("status") != "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL":
        raise ShortImportPreflightError("M65 plan/readiness not consistent")
    return {"status": "M68_SHORT_READY_FOR_EXISTING_M65_IMPORT",
            "short_id": short_id,
            "source_episode_id": transfer_receipt["source_episode_id"],
            "render_job_id": render_job_id,
            "sha256": digest,
            "pi_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--transfer-receipt", type=Path, required=True)
    p.add_argument("--master", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--readiness", type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    args = p.parse_args(argv)
    receipt = json.loads(args.transfer_receipt.read_text(encoding="utf-8"))
    print(json.dumps(assess_short_import(
        receipt, master=args.master, plan=args.plan,
        readiness=args.readiness, render_job_id=args.render_job_id),
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
