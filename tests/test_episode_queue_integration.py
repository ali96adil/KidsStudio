"""Fake-executor M4 tests for Pi media receipts and approved script pinning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.coordinator_api import Coordinator, TransportError
from kidsstudio.media_worker import MediaRecipes, MediaJournal, RemoteMediaWorker
from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_queue import StudioQueue


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakePi:
    def __init__(self, server):
        self.server=server
    def call(self, action, payload):
        return self.server.dispatch(action,payload,"mac-episode-01",
                                    frozenset({"episode_assemble"}))


class FakeExecutor:
    def __init__(self):
        self.calls=[]
    def execute(self, kind, recipe_id, job_id):
        self.calls.append((kind,recipe_id,job_id))
        return {
            "result_status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "artifact_sha256":"c"*64,
            "artifact_bytes":4096,
            "artifact_type":"mp4",
            "publication_approved":False,
        }


class EpisodeRemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",[
            {"title":"Red","objective":"Recognize red"}],activate=True)

        self.source_script=self.root/"script.txt"
        self.source_script.write_text("An owner-reviewed red-ball script")
        self.approved_sha=sha(self.source_script)
        video=self.root/"clip.mp4"
        video.write_bytes(b"fake-video-asset")
        v06=self.root/"face_v06.py"
        v07=self.root/"face_v07.py"
        v06.write_text("pass\n")
        v07.write_text("pass\n")
        self.episode_recipe=self.root/"approved_episode_recipe.json"
        self.episode_recipe.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.root),"output_root":str(self.root/"renders"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(self.source_script),"sha256":self.approved_sha},
            "clips":[{"video":str(video),"sha256":sha(video),"face_cleanup":"none"}],
            "tools":{
                "ffmpeg":sys.executable,"ffprobe":sys.executable,
                "face_python":sys.executable,
                "face_v06":str(v06),"face_v06_sha256":sha(v06),
                "face_v07":str(v07),"face_v07_sha256":sha(v07),
            },
        }))
        self.catalog=self.root/"recipes.json"
        self.catalog.write_text(json.dumps({
          "schema_version":1,
          "recipes":{"red_ball_episode":{
            "kind":"episode_assemble",
            "output_root":str(self.root/"renders"),
            "inputs":{"episode_recipe":str(self.episode_recipe)},
            "sha256":{"episode_recipe":sha(self.episode_recipe)},
          }}
        }))
        self.server=Coordinator(self.queue,self.root/"private_vault",{
            "mac-episode-01":("test-local-token-"+"t"*45,{"episode_assemble"})
        })
        self.executor=FakeExecutor()
        self.worker=RemoteMediaWorker(
            FakePi(self.server),MediaRecipes(self.catalog),
            MediaJournal(self.root/"media_receipts.sqlite"),
            executor=self.executor)

    def script_approved_for_fixture(self, digest=None):
        # Editorial AI and its owner gate are independently tested in M3.
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",
                (digest or self.approved_sha,))

    def test_episode_receipt_does_not_auto_approve(self):
        self.script_approved_for_fixture()
        job_id=self.series.queue_render("colors-ar",1,"red_ball_episode",
                                         media_kind="episode_assemble")
        self.assertEqual(self.queue.get(job_id)["kind"],"episode_assemble")
        self.assertEqual(self.worker.run_once()["status"],"COMPLETED")
        self.assertEqual(len(self.executor.calls),1)
        self.assertEqual(self.series.reconcile(),1)
        ep=self.series.snapshot()["episodes"][0]
        self.assertEqual(ep["state"],"RENDERED_QA_PENDING")
        with self.assertRaises(SeriesError):
            self.series.complete_series("colors-ar")
        self.series.approve_episode("colors-ar",1,
                       "Owner inspected staged video, sound and rights")
        self.series.complete_series("colors-ar")
        self.assertEqual(self.series.snapshot()["series"][0]["state"],
                         "COMPLETED")

    def test_changed_recipe_fails_before_execution(self):
        self.script_approved_for_fixture()
        self.series.queue_render("colors-ar",1,"red_ball_episode",
                                  media_kind="episode_assemble")
        self.episode_recipe.write_text('{"modified":true}')
        result=self.worker.run_once()
        self.assertEqual(result["status"],"CONFIG_REJECTED")
        self.assertEqual(self.executor.calls,[])
        self.series.reconcile()
        self.assertEqual(self.series.snapshot()["episodes"][0]["state"],"BLOCKED")

    def test_script_hash_mismatch_fails_before_execution(self):
        self.script_approved_for_fixture("b"*64)
        self.series.queue_render("colors-ar",1,"red_ball_episode",
                                  media_kind="episode_assemble")
        result=self.worker.run_once()
        self.assertEqual(result["status"],"CONFIG_REJECTED")
        self.assertEqual(self.executor.calls,[])

    def test_media_cannot_use_editorial_complete_to_bypass_receipt(self):
        self.script_approved_for_fixture()
        self.series.queue_render("colors-ar",1,"red_ball_episode",
                                  media_kind="episode_assemble")
        job=self.server.dispatch("claim",{},"mac-episode-01",
                                 frozenset({"episode_assemble"}))["job"]
        with self.assertRaises(TransportError):
            self.server.dispatch("complete",{
                "job_id":job["job_id"],"generation":job["generation"],
                "provider_id":"dummy","model":"pretend","answer":"PASS"
            },"mac-episode-01",frozenset({"episode_assemble"}))


if __name__=="__main__":
    unittest.main()
