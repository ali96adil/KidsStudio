"""M12 end-to-end synthetic Pi→Mac stage bytes→exact M4 assembly recipe QA."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_stage_ledger import StageLedger
from kidsstudio.studio_audio_ledger import AudioEvidenceLedger
from kidsstudio.assembly_lineage import inspect_assembly_lineage, AssemblyLineageError


def sha(file:Path)->str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def fake_video(path,executable):
    return {"width":384,"height":384,"duration":4.0,"audio_streams":1}


class SingleScenePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.db=self.root/"brain.sqlite"
        self.queue=StudioQueue(self.db)
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series(
            "colors-ar","الألوان","ar",
            [{"title":"الأحمر","objective":"تعليم اللون الأحمر"}],activate=True)
        self.script=self.root/"episode_script.txt"
        self.script.write_text("هذه كرة حمراء.",encoding="utf-8")
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=? WHERE series_id='colors-ar' AND ordinal=1""",
                (sha(self.script),))
        self.stages=StageLedger(self.queue)
        self.stages.initialize()
        self.outputs=self.root/"media_outputs"
        self.outputs.mkdir()
        self.stage_info={}
        self.tools=self.root/"tools"
        self.tools.mkdir()
        self.face_a=self.tools/"v06.py";self.face_a.write_text("pass\n")
        self.face_b=self.tools/"v07.py";self.face_b.write_text("pass\n")
        self.catalog=self.root/"assembly_recipe.json"

    def _stage(self,kind,media_name,body,output_status,art_type):
        identifier=self.stages.queue_stage("colors-ar",1,kind,"approved_"+kind)
        lease=self.queue.claim(worker_id="mac",capabilities=[kind])
        self.assertEqual(lease["job_id"],identifier)
        folder=self.outputs/identifier
        folder.mkdir()
        artifact=folder/media_name
        artifact.write_bytes(body)
        content={
          "schema_version":1,"job_id":identifier,"stage":kind,
          "status":output_status,"script_sha256":sha(self.script),
          "source_voice_sha256": (
             self.stage_info["voice_synthesize"]["sha"] if kind=="ltx_animate"
             else None),
          "recipe_sha256":"e"*64,"publication_approved":False,
          "artifact_sha256":sha(artifact),
          "artifact_bytes":artifact.stat().st_size,
          "artifact_type":art_type,
          "duration_seconds":4.0
        }
        (folder/"stage_receipt.json").write_text(json.dumps(content))
        self.queue.complete(
            job_id=identifier,worker_id="mac",
            generation=lease["generation"],result={
                "status":output_status,"artifact_sha256":sha(artifact),
                "artifact_type":art_type,"publication_approved":False,
                "artifact_bytes":artifact.stat().st_size})
        self.stages.reconcile()
        self.stage_info[kind]={"id":identifier,"sha":sha(artifact),"artifact":artifact}
        self.stages.approve("colors-ar",1,kind,sha(artifact),
                            "Owner reviewed exact rendered media and approved it")
        return identifier

    def ready(self):
        self._stage("voice_synthesize","narration.wav",
                    b"fake-voice-bytes"*25,"VOICE_RENDERED_PENDING_QA","wav")
        self._stage("ltx_animate","a2v.mp4",
                    b"fake-video-with-audio"*30,"A2V_RENDERED_PENDING_QA","mp4")
        self.recipe={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.root),"output_root":str(self.root/"assembled"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(self.script),"sha256":sha(self.script)},
            "tools":{
                "ffmpeg":sys.executable,
                "ffprobe":sys.executable,
                "face_python":sys.executable,
                "face_v06":str(self.face_a),"face_v06_sha256":sha(self.face_a),
                "face_v07":str(self.face_b),"face_v07_sha256":sha(self.face_b)
            },
            "clips":[{"video":str(self.stage_info["ltx_animate"]["artifact"]),
                      "sha256":self.stage_info["ltx_animate"]["sha"],
                      "face_cleanup":"bunny_v07"}]
        }
        self.save()

    def save(self):
        self.catalog.write_text(json.dumps(self.recipe),encoding="utf-8")

    def inspect(self):
        return inspect_assembly_lineage(
            self.queue,series_id="colors-ar",ordinal=1,
            voice_output_root=self.outputs,ltx_output_root=self.outputs,
            assembly_recipe=self.catalog,video_prober=fake_video)

    def test_identical_actual_ltx_bytes_are_required_for_montage(self):
        self.ready()
        result=self.inspect()
        self.assertEqual(result["status"],
            "SINGLE_SCENE_ASSEMBLY_INPUT_VERIFIED_NOT_RENDERED")
        self.assertEqual(result["actual_ltx_sha256"],
                         self.stage_info["ltx_animate"]["sha"])
        self.assertEqual(result["scene_count"],1)
        self.assertFalse(result["assembly_performed_now"])
        self.assertFalse((self.root/"assembled").exists())

    def test_swapped_video_is_not_accepted_even_with_valid_local_recipe(self):
        self.ready()
        other=self.root/"different.mp4"
        other.write_bytes(b"other-unapproved-output"*15)
        self.recipe["clips"][0]["video"]=str(other)
        self.recipe["clips"][0]["sha256"]=sha(other)
        self.save()
        with self.assertRaises(AssemblyLineageError):
            self.inspect()

    def test_changed_approved_output_and_receipt_blocked(self):
        self.ready()
        self.stage_info["ltx_animate"]["artifact"].write_bytes(b"new tampered media")
        with self.assertRaises(AssemblyLineageError):
            self.inspect()

    def test_extra_scene_is_not_misreported_as_complete_pipeline(self):
        self.ready()
        self.recipe["clips"].append(dict(self.recipe["clips"][0]))
        self.save()
        with self.assertRaises(AssemblyLineageError) as caught:
            self.inspect()
        self.assertIn("ONE clip",str(caught.exception))

    def test_current_technical_audio_evidence_is_required_when_enabled(self):
        self.ready()
        AudioEvidenceLedger(self.queue).initialize()
        with self.assertRaises(AssemblyLineageError):
            self.inspect()

    def test_changed_mac_receipt_fails_even_if_pi_is_approved(self):
        self.ready()
        jobid=self.stage_info["ltx_animate"]["id"]
        receipt=self.outputs/jobid/"stage_receipt.json"
        record=json.loads(receipt.read_text())
        record["recipe_sha256"]="not valid"
        receipt.write_text(json.dumps(record))
        with self.assertRaises(AssemblyLineageError):
            self.inspect()


if __name__=="__main__":
    unittest.main()
