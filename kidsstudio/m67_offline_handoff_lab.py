"""M67 offline end-to-end handoff acceptance lab.

Simulates file production, hash inventory, transfer verification, Pi receipt
validation and the no-upload policy boundary. Does not call YouTube, SSH,
ComfyUI or Godot. This is NOT a hardware acceptance test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from .m67_master_handoff import inventory, verify_inventory
from .m67_pi_receipts_preflight import preflight
from .youtube_private_upload import file_sha256


def run_lab(workspace=None):
    def execute(root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        movie = root / "episode.mp4"
        # Fixture intentionally not a playable MP4; only the handoff and
        # receipt contract is under test.
        movie.write_bytes(b"offline handoff contract fixture")
        manifest = inventory(root, master=movie, episode_id="colors-ar-001")
        verified = verify_inventory(root, manifest)
        ready = root / "m8_readiness.json"
        ready.write_text('{"fixture":true}')
        plan = root / "private_upload_plan.json"
        plan.write_text(json.dumps({
            "render_job_id": "a" * 32,
            "master_sha256": file_sha256(movie),
            "readiness_sha256": file_sha256(ready)}))
        receipt = preflight(master=movie, plan=plan, readiness=ready,
                            render_job_id="a" * 32,
                            expected_sha256=verified["sha256"])
        plan.write_text(json.dumps({
            "render_job_id": "a" * 32,
            "master_sha256": file_sha256(movie),
            "readiness_sha256": "0" * 64}))
        tampered = preflight(master=movie, plan=plan, readiness=ready,
                             render_job_id="a" * 32,
                             expected_sha256=verified["sha256"])
        ok = (receipt["status"] == "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL"
              and tampered["status"] == "M67_PI_RECEIPTS_BLOCKED")
        return {
            "status": "OFFLINE_HANDOFF_CONTRACT_PASS" if ok else "BLOCKED",
            "cases": {"master_inventory": manifest["status"],
                      "master_integrity": verified["status"],
                      "matching_receipts": receipt["status"],
                      "tampered_receipts": tampered["status"]},
            "network_used": False,
            "youtube_uploaded": False,
            "public_release_authorized": False,
        }
    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="kidsstudio-m67-lab-") as temp:
            return execute(temp)
    workspace = Path(workspace)
    if workspace.exists() or workspace.is_symlink():
        raise FileExistsError("fresh lab workspace required")
    return execute(workspace)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path)
    args = p.parse_args(argv)
    report = run_lab(args.workspace)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "OFFLINE_HANDOFF_CONTRACT_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
