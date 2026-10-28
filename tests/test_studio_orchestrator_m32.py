"""M32 synthetic two-scene orchestration: one job per tick, no outside effects.

These tests use fake completed Mac job receipts/legacy QA and synthetic M30
model evidence. They do NOT qualify a real image, LTX, child-safety model,
Mac/Pi transport, actual publishing, or a real video.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager,SeriesError
from kidsstudio.studio_scenes import SceneLedger,SceneError
from kidsstudio.script_ai_quality import ScriptAIQuality
from kidsstudio.studio_orchestrator import StudioOrchestrator,OrchestrationError
from kidsstudio.scene_repair import SceneRepair
from kidsstudio.scene_ai_qa import SceneAIGate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Orchestration32(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m32-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.manager=SeriesManager(self.queue)
        self.manager.initialize()
        self.manager.create_series("colors-ar","Colors","ar",[
            {"title":"Red and blue","objective":"Recognize red and blue objects"}
        ],activate=True)
        self.parent=self.root/"parent.txt"
        self.parent.write_text("Two friends learn which colors a ball has")
        self.scripts=[]
        for n in (1,2):
            src=self.root/("scene"+str(n)+".txt")
            src.write_text("Scene "+str(n)+" original Arabic educational lesson")
            self.scripts.append(src)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?,owner_review_note=?
                WHERE series_id='colors-ar' AND ordinal=1""",
                (sha(self.parent),"AI_INTERNAL_PRIVATE_ONLY"))
        self.scenes=SceneLedger(self.queue)
        self.scenes.initialize()
        private=self.root/"private_models"
        private.mkdir()
        ai=ScriptAIQuality(self.queue,None,private)
        ai.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_script_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,1,"f"*32,sha(self.parent),
                 "prov_review_a","prov_review_b",
                 "a"*64,"b"*64,"c"*64,
                 "AI_SCRIPT_PRIVATE_READY",self.queue.clock()))
        frozen=self.root/"scenes.json"
        frozen.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"episode_script_sha256":sha(self.parent),
            "scenes":[{"scene":n,"script_sha256":sha(self.scripts[n-1]),
                       "objective":"Identify red and blue toy "+str(n)}
                      for n in (1,2)]
        }))
        scene_result=self.scenes.register_plan(frozen)
        self.plan=self.root/"orchestrator.json"
        self.plan_data={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "script_sha256":sha(self.parent),
            "scene_plan_sha256":scene_result["plan_sha256"],
            "scenes":[{"scene":n,"script_sha256":sha(self.scripts[n-1]),
                       "voice_recipe":"voice_"+str(n),
                       "ltx_recipe":"ltx_"+str(n)} for n in (1,2)],
            "assembly":{"recipe_id":"assembly_one",
                        "catalogue_sha256":"d"*64},
            "public_release_authorized":False
        }
        self.plan.write_text(json.dumps(self.plan_data))
        self.coord=StudioOrchestrator(self.queue)
        self.coord.initialize()

    def pass_job(self,job_id,kind):
        leased=self.queue.claim(worker_id="mac-worker",capabilities=[kind])
        self.assertEqual(leased["job_id"],job_id)
        artifact=hashlib.sha256(job_id.encode()).hexdigest()
        status="VOICE_RENDERED_PENDING_QA" if kind=="voice_synthesize" else "A2V_RENDERED_PENDING_QA"
        typ="wav" if kind=="voice_synthesize" else "mp4"
        self.queue.complete(job_id=job_id,worker_id="mac-worker",
            generation=leased["generation"],result={
                "status":status,"artifact_type":typ,
                "artifact_sha256":artifact,
                "artifact_bytes":300,"publication_approved":False})
        self.scenes.reconcile()
        return artifact

    def approve(self,n,kind,sha256):
        # This synthetic acceptance test uses the existing legacy owner
        # fixture, never a fake M28 model verdict or public authorization.
        if kind=="voice_synthesize" and n==1:
            with self.queue._connection(write=True) as db:
                row=db.execute("""SELECT job_id FROM studio_scene_stages
                    WHERE series_id='colors-ar' AND ordinal=1 AND scene=1
                    AND stage='voice_synthesize'""").fetchone()
                db.execute("""INSERT INTO studio_scene_voice_checks VALUES
                    (?,?,?,?,?,?,?,?)""",
                    ("colors-ar",1,1,row["job_id"],sha256,"f"*64,
                     "TECH_PASS_OWNER_LISTENING_PENDING",self.queue.clock()))
        if kind=="ltx_animate":
            with self.queue._connection(write=True) as db:
                st=db.execute("""SELECT job_id,source_voice_sha256 FROM
                    studio_scene_stages WHERE series_id='colors-ar' AND
                    ordinal=1 AND scene=? AND stage='ltx_animate'""",
                    (n,)).fetchone()
                db.execute("""INSERT INTO studio_scene_audio_checks VALUES
                    (?,?,?,?,?,?,?,?)""",
                    ("colors-ar",1,n,st["job_id"],"e"*64,
                    st["source_voice_sha256"],sha256,
                    "TECH_COMPATIBLE_HUMAN_QA_REQUIRED"))
        self.scenes.approve("colors-ar",1,n,kind,sha256,
                            "Synthetic M32 test approval, no real model execution",
                            owner_listened=(n==1 and kind=="voice_synthesize"))

    def test_read_only_gate_and_conservative_one_job_per_tick(self):
        before=self.coord.status(self.plan)
        self.assertEqual(before["next_action"],"PIN_CURRENT_PLAN")
        self.assertFalse(before["mac_pi_hardware_test_ready"])
        self.assertFalse(before["public_release_authorized"])
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        pinned=self.coord.pin(self.plan)
        self.assertFalse(pinned["public_release_authorized"])
        start=self.coord.tick(self.plan)
        self.assertEqual(start["action"],"FIRST_AI_VOICE")
        j1=start["job_id"]
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],1)
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")
        voice1=self.pass_job(j1,"voice_synthesize")
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "SCENE_VOICE_PENDING_QA")
        self.approve(1,"voice_synthesize",voice1)
        ltx1=self.coord.tick(self.plan)
        self.assertEqual(ltx1["action"],"NEXT_LTX")
        video1=self.pass_job(ltx1["job_id"],"ltx_animate")
        self.approve(1,"ltx_animate",video1)
        voice2=self.coord.tick(self.plan)
        self.assertEqual(voice2["action"],"NEXT_VOICE")
        spoken2=self.pass_job(voice2["job_id"],"voice_synthesize")
        self.approve(2,"voice_synthesize",spoken2)
        ltx2=self.coord.tick(self.plan)
        self.assertEqual(ltx2["action"],"NEXT_LTX")
        video2=self.pass_job(ltx2["job_id"],"ltx_animate")
        self.approve(2,"ltx_animate",video2)
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        self.queue.set_paused(True)
        self.assertEqual(self.coord.tick(self.plan)["next_action"],"PAUSED")
        with self.assertRaises(SeriesError):
            self.manager.queue_render("colors-ar",1,"assembly_one",
                media_kind="episode_assemble",catalogue_sha256="d"*64)
        self.queue.set_paused(False)
        assembled=self.coord.tick(self.plan)
        self.assertEqual(assembled["action"],"ASSEMBLE_FINAL_EPISODE")
        self.assertEqual(self.queue.get(assembled["job_id"])["kind"],"episode_assemble")
        self.assertFalse(assembled["public_release_authorized"])
        status=self.coord.status(self.plan)
        self.assertEqual(status["episode_state"],"RENDER_QUEUED")
        self.assertFalse(status["software_full_cycle_qualified"])
        self.assertFalse(status["mac_pi_hardware_test_ready"])
        self.assertFalse(status["youtube_private_upload_qualified"])

    def _complete_deferred_scene_stages(self):
        self.plan_data["assembly"]["catalogue_sha256"]="AFTER_SCENE_QA"
        self.plan.write_text(json.dumps(self.plan_data))
        self.coord.pin(self.plan)
        for scene in (1,2):
            voice=self.coord.tick(self.plan)
            self.assertEqual(voice["action"],
                "FIRST_AI_VOICE" if scene==1 else "NEXT_VOICE")
            wav=self.pass_job(voice["job_id"],"voice_synthesize")
            self.approve(scene,"voice_synthesize",wav)
            ltx=self.coord.tick(self.plan)
            self.assertEqual(ltx["action"],"NEXT_LTX")
            video=self.pass_job(ltx["job_id"],"ltx_animate")
            self.approve(scene,"ltx_animate",video)
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "M48_ASSEMBLY_CATALOGUE_NOT_BOUND")
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")

    def _deferred_evidence(self):
        from kidsstudio.studio_scenes import assert_scenes_ready
        with self.queue._connection() as db:
            ready=assert_scenes_ready(db,"colors-ar",1,sha(self.parent))
        file=self.root/"m14_scene_evidence.json"
        manifest={
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"script_sha256":sha(self.parent),
            "scene_plan_sha256":self.plan_data["scene_plan_sha256"],
            "assembly_recipe_sha256":"e"*64,
            "voice_output_root":str(self.root/"private_voice"),
            "ltx_output_root":str(self.root/"private_ltx"),
            "scenes":[{
                "scene":x["scene"],
                "scene_script_sha256":x["script_sha256"],
                "voice_job_id":x["voice_job_id"],
                "ltx_job_id":x["ltx_job_id"],
                "voice_sha256":x["voice_sha256"],
                "ltx_sha256":x["ltx_sha256"]
            } for x in ready],
            "publication_approved":False
        }
        file.write_text(json.dumps(manifest))
        return file

    def test_m48_deferred_catalogue_binding_allows_real_timing_and_no_overwrite(self):
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        bound=self.coord.bind_assembly(
            self.plan,evidence_file=evidence,catalogue_sha256="b"*64)
        self.assertEqual(bound["status"],"M48_FROZEN_ASSEMBLY_PINNED_NO_JOB_QUEUED")
        self.assertFalse(bound["render_job_queued"])
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(
                self.plan,evidence_file=evidence,catalogue_sha256="c"*64)
        started=self.coord.tick(self.plan)
        self.assertEqual(started["action"],"ASSEMBLE_FINAL_EPISODE")
        job=json.loads(self.queue.get(started["job_id"])["payload"])
        self.assertEqual(job["catalogue_sha256"],"b"*64)
        self.assertFalse(started["public_release_authorized"])

    def test_m48_rejects_partial_scene_or_swapped_evidence(self):
        self.plan_data["assembly"]["catalogue_sha256"]="AFTER_SCENE_QA"
        self.plan.write_text(json.dumps(self.plan_data))
        self.coord.pin(self.plan)
        with self.assertRaises(SceneError):
            self.coord.bind_assembly(
                self.plan,evidence_file=self.root/"nothing.json",
                catalogue_sha256="b"*64)
        for scene in (1,2):
            voice=self.coord.tick(self.plan)
            wav=self.pass_job(voice["job_id"],"voice_synthesize")
            self.approve(scene,"voice_synthesize",wav)
            ltx=self.coord.tick(self.plan)
            mp4=self.pass_job(ltx["job_id"],"ltx_animate")
            self.approve(scene,"ltx_animate",mp4)
        evidence=self._deferred_evidence()
        original=json.loads(evidence.read_text())
        swapped=json.loads(evidence.read_text())
        swapped["scenes"][0]["voice_sha256"]="f"*64
        evidence.write_text(json.dumps(swapped))
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(
                self.plan,evidence_file=evidence,catalogue_sha256="b"*64)
        evidence.write_text(json.dumps(original))
        self.coord.bind_assembly(
            self.plan,evidence_file=evidence,catalogue_sha256="b"*64)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET artifact_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1 AND scene=2
                AND stage='ltx_animate'""",("f"*64,))
        state=self.coord.status(self.plan)
        self.assertIn(state["next_action"],(
            "SCENE_LTX_QA_APPROVED","M48_ASSEMBLY_SCENES_NOT_VERIFIED"))
        self.assertNotEqual(state["next_action"],"ASSEMBLE_FINAL_EPISODE")
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")

    def test_wrong_plan_sha_and_mutation_never_enqueue(self):
        with self.assertRaises(OrchestrationError):
            self.coord.pin(self.root/"missing.json")
        altered=dict(self.plan_data)
        altered["script_sha256"]="a"*64
        self.plan.write_text(json.dumps(altered))
        with self.assertRaises(OrchestrationError):
            self.coord.pin(self.plan)
        self.plan.write_text(json.dumps(self.plan_data))
        self.coord.pin(self.plan)
        self.plan_data["scenes"][0]["voice_recipe"]="changed"
        self.plan.write_text(json.dumps(self.plan_data))
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_legacy_owner_approval_does_not_implicitly_unlock_ai_pilot(self):
        with self.queue._connection(write=True) as db:
            db.execute("DELETE FROM studio_script_ai_reviews")
        self.coord.pin(self.plan)
        out=self.coord.tick(self.plan)
        self.assertIn("FIRST_VOICE_REQUIRES_AI_SCRIPT_GATE",out["blockers"])
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_paused_queue_refuses_even_valid_plan(self):
        self.coord.pin(self.plan)
        self.queue.set_paused(True)
        out=self.coord.tick(self.plan)
        self.assertEqual(out["next_action"],"PAUSED")
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_plan_is_immutable_and_sequential(self):
        self.coord.pin(self.plan)
        with self.assertRaises(OrchestrationError):
            self.coord.pin(self.plan)
        self.assertEqual(self.coord.status(self.plan)["scenes"][1]["voice"],
                         "NOT_QUEUED")
        self.assertEqual(self.coord.tick(self.plan)["action"],"FIRST_AI_VOICE")
        self.assertEqual(self.coord.status(self.plan)["scenes"][1]["voice"],
                         "NOT_QUEUED")
        with self.assertRaises(OrchestrationError):
            self.coord.pin(self.plan)

    def test_repair_negative_current_voice_uses_scoped_m31_plan(self):
        self.coord.pin(self.plan)
        first=self.coord.tick(self.plan)
        voice_sha=self.pass_job(first["job_id"],"voice_synthesize")
        SceneAIGate(self.queue).initialize()
        repair=SceneRepair(self.queue);repair.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_scene_voice_checks VALUES
                (?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,1,first["job_id"],voice_sha,"e"*64,
                 "TECH_PASS_OWNER_LISTENING_PENDING",self.queue.clock()))
            db.execute("""INSERT INTO studio_scene_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,1,"voice_synthesize",first["job_id"],
                 voice_sha,sha(self.scripts[0]),"f"*64,
                 "a"*64,"b"*64,"e"*64,"provider_abc","provider_xyz",
                 "AI_SCENE_NEEDS_FIX",0.5,self.queue.clock()))
        repair_path=self.root/"repair.json"
        repair_path.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"scene":1,"stage":"voice_synthesize",
            "script_sha256":sha(self.scripts[0]),
            "recipes":["revoice_1","revoice_2"],
            "public_release_authorized":False}))
        repair.register_plan(repair_path)
        status=self.coord.status(self.plan)
        self.assertEqual(status["next_action"],"REPAIR_REJECTED_SCENE")
        retried=self.coord.tick(self.plan)
        self.assertEqual(retried["status"],"M32_ONE_PRIVATE_JOB_QUEUED")
        self.assertEqual(retried["action"],"REPAIR_REJECTED_SCENE")
        self.assertEqual(retried["repair_attempt"],1)
        self.assertNotEqual(retried["job_id"],first["job_id"])
        self.assertEqual(self.queue.get(retried["job_id"])["kind"],
                         "voice_synthesize")
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")
        with self.queue._connection() as db:
            self.assertIsNone(db.execute("""SELECT 1 FROM studio_scene_stages
                WHERE series_id='colors-ar' AND scene=2""").fetchone())

    def test_plan_cannot_advertise_public_permission(self):
        self.plan_data["public_release_authorized"]=True
        self.plan.write_text(json.dumps(self.plan_data))
        with self.assertRaises(OrchestrationError):
            self.coord.pin(self.plan)


if __name__=="__main__":
    unittest.main()
