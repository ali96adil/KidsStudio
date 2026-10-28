"""Local owner-only commands for the persistent series and episode planner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .series_manager import SeriesError, SeriesManager
from .studio_queue import QueueError, StudioQueue


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
    args=parser.parse_args(argv)

    try:
        control=SeriesManager(StudioQueue(args.db))
        if args.cmd=="init":
            control.initialize()
            result={"status":"SCHEMA_READY"}
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
                args.series_id,args.episode,args.recipe,media_kind=args.media_kind)}
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
    except (SeriesError,QueueError,OSError,ValueError,KeyError,TypeError) as exc:
        print("SERIES_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
