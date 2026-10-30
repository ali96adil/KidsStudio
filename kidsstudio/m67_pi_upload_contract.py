"""M67 preflight the Pi inbox contract before attempting PRIVATE upload.

M67's raw SSH MP4 drop is NOT an accepted M65 inbox record. The existing
Pi uploader requires owner-approved episode, render job, plan/readiness
hashes, Pi-side acceptance and a durable one-shot upload journal.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_master_handoff import verify_inventory


REQUIRED = (
    "render_job_id", "series_id", "episode_number", "channel_id",
    "made_for_kids", "contains_synthetic_media",
    "plan_sha256", "readiness_sha256",
)


def assess(root, inventory, approval=None):
    verified = verify_inventory(root, inventory)
    missing = [name for name in REQUIRED
               if not isinstance(approval, dict) or name not in approval]
    if missing:
        return {
            "status": "M67_RAW_MASTER_NOT_REGISTERED_WITH_PI_INBOX",
            "master_sha256": verified["sha256"],
            "missing_pi_policy_fields": missing,
            "next_action": "REGISTER_WITH_EXISTING_M65_PI_ORDINARY_INBOX",
            "pi_upload_authorized": False,
            "public_release_authorized": False,
        }
    # Fields in an arbitrary JSON file do not prove the Pi accepted a video.
    # Only the existing PiOrdinaryInbox.verify(full_sha=True) and policy
    # database are allowed to establish upload eligibility.
    return {
        "status": "M67_PI_SIDE_VERIFICATION_REQUIRED",
        "master_sha256": verified["sha256"],
        "missing_pi_policy_fields": [],
        "next_action": "VERIFY_M65_PI_DB_AND_INBOX_WITH_FULL_SHA",
        "pi_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--approval", type=Path)
    args = p.parse_args(argv)
    data = json.loads(args.inventory.read_text(encoding="utf-8"))
    approval = (json.loads(args.approval.read_text(encoding="utf-8"))
                if args.approval else None)
    result = assess(args.root, data, approval)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
