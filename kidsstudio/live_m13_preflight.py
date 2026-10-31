"""M21: two-step M20 offline + live authenticated Pi M13 check.

Never starts an ML model, claims a lease, queues a scene or publishes.
A TLS freshness observation is not an authorization to actuate the Mac:
the owner must separately approve a real stage and obtain a proper job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any

from .episode_assembly import digest
from .m13_snapshot_gate import verify_two_scene_snapshot, SnapshotGateError
from .remote_worker import RemoteClient, RemoteWorkerError

SHA = re.compile(r"^[0-9a-f]{64}$")
TOKEN_VAR = re.compile(r"^[A-Z][A-Z0-9_]{4,90}$")


class LivePreflightError(ValueError):
    """No verified agreement between offline plan and current Pi observation."""


def verify_live_two_scene_pilot(
    client: RemoteClient,
    mac_contract: str | Path,
    scene_plan: str | Path,
    *,
    expected_plan_sha256: str,
    scene_scripts: tuple[str | Path, str | Path],
    voice_recipes: tuple[str | Path, str | Path],
    pi_snapshot: str | Path,
    pi_snapshot_sha256: str,
    system: str | None = None,
    arch: str | None = None,
    memory_bytes: int | None = None,
    free_bytes: int | None = None,
) -> dict[str, Any]:
    if not isinstance(client, RemoteClient):
        raise LivePreflightError("Only verified remote TLS clients may check live Pi.")
    offline = verify_two_scene_snapshot(
        mac_contract, scene_plan,
        expected_plan_sha256=expected_plan_sha256,
        scene_scripts=scene_scripts, voice_recipes=voice_recipes,
        pi_snapshot=pi_snapshot, pi_snapshot_sha256=pi_snapshot_sha256,
        system=system, arch=arch, memory_bytes=memory_bytes,
        free_bytes=free_bytes,
    )
    plan_path = Path(scene_plan).expanduser().resolve()
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    if digest(plan_path) != expected_plan_sha256:
        raise LivePreflightError("Local scene plan changed after offline verification.")
    nonce = secrets.token_hex(16)
    scenes = [{
        "scene": row["scene"],
        "script_sha256": row["script_sha256"],
        "objective_sha256": hashlib.sha256(
            row["objective"].strip().encode("utf-8")).hexdigest(),
    } for row in data["scenes"]]
    request = {
        "nonce": nonce,
        "series_id": offline["series_id"],
        "episode_number": offline["episode_number"],
        "episode_revision": offline["episode_revision"],
        "scene_plan_sha256": expected_plan_sha256,
        "parent_script_sha256": offline["parent_script_sha256"] if
            "parent_script_sha256" in offline else data["episode_script_sha256"],
        "scenes": scenes,
    }
    response = client.call("pilot-readiness", request)
    expected_keys = set(request) | {
        "schema_version", "status", "observed_at", "jobs_claimed",
        "model_execution_authorized", "publication_approved", "server_time",
    }
    if (not isinstance(response, dict) or set(response) != expected_keys
            or response["schema_version"] != 1
            or response["status"] != "CURRENT_PI_M13_SCENES_MATCH_NO_JOB_CLAIMED"
            or any(response.get(k) != v for k,v in request.items())
            or response["jobs_claimed"] is not False
            or response["model_execution_authorized"] is not False
            or response["publication_approved"] is not False
            or type(response["observed_at"]) not in (int, float)
            or type(response["server_time"]) not in (int, float)
            or abs(response["observed_at"] - response["server_time"]) > 5
            or abs(time.time() - response["observed_at"]) > 15):
        raise LivePreflightError("TLS live observation is stale or mismatched.")
    if (digest(plan_path) != expected_plan_sha256 or
            digest(Path(pi_snapshot)) != pi_snapshot_sha256):
        raise LivePreflightError("Offline plan/snapshot mutated during TLS check.")
    return {
        "schema_version": 1,
        "status": "OFFLINE_AND_LIVE_M13_AGREE_OWNER_EXECUTION_NOT_AUTHORIZED",
        "series_id": request["series_id"],
        "episode_number": request["episode_number"],
        "episode_revision": request["episode_revision"],
        "scene_count": 2,
        "scene_plan_sha256": expected_plan_sha256,
        "offline_snapshot_sha256": pi_snapshot_sha256,
        "live_pi_observed_at": response["observed_at"],
        "live_pi_observed_over_authenticated_tls": True,
        "target_episode_matches_offline_at_observation": True,
        "whole_snapshot_freshness_proven": False,
        "ongoing_live_state_guaranteed": False,
        "model_execution_performed": False,
        "worker_job_claimed": False,
        "owner_device_artistic_and_rights_qa": False,
        "public_release_authorized": False,
        "next_action": "Stop here. Recheck before a separately owner-approved "
                       "leased voice run; actual MLX wrapper and commercial "
                       "rights remain unverified.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-live-m13-preflight",
        description="Read-only HTTPS check after M20 offline SHA snapshot verification.")
    p.add_argument("--coordinator", required=True)
    p.add_argument("--ca-cert", required=True,
                   help="Owner-pinned private Pi TLS certificate or CA")
    p.add_argument("--worker-id", default="mac-voice-01")
    p.add_argument("--token-env", default="KIDS_STUDIO_WORKER_TOKEN")
    p.add_argument("--mac-contract", type=Path, required=True)
    p.add_argument("--scene-plan", type=Path, required=True)
    p.add_argument("--scene-plan-sha256", required=True)
    p.add_argument("--scene-1-script", type=Path, required=True)
    p.add_argument("--scene-1-voice-recipe", type=Path, required=True)
    p.add_argument("--scene-2-script", type=Path, required=True)
    p.add_argument("--scene-2-voice-recipe", type=Path, required=True)
    p.add_argument("--pi-snapshot", type=Path, required=True)
    p.add_argument("--pi-snapshot-sha256", required=True)
    args = p.parse_args(argv)
    if not TOKEN_VAR.fullmatch(args.token_env):
        p.error("Invalid token environment variable name.")
    try:
        client = RemoteClient(
            args.coordinator, worker_id=args.worker_id,
            token=os.environ.get(args.token_env, ""),
            ca_file=args.ca_cert,
        )
        report = verify_live_two_scene_pilot(
            client, args.mac_contract, args.scene_plan,
            expected_plan_sha256=args.scene_plan_sha256,
            scene_scripts=(args.scene_1_script, args.scene_2_script),
            voice_recipes=(args.scene_1_voice_recipe, args.scene_2_voice_recipe),
            pi_snapshot=args.pi_snapshot,
            pi_snapshot_sha256=args.pi_snapshot_sha256,
        )
    except (LivePreflightError, SnapshotGateError, RemoteWorkerError,
            OSError, ValueError, TypeError, KeyError) as exc:
        print("M13_LIVE_PREFLIGHT_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
