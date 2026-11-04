"""M68 explicitly approved short transfer to Pi via existing M67 SSH transport.

Content QA is a separate recorded decision, not inferred from successful
encoding or decoding. Transfers are private staging only, never YouTube upload.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import verify_inventory
from .m67_pi_ssh_transfer import transfer


class ShortTransferError(RuntimeError):
    pass


def transfer_approved_short(root, manifest, qa_receipt, *, host, user,
                            remote_dir, runner=None):
    if manifest.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING":
        raise ShortTransferError("expected M68 short handoff manifest")
    if manifest.get("episode_id") != manifest.get("short_id"):
        raise ShortTransferError("independent short identity required")
    if manifest.get("public_release_authorized") is not False:
        raise ShortTransferError("public release must remain blocked")
    if manifest.get("youtube_upload_authorized") is not False:
        raise ShortTransferError("YouTube upload must remain blocked")
    if not isinstance(qa_receipt, dict) or qa_receipt.get("decision") != "PASS":
        raise ShortTransferError("explicit content QA PASS required")
    if qa_receipt.get("short_id") != manifest.get("short_id"):
        raise ShortTransferError("content QA belongs to another short")
    if qa_receipt.get("source_episode_id") != manifest.get("source_episode_id"):
        raise ShortTransferError("content QA episode mismatch")
    checked = verify_inventory(root, manifest)
    if qa_receipt.get("video_sha256") != checked["sha256"]:
        raise ShortTransferError("content QA does not match pinned MP4")
    kwargs = {"host": host, "user": user, "remote_dir": remote_dir}
    if runner is not None:
        kwargs["runner"] = runner
    report = transfer(root, manifest, **kwargs)
    report["short_id"] = manifest["short_id"]
    report["source_episode_id"] = manifest["source_episode_id"]
    report["status"] = "SHORT_TRANSFERRED_TO_PI_PRIVATE_STAGING"
    report["content_qa"] = "PASS"
    report["youtube_upload_authorized"] = False
    report["public_release_authorized"] = False
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--handoff", type=Path, required=True)
    p.add_argument("--qa-receipt", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--remote-dir", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output already exists")
    manifest = json.loads(args.handoff.read_text(encoding="utf-8"))
    receipt = json.loads(args.qa_receipt.read_text(encoding="utf-8"))
    result = transfer_approved_short(args.root, manifest, receipt,
                                     host=args.host, user=args.user,
                                     remote_dir=args.remote_dir)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
