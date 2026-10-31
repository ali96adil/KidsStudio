"""Read-only consolidated M68 review gate.

AI visual observations and an asset rights ledger are supporting evidence,
not six-axis certification. Unverified dimensions always remain blocked.
No network calls, database writes, upload permission, or public release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import verify_inventory
from .m68_rights_inventory import audit as audit_rights
from .m68_short_content_review import CHECKS


def audit(root, handoff, *, vision_receipt=None, rights_manifest=None):
    if (not isinstance(handoff, dict)
            or handoff.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING"
            or handoff.get("short_id") != handoff.get("episode_id")
            or handoff.get("youtube_upload_authorized") is not False
            or handoff.get("public_release_authorized") is not False):
        raise ValueError("invalid M68 handoff")
    sha = verify_inventory(root, handoff)["sha256"]
    if sha != handoff.get("sha256"):
        raise ValueError("media inventory does not match handoff")
    blockers = []
    checks = {axis: False for axis in CHECKS}
    if vision_receipt is None:
        blockers.append("visual_model_evidence_missing")
    else:
        if (not isinstance(vision_receipt, dict)
                or vision_receipt.get("short_id") != handoff["short_id"]
                or vision_receipt.get("video_sha256") != sha
                or vision_receipt.get("source_episode_id") != handoff.get("source_episode_id")
                or vision_receipt.get("independent_reviewers") != 1
                or not isinstance(vision_receipt.get("local_model_response_sha256"), str)
                or len(vision_receipt["local_model_response_sha256"]) != 64
                or any(ch not in "0123456789abcdef" for ch in vision_receipt["local_model_response_sha256"])
                or vision_receipt.get("decision") != "REJECT"
                or vision_receipt.get("review_scope")
                    != "LOCAL_VISUAL_SAFETY_ONLY_FOUR_AXES_UNVERIFIED"
                or not isinstance(vision_receipt.get("checks"), dict)
                or set(vision_receipt["checks"]) != set(CHECKS)
                or any(type(value) is not bool
                       for value in vision_receipt["checks"].values())
                or any(vision_receipt["checks"][axis] for axis in (
                    "audio", "copyright", "pedagogy", "source_consistency"))):
            raise ValueError("untrusted or incompatible visual diagnostic")
        for axis in ("visual", "age_appropriate"):
            checks[axis] = vision_receipt["checks"][axis]
            if not checks[axis]:
                blockers.append(axis + "_visual_evidence_failed")
    if rights_manifest is None:
        blockers.append("source_rights_inventory_missing")
        rights = None
    else:
        rights = audit_rights(rights_manifest, expected_video_sha256=sha)
        if rights["reasons"]:
            blockers.append("source_rights_inventory_blocked")
        else:
            blockers.append("source_rights_documented_not_legally_verified")
    for axis in ("pedagogy", "audio", "copyright", "source_consistency"):
        blockers.append(axis + "_independent_review_missing")
    return {
        "status": "M68_CONSOLIDATED_REVIEW_BLOCKED",
        "short_id": handoff["short_id"],
        "video_sha256": sha,
        "checks": checks,
        "blockers": blockers,
        "rights_inventory": rights,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--vision-receipt", type=Path)
    parser.add_argument("--rights-manifest", type=Path)
    args = parser.parse_args(argv)
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    vision = (json.loads(args.vision_receipt.read_text(encoding="utf-8"))
              if args.vision_receipt else None)
    result = audit(args.root, handoff, vision_receipt=vision,
                   rights_manifest=args.rights_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
