"""M64 offline Pi-owned LAN media + Google PRIVATE uploader integration.

No real SSH, Google, OAuth, owner devices or publishing. Tests real local
file bytes, SQLite inbox, fake isolated Google transport and Pi-only client.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.pi_media_inbox import PiMediaInbox,InboxError,READY as MEDIA_READY
from kidsstudio.mac_to_pi_transfer import (
    transfer_master_to_pi,LANTransferError,main as mac_main)
from kidsstudio.recovery_private_upload_gate import (
    RecoveryPrivateUploadGate,VERIFIED,FAILED)
from kidsstudio.pi_recovery_uploader import (
    PiPrivateUploadService,GoogleOAuthRefresh)
from kidsstudio.youtube_private_upload import UploadJournal


class FakeGoogle:
    def __init__(self):
        self.calls=[]
        self.processing="succeeded"
    def start(self,token,meta,size):
        self.calls.append(("start",meta))
        assert meta["status"]["privacyStatus"]=="private"
        assert meta["status"]["selfDeclaredMadeForKids"] is True
        return "fake-google-session"
    def put_chunk(self,token,session,data,offset,total):
        self.calls.append(("chunk",len(data)))
        assert offset+len(data)==total
        return 200,"abcdefghijk"
    def verify(self,token,video_id,channel):
        self.calls.append(("verify",video_id))
        return {"video_id":video_id,"channel_id":channel,
            "privacy_status":"private","processing_status":self.processing,
            "verified_using_authenticated_youtube_api":True}


class FakeOAuth:
    def token(self):return "x"*44


class M64LocalPiTransferTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="ks-m64-pi-lan-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.inbox=PiMediaInbox(self.queue,self.root/"private_pi_inbox")
        # M62/LAN tests operate against a precise synthetic, but no invented
        # real YouTube/media approvals; the M62 full gate is tested separately.
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_recovery_private_handoffs(
                proposal_id TEXT PRIMARY KEY,created_at REAL)""")
            db.execute("""INSERT INTO studio_recovery_private_handoffs
                VALUES(?,?)""",("b"*32,1.0))
            db.execute("""CREATE TABLE studio_recovery_intents(
                proposal_id TEXT PRIMARY KEY,series_id TEXT,ordinal INTEGER)""")
            db.execute("""INSERT INTO studio_recovery_intents VALUES(?,?,?)""",
                       ("b"*32,"colors-ar",1))
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,max_uploads_24h INTEGER)""")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES(?,?)""",("colors-ar",2))
        self.inbox.initialize()
        self.gate=RecoveryPrivateUploadGate(self.queue)
        self.gate.initialize()
        self.job="a"*32
        self.proposal="b"*32
        self.channel="UC"+"a"*22
        self.video_bytes=b"M64 PRIVATE SYNTHETIC VIDEO BYTES"*128
        self.sha=hashlib.sha256(self.video_bytes).hexdigest()
        self.proof={
            "job_id":self.job,"proposal_id":self.proposal,
            "master_sha256":self.sha,"series_id":"colors-ar",
            "episode_number":1,"channel_id":self.channel,
            "original_job_id":"c"*32,
            "made_for_kids":True,"contains_synthetic_media":True,
            "policy_revision":1,"script_sha256":"d"*64,
            "review_bundle_sha256":"e"*64,
            "tech_report_sha256":"f"*64}
        self.mac=self.root/"mac_outputs"/self.job
        self.mac.mkdir(parents=True)
        self.master=self.mac/"episode_qa_master.mp4"
        self.master.write_bytes(self.video_bytes)
        self.plan=self.mac/"private_upload_plan.json"
        self.plan.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"proposal_id":self.proposal,
            "recovery_job_id":self.job,"master_sha256":self.sha,
            "target_channel_id":self.channel,
            "title":"Original science lesson",
            "description":"Educational original video",
            "category_id":"27",
            "made_for_kids":True,"contains_synthetic_media":True,
        }))
        self.key=self.root/"transfer_key"
        self.key.write_text("not an actual key; rsync test never uses it")
        self.key.chmod(0o600)

    def _stage(self):
        self.inbox.prepare(self.proposal)
        target=self.inbox.root/self.job
        (target/"episode_qa_master.mp4.part").write_bytes(self.video_bytes)
        shutil.copyfile(self.plan,target/"private_upload_plan.json.part")
        return target

    def _patched(self):
        return patch.object(RecoveryPrivateUploadGate,"_source",
                            return_value=self.proof)

    def test_pi_full_sha_atomically_accepts_and_cannot_overwrite(self):
        with self._patched():
            target=self._stage()
            accepted=self.inbox.accept(self.proposal)
            self.assertEqual(accepted["status"],MEDIA_READY)
            self.assertIs(accepted["mac_required_for_upload"],False)
            self.assertEqual(self.inbox.verify(
                self.proposal,full_sha=True)["master_sha256"],self.sha)
            self.assertFalse((target/"episode_qa_master.mp4.part").exists())
            self.assertEqual((target/"episode_qa_master.mp4").read_bytes(),
                             self.video_bytes)
            with self.assertRaises(InboxError):
                self.inbox.accept(self.proposal)
            (target/"episode_qa_master.mp4").chmod(0o600)
            (target/"episode_qa_master.mp4").write_bytes(
                b"modified bytes "+self.video_bytes[:64])
            with self.assertRaises(InboxError):
                self.inbox.verify(self.proposal,full_sha=True)

    def test_pi_rejects_incomplete_or_forged_media_no_upload(self):
        with self._patched():
            target=self._stage()
            first=target/"episode_qa_master.mp4.part"
            first.write_bytes(self.video_bytes[:-1])
            with self.assertRaises(InboxError):
                self.inbox.accept(self.proposal)
            self.assertFalse((target/"episode_qa_master.mp4").exists())
            first.write_bytes(self.video_bytes)
            values=json.loads((target/"private_upload_plan.json.part").read_text())
            values["target_channel_id"]="UC"+"b"*22
            (target/"private_upload_plan.json.part").write_text(json.dumps(values))
            with self.assertRaises(InboxError):
                self.inbox.accept(self.proposal)
            with self.queue._connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM studio_recovery_pi_media").fetchone()[0],0)

    def test_mac_local_rsync_produces_only_part_files_no_google(self):
        with self._patched():
            target=self.inbox.prepare(self.proposal)
            seen=[]
            def fake_rsync(args,*,check,timeout,stdout,stderr):
                seen.append(args)
                src=Path(args[-2])
                dest=args[-1].split(":")[-1].strip("'")
                Path(dest).write_bytes(src.read_bytes())
            result=transfer_master_to_pi(
                media=self.master,plan_file=self.plan,
                pi_host="pi-kids.local",pi_user="kidsstudio",
                pi_inbox_root=str(self.inbox.root),
                ssh_key=self.key,runner=fake_rsync)
            self.assertEqual(result["status"],
                "M64_MAC_LAN_TRANSFER_SENT_PI_SHA_NOT_YET_CONFIRMED")
            self.assertEqual(len(seen),2)
            self.assertIn("--partial",seen[0])
            self.assertIn("--inplace",seen[0])
            self.assertFalse((self.inbox.root/self.job/
                "episode_qa_master.mp4").exists())
            # The Pi does its own verification, not Mac.
            self.assertEqual(self.inbox.accept(self.proposal)["status"],
                             MEDIA_READY)

    def test_mac_transfer_dry_run_no_key_or_network(self):
        buf=StringIO()
        with redirect_stdout(buf):
            code=mac_main(["--media",str(self.master),
                "--plan",str(self.plan),"--pi-host","pi-kids.local",
                "--pi-user","kidsstudio",
                "--pi-inbox-root",str(self.inbox.root),
                "--ssh-key",str(self.key)])
        self.assertEqual(code,0)
        self.assertIn("NO_NETWORK",buf.getvalue())

    def test_pi_upload_completes_with_mac_absent_and_no_double_post(self):
        google=FakeGoogle()
        journal=UploadJournal(self.root/"pi-only-youtube.sqlite")
        with (self._patched(),
              patch.object(RecoveryPrivateUploadGate,"_audit",
                           return_value=None)):
            self._stage()
            service=PiPrivateUploadService(self.queue,self.inbox,FakeOAuth(),
                journal=journal,transport=google)
            first=service.poll_once()
            self.assertEqual(first["status"],VERIFIED)
            self.assertEqual(first["uploader_device"],"RASPBERRY_PI")
            self.assertIs(first["mac_required_for_upload"],False)
            self.assertEqual([x[0] for x in google.calls],
                             ["start","chunk","verify"])
            self.assertEqual(journal.status(self.job)["state"],"PRIVATE_VERIFIED")
            second=service.poll_once()
            self.assertEqual(second["status"],
                "M64_PI_UPLOAD_IDLE_NO_ELIGIBLE_PRIVATE_MEDIA")
            self.assertEqual(len(google.calls),3)

    def test_pi_processing_is_get_only_without_mac_reupload(self):
        google=FakeGoogle();google.processing="processing"
        journal=UploadJournal(self.root/"pi-only-youtube.sqlite")
        with (self._patched(),
              patch.object(RecoveryPrivateUploadGate,"_audit",
                           return_value=None)):
            self._stage()
            service=PiPrivateUploadService(self.queue,self.inbox,FakeOAuth(),
                journal=journal,transport=google)
            first=service.poll_once()
            self.assertEqual(first["status"],
                             "M63_YOUTUBE_PRIVATE_PROCESSING_PENDING")
            self.assertEqual(len(google.calls),3)
            google.processing="succeeded"
            second=service.poll_once()
            self.assertEqual(second["status"],VERIFIED)
            self.assertEqual([x[0] for x in google.calls],
                             ["start","chunk","verify","verify"])
            self.assertEqual(journal.status(self.job)["state"],"PRIVATE_VERIFIED")


if __name__=="__main__":
    unittest.main()
