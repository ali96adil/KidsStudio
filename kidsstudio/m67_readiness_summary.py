"""M67 production report: statuses plus explicit remaining requirements."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_episode_status import summarize


EXPECTED = {
    "jobs": {"MEDIA_JOBS_PREPARED_NOT_GENERATED"},
    "images": {"IMAGES_GENERATED_PENDING_QA"},
    "voice": {"VOICES_GENERATED_PENDING_QA"},
    "structural": {"MEDIA_STRUCTURALLY_READY_PENDING_QA"},
    "decode": {"MEDIA_DECODED_PENDING_QA"},
    "review": {"ASSETS_QA_READY_FOR_RENDER"},
    "master": {"MASTER_INVENTORIED_NOT_TRANSFERRED"},
    "transfer": {"TRANSFERRED_TO_PI_HASH_VERIFIED", "ALREADY_TRANSFERRED_HASH_VERIFIED"},
}
REQUIRED_STAGES = tuple(EXPECTED)


def readiness(root):
    report = summarize(root)
    observed = {item["stage"]: item["status"] for item in report["steps"]}
    incomplete = [name for name in REQUIRED_STAGES
                  if observed.get(name) not in EXPECTED[name]]
    return {
        "status": "M67_EVIDENCE_INVENTORY_COMPLETE_NOT_HARDWARE_VERIFIED"
                  if not incomplete else "M67_EVIDENCE_INCOMPLETE",
        "incomplete_stages": incomplete,
        "observed": observed,
        "pi_private_upload_confirmed": False,
        "owner_private_video_review_confirmed": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args(argv)
    print(json.dumps(readiness(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
