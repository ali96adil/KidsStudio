"""M63 Mac private upload control tests: fake TLS and fake Google, zero network.

This tests API decisions only. The actual Google OAuth/channel ownership
and real YouTube PRIVATE video must be qualified on the owner's Mac later.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.recovery_private_uploader import (
    RecoveryPrivateUploader, RecoveryPrivateUploaderError, main)
from kidsstudio.youtube_private_upload import UploadJournal


class FakePi:
    def __init__(self):
        self.calls=[]
        self.policy_current=True
        self.job="a"*32
        self.pid="b"*32
        self.sha=None
    def call(self,action,body):
        self.calls.append(action)
        if action=="recovery-private-claim":
            return {"job":{
                "kind":"recovery_private_upload",
                "job_id":self.job,"generation":1,
                "proposal_id":self.pid,
                "master_sha256":self.sha,
                "channel_id":"UC"+"a"*22,
                "public_release_authorized":False}}
        if action=="recovery-private-check":
            return {
                "status":("M63_CURRENT_PRIVATE_UPLOAD_LEASE"
                          if self.policy_current else "M63_REVOKED_NO_UPLOAD"),
                "job_id":self.job,"generation":1,
                "proposal_id":self.pid,
                "series_id":"colors-ar","episode_number":1,
                "master_sha256":self.sha,"channel_id":"UC"+"a"*22,
                "made_for_kids":True,"contains_synthetic_media":True,
                "visibility":"private","public_release_authorized":False}
        if action=="recovery-private-complete":
            receipt=body["receipt"]
            if receipt["ready_for_owner_review"]:
                return {"status":"M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"}
            return {"status":"M63_YOUTUBE_PRIVATE_PROCESSING_PENDING"}
        if action=="recovery-private-fail":
            return {"status":"M63_PRIVATE_UPLOAD_RECONCILIATION_REQUIRED_NO_RETRY"}
        if action=="recovery-private-reverify":
            return {"status":"M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"}
        if action=="recovery-private-heartbeat":
            return {"ok":self.policy_current}
        raise AssertionError("unexpected route "+action)


class FakeYouTube:
    def __init__(self):
        self.metadata=[]
        self.calls=0
        self.processing="succeeded"
    def start(self,token,metadata,size):
        self.calls+=1
        self.metadata.append(metadata)
        return "synthetic-no-real-http"
    def put_chunk(self,token,session,chunk,offset,total):
        self.calls+=1
        assert chunk and offset+len(chunk)==total
        return (200,"abcdefghijk")
    def verify(self,token,video_id,channel):
        self.calls+=1
        return {
            "video_id":video_id,"channel_id":channel,
            "privacy_status":"private",
            "processing_status":self.processing,
            "verified_using_authenticated_youtube_api":True}


class RecoveryUploader63Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m63-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        import hashlib
        self.media=self.root/("a"*32)/"episode_qa_master.mp4"
        self.media.parent.mkdir()
        self.media.write_bytes(b"synthetic-not-a-real-video"*200)
        self.sha=hashlib.sha256(self.media.read_bytes()).hexdigest()
        self.plan=self.root/"private-m63-plan.json"
        self.plan.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "proposal_id":"b"*32,"recovery_job_id":"a"*32,
            "master_sha256":self.sha,"target_channel_id":"UC"+"a"*22,
            "title":"Original colours lesson","description":"Original kids lesson",
            "category_id":"27","made_for_kids":True,
            "contains_synthetic_media":True}))
        self.pi=FakePi();self.pi.sha=self.sha
        self.transport=FakeYouTube()
        self.journal=UploadJournal(self.root/"youtube_m63.sqlite")

    def make_worker(self):
        return RecoveryPrivateUploader(
            self.pi,plan_file=self.plan,media_file=self.media,
            journal=self.journal,token="t"*40,
            transport=self.transport,heartbeat_seconds=.05)

    def test_private_only_uses_exact_channel_and_no_duplicate_network(self):
        first=self.make_worker().run_once()
        self.assertEqual(first["status"],
                         "M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertIs(first["owner_review_available"],True)
        self.assertEqual(self.transport.calls,3)
        metadata=self.transport.metadata[0]
        self.assertEqual(metadata["status"]["privacyStatus"],"private")
        self.assertIs(metadata["status"]["selfDeclaredMadeForKids"],True)
        self.assertIs(metadata["status"]["containsSyntheticMedia"],True)
        self.assertEqual(self.journal.status("a"*32)["state"],"PRIVATE_VERIFIED")
        second=self.make_worker().run_once()
        self.assertEqual(second["status"],"M63_PRIVATE_UPLOAD_BLOCKED_NO_RETRY")
        self.assertEqual(self.transport.calls,3)
        self.assertIn("recovery-private-fail",self.pi.calls)
        self.assertIs(first["public_release_authorized"],False)

    def test_policy_revoked_before_network_stops_without_google(self):
        self.pi.policy_current=False
        result=self.make_worker().run_once()
        self.assertEqual(result["status"],"M63_PRIVATE_UPLOAD_BLOCKED_NO_RETRY")
        self.assertEqual(self.transport.calls,0)

    def test_pending_google_processing_stays_private_no_auto_insert(self):
        self.transport.processing="processing"
        first=self.make_worker().run_once()
        self.assertEqual(first["status"],"M63_YOUTUBE_PRIVATE_PROCESSING_PENDING")
        self.assertIs(first["owner_review_available"],False)
        self.assertEqual(self.journal.status("a"*32)["state"],
                         "UPLOADED_UNVERIFIED")
        self.assertEqual(self.make_worker().run_once()["status"],
                         "M63_PRIVATE_UPLOAD_BLOCKED_NO_RETRY")
        self.assertEqual(self.transport.calls,3)

    def test_get_only_processing_reverify_never_new_upload(self):
        self.transport.processing="processing"
        first=self.make_worker().run_once()
        self.assertEqual(first["status"],"M63_YOUTUBE_PRIVATE_PROCESSING_PENDING")
        start_count=self.transport.calls
        self.transport.processing="succeeded"
        recheck=self.make_worker().reverify_existing()
        self.assertEqual(recheck["status"],
                         "M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertEqual(self.transport.calls,start_count+1)
        self.assertEqual(self.journal.status("a"*32)["state"],"PRIVATE_VERIFIED")
        self.assertIn("recovery-private-reverify",self.pi.calls)
        # Subsequent GET check is intentionally not a second insert.
        with self.assertRaises(RecoveryPrivateUploaderError):
            self.make_worker().reverify_existing()

    def test_changed_media_sha_rejected_before_claim(self):
        self.media.write_bytes(self.media.read_bytes()+b"changed")
        with self.assertRaises(RecoveryPrivateUploaderError):
            self.make_worker()
        self.assertEqual(self.pi.calls,[])

    def test_cli_is_no_network_without_explicit_execute(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out=StringIO()
        with redirect_stdout(out):
            result=main(["--pi-url","https://localhost:8844",
                "--worker-id","mac-private","--plan",str(self.plan),
                "--media",str(self.media),
                "--journal",str(self.root/"unused.sqlite")])
        self.assertEqual(result,0)
        self.assertIn("M64_MAC_GOOGLE_UPLOAD_DISABLED_USE_PI",
                      out.getvalue())
        self.assertFalse((self.root/"unused.sqlite").exists())


if __name__=="__main__":
    unittest.main()
