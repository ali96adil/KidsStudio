"""Offline series production regression tests; no paid API, GPU or upload."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_queue import StudioQueue


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue=StudioQueue(Path(self.temp.name)/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()

    def add(self, n=3, sid="colors-ar", active=True):
        self.series.create_series(sid,"Colors","ar",[
            {"title":f"Lesson {x}","objective":f"Learn color {x}"}
            for x in range(1,n+1)],activate=active)

    def test_active_lock_and_explicit_pause(self):
        self.add()
        with self.assertRaises(SeriesError):
            self.add(sid="letters-ar")
        with self.assertRaises(SeriesError):
            self.series.pause("colors-ar","")
        self.series.pause("colors-ar","Owner-approved series break")
        self.add(sid="letters-ar")
        self.assertEqual(len([s for s in self.series.snapshot()["series"]
                              if s["state"]=="ACTIVE"]),1)

    def test_backlog_is_bounded_and_idempotent(self):
        self.add(n=12)
        with ThreadPoolExecutor(max_workers=4) as pool:
            batches=list(pool.map(lambda _:self.series.plan_drafts(),range(8)))
        self.assertEqual(sum(map(len,batches)),3)
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],3)
        self.assertEqual(self.series.plan_drafts(),[])
        self.assertEqual(len(self.series.snapshot()["episodes"]),12)

    def test_queue_pause_blocks_new_drafts(self):
        self.add()
        self.queue.set_paused(True)
        self.assertEqual(self.series.plan_drafts(),[])
        self.queue.set_paused(False)
        self.assertEqual(len(self.series.plan_drafts()),3)

    def test_full_owner_gated_episode_lifecycle(self):
        self.add(n=1)
        self.series.plan_drafts()
        with self.assertRaises(SeriesError):
            self.series.complete_series("colors-ar")
        with self.assertRaises(SeriesError):
            self.series.queue_render("colors-ar",1,"bunny_scene")
        draft=self.queue.claim(worker_id="writer",capabilities=["script_draft"])
        digest="a"*64
        self.queue.complete_draft_and_enqueue_review(
            job_id=draft["job_id"],worker_id="writer",
            generation=draft["generation"],language="ar",
            result={"status":"DRAFTED_UNREVIEWED",
                    "provider_id":"model_writer",
                    "artifact_sha256":digest,
                    "publication_approved":False})
        self.series.reconcile()
        self.assertEqual(self.series.snapshot()["episodes"][0]["state"],
                         "REVIEW_QUEUED")
        with self.assertRaises(SeriesError):
            self.series.approve_script("colors-ar",1,digest,"I reviewed")
        review=self.queue.claim(worker_id="reviewer",
                                 capabilities=["editorial_review"])
        self.queue.complete(job_id=review["job_id"],worker_id="reviewer",
                            generation=review["generation"],result={
              "status":"EDITORIAL_REVIEW_UNVERIFIED",
              "publication_approved":False})
        self.series.reconcile()
        with self.assertRaises(SeriesError):
            self.series.approve_script("colors-ar",1,"b"*64,"Wrong hash")
        self.series.approve_script("colors-ar",1,digest,
                                   "Owner reviewed exact script")
        self.series.queue_render("colors-ar",1,"approved_bunny_scene")
        with self.assertRaises(SeriesError):
            self.series.approve_episode("colors-ar",1,"Premature approval")
        media=self.queue.claim(worker_id="media",capabilities=["godot_render"])
        self.queue.complete(job_id=media["job_id"],worker_id="media",
                            generation=media["generation"],result={
              "result_status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
              "artifact_type":"mp4","artifact_sha256":"b"*64,
              "publication_approved":False})
        self.series.reconcile()
        self.assertEqual(self.series.snapshot()["episodes"][0]["state"],
                         "RENDERED_QA_PENDING")
        self.series.approve_episode("colors-ar",1,
                                    "Owner checked audiovisual, pedagogy and rights")
        self.series.complete_series("colors-ar")
        self.assertEqual(self.series.snapshot()["series"][0]["state"],
                         "COMPLETED")

    def test_invalid_media_receipt_is_blocked_and_manually_retryable(self):
        self.add(n=1)
        self.series.plan_drafts()
        # The test simulates an owner-approved script to isolate media behavior.
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?""",("a"*64,))
        old=self.series.queue_render("colors-ar",1,"bunny_scene")
        media=self.queue.claim(worker_id="media",capabilities=["godot_render"])
        self.queue.complete(job_id=media["job_id"],worker_id="media",
                            generation=media["generation"],result={
              "status":"COMPLETED"})
        self.series.reconcile()
        self.assertEqual(self.series.snapshot()["episodes"][0]["state"],"BLOCKED")
        with self.assertRaises(SeriesError):
            self.series.approve_episode("colors-ar",1,"Not really reviewed")
        self.assertEqual(self.series.retry_blocked("colors-ar",1,
                         "Operator inspected failed render and authorized retry"),
                         "SCRIPT_APPROVED")
        new=self.series.queue_render("colors-ar",1,"bunny_scene")
        self.assertNotEqual(new,old)

    def test_reject_bad_syllabus_and_bad_note_reference(self):
        with self.assertRaises(SeriesError):
            self.series.create_series("bad","x","ar",[{"title":"Red"}])
        self.add()
        with self.assertRaises(Exception):
            self.series.note("colors-ar","Observe first color",999)
        self.series.note("colors-ar","Observe first color",1)
        self.assertEqual(len(self.series.snapshot()["notes"]),1)


if __name__=="__main__":
    unittest.main()
