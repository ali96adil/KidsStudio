"""M52 Pi-side immutable montage provenance check at worker job claim.

A queue insertion is not permanent permission to render. This gate observes
the current M32/M49/M51 SQLite source-of-truth in the SAME transaction that
grants a Mac worker lease. It never reads Mac private media or calls models.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

SHA = re.compile(r"^[a-f0-9]{64}$")
DEFERRED = "AFTER_SCENE_QA"


def _has_table(db: sqlite3.Connection, table: str) -> bool:
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def m32_montage_claim_blocker(db: sqlite3.Connection, job: Any) -> str | None:
    """Return a bounded reason, or None if permitted / not M32-managed.

    This function deliberately does not update or lease a job. A missing M32
    contract on a known M32 episode blocks claim, including old databases.
    """
    if job["kind"] != "episode_assemble":
        return None
    try:
        if not _has_table(db, "studio_orchestrator_plans"):
            return None  # Legacy standalone M4 job, never M32 registered.

        ep = db.execute("""SELECT e.series_id,e.ordinal,e.state,
            e.source_sha256,e.render_attempt,e.render_job_id,
            s.state AS series_state
            FROM studio_episodes e JOIN studio_series s
              ON s.series_id=e.series_id
            WHERE e.render_job_id=?""", (job["job_id"],)).fetchone()
        if ep is None:
            # An unlinked standalone queue job is not claimed as M32-approved.
            # This helper does not establish an OS/DB-writer security boundary.
            return None

        sid,ordinal=ep["series_id"],ep["ordinal"]
        pinned=db.execute("""SELECT plan_sha256,script_sha256,
            scene_plan_sha256 FROM studio_orchestrator_plans
            WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
        if pinned is None:
            return None  # Pre-M32 episode; preserve legacy owner workflow.

        for name in ("studio_orchestrator_render_contracts",
                     "studio_scene_plans","studio_scenes",
                     "studio_scene_stages"):
            if not _has_table(db,name):
                return "M52_MISSING_M32_SCHEMA"

        if (ep["state"]!="RENDER_QUEUED" or
            ep["series_state"]!="ACTIVE" or
            ep["render_job_id"]!=job["job_id"] or
            pinned["script_sha256"]!=ep["source_sha256"] or
            not isinstance(ep["source_sha256"],str) or
            not SHA.fullmatch(ep["source_sha256"])):
            return "M52_EPISODE_STATE_CHANGED"

        expected_key=(f"series:{sid}:episode:{ordinal}:"
                      f"render:episode_assemble:a{ep['render_attempt']}:"
                      f"{ep['source_sha256'][:16]}")
        if (job["request_key"]!=expected_key or
            job["max_attempts"]!=1):
            return "M52_RENDER_JOB_IDENTITY_CHANGED"

        try:
            payload=json.loads(job["payload"])
        except (ValueError,TypeError):
            return "M52_MALFORMED_RENDER_PAYLOAD"
        if (not isinstance(payload,dict) or
            set(payload)!={"recipe_id","script_sha256","catalogue_sha256"} or
            payload["script_sha256"]!=ep["source_sha256"] or
            not isinstance(payload["recipe_id"],str) or
            not isinstance(payload["catalogue_sha256"],str) or
            not SHA.fullmatch(payload["catalogue_sha256"])):
            return "M52_RENDER_PAYLOAD_CHANGED"

        contract=db.execute("""SELECT plan_sha256,recipe_id,
            catalogue_marker,scene_scripts_sha256
            FROM studio_orchestrator_render_contracts
            WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
        scene_plan=db.execute("""SELECT plan_sha256,episode_script_sha256
            FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
            (sid,ordinal)).fetchone()
        scenes=db.execute("""SELECT scene,script_sha256 FROM studio_scenes
            WHERE series_id=? AND ordinal=? ORDER BY scene""",
            (sid,ordinal)).fetchall()
        if (not contract or not scene_plan or
            contract["plan_sha256"]!=pinned["plan_sha256"] or
            contract["recipe_id"]!=payload["recipe_id"] or
            scene_plan["plan_sha256"]!=pinned["scene_plan_sha256"] or
            scene_plan["episode_script_sha256"]!=ep["source_sha256"] or
            not 2<=len(scenes)<=40 or
            any(row["scene"]!=i or
                not isinstance(row["script_sha256"],str) or
                not SHA.fullmatch(row["script_sha256"])
                for i,row in enumerate(scenes,1))):
            return "M52_ORCHESTRATION_CONTRACT_CHANGED"

        # Recompute exactly as M51; never trust a submitted scene-set hash.
        from .series_manager import scene_script_fingerprint
        if contract["scene_scripts_sha256"]!=scene_script_fingerprint(scenes):
            return "M52_SCENE_IDENTITY_CHANGED"
        from .studio_scenes import assert_scenes_ready
        ready=assert_scenes_ready(db,sid,ordinal,ep["source_sha256"])
        if len(ready)!=len(scenes):
            return "M52_SCENE_QA_CHANGED"

        marker=contract["catalogue_marker"]
        if marker==DEFERRED:
            if not _has_table(db,"studio_orchestrator_assembly_bindings"):
                return "M52_MISSING_ASSEMBLY_BINDING"
            binding=db.execute("""SELECT plan_sha256,catalogue_sha256,
                evidence_sha256,scene_set_sha256
                FROM studio_orchestrator_assembly_bindings
                WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
            current_set_sha=hashlib.sha256(json.dumps(
                ready,sort_keys=True,ensure_ascii=False,
                separators=(",",":"),allow_nan=False
            ).encode("utf-8")).hexdigest()
            if (not binding or
                binding["plan_sha256"]!=pinned["plan_sha256"] or
                binding["catalogue_sha256"]!=payload["catalogue_sha256"] or
                binding["scene_set_sha256"]!=current_set_sha or
                not isinstance(binding["evidence_sha256"],str) or
                not SHA.fullmatch(binding["evidence_sha256"])):
                return "M52_ASSEMBLY_BINDING_CHANGED"
        elif (not isinstance(marker,str) or
              not SHA.fullmatch(marker) or
              marker!=payload["catalogue_sha256"]):
            return "M52_CATALOGUE_PIN_CHANGED"
        return None
    except (sqlite3.Error,ValueError,TypeError,KeyError,IndexError):
        # Incomplete/corrupt M32 DB or stale stage evidence fails closed.
        return "M52_RENDER_PROVENANCE_UNVERIFIABLE"
