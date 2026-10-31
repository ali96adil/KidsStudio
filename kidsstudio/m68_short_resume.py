"""M68 resumable, QA-gated private short transfer using existing M67 transport.

This stages media only. M65 PiOrdinaryInbox remains the exclusive acceptance
and YouTube-upload eligibility authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import verify_inventory
from .m67_pi_transfer_resume import transfer_resumable


class ShortResumeError(RuntimeError):
    pass


def resume_short(root, manifest, qa_receipt, *, host, user, remote_dir,
                 runner=None):
    if (manifest.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING"
            or manifest.get("episode_id") != manifest.get("short_id")
            or manifest.get("youtube_upload_authorized") is not False
            or manifest.get("public_release_authorized") is not False):
        raise ShortResumeError("invalid or unsafe short handoff")
    if (not isinstance(qa_receipt, dict)
            or qa_receipt.get("decision") != "PASS"
            or qa_receipt.get("short_id") != manifest.get("short_id")
            or qa_receipt.get("source_episode_id") != manifest.get("source_episode_id")):
        raise ShortResumeError("matching content QA PASS required")
    digest = verify_inventory(root, manifest)["sha256"]
    if qa_receipt.get("video_sha256") != digest:
        raise ShortResumeError("QA receipt MP4 digest mismatch")
    kwargs = {"host": host, "user": user, "remote_dir": remote_dir}
    if runner is not None:
        kwargs["runner"] = runner
    result = transfer_resumable(root, manifest, **kwargs)
    if result["sha256"] != digest:
        raise ShortResumeError("Pi transfer digest mismatch")
    return {"status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
            "short_id": manifest["short_id"],
            "source_episode_id": manifest["source_episode_id"],
            "remote_master": result["remote_master"],
            "sha256": digest,
            "transfer_status": result["status"],
            "next_action": "REGISTER_EXISTING_M65_RENDER_JOB_AND_VERIFY_PI_INBOX",
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--handoff", type=Path, required=True)
    p.add_argument("--qa-receipt", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--remote-dir", required=True)
    args = p.parse_args(argv)
    result = resume_short(
        args.root, json.loads(args.handoff.read_text(encoding="utf-8")),
        json.loads(args.qa_receipt.read_text(encoding="utf-8")),
        host=args.host, user=args.user, remote_dir=args.remote_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
