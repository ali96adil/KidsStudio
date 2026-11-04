"""M25: completely offline synthetic YouTube API protocol/owner-review tests.

Injected transport never opens a socket. Only safe PRIVATE metadata, one
durable upload attempt, later processing verification and owner Pi import.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from kidsstudio.youtube_private_upload import (
    CHUNK, GoogleYouTubeTransport, UploadJournal, YouTubePrivateError,
    validate_plan, private_upload, verify_existing, _session, main,
)
from kidsstudio.private_preview_review import PreviewReview, PreviewReviewError
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager

VID="XyZabc-123_"
CHANNEL="UC"+"q"*22
TOKEN="test-oauth-bearer-"+"a"*60


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeGoogle:
    def __init__(self, *, processing="succeeded", visibility="private",
                 fail_stage=None):
        self.processing=processing
        self.visibility=visibility
        self.fail_stage=fail_stage
        self.started=0
        self.puts=0
        self.verifications=0
        self.metadata=None
        self.bytes_sent=0

    def start(self, token, metadata, size):
        self.started+=1
        self.metadata=metadata
        self.size=size
        if self.fail_stage=="start":
            raise YouTubePrivateError("Simulated ambiguous start failure")
        return "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=fake"

    def put_chunk(self,token,session,block,offset,total):
        self.puts+=1
        self.bytes_sent+=len(block)
        if self.fail_stage=="put":
            raise YouTubePrivateError("Simulated ambiguous transfer failure")
        if offset+len(block)<total:return 308,offset+len(block)
        return 201,VID

    def verify(self,token,video_id,channel_id):
        self.verifications+=1
        if self.fail_stage=="verify":
            raise YouTubePrivateError("Simulated private video status unavailable")
        return {"video_id":video_id,"channel_id":channel_id,
                "privacy_status":self.visibility,
                "processing_status":self.processing,
                "verified_using_authenticated_youtube_api":True}


class YouTubePrivateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m25-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.media=self.root/"m25_master.mp4"
        self.media.write_bytes(b"FAKE-TEST-MASTER-NOT-REAL-MP4-"*1500)
        self.job="1"*32
        self.ready=self.root/"m8_ready.json"
        self.report={
            "schema_version":1,
            "status":"READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED",
            "series_id":"colors-ar","episode_number":1,
            "render_job_id":self.job,"video_sha256":sha(self.media),
            "owner_final_qa":True,"upload_performed":False,
            "public_release_authorized":False,
        }
        self.ready.write_text(json.dumps(self.report))
        self.plan={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "render_job_id":self.job,"master_sha256":sha(self.media),
            "target_channel_id":CHANNEL,"title":"Original learning colors",
            "description":"Original educational video prepared by Kids Studio",
            "category_id":"27",
            "made_for_kids":True,"contains_synthetic_media":True,
        }
        self.journal=UploadJournal(self.root/"youtube_attempts.sqlite")

    def inspect(self,plan=None):
        return validate_plan(plan or self.plan,self.media,
                             self.ready,sha(self.ready))

    def go(self, transport):
        return private_upload(self.plan,self.media,self.ready,
                     sha(self.ready),self.journal,TOKEN,transport=transport)

    def test_private_only_metadata_exact_owner_pin_and_no_publication(self):
        self.assertFalse(self.inspect()["video_uploaded"])
        fake=FakeGoogle()
        result=self.go(fake)
        self.assertEqual(result["status"],
                         "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertTrue(result["platform_privacy_verified"])
        self.assertTrue(result["ready_for_owner_review"])
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(fake.started,1)
        self.assertEqual(fake.puts,1)
        self.assertEqual(fake.metadata["status"],{
            "privacyStatus":"private",
            "selfDeclaredMadeForKids":True,
            "containsSyntheticMedia":True,
        })
        self.assertNotIn("publishAt",json.dumps(fake.metadata))
        self.assertEqual(fake.bytes_sent,self.media.stat().st_size)
        saved=self.journal.status(self.job)
        self.assertEqual(saved["state"],"PRIVATE_VERIFIED")
        self.assertEqual(saved["video_id"],VID)
        self.assertNotIn(TOKEN,json.dumps(saved))
        with self.assertRaises(YouTubePrivateError):
            self.go(FakeGoogle())

    def test_processing_pending_keeps_single_upload_and_can_verify_existing(self):
        fake=FakeGoogle(processing="processing")
        first=self.go(fake)
        self.assertEqual(first["status"],"YOUTUBE_PRIVATE_PROCESSING_PENDING")
        self.assertFalse(first["ready_for_owner_review"])
        self.assertEqual(self.journal.status(self.job)["state"],"UPLOADED_UNVERIFIED")
        with self.assertRaises(YouTubePrivateError):
            self.go(fake)
        fake.processing="succeeded"
        second=verify_existing(self.plan,self.media,self.ready,sha(self.ready),
                               self.journal,TOKEN,transport=fake)
        self.assertEqual(second["status"],
                         "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertEqual(fake.started,1)
        self.assertEqual(fake.puts,1)
        self.assertEqual(self.journal.status(self.job)["state"],"PRIVATE_VERIFIED")

    def test_not_private_or_wrong_channel_blocks_and_never_reuploads(self):
        f=FakeGoogle(visibility="public")
        with self.assertRaises(YouTubePrivateError):
            self.go(f)
        self.assertEqual(self.journal.status(self.job)["state"],"UPLOADED_UNVERIFIED")
        self.assertEqual(f.started,1)
        with self.assertRaises(YouTubePrivateError):
            self.go(f)
        self.assertEqual(f.started,1)
        wrong=FakeGoogle()
        wrong.verify=lambda token,vid,channel: {
            "video_id":vid,"channel_id":"UC"+"x"*22,
            "privacy_status":"private","processing_status":"succeeded",
            "verified_using_authenticated_youtube_api":True
        }
        with self.assertRaises(YouTubePrivateError):
            verify_existing(self.plan,self.media,self.ready,sha(self.ready),
                            self.journal,TOKEN,transport=wrong)

    def test_ambiguous_network_start_or_put_is_permanently_quarantined(self):
        for stage in ("start","put"):
            with self.subTest(stage=stage):
                local=UploadJournal(self.root/("m25_"+stage+".sqlite"))
                fake=FakeGoogle(fail_stage=stage)
                with self.assertRaises(YouTubePrivateError):
                    private_upload(self.plan,self.media,self.ready,sha(self.ready),
                                   local,TOKEN,transport=fake)
                self.assertEqual(local.status(self.job)["state"],"STARTED")
                with self.assertRaises(YouTubePrivateError):
                    private_upload(self.plan,self.media,self.ready,sha(self.ready),
                                   local,TOKEN,transport=fake)
                self.assertEqual(fake.started,1)

    def test_reject_changed_master_readiness_and_metadata_before_network(self):
        for change in (
            {"made_for_kids":"true"},{"contains_synthetic_media":None},
            {"target_channel_id":"other"},{"title":"x"*101},
            {"category_id":"media"},{"master_sha256":"f"*64},
            {"privacyStatus":"public"}
        ):
            with self.subTest(change=change),self.assertRaises(YouTubePrivateError):
                self.inspect({**self.plan,**change})
        with self.assertRaises(YouTubePrivateError):
            validate_plan(self.plan,self.media,self.ready,"e"*64)
        self.media.write_bytes(self.media.read_bytes()+b"new")
        with self.assertRaises(YouTubePrivateError):
            self.go(FakeGoogle())
        self.assertIsNone(self.journal.status(self.job))

    def test_reverify_cannot_switch_channel_or_metadata_plan(self):
        self.go(FakeGoogle())
        modified={**self.plan,"title":"Different after successful upload"}
        with self.assertRaises(YouTubePrivateError):
            verify_existing(modified,self.media,self.ready,sha(self.ready),
                self.journal,TOKEN,transport=FakeGoogle())
        state=self.journal.status(self.job)
        self.assertEqual(state["state"],"PRIVATE_VERIFIED")

    def test_resumable_origin_and_range_are_fail_closed(self):
        good="https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=abc"
        _session(good)
        for bad in (
            "http://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=abc",
            "https://evil.example/upload/youtube/v3/videos?uploadType=resumable&upload_id=abc",
            "https://www.googleapis.com/redirect?uploadType=resumable&upload_id=abc",
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable",
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=media&upload_id=abc"
        ):
            with self.subTest(url=bad),self.assertRaises(YouTubePrivateError):
                _session(bad)
        transport=GoogleYouTubeTransport()
        transport._request=lambda method,url,token,body,headers: (
            308,{"range":"bytes=0-0"},b""
        )
        with self.assertRaises(YouTubePrivateError):
            transport.put_chunk(TOKEN,good,b"hello",0,5)

    def test_cli_default_is_true_dry_run_no_oauth_or_network(self):
        plan_file=self.root/"upload.json"
        plan_file.write_text(json.dumps(self.plan))
        out=io.StringIO()
        with redirect_stdout(out):
            code=main(["--plan",str(plan_file),"--media",str(self.media),
                "--readiness",str(self.ready),
                "--readiness-sha256",sha(self.ready)])
        self.assertEqual(code,0)
        result=json.loads(out.getvalue())
        self.assertFalse(result["video_uploaded"])
        self.assertEqual(result["youtube_visibility"],"PRIVATE")
        self.assertIsNone(self.journal.status(self.job))

    def test_m25_verified_report_import_matches_current_pi_render(self):
        queue=StudioQueue(self.root/"pi.sqlite")
        queue.initialize()
        manager=SeriesManager(queue)
        manager.initialize()
        manager.create_series("colors-ar","Colors","ar",[
            {"title":"Red","objective":"Identify red"}],activate=True)
        job=queue.enqueue(kind="episode_assemble",request_key="last_render",
                          payload={"recipe_id":"final_master"},max_attempts=1)
        lease=queue.claim(worker_id="mac",capabilities=["episode_assemble"])
        queue.complete(job_id=job["job_id"],worker_id="mac",
            generation=lease["generation"],result={
            "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "artifact_sha256":sha(self.media),"artifact_type":"mp4",
            "artifact_bytes":self.media.stat().st_size,
            "publication_approved":False,
        })
        with queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='EPISODE_APPROVED',
                render_job_id=?,source_sha256=? WHERE
                series_id='colors-ar' AND ordinal=1""",
                (job["job_id"],"d"*64))
        ledger=PreviewReview(queue)
        ledger.initialize()
        # Same per-version upload provenance as the Pi's approved master.
        self.job=job["job_id"]
        self.plan["render_job_id"]=job["job_id"]
        self.report["render_job_id"]=job["job_id"]
        self.ready.write_text(json.dumps(self.report))
        result=self.go(FakeGoogle())
        report_file=self.root/"youtube_m25_api_report.json"
        report_file.write_text(json.dumps(result))
        imported=ledger.record_verified_upload(str(report_file),sha(report_file))
        self.assertTrue(imported["platform_privacy_verified"])
        view=ledger.snapshot()
        self.assertEqual(view["pending_review"],1)
        self.assertTrue(view["previews"][0]["platform_privacy_verified"])
        self.assertFalse(view["previews"][0]["release_authorized"])
        with self.assertRaises(PreviewReviewError):
            ledger.record_verified_upload(str(report_file),sha(report_file))
        edited={**result,"youtube_privacy":"public"}
        forged_file=self.root/"bad_status.json"
        forged_file.write_text(json.dumps(edited))
        with self.assertRaises(PreviewReviewError):
            ledger.record_verified_upload(str(forged_file),sha(forged_file))


if __name__=="__main__":
    unittest.main()
