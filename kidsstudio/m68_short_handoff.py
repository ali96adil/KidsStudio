"""M68 immutable short delivery inventory for the existing M67 Mac-to-Pi transfer.

This builds an individual, SHA-pinned handoff manifest per short. It never
uploads to YouTube, approves QA or changes M65's upload journal.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import inventory, verify_inventory, HandoffError


class ShortHandoffError(RuntimeError):
    pass


def build_short_handoff(root, short, video, decode_receipt):
    if decode_receipt.get("status") != "SHORT_FULLY_DECODED_PENDING_CONTENT_QA":
        raise ShortHandoffError("full media decode receipt required")
    if decode_receipt.get("short_id") != short.get("short_id"):
        raise ShortHandoffError("decode receipt short mismatch")
    if decode_receipt.get("source_episode_id") != short.get("source_episode_id"):
        raise ShortHandoffError("decode receipt episode mismatch")
    if short.get("youtube_visibility") != "PRIVATE_ONLY":
        raise ShortHandoffError("private-only policy required")
    if decode_receipt.get("full_decode") != "PASS":
        raise ShortHandoffError("full decode not passed")
    manifest = inventory(root, master=video, episode_id=short["short_id"])
    checked = verify_inventory(root, manifest)
    if checked["sha256"] != decode_receipt.get("video_sha256"):
        raise ShortHandoffError("rendered MP4 differs from decoded MP4")
    if manifest["master"]["bytes"] != decode_receipt.get("bytes"):
        raise ShortHandoffError("rendered MP4 size changed")
    manifest["source_episode_id"] = short["source_episode_id"]
    manifest["short_id"] = short["short_id"]
    manifest["status"] = "SHORT_HASH_PINNED_CONTENT_QA_PENDING"
    manifest["content_qa"] = "PENDING"
    manifest["pi_transfer_authorized"] = False
    manifest["youtube_upload_authorized"] = False
    manifest["public_release_authorized"] = False
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--short-id", required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--decode-receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output already exists")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    selected = [s for s in plan["shorts"] if s["short_id"] == args.short_id]
    if len(selected) != 1:
        p.error("short id must match exactly once")
    receipt = json.loads(args.decode_receipt.read_text(encoding="utf-8"))
    result = build_short_handoff(args.root, selected[0], args.video, receipt)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["status"], "short_id": args.short_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
