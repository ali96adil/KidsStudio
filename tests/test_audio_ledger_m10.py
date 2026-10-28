"""M10 audio evidence integration with real StudioQueue + M6 stage approvals."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_stage_ledger import StageLedger, StageLedgerError
from kidsstudio.studio_audio_ledger import AudioEvidenceLedger,AudioEvidenceError
from kidsstudio.studio_dashboard import build_snapshot


class AudioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",
            [{"title":"Red","objective":"Recognize the color red"}],activate=True)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes
                SET state='SCRIPT_APPROVED',source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",("a"*64,))
        self.stages=StageLedger(self.queue)
        self.stages.initialize()
        self.audio=AudioEvidenceLedger(self.queue)
        self.audio.initialize()
        self.report_file=self.root/"technical_audio.json"
        self.voice_sha="b"*64
        self.a2v_sha="c"*64

    def _job(self,kind,receipt_status,digest,media_type):
        id=self.stages.queue_stage("colors-ar",1,kind,"owner_"+kind)
        lease=self.queue.claim(worker_id="mac",capabilities=[kind])
        self.assertEqual(lease["job_id"],id)
        self.queue.complete(
            job_id=id,worker_id="mac",generation=lease["generation"],result={
                "status":receipt_status,"artifact_sha256":digest,
                "artifact_type":media_type,"publication_approved":False
            })
        self.stages.reconcile()

    def setup_voice_and_ltx(self):
        self._job("voice_synthesize","VOICE_RENDERED_PENDING_QA",
                  self.voice_sha,"wav")
        self.stages.approve("colors-ar",1,"voice_synthesize",self.voice_sha,
                            "Owner listened to entire approved source WAV")
        self._job("ltx_animate","A2V_RENDERED_PENDING_QA",
                  self.a2v_sha,"mp4")

    def report(self,**changes):
        content={
            "schema_version":1,
            "status":"AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED",
            "voice_sha256":self.voice_sha,
            "a2v_sha256":self.a2v_sha,
            "voice_seconds":4.0,
            "a2v_audio_seconds":4.0,
            "duration_close":True,
            "envelope_correlation":0.97,
            "estimated_lag_seconds":0.04,
            "energy_present":True,
            "audio_content_identity_proven":False,
            "speaker_identity_proven":False,
            "lip_sync_verified":False,
            "owner_audiovisual_review_required":True,
            "publishing_approved":False,
        }
        content.update(changes)
        self.report_file.write_text(json.dumps(content),encoding="utf-8")

    def test_requires_source_approved_voice_and_current_ltx_report(self):
        with self.assertRaises(AudioEvidenceError):
            self.report()
            self.audio.register("colors-ar",1,self.report_file)
        self.setup_voice_and_ltx()
        with self.assertRaises(StageLedgerError):
            self.stages.approve("colors-ar",1,"ltx_animate",self.a2v_sha,
                                "Owner reviewed lipsync and safe motions")
        self.report()
        self.audio.register("colors-ar",1,self.report_file)
        view=build_snapshot(self.queue)
        self.assertEqual(view["episodes"][0]["audio_continuity"]["state"],
                         "TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING")
        self.assertEqual(view["episodes"][0]["stages"][4]["status"],"in_review")
        self.assertEqual(len(self.audio.snapshot()),1)
        with self.assertRaises(AudioEvidenceError):
            self.audio.register("colors-ar",1,self.report_file)
        self.stages.approve("colors-ar",1,"ltx_animate",self.a2v_sha,
                            "Owner reviewed animation, lip sync and scene continuity")
        self.assertEqual(build_snapshot(self.queue)["episodes"][0]["stages"][4]["status"],
                         "complete")

    def test_wrong_voice_sha_and_false_lipsync_claim_rejected(self):
        self.setup_voice_and_ltx()
        self.report(voice_sha256="f"*64)
        with self.assertRaises(AudioEvidenceError):
            self.audio.register("colors-ar",1,self.report_file)
        self.report(lip_sync_verified=True)
        with self.assertRaises(AudioEvidenceError):
            self.audio.register("colors-ar",1,self.report_file)
        self.report(status="AUDIO_CONTINUITY_UNVERIFIED")
        with self.assertRaises(AudioEvidenceError):
            self.audio.register("colors-ar",1,self.report_file)
        with self.assertRaises(StageLedgerError):
            self.stages.approve("colors-ar",1,"ltx_animate",self.a2v_sha,
                               "Unverified source cannot be approved in M10")

    def test_audio_evidence_not_reported_as_ltx_completion(self):
        self.setup_voice_and_ltx()
        self.report()
        self.audio.register("colors-ar",1,self.report_file)
        view=build_snapshot(self.queue)
        self.assertEqual(view["episodes"][0]["audio_continuity"]["correlation"],0.97)
        self.assertNotEqual(view["episodes"][0]["stages"][4]["status"],"complete")
        self.assertFalse(view["limits"]["publishing"])


if __name__=="__main__":
    unittest.main()
