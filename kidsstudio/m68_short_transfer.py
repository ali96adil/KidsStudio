"""M68 transfer approved Shorts via the existing M67 SSH transport.

Requires an independent content-QA receipt pinned to the decoded MP4.
Never authorizes YouTube upload or public publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import verify_inventory
from .m67_pi_ssh_transfer import transfer


class ShortTransferError(RuntimeError):
    pass


def transfer_approved_short(root, handoff, qa_receipt, *, host, user, remote_dir,
                            transport=transfer):
    if handoff.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING":
        raise ShortTransferError("expected M68 pinned short handoff")
    if handoff.get("public_release_authorized") is not False:
        raise ShortTransferError("public release must remain blocked")
    if handoff.get("youtube_upload_authorized") is not False:
        raise ShortTransferError("upload authorization not permitted here")
    if qa_receipt.get("short_id") != handoff.get("short_id"):
        raise ShortTransferError("content QA short id mismatch")
    if qa_receipt.get("source_episode_id") != handoff.get("source_episode_id"):
        raise ShortTransferError("content QA parent episode mismatch")
    if qa_receipt.get("video_sha256") != handoff["master"]["sha256"]:
        raise ShortTransferError("content QA is for another video")
    if qa_receipt.get("content_qa") != "PASS":
        raise ShortTransferError("content QA not passed")
    if qa_receipt.get("youtube_visibility") != "PRIVATE_ONLY":
        raise ShortTransferError("private-only review required")
    verify_inventory(root, handoff)
    result = transport(root, handoff, host=host, user=user, remote_dir=remote_dir)
    if result.get("status") != "TRANSFERRED_TO_PI_HASH_VERIFIED":
        raise ShortTransferError("Pi transfer not verified")
    return {"status": "SHORT_ON_PI_PENDING_PRIVATE_UPLOAD",
            "short_id": handoff["short_id"],
            "source_episode_id": handoff["source_episode_id"],
            "remote_master": result["remote_master"],
            "sha256": result["sha256"],
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--handoff", type=Path, required=True)
    p.add_argument("--content-qa", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--remote-dir", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output exists")
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    qa = json.loads(args.content_qa.read_text(encoding="utf-8"))
    result = transfer_approved_short(args.root, handoff, qa, host=args.host,
                                     user=args.user, remote_dir=args.remote_dir)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
