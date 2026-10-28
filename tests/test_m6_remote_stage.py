"""M6 real queue/coordinator/journal with fake Mac voice and LTX executors."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.coordinator_api import Coordinator
from kidsstudio.media_worker import MediaRecipes, MediaJournal, RemoteMediaWorker
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.studio_stage_ledger import StageLedger
from kidsstudio.studio_dashboard import build_snapshot


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Pi:
    def __init__(self, coordinator):
        self.coordinator=coordinator
    def call(self,action,body):
        return self.coordinator.dispatch(action,body,"mac-stage-m6",
                frozenset({"voice_synthesize","ltx_animate"}))


class FakeModels:
    def __init__(self):
        self.calls=[]
    def execute(self,kind,recipe,job_id):
        self.calls.append((kind,recipe,job_id))
        return {
            "result_status":"VOICE_RENDERED_PENDING_QA" if kind=="voice_synthesize"
                            else "A2V_RENDERED_PENDING_QA",
            "artifact_sha256":"b"*64 if kind=="voice_synthesize" else "c"*64,
            "artifact_bytes":1024,
            "artifact_type":"wav" if kind=="voice_synthesize" else "mp4",
            "publication_approved":False,
        }


class M6RemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue);self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",
             [{"title":"Red","objective":"Learn red"}],activate=True)
        self.ledger=StageLedger(self.queue);self.ledger.initialize()
        self.script=self.root/"approved.txt";self.script.write_text("Original red story")
        self.voice=self.root/"owner_approved.wav";self.voice.write_bytes(b"synthetic audio")
        self.ref=self.root/"original.png";self.ref.write_bytes(b"synthetic original art")
        self.entry=self.root/"approved_adapter.py"
        self.entry.write_text("# Synthetic adapter, never executed by this test\n")
        self.engine=self.root/"engine_manifest.json"
        self.engine.write_text('{"model_pins":"operator_approval_pending"}')
        self.script_hash=sha(self.script)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                 source_sha256=? WHERE series_id='colors-ar' AND ordinal=1""",
                 (self.script_hash,))
        catalog={}
        for kind in ("voice_synthesize","ltx_animate"):
            script_pin={"path":str(self.script),"sha256":self.script_hash}
            inputs=({"script":script_pin} if kind=="voice_synthesize" else {
                "voice_wav":{"path":str(self.voice),"sha256":sha(self.voice)},
                "reference_image":{"path":str(self.ref),"sha256":sha(self.ref)}
            })
            arguments=(["--script","{script}","--engine","{engine_manifest}",
                        "--output","{output}"] if kind=="voice_synthesize" else [
                         "--script","{script}","--audio","{voice_wav}",
                         "--reference","{reference_image}",
                         "--engine","{engine_manifest}","--output","{output}"])
            stage_file=self.root/(kind+".json")
            stage_file.write_text(json.dumps({
               "schema_version":1,"kind":kind,"private_root":str(self.root),
               "output_root":str(self.root/"rendered"),
               "script":script_pin,"inputs":inputs,
               "runner":{"python":sys.executable,
                 "python_sha256":sha(Path(sys.executable)),
                 "entrypoint":str(self.entry),"entrypoint_sha256":sha(self.entry),
                 "args":arguments},
               "engine_manifest":{"path":str(self.engine),"sha256":sha(self.engine)},
               "voice_rights":"INTERNAL_TEST_ONLY",
               "limits":{"timeout_seconds":60,"max_output_bytes":500000},
               "ffprobe":sys.executable
            }))
            catalog[kind+"_recipe"]={
               "kind":kind,"output_root":str(self.root/"rendered"),
               "inputs":{"stage_recipe":str(stage_file)},
               "sha256":{"stage_recipe":sha(stage_file)}
            }
        catalog_file=self.root/"catalog.json"
        catalog_file.write_text(json.dumps({"schema_version":1,"recipes":catalog}))
        self.recipes=MediaRecipes(catalog_file)
        self.coordinator=Coordinator(self.queue,self.root/"vault",{
             "mac-stage-m6":("a"*45,{"voice_synthesize","ltx_animate"})
        })
        self.executor=FakeModels()
        self.worker=RemoteMediaWorker(
            Pi(self.coordinator),self.recipes,
            MediaJournal(self.root/"journal.sqlite"),executor=self.executor)

    def test_real_media_receipts_voice_then_a2v(self):
        voice_id=self.ledger.queue_stage("colors-ar",1,"voice_synthesize",
                                         "voice_synthesize_recipe")
        self.assertEqual(self.worker.run_once()["status"],"COMPLETED")
        self.assertEqual(self.queue.get(voice_id)["state"],"COMPLETED")
        self.ledger.reconcile()
        self.ledger.approve("colors-ar",1,"voice_synthesize","b"*64,
                           "Owner reviewed and approved recorded audio")
        # The voice source from an LTX recipe must be exactly the
        # approved WAV content hash, not just arbitrary Mac audio.
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episode_stages SET artifact_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1
                  AND stage='voice_synthesize'""",(sha(self.voice),))
        # This setup simulates an exact approved local WAV, whereas the
        # fake executor returned a synthetic digest.
        ltx_id=self.ledger.queue_stage("colors-ar",1,"ltx_animate",
                                       "ltx_animate_recipe")
        self.assertEqual(self.worker.run_once()["status"],"COMPLETED")
        self.assertEqual(self.queue.get(ltx_id)["state"],"COMPLETED")
        self.ledger.reconcile()
        self.ledger.approve("colors-ar",1,"ltx_animate","c"*64,
                           "Owner reviewed output movement and lip sync")
        view=build_snapshot(self.queue)
        self.assertEqual(view["episodes"][0]["stages"][3]["status"],"complete")
        self.assertEqual(view["episodes"][0]["stages"][4]["status"],"complete")
        self.assertEqual(len(self.executor.calls),2)
        self.assertEqual({r[0] for r in self.executor.calls},
                         {"voice_synthesize","ltx_animate"})

    def test_corrupted_mac_recipe_preflight_refuses_execution(self):
        self.ledger.queue_stage("colors-ar",1,"voice_synthesize",
                                "voice_synthesize_recipe")
        self.script.write_text("Changed unapproved script")
        state=self.worker.run_once()
        self.assertEqual(state["status"],"CONFIG_REJECTED")
        self.assertEqual(self.executor.calls,[])
        self.ledger.reconcile()
        self.assertEqual(self.ledger.snapshot()[0]["state"],"BLOCKED")

    def test_voice_stage_type_not_masquerade_as_video(self):
        lease_job=self.ledger.queue_stage("colors-ar",1,"voice_synthesize",
                                          "voice_synthesize_recipe")
        lease=self.coordinator.dispatch("claim",{},"mac-stage-m6",
                              frozenset({"voice_synthesize","ltx_animate"}))["job"]
        from kidsstudio.coordinator_api import TransportError
        with self.assertRaises(TransportError):
            self.coordinator.dispatch("complete-media",{
                "job_id":lease_job,"generation":lease["generation"],
                "result_status":"VOICE_RENDERED_PENDING_QA",
                "artifact_type":"mp4","artifact_sha256":"b"*64,
                "artifact_bytes":1024,"publication_approved":False,
            },"mac-stage-m6",frozenset({"voice_synthesize","ltx_animate"}))


if __name__=="__main__":
    unittest.main()
