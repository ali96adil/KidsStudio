"""M62 local QA evidence CLI: no YouTube/API/FFmpeg by default.

Pi commands only register received, independently collected evidence.
Mac 'prepare-technical' explicitly executes full FFmpeg decode against
local recovered master and writes an exclusive M7 JSON file (private).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .studio_queue import StudioQueue
from .recovery_final_qa import RecoveryFinalQA, RecoveryQualityError
from .episode_quality import inspect_video,save_report,TechnicalQAError


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="studio-recovery-quality")
    actions=parser.add_subparsers(dest="action",required=True)
    prep=actions.add_parser("prepare-technical")
    prep.add_argument("--video",type=Path,required=True)
    prep.add_argument("--sha256",required=True)
    prep.add_argument("--report",type=Path,required=True)
    prep.add_argument("--ffmpeg",default="ffmpeg")
    prep.add_argument("--ffprobe",default="ffprobe")
    prep.add_argument("--execute",action="store_true")
    init=actions.add_parser("initialize")
    init.add_argument("--db",type=Path,required=True)
    tech=actions.add_parser("register-technical")
    tech.add_argument("--db",type=Path,required=True)
    tech.add_argument("--proposal-id",required=True)
    tech.add_argument("--report",type=Path,required=True)
    ai=actions.add_parser("register-ai")
    ai.add_argument("--db",type=Path,required=True)
    ai.add_argument("--proposal-id",required=True)
    ai.add_argument("--bundle",type=Path,required=True)
    ai.add_argument("--observed",type=Path,required=True)
    ai.add_argument("--rights",type=Path,required=True)
    stage=actions.add_parser("stage-private")
    stage.add_argument("--db",type=Path,required=True)
    stage.add_argument("--proposal-id",required=True)
    stage.add_argument("--channel-id",required=True)
    stage.add_argument("--made-for-kids",required=True,choices=("yes","no"))
    stage.add_argument("--synthetic-media",required=True,choices=("yes","no"))
    args=parser.parse_args(argv)
    try:
        if args.action=="prepare-technical":
            if not args.execute:
                result={"status":"M62_EXPLICIT_EXECUTE_REQUIRED_NO_FFMPEG",
                        "file_written":False,"network_used":False,
                        "public_release_authorized":False}
            else:
                video=args.video.expanduser()
                output=args.report.expanduser()
                if (not video.is_absolute() or video.is_symlink() or
                    not video.is_file() or not output.is_absolute() or
                    output.is_symlink() or output.exists()):
                    raise RecoveryQualityError("M62 private read/write target invalid.")
                report=inspect_video(video,args.sha256,
                    ffmpeg=args.ffmpeg,ffprobe=args.ffprobe)
                if report["status"]!="TECH_PASS_OWNER_REVIEW_PENDING":
                    raise RecoveryQualityError("M62 full M7 technical report failed.")
                digest=save_report(report,output)
                result={"status":"M62_TECH_REPORT_FROZEN_NOT_UPLOADED",
                        "report_sha256":digest,
                        "master_sha256":args.sha256,
                        "file_written":True,"network_used":False,
                        "public_release_authorized":False}
        else:
            ledger=RecoveryFinalQA(StudioQueue(args.db))
            if args.action=="initialize":
                ledger.initialize()
                result={"status":"M62_QUALITY_SCHEMA_READY_NO_UPLOAD"}
            elif args.action=="register-technical":
                result=ledger.register_technical(args.proposal_id,args.report)
            elif args.action=="register-ai":
                result=ledger.register_ai(args.proposal_id,
                    review_bundle=args.bundle,
                    observed_media_evidence=args.observed,
                    rights_catalogue=args.rights)
            else:
                result=ledger.stage_private_handoff(args.proposal_id,
                    channel_id=args.channel_id,
                    made_for_kids=args.made_for_kids=="yes",
                    contains_synthetic_media=args.synthetic_media=="yes")
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (RecoveryQualityError,TechnicalQAError,OSError,
            ValueError,TypeError,KeyError):
        print("M62_RECOVERY_QUALITY_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
