"""M24 owner review of already uploaded PRIVATE YouTube URLs.

All video IDs, SHA and metadata are synthetic. No YouTube connection or upload,
no AI inference, no actual private videos and no public visibility changes.
"""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from kidsstudio.private_preview_review import PreviewReview, PreviewReviewError
from kidsstudio.owner_review_ui import make_handler
from kidsstudio.studio_dashboard import build_snapshot
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager


FIRST_ID = "AbCD12_ef-X"
SECOND_ID = "XyzAB34_cd-"
ORIGINAL_SHA = "a"*64
REVISED_SHA = "b"*64


class PrivateOwnerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m24-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",
            [{"title":"Red","objective":"Identify red objects"}],activate=True)
        self.ledger=PreviewReview(self.queue)
        self.ledger.initialize()
        self.job=self.make_master(ORIGINAL_SHA)
        self.upload_args={
            "series_id":"colors-ar","episode_number":1,
            "video_id":FIRST_ID,"render_job_id":self.job,
            "master_sha256":ORIGINAL_SHA,
        }

    def make_master(self,sha):
        job=self.queue.enqueue(kind="episode_assemble",
            request_key="final:"+sha[:12],payload={"recipe_id":"owner_pinned"},
            max_attempts=1)
        claim=self.queue.claim(worker_id="mac-01",
            capabilities=["episode_assemble"])
        self.assertEqual(job["job_id"],claim["job_id"])
        self.queue.complete(job_id=job["job_id"],worker_id="mac-01",
            generation=claim["generation"],result={
                "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                "artifact_sha256":sha,"artifact_bytes":9000,
                "artifact_type":"mp4","publication_approved":False,
            })
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='EPISODE_APPROVED',
                render_job_id=?,source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",
                (job["job_id"],"c"*64))
        return job["job_id"]

    def test_private_uploaded_record_awaits_owner_decision_no_publication(self):
        report=self.ledger.record_private_upload(**self.upload_args)
        self.assertEqual(report["state"],"PRIVATE_AWAITING_OWNER_REVIEW")
        self.assertFalse(report["upload_performed_by_this_code"])
        self.assertFalse(report["platform_privacy_verified"])
        self.assertFalse(report["public_release_authorized"])
        review=self.ledger.snapshot()
        self.assertEqual(review["pending_review"],1)
        self.assertEqual(review["previews"][0]["url"],
                         "https://www.youtube.com/watch?v="+FIRST_ID)
        status=build_snapshot(self.queue)
        self.assertEqual(status["private_previews"]["pending_review"],1)
        self.assertEqual(status["episodes"][0]["private_preview"]["state"],
                         "PRIVATE_AWAITING_OWNER_REVIEW")
        self.assertFalse(status["limits"]["publishing"])

    def test_approve_with_timestamp_notes_and_agent_context(self):
        self.ledger.record_private_upload(**self.upload_args)
        self.ledger.add_comment(FIRST_ID,text="At this second the red ball is too small",
                                category="visual",second=42)
        self.ledger.add_comment(FIRST_ID,text="Pronunciation could be clearer",
                                category="audio",second=78)
        result=self.ledger.decide(FIRST_ID,"APPROVE_WITH_NOTES",
            note="Approved today; future episodes should improve pacing")
        self.assertEqual(result["status"],"APPROVED_WITH_NOTES")
        self.assertEqual(result["agent_action"],"CONSIDER_NEXT_EPISODE")
        self.assertFalse(result["youtube_visibility_changed"])
        self.assertFalse(result["public_release_authorized"])
        events=self.ledger.snapshot()["previews"][0]["comments"]
        self.assertEqual(len(events),3)
        self.assertEqual(events[0]["second"],42)
        self.assertEqual(events[0]["agent_action"],"CONSIDER_NEXT_EPISODE")
        self.assertEqual(events[1]["category"],"audio")
        self.assertEqual(events[2]["decision"],"APPROVE_WITH_NOTES")
        with self.queue._connection() as db:
            notes=db.execute("""SELECT note FROM studio_series_notes WHERE
                series_id='colors-ar' AND ordinal=1""").fetchall()
        self.assertEqual(len(notes),1)
        self.assertIn("future episodes",notes[0]["note"])
        with self.assertRaises(PreviewReviewError):
            self.ledger.decide(FIRST_ID,"REQUEST_CHANGES",
                note="Do not silently overwrite previous approval")

    def test_approve_without_notes_and_no_automatic_publication(self):
        self.ledger.record_private_upload(**self.upload_args)
        result=self.ledger.decide(FIRST_ID,"APPROVE")
        self.assertEqual(result["status"],"APPROVED")
        self.assertEqual(result["agent_action"],"NONE")
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(self.ledger.snapshot()["pending_review"],0)

    def test_reject_generates_revision_context_requires_new_master_and_upload(self):
        self.ledger.record_private_upload(**self.upload_args)
        self.ledger.add_comment(FIRST_ID,category="timing",second=12,
                                text="Intro timing needs a slower animation")
        result=self.ledger.decide(FIRST_ID,"REQUEST_CHANGES",
                                  note="Fix cut at 12s before a new private upload")
        self.assertEqual(result["status"],"REVISION_REQUESTED")
        self.assertEqual(result["agent_action"],"TRIAGE_REVISION")
        self.assertFalse(result["public_release_authorized"])
        snapshot=self.ledger.snapshot()
        self.assertEqual(snapshot["revision_requests"],1)
        self.assertEqual(snapshot["previews"][0]["comments"][0]["agent_action"],
                         "TRIAGE_REVISION")
        with self.assertRaises(PreviewReviewError):
            self.ledger.record_private_upload(**{**self.upload_args,
                                                  "video_id":SECOND_ID})
        # Synthetic agent would prepare a separate render, then owner
        # qualifies the NEW exact MP4 before recording another upload.
        revised_job=self.make_master(REVISED_SHA)
        accepted=self.ledger.record_private_upload(
            **{**self.upload_args,"video_id":SECOND_ID,
               "render_job_id":revised_job,"master_sha256":REVISED_SHA})
        self.assertEqual(accepted["version"],2)
        new=self.ledger.snapshot()["previews"]
        self.assertEqual(new[0]["state"],"PRIVATE_AWAITING_OWNER_REVIEW")
        self.assertEqual(new[1]["state"],"REVISION_REQUESTED")
        self.assertFalse(new[0]["release_authorized"])
        self.assertNotEqual(new[0]["video_id"],new[1]["video_id"])
        with self.assertRaises(PreviewReviewError):
            self.ledger.add_comment(FIRST_ID,text="Old draft must be immutable")

    def test_invalid_id_wrong_master_xss_and_duplicate_are_refused(self):
        with self.assertRaises(PreviewReviewError):
            self.ledger.record_private_upload(**{**self.upload_args,
                "video_id":"https://evil.example/"})
        with self.assertRaises(PreviewReviewError):
            self.ledger.record_private_upload(**{**self.upload_args,
                "master_sha256":"f"*64})
        self.ledger.record_private_upload(**self.upload_args)
        with self.assertRaises(PreviewReviewError):
            self.ledger.record_private_upload(**self.upload_args)
        self.ledger.add_comment(FIRST_ID,text="<script>alert('x')</script>",
                                category="other",second=0)
        data=self.ledger.snapshot()["previews"][0]["comments"][0]
        self.assertIn("<script>",data["note"])
        # UI must use textContent and never innerHTML from saved comments.

    def test_wrong_timecode_and_wrong_note_and_approve_with_no_note(self):
        self.ledger.record_private_upload(**self.upload_args)
        for second in (-1,3601,True,0.5):
            with self.subTest(second=second),self.assertRaises(PreviewReviewError):
                self.ledger.add_comment(FIRST_ID,text="Need clarity here",second=second)
        with self.assertRaises(PreviewReviewError):
            self.ledger.decide(FIRST_ID,"APPROVE_WITH_NOTES",note="")
        with self.assertRaises(PreviewReviewError):
            self.ledger.decide(FIRST_ID,"REQUEST_CHANGES",note="")
        self.assertEqual(self.ledger.snapshot()["pending_review"],1)

    def test_render_changes_while_pending_block_notes_and_decision(self):
        self.ledger.record_private_upload(**self.upload_args)
        self.make_master(REVISED_SHA)
        with self.assertRaises(PreviewReviewError):
            self.ledger.add_comment(FIRST_ID,text="This is the wrong current render")
        with self.assertRaises(PreviewReviewError):
            self.ledger.decide(FIRST_ID,"APPROVE",note="")

    def test_http_auth_origin_host_and_mutating_owner_api(self):
        token="owner-secret-for-tests-only-"+"x"*40
        server=ThreadingHTTPServer(("127.0.0.1",0),
            make_handler(self.ledger,token))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
        self.addCleanup(conn.close)
        base=f"127.0.0.1:{server.server_port}"
        def request(method,path,data=None,headers=None):
            headers={"Host":base,**(headers or {})}
            conn.request(method,path,body=(json.dumps(data).encode()
                if data is not None else None),headers=headers)
            response=conn.getresponse()
            content=response.read()
            return response.status,content
        owner={"Authorization":"Bearer "+token}
        wrong_code,_=request("GET","/api/previews")
        self.assertEqual(wrong_code,401)
        code,body=request("GET","/api/candidates",headers=owner)
        self.assertEqual(code,200)
        items=json.loads(body)["candidates"]
        self.assertEqual(items[0]["master_sha256"],ORIGINAL_SHA)
        standard={**owner,"Origin":"http://"+base,
                  "X-KidsStudio-Owner-Action":"yes",
                  "Content-Type":"application/json"}
        code,_=request("POST","/api/private-upload",self.upload_args,
                       headers={**standard,"Origin":"http://attacker.example"})
        self.assertEqual(code,403)
        code,_=request("POST","/api/private-upload",self.upload_args,
                       headers={**standard,"X-KidsStudio-Owner-Action":"no"})
        self.assertEqual(code,403)
        code,_=request("POST","/api/private-upload",self.upload_args,
                       headers={**standard,"Authorization":"Bearer wrong"})
        self.assertEqual(code,401)
        code,_=request("POST","/api/private-upload",self.upload_args,
                       headers=standard)
        self.assertEqual(code,200)
        code,_=request("POST","/api/comment",{
            "video_id":FIRST_ID,"text":"Fix pronunciation at 10 seconds",
            "category":"audio","second":10},headers=standard)
        self.assertEqual(code,200)
        code,body=request("POST","/api/decision",{
            "video_id":FIRST_ID,"decision":"REQUEST_CHANGES",
            "note":"Please re-record the voice before re-upload"},
            headers=standard)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)["status"],"REVISION_REQUESTED")
        code,_=request("POST","/api/decision",{
            "video_id":FIRST_ID,"decision":"APPROVE","note":""},headers=standard)
        self.assertEqual(code,409)
        code,_=request("GET","/api/previews",headers={
            **owner,"Host":"attacker.example"})
        self.assertEqual(code,403)
        for path in ("/","/owner-review.js","/owner-review.css"):
            code,body=request("GET",path)
            self.assertEqual(code,200,path)
            self.assertGreater(len(body),100)

    def test_uninitialized_preview_schema_does_not_auto_initialize_dashboard(self):
        q=StudioQueue(self.root/"other.sqlite")
        q.initialize()
        SeriesManager(q).initialize()
        SeriesManager(q).create_series("shapes-ar","Shapes","ar",[
            {"title":"Circle","objective":"Recognize circle"}],activate=True)
        snapshot=build_snapshot(q)
        self.assertEqual(snapshot["private_previews"]["state"],"NOT_CONFIGURED")
        self.assertEqual(snapshot["private_previews"]["pending_review"],0)


if __name__=="__main__":
    unittest.main()
