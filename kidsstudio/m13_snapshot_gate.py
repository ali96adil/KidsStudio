"""M20 — immutable offline M13 Studio Brain snapshot versus M19 Mac scene handoff.

Read ONLY an independently owner-pinned, WAL-free, consistent SQLite backup,
not the live Pi database. A file copy or claimed origin does not attest to
Pi identity/freshness. No worker, GPU, network, migration or publishing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .episode_assembly import _ensure_private, digest
from .mac_contract import MacIntakeError
from .engine_qualification import EngineQualificationError
from .handoff_review import HandoffError
from .two_scene_preflight import (
    PilotPreflightError, inspect_two_scene_voice_pilot,
)
from .voice_animation_stage import StageError

SHA = re.compile(r"^[0-9a-f]{64}$")
TABLES = frozenset({
    "studio_series", "studio_episodes", "studio_series_audit",
    "studio_scene_plans", "studio_scenes", "studio_scene_stages",
})


class SnapshotGateError(ValueError):
    """Immutable offline M13 snapshot is unsafe, missing or inconsistent."""


def _approved_snapshot(file: str | Path, expected_sha256: str,
                       approved_root: Path) -> Path:
    requested = Path(file).expanduser()
    if (not requested.is_absolute() or requested.is_symlink()
            or not isinstance(expected_sha256, str)
            or not SHA.fullmatch(expected_sha256)):
        raise SnapshotGateError("Exact SHA and absolute non-symlink offline snapshot required.")
    resolved = requested.resolve()
    _ensure_private(resolved.parent)
    if (not resolved.is_relative_to(approved_root)
            or not resolved.is_file() or resolved.suffix not in (".db", ".sqlite")
            or not 0 < resolved.stat().st_size <= 250_000_000):
        raise SnapshotGateError("Offline Studio Brain snapshot missing or outside approved root.")
    # immutable=1 deliberately ignores WAL. Thus, it is UNSAFE for a live
    # WAL-backed database. Require a standalone checkpointed sqlite backup.
    if any(Path(str(resolved) + side).exists() for side in ("-wal", "-shm", "-journal")):
        raise SnapshotGateError("Snapshot has SQLite live database sidecars.")
    if digest(resolved) != expected_sha256:
        raise SnapshotGateError("Offline SQLite backup changed since owner pinned it.")
    return resolved


def verify_two_scene_snapshot(
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
    mac_report = inspect_two_scene_voice_pilot(
        mac_contract, scene_plan,
        expected_plan_sha256=expected_plan_sha256,
        scene_scripts=scene_scripts, voice_recipes=voice_recipes,
        system=system, arch=arch, memory_bytes=memory_bytes, free_bytes=free_bytes,
    )
    mac_path = Path(mac_contract).expanduser().resolve()
    obj = json.loads(mac_path.read_text(encoding="utf-8"))
    root = _ensure_private(Path(obj["private_roots"][0]))
    backup = _approved_snapshot(pi_snapshot, pi_snapshot_sha256, root)
    local_plan = json.loads(Path(scene_plan).read_text(encoding="utf-8"))
    sid = mac_report["series_id"]
    ordinal = mac_report["episode_number"]

    # mode=ro+immutable=1 never writes shm/wal or alters a snapshot.
    # A consistent backup is required by the caller, not made implicitly.
    url = backup.as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(url, uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if [r[0] for r in db.execute("PRAGMA integrity_check")] != ["ok"]:
            raise SnapshotGateError("Snapshot SQLite integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise SnapshotGateError("Snapshot foreign keys invalid.")
        existing = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not TABLES.issubset(existing):
            raise SnapshotGateError("Offline M13 schema missing.")
        active = db.execute(
            "SELECT COUNT(*) FROM studio_series WHERE state='ACTIVE'"
        ).fetchone()[0]
        series = db.execute(
            "SELECT state,language FROM studio_series WHERE series_id=?", (sid,)
        ).fetchone()
        ep = db.execute(
            "SELECT state,source_sha256,owner_review_note,revision "
            "FROM studio_episodes WHERE series_id=? AND ordinal=?",
            (sid, ordinal),
        ).fetchone()
        plan_row = db.execute(
            "SELECT plan_sha256,episode_script_sha256 FROM studio_scene_plans "
            "WHERE series_id=? AND ordinal=?", (sid, ordinal)
        ).fetchone()
        if (active != 1 or series is None or series["state"] != "ACTIVE"
                or series["language"] not in ("ar", "en")
                or ep is None or ep["state"] != "SCRIPT_APPROVED"
                or ep["source_sha256"] != mac_report["parent_script_sha256"]
                or not isinstance(ep["owner_review_note"], str)
                or len(ep["owner_review_note"].strip()) < 5
                or type(ep["revision"]) is not int or ep["revision"] < 1
                or plan_row is None
                or plan_row["plan_sha256"] != expected_plan_sha256
                or plan_row["episode_script_sha256"] != ep["source_sha256"]):
            raise SnapshotGateError("Active parent approval or pinned M13 plan mismatch.")
        audit = db.execute(
            "SELECT COUNT(*) FROM studio_series_audit WHERE series_id=? "
            "AND ordinal=? AND action='SCRIPT_APPROVED_BY_OWNER'",
            (sid, ordinal),
        ).fetchone()[0]
        if audit < 1:
            raise SnapshotGateError("Owner-approved episode audit record absent.")
        rows = db.execute(
            "SELECT scene,script_sha256,objective FROM studio_scenes "
            "WHERE series_id=? AND ordinal=? ORDER BY scene",
            (sid, ordinal),
        ).fetchall()
        if len(rows) != 2:
            raise SnapshotGateError("Offline M13 scene count is not two.")
        for index, row in enumerate(rows):
            local = local_plan["scenes"][index]
            if (type(row["scene"]) is not int or row["scene"] != index + 1
                    or row["script_sha256"] != local["script_sha256"]
                    or row["script_sha256"] !=
                    mac_report["scenes"][index]["scene_script_sha256"]
                    or row["objective"] != local["objective"].strip()):
                raise SnapshotGateError("M13 canonical scene differs from Mac scene plan.")
        # The first voice pilot must not silently duplicate already queued or
        # completed local M13 media work. An operator can reconcile separately.
        started = db.execute(
            "SELECT COUNT(*) FROM studio_scene_stages "
            "WHERE series_id=? AND ordinal=?", (sid, ordinal)
        ).fetchone()[0]
        if started:
            raise SnapshotGateError("Scene work already has M13 stage records.")
    if digest(backup) != pi_snapshot_sha256:
        raise SnapshotGateError("Offline snapshot mutated during verification.")
    if digest(Path(scene_plan)) != expected_plan_sha256:
        raise SnapshotGateError("Scene plan mutated during verification.")

    return {
        "schema_version": 1,
        "status": "OFFLINE_M13_SNAPSHOT_MATCH_NOT_LIVE_PI_ATTESTED",
        "series_id": sid,
        "episode_number": ordinal,
        "episode_revision": ep["revision"],
        "scene_count": 2,
        "scene_plan_sha256": expected_plan_sha256,
        "snapshot_sha256": pi_snapshot_sha256,
        "mac_contract_sha256": mac_report["mac_contract_sha256"],
        "owner_approval_record_found_in_snapshot": True,
        "offline_scene_records_match": True,
        "snapshot_originally_came_from_pi_proven": False,
        "snapshot_freshness_verified": False,
        "live_pi_state_verified": False,
        "model_inference_performed": False,
        "any_worker_jobs_queued": False,
        "media_generated": False,
        "publication_approved": False,
        "next_action": "At owner device acceptance, authenticate current Pi "
                       "state and reconcile snapshot freshness before any "
                       "Chatterbox model execution; review real wrapper and rights.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-m13-snapshot-gate",
        description="Read-only M13 offline SQLite snapshot + M19 Mac handoff.")
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
    try:
        result = verify_two_scene_snapshot(
            args.mac_contract, args.scene_plan,
            expected_plan_sha256=args.scene_plan_sha256,
            scene_scripts=(args.scene_1_script, args.scene_2_script),
            voice_recipes=(args.scene_1_voice_recipe, args.scene_2_voice_recipe),
            pi_snapshot=args.pi_snapshot, pi_snapshot_sha256=args.pi_snapshot_sha256,
        )
    except (SnapshotGateError, PilotPreflightError, HandoffError,
            MacIntakeError, EngineQualificationError, StageError,
            sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        print("M13_SNAPSHOT_GATE_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
