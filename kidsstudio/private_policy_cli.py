"""Owner policy CLI for agent-run PRIVATE-only YouTube uploads (M26).

The grant is a standing owner consent scoped to one series, exact YouTube
channel, explicit audience/synthetic-media declarations and 24h budget.
It never grants PUBLIC/scheduled publication or automatic owner acceptance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .private_upload_policy import PrivateUploadPolicy, PrivatePolicyError
from .studio_queue import StudioQueue


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-private-policy")
    p.add_argument("--db",required=True,type=Path)
    commands=p.add_subparsers(dest="action",required=True)
    commands.add_parser("init")
    grant=commands.add_parser("grant")
    grant.add_argument("series_id")
    grant.add_argument("--channel-id",required=True)
    grant.add_argument("--max-uploads-24h",type=int,default=1)
    grant.add_argument("--made-for-kids",action="store_true",required=True)
    grant.add_argument("--contains-synthetic-media",action="store_true",required=True)
    grant.add_argument("--owner-note",required=True)
    pause=commands.add_parser("pause")
    pause.add_argument("series_id")
    args=p.parse_args(argv)
    try:
        ledger=PrivateUploadPolicy(StudioQueue(args.db))
        if args.action=="init":
            ledger.initialize()
            result={"status":"PRIVATE_POLICY_SCHEMA_READY_NO_PERMISSION"}
        elif args.action=="grant":
            result=ledger.grant(args.series_id,channel_id=args.channel_id,
                max_uploads_24h=args.max_uploads_24h,
                made_for_kids=args.made_for_kids,
                contains_synthetic_media=args.contains_synthetic_media,
                owner_note=args.owner_note)
        else:
            result=ledger.pause(args.series_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (PrivatePolicyError,ValueError,OSError) as exc:
        print("PRIVATE_POLICY_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
