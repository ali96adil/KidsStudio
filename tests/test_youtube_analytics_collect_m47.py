"""M47 official API read-only collector: mocked HTTP, real M15 DB import.

No OAuth credentials, Google network, channel access, publication or model
work is performed in any test. The fake response uses the official report
column names and one aggregate row, not invented impressions/CTR.
"""
from __future__ import annotations

from datetime import date,timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit,parse_qs

from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.studio_learning import LearningLedger
from kidsstudio.youtube_analytics_collect import (
    build_collection,_decode_api,_write_new_json,AnalyticsCollectionError,
    _read_response,ENDPOINT,METRICS,SOURCE
)


class YouTubeAnalyticsReadOnlyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m47-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.q=StudioQueue(self.root/"studio.sqlite")
        self.q.initialize()
        self.series=SeriesManager(self.q);self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",[
            {"title":"Red lesson","objective":"Recognize red"},
            {"title":"Blue lesson","objective":"Recognize blue"}],activate=True)
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='EPISODE_APPROVED',source_sha256=?
                WHERE series_id='colors-ar'""",("a"*64,))
        self.learn=LearningLedger(self.q);self.learn.initialize()
        self.channel="UC"+"a"*22
        day=(date.today()-timedelta(days=15)).isoformat()
        self.plan={
            "schema_version":1,"channel_id":self.channel,
            "profiles":[{
                "series_id":"colors-ar","ordinal":i,
                "video_id":"vid"+"x"*7+str(i),
                "language":"ar","format_type":"short",
                "duration_seconds":42,
                "published_date":day,
                "hook_style":"question_first" if i==1 else "story_first",
                "story_style":"original_adventure",
                "pace_style":"calm",
                "participation_style":"ask_and_pause",
                "owner_education_verified":True,
            } for i in (1,2)]
        }
        self.file=self.root/"profiles.json"
        self.file.write_text(json.dumps(self.plan),encoding="utf-8")
        self.record=self.root/"captured.json"
        self.calls=[]
        self.token="OwnerAuthorizedAccessTokenFromEnvironment12345"

    def responder(self,url,token):
        self.assertEqual(token,self.token)
        parsed=urlsplit(url)
        self.assertEqual(parsed.scheme,"https")
        self.assertEqual(parsed.netloc,"youtubeanalytics.googleapis.com")
        self.assertEqual(parsed.path,"/v2/reports")
        q=parse_qs(parsed.query)
        self.assertEqual(q["ids"],["channel=="+self.channel])
        self.assertEqual(q["metrics"],[",".join(METRICS)])
        self.assertEqual(q["startDate"],[self.plan["profiles"][0]["published_date"]])
        self.assertEqual(q["endDate"],[
            (date.fromisoformat(self.plan["profiles"][0]["published_date"])
             +timedelta(days=6)).isoformat()])
        self.assertEqual(set(q),{"ids","startDate","endDate","metrics","filters"})
        self.assertEqual(len(q["filters"][0].split("==")[1]),11)
        self.calls.append(url)
        return {
            "kind":"youtubeAnalytics#resultTable",
            "columnHeaders":[{"name":name,"columnType":"METRIC",
                              "dataType":"INTEGER" if name=="views" else "FLOAT"}
                             for name in METRICS],
            "rows":[[400,210.0,31.5,75.0]]
        }

    def collect(self,execute=False,fetcher=None):
        return build_collection(
            self.q,self.file,channel_id=self.channel,token=self.token,
            execute=execute,fetcher=fetcher or self.responder)

    def test_default_dry_run_has_zero_api_calls_and_no_files(self):
        def forbidden(url,token):
            self.fail("No HTTP request allowed in default mode.")
        packet,report=self.collect(fetcher=forbidden)
        self.assertEqual(packet,{})
        self.assertEqual(report["status"],"M47_READ_ONLY_PLAN_NO_NETWORK")
        self.assertEqual(report["requests_sent"],0)
        self.assertFalse(self.record.exists())
        self.assertFalse(report["public_release_authorized"])

    def test_exact_two_video_official_get_and_separate_m15_import(self):
        packet,report=self.collect(execute=True)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(report["metrics_collected"],2)
        self.assertEqual(packet["source"],SOURCE)
        for metric in packet["metrics"]:
            self.assertEqual(metric["views"],400)
            self.assertEqual(metric["impressions"],0)
            self.assertIsNone(metric["ctr_percent"])
            self.assertEqual(metric["window_days"],7)
            self.assertEqual(metric["average_view_percentage"],75.0)
        with self.q._connection() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM studio_video_metrics").fetchone()[0],0)
        _write_new_json(self.record,packet)
        self.assertEqual(self.record.stat().st_mode & 0o777,0o600)
        imported=self.learn.import_export(self.record)
        self.assertEqual(imported["new_snapshots"],2)
        self.assertEqual(self.learn.import_export(self.record)["new_snapshots"],0)
        self.assertEqual(self.learn.analyze("colors-ar")["new_proposals"],0)
        self.assertFalse(report["private_upload_permitted"])
        with self.assertRaises(AnalyticsCollectionError):
            _write_new_json(self.record,packet)

    def test_empty_analytics_rows_are_not_invented_as_zero_views(self):
        def no_metrics(url,token):
            return {"columnHeaders":[{"name":x} for x in METRICS],
                    "rows":[]}
        with self.assertRaises(AnalyticsCollectionError):
            self.collect(execute=True,fetcher=no_metrics)
        self.assertFalse(self.record.exists())

    def test_bad_metrics_or_unexpected_columns_block_all(self):
        bads=[
            {"columnHeaders":[{"name":"views"}],"rows":[[100]]},
            {"columnHeaders":[{"name":x} for x in METRICS],
             "rows":[[True,100,20,50]]},
            {"columnHeaders":[{"name":x} for x in METRICS],
             "rows":[[50,100,30,402]]},
            {"columnHeaders":[{"name":x} for x in METRICS],
             "rows":[[20,100,30,50],[21,100,30,50]]},
            {"error":{"message":"account error"},"columnHeaders":[
                {"name":x} for x in METRICS],"rows":[[20,100,30,50]]},
        ]
        for obj in bads:
            with self.subTest(obj=obj),self.assertRaises(AnalyticsCollectionError):
                _decode_api(obj)

    def test_channel_identity_approval_and_early_publication_guard(self):
        with self.assertRaises(AnalyticsCollectionError):
            build_collection(self.q,self.file,channel_id="UCBAD")
        self.plan["channel_id"]="UC"+"b"*22
        self.file.write_text(json.dumps(self.plan))
        with self.assertRaises(AnalyticsCollectionError):
            self.collect()
        self.plan["channel_id"]=self.channel
        self.plan["profiles"][0]["published_date"]=date.today().isoformat()
        self.file.write_text(json.dumps(self.plan))
        with self.assertRaises(AnalyticsCollectionError):
            self.collect()

    def test_refuses_private_or_unapproved_episodes(self):
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='PLANNED'
                WHERE series_id='colors-ar' AND ordinal=1""")
        with self.assertRaises(AnalyticsCollectionError):
            self.collect()

    def test_shorts_replay_retention_above_100_is_preserved(self):
        def replay(url,token):
            result=self.responder(url,token)
            result["rows"]=[[620,400.0,61.0,145.2]]
            return result
        packet,report=self.collect(execute=True,fetcher=replay)
        self.assertEqual(report["metrics_collected"],2)
        self.assertEqual(packet["metrics"][0]["average_view_percentage"],145.2)
        _write_new_json(self.record,packet)
        self.assertEqual(self.learn.import_export(self.record)["new_snapshots"],2)

    def test_output_validation_blocks_preexisting_file_before_http(self):
        from kidsstudio.youtube_analytics_collect import _validate_destination
        self.record.write_text("protected existing report")
        with self.assertRaises(AnalyticsCollectionError):
            _validate_destination(self.record)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.record.read_text(),"protected existing report")

    def test_missing_token_or_same_video_cannot_query(self):
        with self.assertRaises(AnalyticsCollectionError):
            build_collection(self.q,self.file,channel_id=self.channel,
                             token="",execute=True,fetcher=self.responder)
        self.plan["profiles"][1]["video_id"]=self.plan["profiles"][0]["video_id"]
        self.file.write_text(json.dumps(self.plan))
        with self.assertRaises(AnalyticsCollectionError):
            self.collect(execute=True)
        self.assertEqual(self.calls,[])

    def test_readonly_HTTP_rejects_untrusted_host_and_redirects(self):
        with self.assertRaises(AnalyticsCollectionError):
            _read_response("https://evil.example/v2/reports?x=1",self.token)
        from kidsstudio.youtube_analytics_collect import _NeverRedirect
        handler=_NeverRedirect()
        with self.assertRaises(AnalyticsCollectionError):
            handler.redirect_request(None,None,302,"redirect",{},"https://evil.example/")


if __name__=="__main__":
    unittest.main()
