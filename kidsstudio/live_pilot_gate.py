"""M21: authenticated, read-only *current* Pi scene observation.

This is a narrowly scoped status probe, NOT a job claim or render license.
The caller supplies only approved identities and SHA256s; no artwork/text,
model commands, filesystem paths, tokens or authority to execute anything.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .studio_queue import StudioQueue

SHA = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")
IDENT = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")


class LivePilotError(ValueError):
    """Authenticated M13 live observation is blocked or disagrees."""


def observe_live_scene_plan(queue: StudioQueue, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) != {
        "nonce", "series_id", "episode_number", "episode_revision",
        "scene_plan_sha256", "parent_script_sha256", "scenes",
    }:
        raise LivePilotError("Strict read-only pilot request schema required.")
    sid = request["series_id"]
    ordinal = request["episode_number"]
    revision = request["episode_revision"]
    nonce = request["nonce"]
    if (not isinstance(nonce, str) or not NONCE.fullmatch(nonce)
            or not isinstance(sid, str) or not IDENT.fullmatch(sid)
            or type(ordinal) is not int or not 1 <= ordinal <= 120
            or type(revision) is not int or not 1 <= revision <= 1_000_000
            or any(not isinstance(request[k], str) or
                   not SHA.fullmatch(request[k]) for k in
                   ("scene_plan_sha256", "parent_script_sha256"))):
        raise LivePilotError("Invalid pilot identity, revision or SHA pins.")
    scenes = request["scenes"]
    if (not isinstance(scenes, list) or len(scenes) != 2
            or any(not isinstance(x, dict) or set(x) != {
                "scene", "script_sha256", "objective_sha256"} for x in scenes)):
        raise LivePilotError("Exactly two fully pinned scene descriptions required.")
    for i, scene in enumerate(scenes, 1):
        if (type(scene["scene"]) is not int or scene["scene"] != i or
                any(not isinstance(scene[k], str) or not SHA.fullmatch(scene[k])
                    for k in ("script_sha256", "objective_sha256"))):
            raise LivePilotError("Scene pins or order invalid.")
    if scenes[0]["script_sha256"] == scenes[1]["script_sha256"]:
        raise LivePilotError("Distinct scripts required.")

    # A deferred transaction gives all SELECTs a coherent point-in-time
    # SQLite snapshot; no writes, leases, side effects or backup files.
    with queue._connection() as db:
        db.execute("BEGIN")
        if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
            raise LivePilotError("Coordinator is paused.")
        active = db.execute(
            "SELECT COUNT(*) FROM studio_series WHERE state='ACTIVE'"
        ).fetchone()[0]
        ep = db.execute("""SELECT e.state,e.source_sha256,e.revision,
            e.owner_review_note,s.state AS series_state FROM studio_episodes e
            JOIN studio_series s USING(series_id)
            WHERE e.series_id=? AND e.ordinal=?""", (sid, ordinal)).fetchone()
        plan = db.execute("""SELECT plan_sha256,episode_script_sha256
            FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
            (sid, ordinal)).fetchone()
        if (active != 1 or ep is None or ep["state"] != "SCRIPT_APPROVED"
                or ep["series_state"] != "ACTIVE" or ep["revision"] != revision
                or ep["source_sha256"] != request["parent_script_sha256"]
                or not isinstance(ep["owner_review_note"], str)
                or len(ep["owner_review_note"].strip()) < 5
                or plan is None or plan["plan_sha256"] != request["scene_plan_sha256"]
                or plan["episode_script_sha256"] != ep["source_sha256"]):
            raise LivePilotError("Current Pi episode revision/plan is not approved.")
        from .script_gate import current_script_mode
        if current_script_mode(db,sid,ordinal) is None:
            raise LivePilotError("Current owner or M30 independent AI script proof missing.")
        actual = db.execute("""SELECT scene,script_sha256,objective
            FROM studio_scenes WHERE series_id=? AND ordinal=?
            ORDER BY scene""", (sid, ordinal)).fetchall()
        if len(actual) != 2:
            raise LivePilotError("Current Pi episode has wrong number of scenes.")
        import hashlib
        for i, row in enumerate(actual):
            objective_sha = hashlib.sha256(
                row["objective"].encode("utf-8")).hexdigest()
            if (row["scene"] != scenes[i]["scene"]
                    or row["script_sha256"] != scenes[i]["script_sha256"]
                    or objective_sha != scenes[i]["objective_sha256"]):
                raise LivePilotError("Current Pi scene differs from owner-pinned plan.")
        if db.execute("""SELECT 1 FROM studio_scene_stages
            WHERE series_id=? AND ordinal=? LIMIT 1""",
            (sid, ordinal)).fetchone():
            raise LivePilotError("Existing Pi stage work requires owner reconciliation.")
        # The status request must not claim an active lease; any episode work
        # queued elsewhere remains outside the authority of this status gate.
        import time
        observed_at = time.time()
        db.execute("COMMIT")

    return {
        "schema_version": 1,
        "status": "CURRENT_PI_M13_SCENES_MATCH_NO_JOB_CLAIMED",
        "nonce": nonce,
        "series_id": sid,
        "episode_number": ordinal,
        "episode_revision": revision,
        "scene_plan_sha256": request["scene_plan_sha256"],
        "parent_script_sha256": request["parent_script_sha256"],
        "scenes": scenes,
        "observed_at": observed_at,
        "jobs_claimed": False,
        "model_execution_authorized": False,
        "publication_approved": False,
    }
