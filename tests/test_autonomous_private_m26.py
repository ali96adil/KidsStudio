"""M26 end-to-end offline Pi-to-Mac autonomous PRIVATE upload tests.

Simulated owner policy + SQLite episode QA + fake Google API. No network,
actual YouTube OAuth, models, user's media or public posting. Tests both
policy gates and the final atomic handoff into the M24 owner review queue.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.coordinator_api import Coordinator, TransportError
from kidsstudio.private_upload_policy import PrivateUploadPolicy, PrivatePolicyError
from kidsstudio.private_upload_agent import (
    PrivateCatalogue, PrivateUploadAgent, PrivateAgentError,
)
from kidsstudio.private_preview_review import PreviewReview
from kidsstudio.studio_quality_ledger import QualityLedger
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.youtube_private_upload import UploadJournal, YouTubePrivateError

CHANNEL="UC"+"r"*22
VIDEO="MmNn_11-abc"
TOKEN="fake-google-oauth-token"+"x"*60


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeYouTube:
    def __init__(self, *, processing="succeeded", visibility="private",
                 after_start=None):
        self.started=0
        self.processing=processing
        self.visibility=visibility
        self.after_start=after_start
        self.metadata=None

    def start(self,token,metadata,size):
        self.started+=1
        self.metadata=metadata
        if self.after_start:
            self.after_start()
        return "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=test"

    def put_chunk(self,token,session,data,offset,total):
        return 201,VIDEO

    def verify(self,token,video_id,channel_id):
        return {"video_id":video_id,"channel_id":channel_id,
            "privacy_status":self.visibility,
            "processing_status":self.processing,
            "verified_using_authenticated_youtube_api":True}


class FakePi:
    def __init__(self,coordinator,policy):
        self.coordinator=coordinator
        self.policy=policy
        self.calls=[]
        self.on_second_proof=None
        self.proofs=0

    def call(self,action,request):
        self.calls.append(action)
        if action=="private-upload-lease-check":
            self.proofs+=1
            if self.proofs==2 and self.on_second_proof:
                self.on_second_proof()
        try:
            return self.coordinator.dispatch(
                action,request,"mac-private-uploader",
                frozenset({"youtube_private_upload"}))
        except (TransportError,ValueError,KeyError,TypeError) as exc:
            from kidsstudio.remote_worker import RemoteWorkerError
            raise RemoteWorkerError("fake-Pi rejected "+action) from None


class AutonomousPrivateUploadTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m26-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.root.mkdir(exist_ok=True)
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        series=SeriesManager(self.queue)
        series.initialize()
        series.create_series("colors-ar","Colors","ar",[
            {"title":"Red","objective":"Discover the color red"}],
            activate=True)
        self.media=self.root/"final_master.mp4"
        self.media.write_bytes(b"SYNTHETIC-NONVIDEO-TEST-MASTER-"*400)
        self.render=self.queue.enqueue(
            kind="episode_assemble",request_key="test-final-video",
            payload={"recipe_id":"test-final"},max_attempts=1)
        claim=self.queue.claim(worker_id="mac-stage",
                               capabilities=["episode_assemble"])
        self.queue.complete(job_id=self.render["job_id"],worker_id="mac-stage",
            generation=claim["generation"],result={
            "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "artifact_sha256":sha(self.media),"artifact_type":"mp4",
            "artifact_bytes":self.media.stat().st_size,
            "publication_approved":False})
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='EPISODE_APPROVED',
                render_job_id=?,source_sha256=? WHERE
                series_id='colors-ar' AND ordinal=1""",
                (self.render["job_id"],"e"*64))
        QualityLedger(self.queue).initialize()
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_quality_reviews(
                series_id,ordinal,render_job_id,media_sha256,tech_report_sha256,
                review_report_sha256,checks_passed,state,created_at,updated_at)
                VALUES (?,?,?,?,?,?,11,'READY_FOR_OWNER_EPISODE_APPROVAL',?,?)""",
                ("colors-ar",1,self.render["job_id"],sha(self.media),
                 "a"*64,"b"*64,1.0,1.0))
        PreviewReview(self.queue).initialize()
        self.policy=PrivateUploadPolicy(self.queue)
        self.policy.initialize()
        self.plan={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "render_job_id":self.render["job_id"],
            "master_sha256":sha(self.media),
            "target_channel_id":CHANNEL,
            "title":"Original educational colors — red",
            "description":"Our original learning video",
            "category_id":"27",
            "made_for_kids":True,
            "contains_synthetic_media":True,
        }
        self.ready=self.root/"m8_ready.json"
        self.ready.write_text(json.dumps({
            "schema_version":1,
            "status":"READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED",
            "series_id":"colors-ar","episode_number":1,
            "render_job_id":self.render["job_id"],
            "video_sha256":sha(self.media),
            "owner_final_qa":True,
            "upload_performed":False,
            "public_release_authorized":False}))
        self.plan_file=self.root/"upload_plan.json"
        self.plan_file.write_text(json.dumps(self.plan))
        self.catalogue_file=self.root/"private_catalogue.json"
        self.catalogue_file.write_text(json.dumps({
            "schema_version":1,"private_root":str(self.root),
            "entries":[{"plan":str(self.plan_file),"media":str(self.media),
                        "readiness":str(self.ready),
                        "readiness_sha256":sha(self.ready)}]
        }))
        self.catalogue=PrivateCatalogue(self.catalogue_file)
        self.journal=UploadJournal(self.root/"mac_uploads.sqlite")
        self.coordinator=Coordinator(self.queue,self.root/"vault",{
            "mac-private-uploader":("c"*64,{"youtube_private_upload"})})
        self.pi=FakePi(self.coordinator,self.policy)

    def grant(self,max_uploads=1):
        return self.policy.grant("colors-ar",channel_id=CHANNEL,
            max_uploads_24h=max_uploads,made_for_kids=True,
            contains_synthetic_media=True,
            owner_note="Owner authorizes bounded private-only uploads; no public release")

    def agent(self,transport=None):
        return PrivateUploadAgent(self.pi,self.catalogue,self.journal,TOKEN,
                                  transport=transport or FakeYouTube())

    def test_without_standing_owner_grant_no_job_and_no_youtube(self):
        google=FakeYouTube()
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],"NO_ELIGIBLE_PRIVATE_UPLOAD_JOB")
        self.assertEqual(google.started,0)
        self.assertIsNone(self.journal.status(self.render["job_id"]))
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],0)

    def test_owner_grant_autonomous_private_job_to_owner_review(self):
        self.grant()
        google=FakeYouTube()
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],
            "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertTrue(result["owner_review_queued"])
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(google.started,1)
        self.assertGreaterEqual(self.pi.proofs,2)
        self.assertEqual(google.metadata["status"]["privacyStatus"],"private")
        self.assertNotIn("publishAt",str(google.metadata))
        view=PreviewReview(self.queue).snapshot()
        self.assertEqual(view["pending_review"],1)
        self.assertEqual(view["previews"][0]["video_id"],VIDEO)
        self.assertTrue(view["previews"][0]["platform_privacy_verified"])
        self.assertFalse(view["public_release_authorized"])
        repeated=self.agent(google).run_once()
        self.assertEqual(repeated["status"],"NO_ELIGIBLE_PRIVATE_UPLOAD_JOB")
        self.assertEqual(google.started,1)

    def test_paused_owner_grant_refuses_auto_queue(self):
        self.grant()
        self.policy.pause("colors-ar")
        google=FakeYouTube()
        self.assertEqual(self.agent(google).run_once()["status"],
                         "NO_ELIGIBLE_PRIVATE_UPLOAD_JOB")
        self.assertEqual(google.started,0)

    def test_revocation_at_second_live_pi_proof_quarantines_before_network(self):
        self.grant()
        self.pi.on_second_proof=lambda:self.policy.pause("colors-ar")
        google=FakeYouTube()
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],
                         "UPLOAD_MANUAL_RECONCILIATION_REQUIRED")
        self.assertEqual(google.started,0)
        self.assertEqual(self.journal.status(self.render["job_id"])["state"],
                         "STARTED")
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],0)
        self.assertEqual(self.agent(google).run_once()["status"],
                         "NO_ELIGIBLE_PRIVATE_UPLOAD_JOB")
        self.assertEqual(google.started,0)

    def test_upload_processing_not_finished_never_enters_review(self):
        self.grant()
        google=FakeYouTube(processing="processing")
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],"YOUTUBE_PRIVATE_PROCESSING_PENDING")
        self.assertFalse(result["owner_review_queued"])
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],0)
        self.assertEqual(google.started,1)
        self.assertEqual(self.agent(google).run_once()["status"],
                         "NO_ELIGIBLE_PRIVATE_UPLOAD_JOB")

    def test_public_visibility_response_never_enqueues_owner_review(self):
        self.grant()
        google=FakeYouTube(visibility="public")
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],
                         "UPLOAD_MANUAL_RECONCILIATION_REQUIRED")
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],0)
        self.assertEqual(google.started,1)

    def test_tampered_owner_plan_not_uploaded(self):
        self.grant()
        self.plan_file.write_text(self.plan_file.read_text()+"\n")
        google=FakeYouTube()
        result=self.agent(google).run_once()
        self.assertEqual(result["status"],"UPLOAD_CONFIG_REJECTED")
        self.assertEqual(google.started,0)
        self.assertIsNone(self.journal.status(self.render["job_id"]))

    def test_wrong_mac_worker_capability_denied(self):
        self.grant()
        with self.assertRaises(TransportError):
            self.coordinator.dispatch("request-private-upload",{},
                "mac-untrusted",frozenset({"voice_synthesize"}))
        with self.assertRaises(TransportError):
            self.coordinator.dispatch("complete-private-upload",{},
                "mac-untrusted",frozenset({"voice_synthesize"}))

    def test_no_publishing_from_fake_owner_approval(self):
        self.grant()
        google=FakeYouTube()
        self.agent(google).run_once()
        decisions=PreviewReview(self.queue)
        result=decisions.decide(VIDEO,"APPROVE",
                               note="The episode is good to publish separately")
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse(result["youtube_visibility_changed"])
        self.assertEqual(google.started,1)


if __name__=="__main__":
    unittest.main()
