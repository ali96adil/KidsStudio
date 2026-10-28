"""M24 owner-only CLI for uploaded PRIVATE video reviews and notes.

No uploader, no public visibility change. Call 'init' explicitly before
starting local token-gated owner-review server.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .private_preview_review import PreviewReview, PreviewReviewError
from .studio_queue import StudioQueue


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-preview-review",
        description="Record and review ALREADY uploaded private YouTube videos.")
    p.add_argument("--db",type=Path,required=True)
    cmd=p.add_subparsers(dest="action",required=True)
    cmd.add_parser("init")
    upload=cmd.add_parser("record-private")
    upload.add_argument("series_id")
    upload.add_argument("episode_number",type=int)
    upload.add_argument("--video-id",required=True)
    upload.add_argument("--render-job-id",required=True)
    upload.add_argument("--master-sha256",required=True)
    comment=cmd.add_parser("comment")
    comment.add_argument("video_id")
    comment.add_argument("--text",required=True)
    comment.add_argument("--category",default="other",choices=[
        "audio","animation","text","education","timing",
        "visual","thumbnail","other"])
    comment.add_argument("--second",type=int)
    decision=cmd.add_parser("decide")
    decision.add_argument("video_id")
    decision.add_argument("--decision",required=True,choices=[
        "APPROVE","APPROVE_WITH_NOTES","REQUEST_CHANGES"])
    decision.add_argument("--note",default="")
    cmd.add_parser("list")
    try:
        ledger=PreviewReview(StudioQueue(p.parse_args(argv).db))
        args=p.parse_args(argv)
        if args.action=="init":
            ledger.initialize()
            result={"status":"PRIVATE_REVIEW_SCHEMA_READY_NO_UPLOAD"}
        elif args.action=="record-private":
            result=ledger.record_private_upload(args.series_id,
                args.episode_number,video_id=args.video_id,
                render_job_id=args.render_job_id,
                master_sha256=args.master_sha256)
        elif args.action=="comment":
            result=ledger.add_comment(args.video_id,text=args.text,
                                      category=args.category,second=args.second)
        elif args.action=="decide":
            result=ledger.decide(args.video_id,args.decision,note=args.note)
        else:
            result=ledger.snapshot()
    except (PreviewReviewError,ValueError,TypeError,KeyError,OSError) as exc:
        print("PRIVATE_REVIEW_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
