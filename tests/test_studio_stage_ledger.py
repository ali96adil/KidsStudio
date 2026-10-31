"""M6 voice→LTX provenance and dashboard tests on local synthetic Pi SQLite."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_stage_ledger import StageLedger, StageLedgerError
from kidsstudio.studio_dashboard import build_snapshot


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.queue=StudioQueue(Path(self.tmp.name)/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue);self.series.initialize()
        self.series.create_series("colors-ar","الألوان","ar",
              [{"title":"أحمر","objective":"تعليم اللون الأحمر"}],activate=True)
        self.stages=StageLedger(self.queue);self.stages.initialize()
        self.digest="a"*64
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                        source_sha256=? WHERE series_id='colors-ar' AND ordinal=1""",
                        (self.digest,))

    def _complete_voice(self):
        job=self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_local_v1")
        lease=self.queue.claim(worker_id="macvoice",
                                capabilities=["voice_synthesize"])
        self.assertEqual(lease["job_id"],job)
        self.queue.complete(job_id=job,worker_id="macvoice",
                            generation=lease["generation"],result={
              "status":"VOICE_RENDERED_PENDING_QA",
              "artifact_sha256":"b"*64,"artifact_type":"wav",
              "publication_approved":False})
        self.assertEqual(self.stages.reconcile(),1)
        return job

    def test_sequence_refuses_a2v_until_voice_owner_approves(self):
        with self.assertRaises(StageLedgerError):
            self.stages.queue_stage("colors-ar",1,"ltx_animate","ltx_local_v1")
        self._complete_voice()
        view=build_snapshot(self.queue)
        self.assertEqual(view["episodes"][0]["stages"][3]["status"],"in_review")
        self.assertEqual(view["episodes"][0]["stages"][4]["status"],"not_tracked")
        with self.assertRaises(StageLedgerError):
            self.stages.queue_stage("colors-ar",1,"ltx_animate","ltx_local_v1")
        with self.assertRaises(StageLedgerError):
            self.stages.approve("colors-ar",1,"voice_synthesize","c"*64,
                                "Looked at voice output and approved")
        self.stages.approve("colors-ar",1,"voice_synthesize","b"*64,
                            "Owner listened and verified exact voice WAV")
        view=build_snapshot(self.queue)
        self.assertEqual(view["episodes"][0]["stages"][3]["status"],"complete")
        next_job=self.stages.queue_stage("colors-ar",1,"ltx_animate","ltx_local_v1")
        payload=json.loads(self.queue.get(next_job)["payload"])
        self.assertEqual(payload["script_sha256"],self.digest)
        self.assertEqual(payload["voice_sha256"],"b"*64)
        with self.assertRaises(SeriesError):
            self.series.queue_render("colors-ar",1,"composite",
                                     media_kind="episode_assemble")
        lease=self.queue.claim(worker_id="macltx",capabilities=["ltx_animate"])
        self.queue.complete(job_id=next_job,worker_id="macltx",
                            generation=lease["generation"],result={
             "status":"A2V_RENDERED_PENDING_QA","artifact_sha256":"c"*64,
             "artifact_type":"mp4","publication_approved":False})
        self.stages.reconcile()
        self.assertEqual(build_snapshot(self.queue)["episodes"][0]["stages"][4]["status"],
                         "in_review")
        self.stages.approve("colors-ar",1,"ltx_animate","c"*64,
                            "Owner checked audio animation lip sync")
        self.assertEqual(build_snapshot(self.queue)["episodes"][0]["stages"][4]["status"],
                         "complete")
        self.series.queue_render("colors-ar",1,"composite",
                                 media_kind="episode_assemble")

    def test_failed_voice_no_automatic_retry(self):
        job=self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_v1")
        lease=self.queue.claim(worker_id="mac",capabilities=["voice_synthesize"])
        self.queue.fail(job_id=job,worker_id="mac",generation=lease["generation"],
                        error_code="ENGINE_FAILURE",retryable=False)
        self.stages.reconcile()
        self.assertEqual(self.stages.snapshot()[0]["state"],"BLOCKED")
        with self.assertRaises(StageLedgerError):
            self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_v1")
        with self.assertRaises(StageLedgerError):
            self.stages.approve("colors-ar",1,"voice_synthesize","b"*64,
                                "Not rendered but trying to approve")
        self.stages.retry_blocked("colors-ar",1,"voice_synthesize",
                        "Owner inspected failed hardware worker and reauthorized")
        new=self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_v1")
        self.assertNotEqual(new,job)

    def test_double_enqueue_and_forged_status_rejected(self):
        job=self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_v1")
        with self.assertRaises(StageLedgerError):
            self.stages.queue_stage("colors-ar",1,"voice_synthesize","voice_v1")
        lease=self.queue.claim(worker_id="mac",capabilities=["voice_synthesize"])
        self.queue.complete(job_id=job,worker_id="mac",generation=lease["generation"],
                            result={"status":"FAKE_PASS","artifact_sha256":"e"*64,
                                    "artifact_type":"wav","publication_approved":False})
        self.stages.reconcile()
        self.assertEqual(self.stages.snapshot()[0]["state"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
