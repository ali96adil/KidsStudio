"""M8 owner-only readiness attestation for a later MANUAL private video upload.

Requires fully accepted episode, CURRENT render job QA, and a verified
immutable private archive. This module DOES NOT upload or contact YouTube.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from .private_archive import verify_archive, ArchiveError
from .studio_queue import StudioQueue

SHA=re.compile(r"^[a-f0-9]{64}$")


class PrivateReleaseError(ValueError):
    """Episode is not qualified for a manually initiated private preview."""


def check_readiness(queue: StudioQueue, archive_dir: str | Path,
                    *, series_id: str, ordinal: int) -> dict[str, Any]:
    if not isinstance(series_id,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,47}",series_id):
        raise PrivateReleaseError("Invalid series identifier.")
    if type(ordinal) is not int or ordinal<1 or ordinal>120:
        raise PrivateReleaseError("Invalid episode number.")
    archive=verify_archive(archive_dir)
    if archive["series_id"]!=series_id or archive["episode_number"]!=ordinal:
        raise PrivateReleaseError("Archive belongs to a different episode.")
    with queue._connection() as db:
        ep=db.execute("""SELECT * FROM studio_episodes
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
        if ep is None or ep["state"]!="EPISODE_APPROVED":
            raise PrivateReleaseError("Final internal owner approval missing.")
        if not ep["render_job_id"] or not ep["source_sha256"] or not SHA.fullmatch(ep["source_sha256"]):
            raise PrivateReleaseError("Approved script/render lineage missing.")
        job=db.execute("""SELECT state,kind,result_json FROM jobs WHERE job_id=?""",
                       (ep["render_job_id"],)).fetchone()
        if job is None or job["state"]!="COMPLETED" or job["kind"] not in (
                "episode_assemble","godot_render"):
            raise PrivateReleaseError("Completed private render receipt missing.")
        receipt=json.loads(job["result_json"] or "{}")
        video_sha=receipt.get("artifact_sha256")
        if (receipt.get("status",receipt.get("result_status")) !=
                "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW" or
            not isinstance(video_sha,str) or not SHA.fullmatch(video_sha) or
            receipt.get("artifact_type")!="mp4" or
            receipt.get("publication_approved") is not False):
            raise PrivateReleaseError("Render receipt is not a verified private MP4.")
        qa_table=db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_quality_reviews'""").fetchone()
        if qa_table is None:
            raise PrivateReleaseError("M7 final QA schema missing.")
        qa=db.execute("""SELECT * FROM studio_quality_reviews
            WHERE series_id=? AND ordinal=? AND render_job_id=?""",
            (series_id,ordinal,ep["render_job_id"])).fetchone()
        if (qa is None or qa["state"]!="READY_FOR_OWNER_EPISODE_APPROVAL" or
            qa["checks_passed"]!=11 or
            not qa["review_report_sha256"] or
            not SHA.fullmatch(qa["review_report_sha256"]) or
            not SHA.fullmatch(qa["tech_report_sha256"]) or
            qa["media_sha256"]!=video_sha):
            raise PrivateReleaseError("M7 technical and human QA on current render required.")
        stages=db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_episode_stages'""").fetchone()
        if stages:
            current=db.execute("""SELECT stage,state,script_sha256,job_id,artifact_sha256,source_voice_sha256
                FROM studio_episode_stages
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchall()
            if current and (
                len(current)!=2 or
                {x["stage"] for x in current}!={"voice_synthesize","ltx_animate"} or
                any(x["state"]!="QA_APPROVED" or
                    x["script_sha256"]!=ep["source_sha256"] for x in current)
            ):
                raise PrivateReleaseError("Audio/animation stage QA incomplete.")
            if current:
                approved={item["stage"]:item for item in current}
                voice,ltx=approved["voice_synthesize"],approved["ltx_animate"]
                if (ltx["source_voice_sha256"]!=voice["artifact_sha256"] or
                    not isinstance(voice["artifact_sha256"],str) or
                    not SHA.fullmatch(voice["artifact_sha256"]) or
                    not isinstance(ltx["artifact_sha256"],str) or
                    not SHA.fullmatch(ltx["artifact_sha256"])):
                    raise PrivateReleaseError("Voice and LTX content provenance diverged.")
                for kind,item,status,typ in (
                    ("voice_synthesize",voice,"VOICE_RENDERED_PENDING_QA","wav"),
                    ("ltx_animate",ltx,"A2V_RENDERED_PENDING_QA","mp4")
                ):
                    source=db.execute("""SELECT kind,state,result_json FROM jobs
                        WHERE job_id=?""",(item["job_id"],)).fetchone()
                    try:
                        data=json.loads(source["result_json"] or "{}") if source else {}
                    except (TypeError,ValueError):
                        data={}
                    if (not source or source["kind"]!=kind or
                        source["state"]!="COMPLETED" or
                        data.get("status")!=status or
                        data.get("artifact_type")!=typ or
                        data.get("artifact_sha256")!=item["artifact_sha256"] or
                        data.get("publication_approved") is not False):
                        raise PrivateReleaseError("Unverified Pi media receipt in staged episode.")
            if current and db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='studio_audio_checks'""").fetchone():
                lineage=db.execute("""SELECT stage,job_id,artifact_sha256 FROM
                    studio_episode_stages WHERE series_id=? AND ordinal=?""",
                    (series_id,ordinal)).fetchall()
                kinds={item["stage"]:item for item in lineage}
                voice=kinds.get("voice_synthesize")
                ltx=kinds.get("ltx_animate")
                audio=(db.execute("""SELECT voice_sha256,a2v_sha256,status
                     FROM studio_audio_checks WHERE series_id=? AND ordinal=?
                     AND ltx_job_id=?""",
                     (series_id,ordinal,ltx["job_id"])).fetchone()
                     if voice and ltx else None)
                if (not audio or
                    audio["voice_sha256"]!=voice["artifact_sha256"] or
                    audio["a2v_sha256"]!=ltx["artifact_sha256"] or
                    audio["status"]!="TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING"):
                    raise PrivateReleaseError("Current LTX audio technical evidence missing.")
    items={x["role"]:x["sha256"] for x in archive["files"]}
    for role, expected in (
        ("episode_master",video_sha),
        ("approved_script",ep["source_sha256"]),
        ("technical_qa",qa["tech_report_sha256"]),
        ("owner_qa",qa["review_report_sha256"]),
    ):
        if items.get(role)!=expected:
            raise PrivateReleaseError(f"Archived {role} differs from approved receipt.")
    return {
        "schema_version":1,
        "status":"READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED",
        "series_id":series_id,"episode_number":ordinal,
        "render_job_id":ep["render_job_id"],
        "video_sha256":video_sha,
        "archive_manifest_sha256":archive["archive_manifest_sha256"],
        "owner_final_qa":True,
        "upload_performed":False,"video_visibility":"NOT_SET",
        "public_release_authorized":False,
        "next_action":"Owner manually reviews private-upload settings and authorizes separately.",
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-private-readiness")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--series",required=True)
    p.add_argument("--episode",type=int,required=True)
    args=p.parse_args(argv)
    try:
        report=check_readiness(StudioQueue(args.db),args.archive,
                               series_id=args.series,ordinal=args.episode)
    except (PrivateReleaseError,ArchiveError,OSError,ValueError,KeyError) as exc:
        print("PRIVATE_PREVIEW_NOT_READY: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
