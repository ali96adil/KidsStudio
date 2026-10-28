"""M9 offline acceptance inventory for the single final owner Mac/Pi test.

Read-only: never activates agents, runs ML models, changes SQLite, uploads,
publishes, migrates or even marks a milestone as production-validated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .backup_drill import restore_drill, BackupError
from .private_release import check_readiness, PrivateReleaseError
from .studio_queue import StudioQueue

HEX=re.compile(r"^[a-f0-9]{64}$")
ID=re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

REQUIRED_TABLES=("jobs","settings","studio_series","studio_episodes",
                 "studio_episode_stages","studio_quality_reviews")


class AcceptanceError(ValueError):
    """Database or production provenance is inconsistent."""


def _table_exists(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone())


def _receipt(job: sqlite3.Row | None, kind: str, expected: str) -> bool:
    if job is None or job["kind"]!=kind or job["state"]!="COMPLETED":
        return False
    try:
        r=json.loads(job["result_json"] or "{}")
    except (TypeError, ValueError):
        return False
    return (r.get("status",r.get("result_status"))==expected and
            isinstance(r.get("artifact_sha256"),str) and
            HEX.fullmatch(r["artifact_sha256"]) is not None and
            r.get("publication_approved") is False)


def inspect_studio(queue: StudioQueue, *, backup_file: str | Path | None = None,
                   archive_dir: str | Path | None = None,
                   series_id: str | None = None,
                   ordinal: int | None = None) -> dict[str, Any]:
    if bool(archive_dir) != (series_id is not None and ordinal is not None):
        raise AcceptanceError("Archive check needs archive, series and episode together.")
    findings=[]
    def add(code, status, action, *, count=None):
        finding={"code":code,"status":status,"next_action":action}
        if count is not None:
            finding["count"]=count
        findings.append(finding)
    if not queue.path.is_file():
        raise AcceptanceError("Existing Studio Brain DB required; nothing was auto-initialized.")
    with queue._connection() as db:
        if [row[0] for row in db.execute("PRAGMA integrity_check")]!=["ok"]:
            raise AcceptanceError("Studio Brain SQLite integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise AcceptanceError("Studio Brain has broken foreign-key references.")
        missing=[name for name in REQUIRED_TABLES if not _table_exists(db,name)]
        if missing:
            add("required_schema","BLOCKED",
                "Initialize missing M3/M6/M7 schema before any production test.",
                count=len(missing))
            return {
              "schema_version":1,
              "status":"BLOCKED_LOCAL_SCHEMA_INCOMPLETE",
              "created_at":datetime.now(timezone.utc).isoformat(),
              "findings":findings,"owner_device_qualified":False,
              "full_episode_rendered_on_owner_mac":False,
              "public_release_authorized":False,
            }
        add("required_schema","PASS","No action: required schema exists.")
        series=db.execute("""SELECT series_id,title,state FROM studio_series
                            ORDER BY created_at,series_id""").fetchall()
        active=[x for x in series if x["state"]=="ACTIVE"]
        add("active_series","PASS" if len(active)==1 else "ACTION",
            "Keep exactly one active curriculum, with ordered episodes.",
            count=len(active))
        episodes=db.execute("""SELECT * FROM studio_episodes
            ORDER BY series_id,ordinal""").fetchall()
        if not episodes:
            add("episodes","ACTION","Seed an original complete planned curriculum.",count=0)
        else:
            add("episodes","PASS","Review ordered syllabus and language choices.",
                count=len(episodes))
        broken=[]
        for series_row in series:
            ordinals=[e["ordinal"] for e in episodes
                      if e["series_id"]==series_row["series_id"]]
            if ordinals != list(range(1,len(ordinals)+1)):
                broken.append("curriculum_gap")
        for ep in episodes:
            sid,no,state=ep["series_id"],ep["ordinal"],ep["state"]
            render_id=ep["render_job_id"]
            if state in ("DRAFT_QUEUED","REVIEW_QUEUED"):
                job=db.execute("SELECT kind,state FROM jobs WHERE job_id=?",
                               (ep["draft_job_id"],)).fetchone()
                if not job or job["kind"]!="script_draft":
                    broken.append("missing_draft_job")
            if state in ("RENDER_QUEUED","RENDERED_QA_PENDING","EPISODE_APPROVED"):
                job=db.execute("SELECT * FROM jobs WHERE job_id=?",(render_id,)).fetchone()
                if (not job or job["kind"] not in ("godot_render","episode_assemble")
                    or state in ("RENDERED_QA_PENDING","EPISODE_APPROVED") and
                    not _receipt(job,job["kind"],
                         "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW")):
                    broken.append("render_lineage")
                if state=="EPISODE_APPROVED":
                    qa=db.execute("""SELECT state,checks_passed,media_sha256 FROM
                      studio_quality_reviews WHERE series_id=? AND ordinal=?
                      AND render_job_id=?""",(sid,no,render_id)).fetchone()
                    if not qa or qa["state"]!="READY_FOR_OWNER_EPISODE_APPROVAL" or qa["checks_passed"]!=11:
                        broken.append("approved_episode_missing_m7")
                    elif job:
                        try: sha=json.loads(job["result_json"] or "{}").get("artifact_sha256")
                        except (TypeError,ValueError): sha=None
                        if sha!=qa["media_sha256"]:
                            broken.append("mismatched_qa_hash")
            rows=db.execute("""SELECT stage,state,script_sha256,source_voice_sha256,
                         artifact_sha256,job_id FROM studio_episode_stages
                         WHERE series_id=? AND ordinal=?""",(sid,no)).fetchall()
            if rows:
                tags={x["stage"]:x for x in rows}
                if any(x["script_sha256"]!=ep["source_sha256"] for x in rows):
                    broken.append("stage_script_diverged")
                if tags.get("ltx_animate"):
                    voice=tags.get("voice_synthesize")
                    ltx=tags["ltx_animate"]
                    if (not voice or not ltx["source_voice_sha256"] or
                        ltx["source_voice_sha256"]!=voice["artifact_sha256"]):
                        broken.append("stage_voice_diverged")
                for stage in rows:
                    j=db.execute("SELECT * FROM jobs WHERE job_id=?",
                                 (stage["job_id"],)).fetchone() if stage["job_id"] else None
                    if (stage["state"] in ("PENDING_QA","QA_APPROVED")
                        and not _receipt(j,stage["stage"],
                            "VOICE_RENDERED_PENDING_QA" if stage["stage"]=="voice_synthesize"
                            else "A2V_RENDERED_PENDING_QA")):
                        broken.append("unverified_media_stage")
        add("provenance","BLOCKED" if broken else "PASS",
            "Reconcile mismatched queue and per-render QA receipts before acceptance."
             if broken else "No broken stored job references detected.",
            count=len(broken))
        pending=db.execute("""SELECT state,COUNT(*) AS n FROM studio_episodes
                             GROUP BY state""").fetchall()
        counts={r["state"]:r["n"] for r in pending}
        open_jobs=db.execute("""SELECT COUNT(*) FROM jobs
                                WHERE state IN ('QUEUED','LEASED')""").fetchone()[0]
        add("queue_drain","PASS" if open_jobs==0 else "ACTION",
            "Stop/finish pending worker jobs before the final frozen snapshot.",
            count=open_jobs)
        add("first_real_episode",
            "ACTION" if counts.get("EPISODE_APPROVED",0)==0 else "PASS",
            "Generate, watch and review one complete real episode on the owner Mac.",
            count=counts.get("EPISODE_APPROVED",0))
    backup_result=None
    if backup_file is None:
        add("restore_drill","ACTION",
            "Create a private consistent SQLite backup and run sacrificial restore drill.")
    else:
        try:
            backup_result=restore_drill(backup_file)
            add("restore_drill","PASS","Restore drill verified in isolated temporary database.")
        except (BackupError,sqlite3.DatabaseError,OSError,ValueError):
            add("restore_drill","BLOCKED","Fix or replace unverified backup; do not overwrite production.")
    preview_result=None
    if archive_dir is None:
        add("private_preview","ACTION",
            "Provide verified archive and selected episode after human QA; never upload automatically.")
    else:
        try:
            preview_result=check_readiness(queue,archive_dir,
                                            series_id=series_id,ordinal=ordinal)
            add("private_preview","PASS",
                "Owner may separately authorize manual PRIVATE preview; not uploaded.")
        except (PrivateReleaseError,OSError,ValueError,KeyError):
            add("private_preview","BLOCKED",
                "Reconcile archive hashes with current render, M7 QA and script.")
    # NOT possible to prove engine operation, licenses or educational
    # effectiveness from a repository-only tool or database snapshot.
    add("live_chatterbox_ltx","DEVICE_TEST_REQUIRED",
        "Qualify the exact installed Apple Silicon Chatterbox/LTX wrappers and model weights.")
    add("owner_artistic_educational_rights","HUMAN_REVIEW_REQUIRED",
        "Watch real rendered episode; verify original content, learning and commercial rights.")
    add("separate_backup","ACTION",
        "Copy encrypted backups to independent storage and test recovery (manual owner decision).")
    hard=any(x["status"]=="BLOCKED" for x in findings)
    action=any(x["status"]=="ACTION" for x in findings)
    return {
        "schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),
        "status":("BLOCKED_RECONCILIATION" if hard else
                  "INTEGRATION_PREPARATION_INCOMPLETE" if action else
                  "CODE_HANDOFF_READY_DEVICE_ACCEPTANCE_REQUIRED"),
        "findings":findings,
        "episode_states":counts,"series_total":len(series),
        "active_series_count":len(active),
        "backup_drill_status":backup_result["status"] if backup_result else "NOT_PROVEN",
        "private_preview_status":preview_result["status"] if preview_result else "NOT_PROVEN",
        "owner_device_qualified":False,
        "full_episode_rendered_on_owner_mac":False,
        "public_release_authorized":False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-acceptance-review")
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--backup",type=Path)
    p.add_argument("--archive",type=Path)
    p.add_argument("--series")
    p.add_argument("--episode",type=int)
    args=p.parse_args(argv)
    try:
        report=inspect_studio(StudioQueue(args.db),backup_file=args.backup,
                              archive_dir=args.archive,series_id=args.series,
                              ordinal=args.episode)
    except (AcceptanceError,sqlite3.DatabaseError,OSError,ValueError) as exc:
        print("STUDIO_ACCEPTANCE_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
