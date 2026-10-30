"""M65 ordinary educational video: Mac LAN bytes -> Pi M8 QA -> Pi Google.

Reuses independent M26 synthetic original approved episode receipts. Real
media and OAuth/YouTube/network requests are NOT used by these tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_autonomous_private_m26 import (
    AutonomousPrivateUploadTests,FakeYouTube,CHANNEL)
from kidsstudio.pi_media_inbox import PiMediaInbox
from kidsstudio.pi_ordinary_inbox import (
    PiOrdinaryInbox,OrdinaryInboxError,READY)
from kidsstudio.pi_ordinary_uploader import PiOrdinaryUploadService
from kidsstudio.mac_ordinary_to_pi import transfer_ordinary_to_pi
from kidsstudio.youtube_private_upload import UploadJournal
from kidsstudio.private_preview_review import PreviewReview
from kidsstudio.private_upload_policy import PrivatePolicyError


class FakeOAuth:
    def token(self):return "x"*46


class M65PiOrdinaryUploadTests(unittest.TestCase):
    def setUp(self):
        # Reuse a real M26 policy+QA+render ledger, rather than forging
        # approval in the new Pi ordinary receiver tests.
        original=AutonomousPrivateUploadTests(
            "test_owner_grant_autonomous_private_job_to_owner_review")
        original.setUp()
        self.addCleanup(original.doCleanups)
        self.old=original
        self.old.grant()
        self.queue=original.queue
        self.root=original.root
        self.job=original.render["job_id"]
        self.inbox=PiOrdinaryInbox(self.queue,self.root/"pi-inbox")
        PiMediaInbox(self.queue,self.root/"pi-inbox").root.mkdir(
            parents=True,mode=0o700)
        self.inbox.initialize()
        self.mac=self.root/"mac_renders"/self.job
        self.mac.mkdir(parents=True)
        self.master=self.mac/"episode_qa_master.mp4"
        shutil.copyfile(self.old.media,self.master)
        self.plan=self.root/"mac_plan.json"
        shutil.copyfile(self.old.plan_file,self.plan)
        self.ready=self.root/"mac_m8.json"
        shutil.copyfile(self.old.ready,self.ready)
        self.journal=UploadJournal(self.root/"pi-only-upload.sqlite")

    def stage(self):
        self.inbox.prepare(self.job)
        folder=self.inbox.root/self.job
        shutil.copyfile(self.master,folder/"episode_qa_master.mp4.part")
        shutil.copyfile(self.plan,folder/"private_upload_plan.json.part")
        shutil.copyfile(self.ready,folder/"m8_readiness.json.part")
        return folder

    def test_pi_full_original_master_sha_m8_and_owner_gate(self):
        folder=self.stage()
        accepted=self.inbox.accept(self.job)
        self.assertEqual(accepted["status"],READY)
        checked=self.inbox.verify(self.job,full_sha=True)
        self.assertEqual(checked["master_sha256"],
                         hashlib.sha256(self.master.read_bytes()).hexdigest())
        self.assertTrue(checked["catalogue"].is_file())
        with self.assertRaises(OrdinaryInboxError):
            self.inbox.accept(self.job)
        self.assertFalse((folder/"episode_qa_master.mp4.part").exists())

    def test_pi_rejects_modified_original_media_and_policy(self):
        folder=self.stage()
        original=folder/"episode_qa_master.mp4.part"
        original.write_bytes(original.read_bytes()+b"tampered")
        with self.assertRaises(OrdinaryInboxError):
            self.inbox.accept(self.job)
        shutil.copyfile(self.master,original)
        self.inbox.accept(self.job)
        self.old.policy.pause("colors-ar")
        with self.assertRaises(OrdinaryInboxError):
            self.inbox.verify(self.job,full_sha=True)

    def test_pi_service_uploads_original_episode_without_mac(self):
        self.stage()
        fake=FakeYouTube()
        service=PiOrdinaryUploadService(
            self.queue,self.inbox,FakeOAuth(),
            journal=self.journal,transport=fake)
        done=service.poll_once()
        self.assertEqual(done["status"],
            "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertEqual(done["uploader_device"],"RASPBERRY_PI")
        self.assertFalse(done["mac_required_for_upload"])
        self.assertEqual(fake.started,1)
        previews=PreviewReview(self.queue).snapshot()
        self.assertEqual(previews["pending_review"],1)
        self.assertEqual(self.journal.status(self.job)["state"],
                         "PRIVATE_VERIFIED")
        self.assertEqual(service.poll_once()["status"],
                         "M65_PI_ORDINARY_UPLOAD_IDLE")
        self.assertEqual(fake.started,1)

    def test_pi_get_only_processing_after_mac_power_off(self):
        self.stage()
        google=FakeYouTube(processing="processing")
        service=PiOrdinaryUploadService(
            self.queue,self.inbox,FakeOAuth(),
            journal=self.journal,transport=google)
        first=service.poll_once()
        self.assertEqual(first["status"],"YOUTUBE_PRIVATE_PROCESSING_PENDING")
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],0)
        self.assertEqual(google.started,1)
        google.processing="succeeded"
        second=service.poll_once()
        self.assertEqual(second["status"],"M65_PI_PRIVATE_OWNER_REVIEW_READY")
        self.assertEqual(second["uploader_device"],"RASPBERRY_PI")
        self.assertEqual(PreviewReview(self.queue).snapshot()["pending_review"],1)
        self.assertEqual(google.started,1)
        self.assertEqual(self.journal.status(self.job)["state"],
                         "PRIVATE_VERIFIED")
        self.assertEqual(service.poll_once()["status"],
                         "M65_PI_ORDINARY_UPLOAD_IDLE")
        self.assertEqual(google.started,1)

    def test_mac_ordinary_rsync_only_sends_three_part_files(self):
        self.inbox.prepare(self.job)
        seen=[]
        def pretend_rsync(args,*,check,timeout,stdout,stderr):
            seen.append(args)
            src=Path(args[-2])
            dest=Path(args[-1].split(":")[-1].strip("'"))
            shutil.copyfile(src,dest)
        key=self.root/"m65-transfer.key"
        key.write_text("test-not-a-real-key")
        key.chmod(0o600)
        outcome=transfer_ordinary_to_pi(
            media=self.master,plan_file=self.plan,readiness_file=self.ready,
            pi_host="pi-kids.local",pi_user="kidsstudio",
            pi_inbox_root=str(self.inbox.root),ssh_key=key,
            runner=pretend_rsync)
        self.assertEqual(outcome["status"],
                         "M65_MAC_ORDINARY_LAN_SENT_PI_HASH_PENDING")
        self.assertEqual(len(seen),3)
        self.assertEqual(self.inbox.accept(self.job)["status"],READY)
        self.assertTrue(self.inbox.verify(self.job,full_sha=True))


if __name__=="__main__":
    unittest.main()
