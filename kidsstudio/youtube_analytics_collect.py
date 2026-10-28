"""M47 owner-authorized, READ-ONLY official YouTube Analytics collection.

No Google account connection is attempted without --execute and a short-lived
OAuth access token supplied at runtime via an environment variable. No refresh
tokens, OAuth browser flow, video uploads, publications or arbitrary URLs.
The fixed official API reports VIDEO metrics available via YouTube Analytics,
not thumbnail impressions/CTR (which are NOT exposed by this reports query).
Creates a NEW owner-private M15 packet, then owner may separately import.
"""
from __future__ import annotations

import argparse
from datetime import date,timedelta
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any,Callable
from urllib import parse, request, error

from .episode_assembly import _ensure_private
from .studio_queue import StudioQueue
from .studio_learning import LearningLedger,LearningError,VIDEO,FEATURES,SERIES,TOKEN

ENDPOINT="https://youtubeanalytics.googleapis.com/v2/reports"
METRICS=("views","estimatedMinutesWatched","averageViewDuration","averageViewPercentage")
SOURCE="OWNER_AUTHORIZED_YOUTUBE_ANALYTICS_API_READONLY"
MAX_BATCH=8
MAX_RESPONSE=64_000
TIMEOUT_SECONDS=12
CHANNEL=re.compile(r"^UC[A-Za-z0-9_-]{22}$")


class AnalyticsCollectionError(ValueError):
    """Unverified channel/video, incomplete official metrics or unsafe request."""


class _NeverRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise AnalyticsCollectionError("Analytics API redirects are forbidden.")


def _read_response(url:str,token:str)->dict:
    if not url.startswith(ENDPOINT+"?"):
        raise AnalyticsCollectionError("Only the official YouTube Analytics endpoint allowed.")
    req=request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/json",
        "User-Agent":"KidsStudio-ReadOnly-Analytics/1.0"
    },method="GET")
    opener=request.build_opener(_NeverRedirect)
    try:
        with opener.open(req,timeout=TIMEOUT_SECONDS) as response:
            if response.status!=200 or (
                    response.headers.get("Content-Type","").split(";")[0].strip()
                    !="application/json"):
                raise AnalyticsCollectionError("Unexpected YouTube Analytics HTTP response.")
            raw=response.read(MAX_RESPONSE+1)
    except (OSError,error.URLError,error.HTTPError) as exc:
        raise AnalyticsCollectionError("Read-only YouTube Analytics request failed.") from exc
    if not raw or len(raw)>MAX_RESPONSE:
        raise AnalyticsCollectionError("Unbounded or empty analytics response.")
    try:obj=json.loads(raw)
    except (ValueError,UnicodeError) as exc:
        raise AnalyticsCollectionError("Invalid Analytics API JSON.") from exc
    if not isinstance(obj,dict):
        raise AnalyticsCollectionError("Unexpected API result type.")
    return obj


