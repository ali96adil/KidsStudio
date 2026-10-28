"""M7 offline technical and human quality gates; synthetic media only."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.episode_quality import CHECKS, inspect_video, save_report
from kidsstudio.studio_quality_ledger import (
    CRITERIA, QualityGateError, QualityLedger,
)
from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_dashboard import build_snapshot
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.episode_assembly import digest


def fake_probe(path, executable):
    return {
        "format":{"duration":"10.5"},
        "streams":[
            {"codec_type":"video","codec_name":"h264",
             "width":1280,"height":720,"r_frame_rate":"24/1"},
            {"codec_type":"audio","codec_name":"aac","sample_rate":"48000"},
        ]
    }


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",
             [{"title":"Red Ball","objective":"Identify the color red"}],activate=True)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",("a"*64,))
        self.video=self.root/"episode.mp4"
        self.video.write_bytes(b"synthetic-av"*700)
        self.video_sha=digest(self.video)
        self.job=self.series.queue_render("colors-ar",1,"owner_recipe",
                                           media_kind="episode_assemble")
        lease=self.queue.claim(worker_id="media",capabilities=["episode_assemble"])
        self.queue.complete(job_id=self.job,worker_id="media",
                           generation=lease["generation"],result={
              "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
              "artifact_type":"mp4","artifact_sha256":self.video_sha,
              "publication_approved":False})
        self.series.reconcile()
        self.ledger=QualityLedger(self.queue)
        self.ledger.initialize()
        self.tech=self.root/"technical_report.json"
        self.review=self.root/"owner_review.json"

    def technical_report(self, *, expect_sha=None, probe=fake_probe, decode=None):
        return inspect_video(self.video, expect_sha or self.video_sha,
              probe_fn=probe,decode_fn=decode or (lambda p,e:True))

    def write_technical(self, report=None):
        save_report(report or self.technical_report(),self.tech)

    def write_human(self, *, overrides=None, media=None):
        criteria={
          key:{"decision":"PASS","evidence":
             "Owner examined the complete episode and verified " + key}
          for key in CRITERIA
        }
        if overrides:
            criteria.update(overrides)
        self.review.write_text(json.dumps({
           "schema_version":1,"media_sha256":media or self.video_sha,
           "reviewer_role":"owner","criteria":criteria,
           "summary":"Owner completed a full watch, reviewed the learning aim, "
                     "speech, safety, originality and license evidence."
        }),encoding="utf-8")

    def test_technical_pass_is_not_episode_approval(self):
        report=self.technical_report()
        self.assertEqual(set(report["checks"]),set(CHECKS))
        self.assertEqual(report["status"],"TECH_PASS_OWNER_REVIEW_PENDING")
        self.assertFalse(report["subjective_checks_performed"])
        self.assertFalse(report["publishing_approved"])
        self.write_technical(report)
        with self.assertRaises(SeriesError):
            self.series.approve_episode("colors-ar",1,
                            "Incorrect premature owner approval")
        self.ledger.register_technical("colors-ar",1,self.tech)
        self.assertEqual(build_snapshot(self.queue)["episodes"][0]["quality"]["state"],
                         "TECH_PASSED_WAITING_HUMAN")
        with self.assertRaises(SeriesError):
            self.series.approve_episode("colors-ar",1,
                           "Still no owner pedagogic rights QA")

    def test_full_review_human_owner_gate_and_persistence(self):
        self.write_technical()
        self.ledger.register_technical("colors-ar",1,self.tech)
        self.write_human()
        self.ledger.submit_owner_review("colors-ar",1,self.review)
        state=build_snapshot(self.queue)["episodes"][0]["quality"]
        self.assertEqual(state["criteria_passed"],len(CRITERIA))
        self.assertEqual(state["state"],"READY_FOR_OWNER_EPISODE_APPROVAL")
        self.series.approve_episode("colors-ar",1,
             "Owner verified final sound, pedagogy and commercial source rights")
        self.assertEqual(build_snapshot(StudioQueue(self.queue.path))["overview"]["episodes_approved"],1)
        self.assertFalse("PUBLISHED" in build_snapshot(self.queue)["episodes"][0]["state"])
        with self.assertRaises(QualityGateError):
            self.ledger.register_technical("colors-ar",1,self.tech)

    def test_fail_closed_on_mismatched_hash_and_no_decode(self):
        r=self.technical_report(expect_sha="f"*64)
        self.assertEqual(r["status"],"TECH_FAILED")
        self.assertFalse(r["checks"]["media_sha256_matches"])
        self.write_technical(r)
        with self.assertRaises(QualityGateError):
            self.ledger.register_technical("colors-ar",1,self.tech)
        # a decode failure cannot be counted as TECH_PASS
        self.assertEqual(self.technical_report(decode=lambda p,e:False)["status"],
                         "TECH_FAILED")

    def test_wrong_codec_and_fps_rejected(self):
        def bad(p,e):
            result=fake_probe(p,e)
            result["streams"][0]["r_frame_rate"]="30/1"
            result["streams"][1]["codec_name"]="mp3"
            return result
        r=self.technical_report(probe=bad)
        self.assertFalse(r["checks"]["frame_rate_24"])
        self.assertFalse(r["checks"]["aac_audio"])
        self.assertEqual(r["status"],"TECH_FAILED")

    def test_missing_criterion_and_changed_media_rejected(self):
        self.write_technical()
        self.ledger.register_technical("colors-ar",1,self.tech)
        self.write_human(overrides={"child_safety":{
            "decision":"PENDING","evidence":"Requires further child safety review evidence"}})
        with self.assertRaises(QualityGateError):
            self.ledger.submit_owner_review("colors-ar",1,self.review)
        self.write_human(media="c"*64)
        with self.assertRaises(QualityGateError):
            self.ledger.submit_owner_review("colors-ar",1,self.review)
        self.assertEqual(self.ledger.snapshot()[0]["state"],
                         "TECH_PASSED_WAITING_HUMAN")

    def test_stale_render_report_fails_when_new_render_is_current(self):
        self.write_technical()
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes
                 SET render_job_id=?,state='RENDERED_QA_PENDING'
                 WHERE series_id='colors-ar' AND ordinal=1""",("0"*32,))
        with self.assertRaises(QualityGateError):
            self.ledger.register_technical("colors-ar",1,self.tech)


if __name__=="__main__":
    unittest.main()
