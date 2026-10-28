"""Local owner-only commands for the persistent series and episode planner."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .series_manager import SeriesError, SeriesManager
from .studio_queue import QueueError, StudioQueue
from .studio_stage_ledger import StageLedger, StageLedgerError
from .studio_quality_ledger import QualityLedger, QualityGateError
from .agent_final_qa import AgentFinalQA
from .studio_audio_ledger import AudioEvidenceLedger, AudioEvidenceError
from .studio_scenes import SceneLedger, SceneError
from .scene_ai_qa import SceneAIGate


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(prog="python -m kidsstudio.series_cli")
    parser.add_argument("--db",type=Path,required=True,
                        help="Existing local Studio Brain SQLite DB (outside Git)")
    commands=parser.add_subparsers(dest="cmd",required=True)
    commands.add_parser("init")
    add=commands.add_parser("add-series")
    add.add_argument("--plan",type=Path,required=True)
    add.add_argument("--activate",action="store_true")
    active=commands.add_parser("activate")
    active.add_argument("series_id")
    pause=commands.add_parser("pause")
    pause.add_argument("series_id")
    pause.add_argument("--reason",required=True)
    prepare=commands.add_parser("prepare")
    prepare.add_argument("--limit",type=int,default=3)
    commands.add_parser("sync")
    commands.add_parser("status")
    note=commands.add_parser("note")
    note.add_argument("series_id")
    note.add_argument("--episode",type=int)
    note.add_argument("--text",required=True)
    approve=commands.add_parser("approve-script")
    approve.add_argument("series_id")
    approve.add_argument("episode",type=int)
    approve.add_argument("--sha256",required=True)
    approve.add_argument("--note",required=True)
    render=commands.add_parser("queue-render")
    render.add_argument("series_id")
    render.add_argument("episode",type=int)
    render.add_argument("--recipe",required=True)
    render.add_argument("--media-kind",choices=["godot_render","episode_assemble"],default="godot_render")
    render.add_argument("--catalogue-sha256",help="Required exact M14 catalogue SHA for multi-scene render")
    retry=commands.add_parser("retry-blocked")
    retry.add_argument("series_id")
    retry.add_argument("episode",type=int)
    retry.add_argument("--reason",required=True)
    episode=commands.add_parser("approve-episode")
    episode.add_argument("series_id")
    episode.add_argument("episode",type=int)
    episode.add_argument("--note",required=True)
    done=commands.add_parser("complete")
    done.add_argument("series_id")
    commands.add_parser("init-stages")
    stagejob=commands.add_parser("queue-stage")
    stagejob.add_argument("series_id")
    stagejob.add_argument("episode",type=int)
    stagejob.add_argument("--stage",required=True,choices=["voice_synthesize","ltx_animate"])
    stagejob.add_argument("--recipe",required=True)
    commands.add_parser("sync-stages")
    approve_stage=commands.add_parser("approve-stage")
    approve_stage.add_argument("series_id")
    approve_stage.add_argument("episode",type=int)
    approve_stage.add_argument("--stage",required=True,choices=["voice_synthesize","ltx_animate"])
    approve_stage.add_argument("--sha256",required=True)
    approve_stage.add_argument("--note",required=True)
    retry_stage=commands.add_parser("retry-stage")
    retry_stage.add_argument("series_id")
    retry_stage.add_argument("episode",type=int)
    retry_stage.add_argument("--stage",required=True,choices=["voice_synthesize","ltx_animate"])
    retry_stage.add_argument("--reason",required=True)
    commands.add_parser("init-quality")
    qualitytech=commands.add_parser("register-technical-qa")
    qualitytech.add_argument("series_id")
    qualitytech.add_argument("episode",type=int)
    qualitytech.add_argument("--report",required=True,type=Path)
    qualityhuman=commands.add_parser("submit-human-qa")
    qualityhuman.add_argument("series_id")
    qualityhuman.add_argument("episode",type=int)
    qualityhuman.add_argument("--review",required=True,type=Path)
    commands.add_parser("quality-status")
    commands.add_parser("init-ai-final-qa")
    agent=commands.add_parser("register-ai-final-qa")
    agent.add_argument("series_id")
    agent.add_argument("episode",type=int)
    agent.add_argument("--bundle",type=Path,required=True)
    agent.add_argument("--observed-evidence",type=Path,required=True)
    agent.add_argument("--rights",type=Path,required=True)
    finalize=commands.add_parser("finalize-ai-private")
    finalize.add_argument("series_id")
    finalize.add_argument("episode",type=int)
    commands.add_parser("init-audio-evidence")
    audio=commands.add_parser("register-audio-evidence")
    audio.add_argument("series_id")
    audio.add_argument("episode",type=int)
    audio.add_argument("--report",required=True,type=Path)
    commands.add_parser("audio-evidence-status")
    commands.add_parser("init-scenes")
    scene_plan=commands.add_parser("register-scene-plan")
    scene_plan.add_argument("--plan",type=Path,required=True)
    scene_job=commands.add_parser("queue-scene-stage")
    scene_job.add_argument("series_id")
    scene_job.add_argument("episode",type=int)
    scene_job.add_argument("scene",type=int)
    scene_job.add_argument("--stage",required=True,choices=["voice_synthesize","ltx_animate"])
    scene_job.add_argument("--recipe",required=True)
    pilot=commands.add_parser("queue-first-voice-pilot")
    pilot.add_argument("series_id")
    pilot.add_argument("episode",type=int)
    pilot.add_argument("--recipe",required=True)
    pilot.add_argument("--plan-sha256",required=True)
    pilot.add_argument("--owner-note",required=True)
    voiceqa=commands.add_parser("register-scene-voice-qa")
    voiceqa.add_argument("series_id")
    voiceqa.add_argument("episode",type=int)
    voiceqa.add_argument("scene",type=int)
    voiceqa.add_argument("--report",type=Path,required=True)
    commands.add_parser("init-scene-ai-qa")
    ai_scene=commands.add_parser("register-scene-ai-qa")
    ai_scene.add_argument("series_id")
    ai_scene.add_argument("episode",type=int)
    ai_scene.add_argument("scene",type=int)
    ai_scene.add_argument("--stage",choices=["voice_synthesize","ltx_animate"],required=True)
    ai_scene.add_argument("--report",type=Path,required=True)
    ai_scene.add_argument("--observations",type=Path,required=True)
    ai_scene.add_argument("--rights",type=Path,required=True)
    ai_approve=commands.add_parser("auto-approve-scene-stage")
    ai_approve.add_argument("series_id")
    ai_approve.add_argument("episode",type=int)
    ai_approve.add_argument("scene",type=int)
    ai_approve.add_argument("--stage",choices=["voice_synthesize","ltx_animate"],required=True)
    commands.add_parser("sync-scene-stages")
    scene_audio=commands.add_parser("register-scene-audio")
    scene_audio.add_argument("series_id")
    scene_audio.add_argument("episode",type=int)
    scene_audio.add_argument("scene",type=int)
    scene_audio.add_argument("--report",type=Path,required=True)
    scene_approve=commands.add_parser("approve-scene-stage")
    scene_approve.add_argument("series_id")
    scene_approve.add_argument("episode",type=int)
    scene_approve.add_argument("scene",type=int)
    scene_approve.add_argument("--stage",choices=["voice_synthesize","ltx_animate"],required=True)
    scene_approve.add_argument("--sha256",required=True)
    scene_approve.add_argument("--note",required=True)
    scene_approve.add_argument("--owner-listened",action="store_true",
                               help="Explicit human WAV listening for M23 pilot voice only")
    scene_status=commands.add_parser("scene-status")
    scene_status.add_argument("series_id")
    scene_status.add_argument("episode",type=int)
    args=parser.parse_args(argv)

    try:
        queue=StudioQueue(args.db)
        control=SeriesManager(queue)
        stages=StageLedger(queue)
        quality=QualityLedger(queue)
        ai_final=AgentFinalQA(queue)
        audio_evidence=AudioEvidenceLedger(queue)
        scenes=SceneLedger(queue)
        ai_scenes=SceneAIGate(
            queue,attestation_key=os.environ.get(
                "KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode("utf-8"))
        if args.cmd=="init":
            control.initialize()
            result={"status":"SCHEMA_READY"}
        elif args.cmd=="init-scenes":
            scenes.initialize()
            result={"status":"SCENE_LEDGER_READY"}
        elif args.cmd=="register-scene-plan":
            result=scenes.register_plan(args.plan)
        elif args.cmd=="queue-scene-stage":
            job=scenes.queue_stage(args.series_id,args.episode,args.scene,
                                   args.stage,args.recipe)
            result={"job_id":job,"status":"SCENE_MEDIA_QUEUED"}
        elif args.cmd=="queue-first-voice-pilot":
            job=scenes.queue_first_voice_pilot(
                args.series_id,args.episode,args.recipe,
                args.plan_sha256,args.owner_note)
            result={"job_id":job,
                    "status":"FIRST_SCENE_VOICE_QUEUED_OWNER_APPROVED_NO_MODEL_RUN"}
        elif args.cmd=="register-scene-voice-qa":
            result=scenes.register_voice_technical(
                args.series_id,args.episode,args.scene,args.report)
        elif args.cmd=="init-scene-ai-qa":
            ai_scenes.initialize()
            result={"status":"AI_SCENE_QA_READY_NO_MODEL_CONNECTED"}
        elif args.cmd=="register-scene-ai-qa":
            result=ai_scenes.register(args.series_id,args.episode,
                args.scene,args.stage,report_file=args.report,
                observation_file=args.observations,rights_file=args.rights)
        elif args.cmd=="auto-approve-scene-stage":
            result=ai_scenes.auto_approve(args.series_id,args.episode,
                                          args.scene,args.stage)
        elif args.cmd=="sync-scene-stages":
            result={"updated_stages":scenes.reconcile()}
        elif args.cmd=="register-scene-audio":
            scenes.register_audio(args.series_id,args.episode,args.scene,args.report)
            result={"status":"SCENE_AUDIO_EVIDENCE_REGISTERED"}
        elif args.cmd=="approve-scene-stage":
            scenes.approve(args.series_id,args.episode,args.scene,args.stage,
                           args.sha256,args.note,
                           owner_listened=args.owner_listened)
            result={"status":"SCENE_STAGE_QA_APPROVED"}
        elif args.cmd=="scene-status":
            result=scenes.snapshot(args.series_id,args.episode)
        elif args.cmd=="init-audio-evidence":
            audio_evidence.initialize()
            result={"status":"AUDIO_EVIDENCE_LEDGER_READY"}
        elif args.cmd=="register-audio-evidence":
            audio_evidence.register(args.series_id,args.episode,args.report)
            result={"status":"AUDIO_TECHNICAL_CHECK_REGISTERED_OWNER_QA_PENDING"}
        elif args.cmd=="audio-evidence-status":
            result={"audio_evidence":audio_evidence.snapshot()}
        elif args.cmd=="init-ai-final-qa":
            ai_final.initialize()
            result={"status":"AI_FINAL_QA_LEDGER_READY_NO_APPROVAL"}
        elif args.cmd=="register-ai-final-qa":
            result=ai_final.register(args.series_id,args.episode,
                review_bundle=args.bundle,
                observed_media_evidence=args.observed_evidence,
                rights_catalogue=args.rights)
        elif args.cmd=="finalize-ai-private":
            result=control.finalize_ai_private(args.series_id,args.episode)
        elif args.cmd=="init-quality":
            quality.initialize()
            result={"status":"QUALITY_LEDGER_READY"}
        elif args.cmd=="register-technical-qa":
            quality.register_technical(args.series_id,args.episode,args.report)
            result={"status":"TECH_PASSED_WAITING_HUMAN"}
        elif args.cmd=="submit-human-qa":
            quality.submit_owner_review(args.series_id,args.episode,args.review)
            result={"status":"READY_FOR_OWNER_EPISODE_APPROVAL"}
        elif args.cmd=="quality-status":
            result={"quality":quality.snapshot()}
        elif args.cmd=="init-stages":
            stages.initialize()
            result={"status":"STAGE_LEDGER_READY"}
        elif args.cmd=="queue-stage":
            job=stages.queue_stage(args.series_id,args.episode,args.stage,args.recipe)
            result={"job_id":job,"status":"QUEUED_FOR_APPROVED_MAC_WORKER"}
        elif args.cmd=="sync-stages":
            result={"updated_stages":stages.reconcile()}
        elif args.cmd=="approve-stage":
            stages.approve(args.series_id,args.episode,args.stage,args.sha256,args.note)
            result={"status":"STAGE_QA_APPROVED_INTERNAL_ONLY"}
        elif args.cmd=="retry-stage":
            stages.retry_blocked(args.series_id,args.episode,args.stage,args.reason)
            result={"status":"RESET_FOR_MANUAL_RETRY"}
        elif args.cmd=="add-series":
            plan=json.loads(args.plan.read_text(encoding="utf-8"))
            if not isinstance(plan,dict) or set(plan)!={"series_id","title","language","lessons"}:
                raise SeriesError("Plan keys: series_id/title/language/lessons only.")
            control.create_series(**plan,activate=args.activate)
            result={"status":"SERIES_CREATED","series_id":plan["series_id"]}
        elif args.cmd=="activate":
            control.activate(args.series_id)
            result={"status":"ACTIVE"}
        elif args.cmd=="pause":
            control.pause(args.series_id,args.reason)
            result={"status":"PAUSED"}
        elif args.cmd=="prepare":
            result={"queued":control.plan_drafts(limit=args.limit)}
        elif args.cmd=="sync":
            result={"updated_episodes":control.reconcile()}
        elif args.cmd=="note":
            control.note(args.series_id,args.text,args.episode)
            result={"status":"NOTED"}
        elif args.cmd=="approve-script":
            control.approve_script(args.series_id,args.episode,args.sha256,args.note)
            result={"status":"SCRIPT_APPROVED"}
        elif args.cmd=="queue-render":
            result={"render_job_id":control.queue_render(
                args.series_id,args.episode,args.recipe,media_kind=args.media_kind,
                                                catalogue_sha256=args.catalogue_sha256)}
        elif args.cmd=="retry-blocked":
            result={"resumed_state":control.retry_blocked(
                args.series_id,args.episode,args.reason)}
        elif args.cmd=="approve-episode":
            control.approve_episode(args.series_id,args.episode,args.note)
            result={"status":"EPISODE_APPROVED_INTERNAL_ONLY"}
        elif args.cmd=="complete":
            control.complete_series(args.series_id)
            result={"status":"SERIES_PRODUCTION_COMPLETED"}
        else:
            result=control.snapshot()
    except (SeriesError,SceneError,StageLedgerError,QualityGateError,AudioEvidenceError,QueueError,OSError,ValueError,KeyError,TypeError) as exc:
        print("SERIES_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