def _validate_profile(db,profile:dict)->None:
    keys={"series_id","ordinal","video_id","language","format_type",
          "duration_seconds","published_date","hook_style",
          "story_style","pace_style","participation_style",
          "owner_education_verified"}
    if not isinstance(profile,dict) or set(profile)!=keys:
        raise AnalyticsCollectionError("Complete owner-approved M15 video profile required.")
    sid=profile["series_id"];ordinal=profile["ordinal"]
    if (not isinstance(sid,str) or not SERIES.fullmatch(sid) or
        type(ordinal) is not int or not 1<=ordinal<=120 or
        not isinstance(profile["video_id"],str) or not VIDEO.fullmatch(profile["video_id"]) or
        profile["format_type"] not in ("short","long") or
        profile["language"] not in ("ar","en") or
        type(profile["duration_seconds"]) is not int or
        not 10<=profile["duration_seconds"]<=1800 or
        profile["owner_education_verified"] is not True or
        any(not isinstance(profile[name],str) or not TOKEN.fullmatch(profile[name])
            for name in FEATURES)):
        raise AnalyticsCollectionError("Invalid profile identity, duration or creative tags.")
    try:
        published=date.fromisoformat(profile["published_date"])
    except (TypeError,ValueError) as exc:
        raise AnalyticsCollectionError("Invalid video publication date.") from exc
    if published.isoformat()!=profile["published_date"] or published>date.today():
        raise AnalyticsCollectionError("Invalid publication day.")
    if (date.today()-published).days<10:
        raise AnalyticsCollectionError(
            "At least ten days after publication required for a complete first-week report.")
    ep=db.execute("""SELECT e.state,s.language FROM studio_episodes e
        JOIN studio_series s ON s.series_id=e.series_id
        WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
    if not ep or ep["state"] not in ("EPISODE_APPROVED","PUBLISHED") or (
            ep["language"]!=profile["language"]):
        raise AnalyticsCollectionError("Only produced/approved Studio Brain videos may be measured.")


def _build_url(channel_id:str,video_id:str,start:date,end:date)->str:
    # EXACTLY one video, one 7-day interval, only non-monetary read metrics.
    args={
        "ids":"channel=="+channel_id,
        "startDate":start.isoformat(),
        "endDate":end.isoformat(),
        "metrics":",".join(METRICS),
        "filters":"video=="+video_id,
    }
    return ENDPOINT+"?"+parse.urlencode(args)


def _decode_api(obj:dict)->tuple[int,float,float,float]|None:
    expected=[{"name":name,"columnType":kind,"dataType":dtype} for name,kind,dtype in []]
    headers=obj.get("columnHeaders")
    if (not isinstance(headers,list) or
        [h.get("name") for h in headers if isinstance(h,dict)]!=list(METRICS)
        or len(headers)!=len(METRICS) or
        "error" in obj):
        raise AnalyticsCollectionError("Required official analytics columns are absent.")
    rows=obj.get("rows",[])
    if not isinstance(rows,list) or len(rows)>1:
        raise AnalyticsCollectionError("Only one video-aggregate result row supported.")
    if not rows:
        return None  # Inaccessible, suppressed or not yet reported: never fabricate zeros.
    row=rows[0]
    if not isinstance(row,list) or len(row)!=4:
        raise AnalyticsCollectionError("Malformed aggregate row.")
    views,minutes,duration,percentage=row
    if (type(views) is not int or not 0<=views<=10**10 or
        any(type(v) not in (int,float) or not math.isfinite(v) for v in
            (minutes,duration,percentage)) or
        not 0<=minutes<=10**10 or
        not 0<=duration<=7200 or
        not 0<=percentage<=400):
        raise AnalyticsCollectionError("Analytics API returned invalid metric values.")
    return views,float(minutes),float(duration),float(percentage)


def build_collection(queue:StudioQueue,profiles_file:str|Path, *,
                     channel_id:str,
                     token:str|None=None,execute:bool=False,
                     fetcher:Callable[[str,str],dict]=_read_response)->tuple[dict,dict]:
    """Read-only for Studio Brain. execute=True fetches <=8 official GETs.

    Snapshot means the end of the fixed seven-day measurement interval,
    not today's lifetime views. Individual days and private viewers are
    never queried or stored.
    """
    if not isinstance(channel_id,str) or not CHANNEL.fullmatch(channel_id):
        raise AnalyticsCollectionError("A pinned 24-character owner channel ID is required.")
    path=Path(profiles_file).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise AnalyticsCollectionError("Absolute non-symlink private profile plan required.")
    path=path.resolve();_ensure_private(path.parent)
    if not 0<path.stat().st_size<=120_000:
        raise AnalyticsCollectionError("Profile plan oversized/empty.")
    try:input_doc=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError) as exc:
        raise AnalyticsCollectionError("Invalid private profile plan.") from exc
    if (not isinstance(input_doc,dict) or
        set(input_doc)!={"schema_version","channel_id","profiles"} or
        input_doc["schema_version"]!=1 or input_doc["channel_id"]!=channel_id or
        not isinstance(input_doc["profiles"],list) or
        not 1<=len(input_doc["profiles"])<=MAX_BATCH):
        raise AnalyticsCollectionError("Plan must have 1–8 profiles for exact owner channel.")
    profiles=input_doc["profiles"]
    seen_vid=set();seen_episodes=set();queries=[]
    with queue._connection() as db:
        for profile in profiles:
            _validate_profile(db,profile)
            video=profile["video_id"]
            ep=(profile["series_id"],profile["ordinal"])
            if video in seen_vid or ep in seen_episodes:
                raise AnalyticsCollectionError("Duplicate video or episode in read-only batch.")
            seen_vid.add(video);seen_episodes.add(ep)
            start=date.fromisoformat(profile["published_date"])
            end=start+timedelta(days=6)
            queries.append((profile,_build_url(channel_id,video,start,end),start+timedelta(days=7)))
    if not execute:
        return {},{
            "schema_version":1,
            "status":"M47_READ_ONLY_PLAN_NO_NETWORK",
            "planned_video_count":len(queries),
            "requests_sent":0,"metrics_collected":0,
            "private_upload_permitted":False,"public_release_authorized":False,
            "token_required_only_for_execute":True,
        }
    if not isinstance(token,str) or not 24<=len(token)<=8192 or any(
            c in token for c in "\r\n\0 \t"):
        raise AnalyticsCollectionError("Short-lived, explicitly supplied OAuth access token required.")
    records=[]
    for profile,url,day in queries:
        metrics=_decode_api(fetcher(url,token))
        if metrics is None:
            continue
        views,minutes,duration,percentage=metrics
        # The v2 Analytics endpoint does NOT return thumbnail reach/CTR
        # with these metrics; never infer impressions from total views.
        records.append({
            "series_id":profile["series_id"],
            "ordinal":profile["ordinal"],
            "video_id":profile["video_id"],
            "snapshot_date":day.isoformat(),
            "window_days":7,
            "views":views,
            "impressions":0,
            "ctr_percent":None,
            "average_view_percentage":percentage,
            "average_view_duration_seconds":duration,
            "estimated_watch_minutes":minutes,
        })
    if not records:
        raise AnalyticsCollectionError(
            "No complete official data returned; no zero-view snapshots were invented.")
    return {
        "schema_version":1,
        "source":SOURCE,
        "profiles":[p for p in profiles if any(
            m["video_id"]==p["video_id"] for m in records)],
        "metrics":records,
    },{
        "schema_version":1,
        "status":"M47_OWNER_AUTHORIZED_READONLY_REPORT_CAPTURED_NOT_IMPORTED",
        "planned_video_count":len(queries),
        "requests_sent":len(queries),
        "metrics_collected":len(records),
        "thumbnail_impressions_available":False,
        "ctr_available":False,
        "learning_proposals_created":False,
        "private_upload_permitted":False,
        "public_release_authorized":False,
    }


def _write_new_json(file:str|Path,packet:dict)->None:
    destination=Path(file).expanduser()
    if (not destination.is_absolute() or destination.is_symlink() or
        destination.suffix.lower()!=".json" or destination.exists() or
        not destination.parent.is_dir() or
        (destination.parent.stat().st_mode & 0o022)):
        raise AnalyticsCollectionError("Use a NEW JSON path under a non-writable-by-others private directory.")
    _ensure_private(destination.parent)
    encoded=(json.dumps(packet,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
    if len(encoded)>200_000:
        raise AnalyticsCollectionError("Refusing oversized private captured report.")
    fd=os.open(str(destination),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as output:
        output.write(encoded);output.flush();os.fsync(output.fileno())


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-analytics-collect")
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--profiles",required=True,type=Path)
    p.add_argument("--channel-id",required=True)
    p.add_argument("--out",type=Path)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    try:
        if args.execute and args.out is None:
            raise AnalyticsCollectionError("--execute requires a new private output file.")
        packet,report=build_collection(
            StudioQueue(args.db),args.profiles,
            channel_id=args.channel_id,
            token=os.environ.get("KIDS_STUDIO_YT_ANALYTICS_TOKEN"),
            execute=args.execute)
        if args.execute:
            _write_new_json(args.out,packet)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (AnalyticsCollectionError,LearningError,OSError,KeyError,
            ValueError,TypeError) as exc:
        # Never print token, untrusted HTTP response bodies, private media paths.
        print("M47_ANALYTICS_NOT_CAPTURED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
