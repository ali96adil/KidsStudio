"""M68 final release audit: explicit blockers for Mac/Pi/YouTube readiness.

Read-only. A successful audit is NOT permission to publish; all uploads
remain PRIVATE and only M65's existing policy engine can upload.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .m67_master_handoff import verify_inventory


_SHA = re.compile(r"^[0-9a-f]{64}$")


def audit(root, plan, qualification, qa_by_short=None, imports_by_short=None):
    qa_by_short = qa_by_short or {}
    imports_by_short = imports_by_short or {}
    shorts = plan.get("shorts", [])
    records = qualification.get("shorts", [])
    blockers = []
    if not shorts or len({s.get("short_id") for s in shorts}) != len(shorts):
        blockers.append("SHORT_PLAN_EMPTY_OR_DUPLICATE")
    if qualification.get("episode_id") != plan.get("episode_id"):
        blockers.append("QUALIFICATION_EPISODE_MISMATCH")
    indexed = {}
    for record in records:
        sid = record.get("short_id")
        if sid in indexed:
            blockers.append("DUPLICATE_QUALIFICATION")
        indexed[sid] = record
    for short in shorts:
        sid = short["short_id"]
        record = indexed.get(sid)
        if not record:
            blockers.append(f"{sid}:MISSING_QUALIFICATION")
            continue
        decoded = record.get("decode", {})
        handoff = record.get("handoff", {})
        digest = decoded.get("video_sha256")
        if (decoded.get("status") != "SHORT_FULLY_DECODED_PENDING_CONTENT_QA"
                or decoded.get("full_decode") != "PASS"
                or not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            blockers.append(f"{sid}:FULL_DECODE_NOT_VERIFIED")
            continue
        if handoff.get("short_id") != sid or handoff.get("source_episode_id") != short.get("source_episode_id"):
            blockers.append(f"{sid}:HANDOFF_IDENTITY_MISMATCH")
            continue
        if handoff.get("master", {}).get("sha256") != digest:
            blockers.append(f"{sid}:HANDOFF_DIGEST_MISMATCH")
            continue
        try:
            verify_inventory(root, handoff)
        except (OSError, ValueError, KeyError, RuntimeError):
            blockers.append(f"{sid}:LOCAL_MASTER_CHANGED")
            continue
        qa = qa_by_short.get(sid, {})
        if (qa.get("content_qa") != "PASS"
                or qa.get("video_sha256") != digest
                or qa.get("short_id") != sid
                or qa.get("source_episode_id") != short.get("source_episode_id")
                or qa.get("youtube_visibility") != "PRIVATE_ONLY"):
            blockers.append(f"{sid}:CONTENT_QA_PENDING_OR_MISMATCH")
        imported = imports_by_short.get(sid, {})
        if (imported.get("status") != "M68_SHORT_ACCEPTED_IN_M65_INBOX_NOT_UPLOADED"
                or imported.get("short_id") != sid
                or imported.get("master_sha256") != digest):
            blockers.append(f"{sid}:PI_M65_IMPORT_NOT_CONFIRMED")
    if set(indexed) != {s.get("short_id") for s in shorts}:
        blockers.append("QUALIFICATION_SET_MISMATCH")
    return {
        "status": "M68_INTEGRATION_EVIDENCE_COMPLETE_PRIVATE_ONLY" if not blockers
                  else "M68_INTEGRATION_BLOCKED",
        "episode_id": plan.get("episode_id"),
        "shorts_expected": len(shorts),
        "blockers": blockers,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
        "next_action": "M65_PRIVATE_UPLOAD_POLICY_CHECK" if not blockers
                       else "RESOLVE_BLOCKERS",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--qualification", type=Path, required=True)
    p.add_argument("--content-qa", type=Path)
    p.add_argument("--pi-imports", type=Path)
    args = p.parse_args(argv)
    def load(path):
        return json.loads(path.read_text(encoding="utf-8")) if path else {}
    report = audit(args.root, load(args.plan), load(args.qualification),
                   load(args.content_qa), load(args.pi_imports))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
