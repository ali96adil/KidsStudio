"""M61 TLS Mac worker one-shot journal tests; no devices or network."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.media_worker import MediaJournal
from kidsstudio.recovery_remote_worker import RemoteRecoveryWorker


class FakePi:
    def __init__(self):
        self.job="a"*32
        self.calls=[]
        self.claims=0
        self.complete_ok=True
    def call(self,action,body):
        self.calls.append((action,body))
        if action=="recovery-claim":
            self.claims+=1
            return {"job":{
                "kind":"recovery_assemble",
                "job_id":self.job,"generation":1,
                "proposal_id":"b"*32,
                "original_job_id":"c"*32,
                "recipe_sha256":"d"*64,
            }}
        if action=="recovery-complete":
            if not self.complete_ok:
                raise ValueError("synthetic dropped ack")
            return {"status":"M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW"}
        if action=="recovery-fail":
            return {"status":"M61_FAILED_REQUIRES_MANUAL_RECONCILIATION"}
        if action=="recovery-pre-execution-check":
            return {"status":"M61_CURRENT_PRIVATE_RECOVERY_LEASE"}
        if action=="recovery-heartbeat":
            return {"ok":True}
        raise ValueError("unsupported fake Pi call")


class RemoteRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m61-worker-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.file=self.root/"original_payload.json"
        self.file.write_text(json.dumps({
            "recipe_id":"assembly_one",
            "script_sha256":"e"*64,"catalogue_sha256":"f"*64
        }))
        self.pi=FakePi()
        self.journal=MediaJournal(self.root/"journal.sqlite")
        self.executions=[]
        def execute(recipes,journal,**params):
            self.executions.append(params)
            return {"status":"M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW",
                    "artifact_sha256":"1"*64,
                    "artifact_bytes":4096,
                    "final_m7_full_decode_passed":True,
                    "publication_approved":False}
        self.executor=execute

    def worker(self):
        return RemoteRecoveryWorker(
            self.pi,object(),self.journal,
            original_job_id="c"*32,proposal_id="b"*32,
            original_payload_file=self.file,
            heartbeat_seconds=.05,executor=self.executor)

    def test_m61_one_at_most_start_and_no_rerender_on_replay(self):
        w=self.worker()
        first=w.run_once()
        self.assertEqual(first["status"],"M61_COMPLETED_PRIVATE_REVIEW_REQUIRED")
        self.assertEqual(len(self.executions),1)
        self.assertEqual(self.pi.calls[0],
            ("recovery-claim",{"proposal_id":"b"*32}))
        self.assertEqual(sum(a=="recovery-complete" for a,_ in self.pi.calls),1)
        second=w.run_once()
        self.assertEqual(second["status"],"M61_MAC_REPLAY_BLOCKED_NO_RETRY")
        self.assertEqual(len(self.executions),1)
        self.assertEqual(sum(a=="recovery-fail" for a,_ in self.pi.calls),1)

    def test_m61_uncertain_pi_ack_never_regenerates_media(self):
        self.pi.complete_ok=False
        w=self.worker()
        first=w.run_once()
        self.assertEqual(first["status"],"M61_PENDING_ACK_NO_AUTO_RETRY")
        second=w.run_once()
        self.assertEqual(second["status"],"M61_MAC_REPLAY_BLOCKED_NO_RETRY")
        self.assertEqual(len(self.executions),1)

    def test_m61_unsafe_private_original_payload_rejected_before_claim(self):
        self.file.write_text(json.dumps({
            "recipe_id":"assembly_one","script_sha256":"e"*64,
            "catalogue_sha256":"f"*64,
            "unsafe_public_release_authorized":True}))
        with self.assertRaises(ValueError):
            self.worker()
        self.assertEqual(self.pi.calls,[])


if __name__=="__main__":
    unittest.main()
