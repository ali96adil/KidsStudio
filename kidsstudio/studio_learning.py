"""M15 Kids Studio: measured, owner-reviewed learning from video performance.

Offline, local SQLite only. No YouTube credentials, scraping, upload, model
calls, post scheduling, automated edits or paid analytics providers.

Observe comparable *full 7-day performance windows* for owner-registered
episodes. Segment by series/language/format; surface exploratory patterns,
not causal claims. Approval records production guidance only and can never
silently rewrite an approved script or override child-safety/education QA.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any

from .episode_assembly import _ensure_private, digest
from .studio_queue import StudioQueue

SERIES=re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
VIDEO=re.compile(r"^[A-Za-z0-9_-]{11}$")
TOKEN=re.compile(r"^[a-z][a-z0-9_]{2,39}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
FEATURES=("hook_style","story_style","pace_style","participation_style")
MIN_VIDEOS_PER_SIDE=3
MIN_VIEWS_PER_SIDE=300
# Shorts feeds do not reliably produce thumbnail impressions; do not
# suppress meaningful Shorts learning merely because reach/CTR is missing.
MIN_IMPRESSIONS_PER_SIDE=2000
WINDOW_DAYS=7
MAX_EPISODES=500
MAX_ROWS=2000


class LearningError(ValueError):
    """Local analytics evidence is incomplete, unmatched, or untrustworthy."""


def _json_file(file: str | Path)->tuple[dict,str]:
    candidate=Path(file).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        raise LearningError("Use an absolute private non-symlink JSON export.")
    candidate=candidate.resolve()
    _ensure_private(candidate.parent)
    if not candidate.is_file() or not 0<candidate.stat().st_size<=200_000:
        raise LearningError("Analytics export missing or oversized.")
    try: obj=json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:raise LearningError("Invalid analytics JSON.") from exc
    if not isinstance(obj,dict):
        raise LearningError("Analytics export must be an object.")
    return obj,digest(candidate)


def _iso_day(value: Any)->str:
    if not isinstance(value,str) or len(value)!=10:
        raise LearningError("Full YYYY-MM-DD date required.")
    try:
        parsed=date.fromisoformat(value)
    except ValueError as exc:
        raise LearningError("Invalid calendar date.") from exc
    if parsed.isoformat()!=value or parsed>date.today():
        raise LearningError("Future or malformed analytics date.")
    return value


def _style(value: Any)->str:
    if not isinstance(value,str) or not TOKEN.fullmatch(value):
        raise LearningError("Style names must be stable simple identifiers.")
    return value


class LearningLedger:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_video_profiles(
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                video_id TEXT NOT NULL UNIQUE,language TEXT NOT NULL,
                format_type TEXT NOT NULL,duration_seconds INTEGER NOT NULL,
                published_date TEXT NOT NULL,
                hook_style TEXT NOT NULL,story_style TEXT NOT NULL,
                pace_style TEXT NOT NULL,participation_style TEXT NOT NULL,
                owner_education_verified INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal),
                FOREIGN KEY(series_id,ordinal)
                  REFERENCES studio_episodes(series_id,ordinal)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_video_metrics(
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                snapshot_date TEXT NOT NULL,
                window_days INTEGER NOT NULL,
                views INTEGER NOT NULL,impressions INTEGER NOT NULL,
                ctr_percent REAL,average_view_percentage REAL,
                average_view_duration_seconds REAL,
                estimated_watch_minutes REAL,
                source_sha256 TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,snapshot_date,window_days),
                FOREIGN KEY(series_id,ordinal)
                  REFERENCES studio_video_profiles(series_id,ordinal)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_learning_proposals(
                proposal_id TEXT PRIMARY KEY,
                series_id TEXT NOT NULL,
                window_days INTEGER NOT NULL,feature_name TEXT NOT NULL,
                winning_style TEXT NOT NULL,comparison_style TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PROPOSED',
                owner_rationale TEXT,created_at REAL NOT NULL,
                decided_at REAL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_learning_audit(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT NOT NULL,event_type TEXT NOT NULL,
                at REAL NOT NULL
            )""")

    def import_export(self,file:str|Path)->dict:
        packet,source_sha=_json_file(file)
        if set(packet)!={"schema_version","source","profiles","metrics"} or (
                packet["schema_version"]!=1 or
                packet["source"] not in (
                    "OWNER_VERIFIED_YOUTUBE_STUDIO_EXPORT",
                    "OWNER_AUTHORIZED_YOUTUBE_ANALYTICS_API_READONLY")):
            raise LearningError("Explicit owner-verified YouTube Studio export required.")
        profiles,metrics=packet["profiles"],packet["metrics"]
        if (not isinstance(profiles,list) or not isinstance(metrics,list)
            or not 1<=len(profiles)<=MAX_EPISODES
            or not 1<=len(metrics)<=MAX_ROWS):
            raise LearningError("Bounded real analytics data required.")
        indexed={}
        ids=set()
        for item in profiles:
            required={"series_id","ordinal","video_id","language","format_type",
                      "duration_seconds","published_date","hook_style",
                      "story_style","pace_style","participation_style",
                      "owner_education_verified"}
            if not isinstance(item,dict) or set(item)!=required:
                raise LearningError("Video metadata incomplete.")
            sid,no=item["series_id"],item["ordinal"]
            if (not isinstance(sid,str) or not SERIES.fullmatch(sid) or
                type(no) is not int or no<1 or no>120 or (sid,no) in indexed or
                not isinstance(item["video_id"],str) or not VIDEO.fullmatch(item["video_id"]) or
                item["video_id"] in ids or
                item["language"] not in ("ar","en") or
                item["format_type"] not in ("long","short") or
                type(item["duration_seconds"]) is not int or
                not 10<=item["duration_seconds"]<=1800 or
                item["owner_education_verified"] is not True):
                raise LearningError("Duplicate/unapproved video identity or format.")
            _iso_day(item["published_date"])
            for feature in FEATURES:_style(item[feature])
            indexed[(sid,no)]=item;ids.add(item["video_id"])
        typed=[]
        seen=set()
        for item in metrics:
            required={"series_id","ordinal","video_id","snapshot_date",
                      "window_days","views","impressions","ctr_percent",
                      "average_view_percentage","average_view_duration_seconds",
                      "estimated_watch_minutes"}
            if not isinstance(item,dict) or set(item)!=required:
                raise LearningError("Expected exact time-window analytics metrics.")
            sid,no=item["series_id"],item["ordinal"]
            profile=indexed.get((sid,no))
            if profile is None or item["video_id"]!=profile["video_id"]:
                raise LearningError("Metrics not tied to an owner-approved video.")
            day=_iso_day(item["snapshot_date"])
            if (type(item["window_days"]) is not int or item["window_days"]!=WINDOW_DAYS
                or (sid,no,day) in seen):
                raise LearningError("Only unique seven-day reporting windows supported.")
            published=date.fromisoformat(profile["published_date"])
            snapshot=date.fromisoformat(day)
            age_days=(snapshot-published).days
            if age_days<WINDOW_DAYS or age_days>180:
                raise LearningError("Metrics date outside comparable published age.")
            for key in ("views","impressions"):
                if type(item[key]) is not int or not 0<=item[key]<=10**10:
                    raise LearningError("Invalid views or impressions.")
            optional={
                "ctr_percent":(0,100),
                "average_view_percentage":(0,400),
                "average_view_duration_seconds":(0,profile["duration_seconds"]*4),
                "estimated_watch_minutes":(0,10**10),
            }
            for key,(lower,upper) in optional.items():
                value=item[key]
                if value is not None and (
                    type(value) not in (int,float) or not math.isfinite(value)
                    or not lower<=value<=upper):
                    raise LearningError("Invalid or misleading analytics measurement.")
            if item["impressions"]==0 and item["ctr_percent"] is not None:
                raise LearningError("CTR requires actual impressions.")
            seen.add((sid,no,day));typed.append(item)
        # Fail the WHOLE import if any identity, metric or existing row differs.
        with self.queue._connection(write=True) as db:
            for key,item in indexed.items():
                ep=db.execute("""SELECT e.state,s.language FROM studio_episodes e
                     JOIN studio_series s ON e.series_id=s.series_id
                     WHERE e.series_id=? AND e.ordinal=?""",key).fetchone()
                if (ep is None or ep["state"] not in ("EPISODE_APPROVED","PUBLISHED") or
                    ep["language"]!=item["language"]):
                    raise LearningError("Only owner-approved produced episodes can be analyzed.")
                existing=db.execute("""SELECT * FROM studio_video_profiles
                    WHERE series_id=? AND ordinal=?""",key).fetchone()
                if existing:
                    for field in ("video_id","language","format_type",
                                  "duration_seconds","published_date",*FEATURES):
                        if existing[field]!=item[field]:
                            raise LearningError("Video profile changed; immutable identity required.")
                else:
                    db.execute("""INSERT INTO studio_video_profiles
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                        key[0],key[1],item["video_id"],item["language"],
                        item["format_type"],item["duration_seconds"],
                        item["published_date"],*(item[k] for k in FEATURES),
                        1,time.time()))
            added=0
            for item in typed:
                key=(item["series_id"],item["ordinal"],
                     item["snapshot_date"],WINDOW_DAYS)
                existing=db.execute("""SELECT source_sha256 FROM studio_video_metrics
                    WHERE series_id=? AND ordinal=? AND snapshot_date=?
                    AND window_days=?""",key).fetchone()
                if existing:
                    if existing["source_sha256"]!=source_sha:
                        raise LearningError("Analytics snapshot exists; no silent replacement.")
                    continue
                db.execute("""INSERT INTO studio_video_metrics
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",(
                    key[0],key[1],key[2],WINDOW_DAYS,
                    item["views"],item["impressions"],item["ctr_percent"],
                    item["average_view_percentage"],
                    item["average_view_duration_seconds"],
                    item["estimated_watch_minutes"],source_sha,time.time()))
                added+=1
        # Agent-style one-shot detection runs automatically after an explicitly
        # owner-authorized import. It never changes a script or publication.
        learned=[self.analyze(sid) for sid in sorted({k[0] for k in indexed})]
        return {"status":"ANALYTICS_SNAPSHOTS_IMPORTED_NO_PRODUCTION_CHANGE",
                "profiles":len(profiles),"new_snapshots":added,
                "new_learning_proposals":sum(x["new_proposals"] for x in learned),
                "source_sha256":source_sha,"production_modified":False,
                "publishing_performed":False}

    def analyze(self,series_id:str)->dict:
        if not isinstance(series_id,str) or not SERIES.fullmatch(series_id):
            raise LearningError("Valid series ID required.")
        with self.queue._connection() as db:
            rows=db.execute("""SELECT p.*,m.snapshot_date,m.views,
                m.impressions,m.ctr_percent,m.average_view_percentage
                FROM studio_video_profiles p JOIN studio_video_metrics m
                  USING(series_id,ordinal)
                WHERE p.series_id=? AND m.window_days=?
                AND m.snapshot_date=(
                  SELECT MAX(m2.snapshot_date) FROM studio_video_metrics m2
                  WHERE m2.series_id=m.series_id AND m2.ordinal=m.ordinal
                  AND m2.window_days=m.window_days)
                ORDER BY p.ordinal""",(series_id,WINDOW_DAYS)).fetchall()
        samples=[dict(row) for row in rows]
        # Only compare same format/language and matching post-publication
        # age cohorts (7..30 days or 31..180 days). No casual short-vs-long.
        for x in samples:
            age=(date.fromisoformat(x["snapshot_date"])-
                 date.fromisoformat(x["published_date"])).days
            x["age_bucket"]="early" if age<=30 else "mature"
        candidates=[]
        for feature in FEATURES:
            groups={}
            for x in samples:
                key=(x["language"],x["format_type"],x["age_bucket"])
                groups.setdefault(key,{}).setdefault(x[feature],[]).append(x)
            for segment,variants in groups.items():
                eligible={}
                for style,collection in variants.items():
                    seen_views=sum(x["views"] for x in collection)
                    seen_impressions=sum(x["impressions"] for x in collection)
                    valid_ret=[x["average_view_percentage"] for x in collection
                               if x["average_view_percentage"] is not None]
                    valid_ctr=[x["ctr_percent"] for x in collection
                               if x["ctr_percent"] is not None]
                    if (len(collection)<MIN_VIDEOS_PER_SIDE or
                        seen_views<MIN_VIEWS_PER_SIDE or
                        (segment[1]=="long" and
                         seen_impressions<MIN_IMPRESSIONS_PER_SIDE) or
                        len(valid_ret)<MIN_VIDEOS_PER_SIDE):
                        continue
                    eligible[style]={
                        "n":len(collection),"views":seen_views,
                        "impressions":seen_impressions,
                        "median_views_per_day":round(
                            statistics.median(x["views"]/WINDOW_DAYS for x in collection),2),
                        "median_retention_pct":round(statistics.median(valid_ret),2),
                        "median_ctr_pct":round(statistics.median(valid_ctr),2)
                                          if len(valid_ctr)>=MIN_VIDEOS_PER_SIDE else None
                    }
                if len(eligible)<2:
                    continue
                ordered=sorted(eligible.items(),
                               key=lambda v:(v[1]["median_retention_pct"],
                                              v[1]["median_views_per_day"]),
                               reverse=True)
                winning,second=ordered[0],ordered[1]
                diff=round(winning[1]["median_retention_pct"]-
                           second[1]["median_retention_pct"],2)
                view_ratio=round(
                    winning[1]["median_views_per_day"]/
                    max(1.0,second[1]["median_views_per_day"]),2)
                if diff<8 or view_ratio<1.15:
                    continue
                evidence={
                    "schema_version":1,"series_id":series_id,
                    "window_days":WINDOW_DAYS,
                    "feature_name":feature,
                    "winning_style":winning[0],
                    "comparison_style":second[0],
                    "segment":{"language":segment[0],"format":segment[1],
                               "age_bucket":segment[2]},
                    "winner":winning[1],"comparison":second[1],
                    "retention_point_difference":diff,
                    "view_rate_ratio":view_ratio,
                    "confidence":"OBSERVATIONAL_EXPLORATORY_NOT_CAUSAL",
                    "education_and_safety_review_required":True,
                    "automatic_script_change":False,
                    "publication_authorized":False,
                }
                raw=json.dumps(evidence,sort_keys=True,
                               ensure_ascii=False,separators=(",",":"))
                pid=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
                candidates.append((pid,evidence,raw))
        inserted=0
        with self.queue._connection(write=True) as db:
            for pid,evidence,raw in candidates:
                existing=db.execute("""SELECT 1 FROM studio_learning_proposals
                    WHERE proposal_id=?""",(pid,)).fetchone()
                if existing:continue
                db.execute("""INSERT INTO studio_learning_proposals
                    (proposal_id,series_id,window_days,feature_name,
                    winning_style,comparison_style,evidence_json,
                    evidence_sha256,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",(
                    pid,series_id,WINDOW_DAYS,evidence["feature_name"],
                    evidence["winning_style"],evidence["comparison_style"],
                    raw,hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "PROPOSED",time.time()))
                inserted+=1
        return {"status":"OBSERVATIONAL_LEARNING_ONLY",
                "series_id":series_id,"videos_compared":len(samples),
                "new_proposals":inserted,
                "insufficient_data":len(samples)<2*MIN_VIDEOS_PER_SIDE,
                "recommendations_require_owner_review":True,
                "automated_content_changes":False,
                "publication_authorized":False}

    def decide(self,proposal_id:str,*,decision:str,owner_note:str)->dict:
        if (not isinstance(proposal_id,str) or not re.fullmatch(r"[a-f0-9]{32}",proposal_id)
            or decision not in ("ADOPT_FOR_FUTURE_EXPERIMENT","REJECT")
            or not isinstance(owner_note,str) or
            not 30<=len(owner_note.strip())<=1000):
            raise LearningError("Explicit owner decision with substantive education/rights note required.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT * FROM studio_learning_proposals
                WHERE proposal_id=?""",(proposal_id,)).fetchone()
            if row is None or row["status"]!="PROPOSED":
                raise LearningError("Proposal already decided or unavailable.")
            db.execute("""UPDATE studio_learning_proposals
                SET status=?,owner_rationale=?,decided_at=?
                WHERE proposal_id=?""",(
                decision,owner_note.strip(),time.time(),proposal_id))
            db.execute("""INSERT INTO studio_learning_audit
                (proposal_id,event_type,at) VALUES (?,?,?)""",
                (proposal_id,decision,time.time()))
        return {"status":decision,"proposal_id":proposal_id,
                "effect":"FUTURE_CREATIVE_BRIEF_ONLY_NOT_SCRIPT_MUTATION",
                "publication_authorized":False}

    def snapshot(self,series_id:str,limit:int=30)->dict:
        if not isinstance(series_id,str) or not SERIES.fullmatch(series_id):
            raise LearningError("Valid series required.")
        with self.queue._connection() as db:
            proposals=db.execute("""SELECT proposal_id,status,feature_name,
                winning_style,comparison_style,evidence_json
                FROM studio_learning_proposals
                WHERE series_id=? ORDER BY created_at DESC LIMIT ?""",
                (series_id,min(max(1,limit),30))).fetchall()
            count=db.execute("""SELECT COUNT(*) FROM studio_video_metrics
                WHERE series_id=?""",(series_id,)).fetchone()[0]
        return {"series_id":series_id,"observed_windows":count,
                "proposals":[{
                    "id":r["proposal_id"],"state":r["status"],
                    "feature":r["feature_name"],"candidate":r["winning_style"],
                    "baseline":r["comparison_style"],
                    "evidence":json.loads(r["evidence_json"])
                } for r in proposals],
                "source":"OWNER_VERIFIED_LOCAL_YOUTUBE_STUDIO_EXPORT",
                "causation_proven":False,"automatic_content_changes":False,
                "publication_authorized":False}


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-learning")
    p.add_argument("--db",type=Path,required=True)
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("init")
    imports=sub.add_parser("import")
    imports.add_argument("--file",type=Path,required=True)
    analyze=sub.add_parser("analyze")
    analyze.add_argument("--series",required=True)
    status=sub.add_parser("status")
    status.add_argument("--series",required=True)
    approve=sub.add_parser("decide")
    approve.add_argument("--proposal-id",required=True)
    approve.add_argument("--decision",required=True,choices=[
        "ADOPT_FOR_FUTURE_EXPERIMENT","REJECT"])
    approve.add_argument("--owner-note",required=True)
    args=p.parse_args(argv)
    try:
        ledger=LearningLedger(StudioQueue(args.db))
        if args.action=="init":ledger.initialize();result={"status":"LEARNING_LEDGER_READY"}
        elif args.action=="import":result=ledger.import_export(args.file)
        elif args.action=="analyze":result=ledger.analyze(args.series)
        elif args.action=="status":result=ledger.snapshot(args.series)
        else:result=ledger.decide(args.proposal_id,
                                  decision=args.decision,owner_note=args.owner_note)
    except (LearningError,OSError,ValueError,KeyError,TypeError) as exc:
        print("STUDIO_LEARNING_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
