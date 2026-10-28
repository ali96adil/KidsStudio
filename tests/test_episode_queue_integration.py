"""M4 remote media receipt, Studio Brain and Series Manager integration tests.

All rendering and external inference replaced with a fake approved executor.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.coordinator_api import Coordinator
from kidsstudio.media_worker import MediaRecipes, MediaJournal, RemoteMediaWorker
from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_queue import StudioQueue


class TestPi:
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
        self.episode_recipe=self.root/"approved_episode_recipe.json"
        self.episode_recipe.write_text('{"approved_for_internal_only":true}')
        checksum=hashlib.sha256(self.episode_recipe.read_bytes()).hexdigest()
        self.catalog=self.root/"recipes.json"
        self.catalog.write_text(json.dumps({
          "schema_version":1,
          "recipes":{"red_ball_episode":{
            "kind":"episode_assemble",
            "output_root":str(self.root/"renders"),
            "inputs":{"episode_recipe":str(self.episode_recipe)},
            "sha256":{"episode_recipe":checksum},
          }}
        }))
        self.server=Coordinator(self.queue,self.root/"private_vault",{
            "mac-episode-01":("test-local-token-"+"t"*45,{"episode_assemble"})
        })
        self.executor=FakeExecutor()
        self.worker=RemoteMediaWorker(
            TestPi(self.server),MediaRecipes(self.catalog),
            MediaJournal(self.root/"media_receipts.sqlite"),
            executor=self.executor)

    def script_approved_for_fixture(self):
        # The independent editorial logic is separately tested in M3.
        # This test isolates the media handoff without using real AI.
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",("a"*64,))

    def test_episode_media_receipt_does_not_auto_approve(self):
        self.script_approved_for_fixture()
        job_id=self.series.queue_render("colors-ar",1,"red_ball_episode",
                                         media_kind="episode_assemble")
        self.assertEqual(self.queue.get(job_id)["kind"],"episode_assemble")
        self.assertEqual(self.worker.run_once()["status"],"COMPLETED")
        self.assertEqual(len(self.executor.calls),1)
        self.assertEqual(self.series.reconcile(),1)
        ep=self.series.snapshot()["episodes"][0]
        self.assertEqual(ep["state"],"RENDERED_QA_PENDING")
        self.assertIsNone(ep.get("publication_approved"))
        with self.assertRaises(SeriesError):
            self.series.complete_series("colors-ar")
        self.series.approve_episode("colors-ar",1,
                       "Owner inspected the staged video, sound and rights")
        self.series.complete_series("colors-ar")
        self.assertEqual(self.series.snapshot()["series"][0]["state"],
                         "COMPLETED")

    def test_changed_approved_recipe_fails_before_execution(self):
        self.script_approved_for_fixture()
        self.series.queue_render("colors-ar",1,"red_ball_episode",
                                  media_kind="episode_assemble")
        self.episode_recipe.write_text('{"modified":true}')
        result=self.worker.run_once()
        self.assertEqual(result["status"],"CONFIG_REJECTED")
        self.assertEqual(self.executor.calls,[])
        self.series.reconcile()
        self.assertEqual(self.series.snapshot()["episodes"][0]["state"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
