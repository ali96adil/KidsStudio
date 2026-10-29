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

    def _deferred_catalogue(self,evidence):
        # Pi sees only an owner-transferred copy of the M14 catalogue.
        # Its original Mac paths are metadata, not files read by the Pi.
        manifest=json.loads(evidence.read_text())
        file=self.root/"m14_owner_catalogue.json"
        file.write_text(json.dumps({
            "schema_version":1,
            "recipes":{"assembly_one":{
                "kind":"episode_assemble",
                "output_root":str(self.root/"mac_assembled"),
                "inputs":{
                    "episode_recipe":str(self.root/"mac_episode_recipe.json"),
                    "scene_evidence":str(self.root/"mac_scene_evidence.json")},
                "sha256":{
                    "episode_recipe":manifest["assembly_recipe_sha256"],
                    "scene_evidence":sha(evidence)}
            }}
        }))
        return file

    def test_m48_deferred_catalogue_binding_allows_real_timing_and_no_overwrite(self):
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        bound=self.coord.bind_assembly(
            self.plan,evidence_file=evidence,catalogue_file=catalogue,
            catalogue_sha256=sha(catalogue))
        self.assertEqual(bound["status"],"M48_FROZEN_ASSEMBLY_PINNED_NO_JOB_QUEUED")
        self.assertFalse(bound["render_job_queued"])
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(
                self.plan,evidence_file=evidence,catalogue_file=catalogue,
                catalogue_sha256="c"*64)
        started=self.coord.tick(self.plan)
        self.assertEqual(started["action"],"ASSEMBLE_FINAL_EPISODE")
        job=json.loads(self.queue.get(started["job_id"])["payload"])
        self.assertEqual(job["catalogue_sha256"],sha(catalogue))
        self.assertFalse(started["public_release_authorized"])

    def test_m48_rejects_partial_scene_or_swapped_evidence(self):
        self.plan_data["assembly"]["catalogue_sha256"]="AFTER_SCENE_QA"
        self.plan.write_text(json.dumps(self.plan_data))
        self.coord.pin(self.plan)
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(
                self.plan,evidence_file=self.root/"nothing.json",
                catalogue_file=self.root/"missing_catalogue.json",
                catalogue_sha256="b"*64)
        for scene in (1,2):
            voice=self.coord.tick(self.plan)
            wav=self.pass_job(voice["job_id"],"voice_synthesize")
            self.approve(scene,"voice_synthesize",wav)
            ltx=self.coord.tick(self.plan)
            mp4=self.pass_job(ltx["job_id"],"ltx_animate")
            self.approve(scene,"ltx_animate",mp4)
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        original=json.loads(evidence.read_text())
        swapped=json.loads(evidence.read_text())
        swapped["scenes"][0]["voice_sha256"]="f"*64
        evidence.write_text(json.dumps(swapped))
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(
                self.plan,evidence_file=evidence,catalogue_file=catalogue,
                catalogue_sha256=sha(catalogue))
        evidence.write_text(json.dumps(original))
        self.coord.bind_assembly(
            self.plan,evidence_file=evidence,catalogue_file=catalogue,
                catalogue_sha256=sha(catalogue))
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

    def test_m49_rejects_forged_catalogue_metadata_and_wrong_digest(self):
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(self.plan,evidence_file=evidence,
                catalogue_file=catalogue,catalogue_sha256="0"*64)
        original=json.loads(catalogue.read_text())
        wrong=json.loads(catalogue.read_text())
        wrong["recipes"]["assembly_one"]["sha256"]["scene_evidence"]="a"*64
        catalogue.write_text(json.dumps(wrong))
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(self.plan,evidence_file=evidence,
                catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        wrong=json.loads(json.dumps(original))
        wrong["recipes"]["assembly_one"]["sha256"]["episode_recipe"]="f"*64
        catalogue.write_text(json.dumps(wrong))
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(self.plan,evidence_file=evidence,
                catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        wrong=json.loads(json.dumps(original))
        wrong["recipes"]["different_episode"]=wrong["recipes"].pop("assembly_one")
        catalogue.write_text(json.dumps(wrong))
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(self.plan,evidence_file=evidence,
                catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        catalogue.write_text(json.dumps(original))
        bound=self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        self.assertEqual(bound["catalogue_sha256"],sha(catalogue))
        self.assertFalse(bound["render_job_queued"])
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_m49_refuses_symlinked_catalogue_without_dispatch(self):
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        alias=self.root/"catalogue_redirect.json"
        alias.symlink_to(catalogue)
        with self.assertRaises(OrchestrationError):
            self.coord.bind_assembly(self.plan,evidence_file=evidence,
                catalogue_file=alias,catalogue_sha256=sha(catalogue))
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "M48_ASSEMBLY_CATALOGUE_NOT_BOUND")

    def test_m50_scene_plan_change_after_status_cannot_enqueue(self):
        """A stale green snapshot must not override a new DB scene plan."""
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        original=self.coord.series.queue_render
        def changed_between_checks(*args,**kwargs):
            with self.queue._connection(write=True) as db:
                db.execute("""UPDATE studio_scene_plans SET plan_sha256=?
                    WHERE series_id='colors-ar' AND ordinal=1""",("f"*64,))
            return original(*args,**kwargs)
        self.coord.series.queue_render=changed_between_checks
        try:
            with self.assertRaises(SeriesError):
                self.coord.tick(self.plan)
        finally:
            self.coord.series.queue_render=original
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        with self.queue._connection() as db:
            episode=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
        self.assertEqual(episode["state"],"SCRIPT_APPROVED")

    def test_m50_catalogue_binding_change_after_status_cannot_enqueue(self):
        """The SHA read by tick must still match at atomic job insertion."""
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        original=self.coord.series.queue_render
        def changed_between_checks(*args,**kwargs):
            with self.queue._connection(write=True) as db:
                db.execute("""UPDATE studio_orchestrator_assembly_bindings
                    SET catalogue_sha256=? WHERE series_id='colors-ar'
                    AND ordinal=1""",("f"*64,))
            return original(*args,**kwargs)
        self.coord.series.queue_render=changed_between_checks
        try:
            with self.assertRaises(SeriesError):
                self.coord.tick(self.plan)
        finally:
            self.coord.series.queue_render=original
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        with self.queue._connection() as db:
            episode=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
        self.assertEqual(episode["state"],"SCRIPT_APPROVED")

    def test_m51_manual_series_render_cannot_bypass_bound_plan(self):
        """The older series queue-render CLI must not skip M32 binding."""
        self._complete_deferred_scene_stages()
        with self.assertRaisesRegex(SeriesError,"studio-orchestrator tick"):
            self.manager.queue_render("colors-ar",1,"assembly_one",
                media_kind="episode_assemble",catalogue_sha256="a"*64)
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        with self.assertRaisesRegex(SeriesError,"studio-orchestrator tick"):
            self.manager.queue_render("colors-ar",1,"assembly_one",
                media_kind="episode_assemble",catalogue_sha256=sha(catalogue))
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        self.assertEqual(self.coord.tick(self.plan)["action"],
                         "ASSEMBLE_FINAL_EPISODE")

    def test_m51_forged_recipe_or_pre_pinned_catalogue_never_queues(self):
        """Even with an M32 SHA, caller cannot replace its montage recipe."""
        self.coord.pin(self.plan)
        # Complete scene stages on the legacy literal catalog route.
        for scene in (1,2):
            voice=self.coord.tick(self.plan)
            wav=self.pass_job(voice["job_id"],"voice_synthesize")
            self.approve(scene,"voice_synthesize",wav)
            visual=self.coord.tick(self.plan)
            mp4=self.pass_job(visual["job_id"],"ltx_animate")
            self.approve(scene,"ltx_animate",mp4)
        plan_sha=sha(self.plan)
        for recipe,catalogue in (("forged_recipe","d"*64),
                                  ("assembly_one","f"*64)):
            with self.assertRaises(SeriesError):
                self.manager.queue_render("colors-ar",1,recipe,
                    media_kind="episode_assemble",catalogue_sha256=catalogue,
                    orchestrator_plan_sha256=plan_sha)
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)
        self.assertEqual(self.coord.tick(self.plan)["action"],
                         "ASSEMBLE_FINAL_EPISODE")

    def test_m51_missing_contract_fails_closed_without_repin(self):
        """Pre-upgrade plans cannot dispatch until contract is reconciled."""
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        with self.queue._connection(write=True) as db:
            db.execute("""DELETE FROM studio_orchestrator_render_contracts
                WHERE series_id='colors-ar' AND ordinal=1""")
        status=self.coord.status(self.plan)
        self.assertIn("M51_RENDER_CONTRACT_MISSING_OR_CHANGED",status["blockers"])
        self.assertEqual(status["next_action"],"STOP_AND_RECONCILE")
        with self.assertRaises(SeriesError):
            self.manager.queue_render("colors-ar",1,"assembly_one",
                media_kind="episode_assemble",catalogue_sha256=sha(catalogue),
                orchestrator_plan_sha256=sha(self.plan),
                require_orchestrator_binding=True)
        self.assertEqual(self.coord.tick(self.plan)["status"],
                         "M32_BLOCKED_NO_JOB_QUEUED")
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_m51_changed_scene_identity_between_status_and_enqueue(self):
        """The scene script identity cannot mutate after the green tick."""
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        self.assertEqual(self.coord.status(self.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        original=self.coord.series.queue_render
        def mutated(*args,**kwargs):
            with self.queue._connection(write=True) as db:
                db.execute("""UPDATE studio_scenes SET script_sha256=?
                    WHERE series_id='colors-ar' AND ordinal=1 AND scene=2""",
                    ("f"*64,))
            return original(*args,**kwargs)
        self.coord.series.queue_render=mutated
        try:
            with self.assertRaises((SeriesError,SceneError)):
                self.coord.tick(self.plan)
        finally:
            self.coord.series.queue_render=original
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def _m52_queue_deferred_montage(self):
        self._complete_deferred_scene_stages()
        evidence=self._deferred_evidence()
        catalogue=self._deferred_catalogue(evidence)
        self.coord.bind_assembly(self.plan,evidence_file=evidence,
            catalogue_file=catalogue,catalogue_sha256=sha(catalogue))
        started=self.coord.tick(self.plan)
        self.assertEqual(started["action"],"ASSEMBLE_FINAL_EPISODE")
        self.assertEqual(self.queue.get(started["job_id"])["state"],"QUEUED")
        return started["job_id"]

    def _m52_assert_claim_revoked(self,job_id,reason):
        lease=self.queue.claim(worker_id="mac-worker",
                               capabilities=["episode_assemble"])
        self.assertIsNone(lease)
        stale=self.queue.get(job_id)
        self.assertEqual(stale["state"],"FAILED")
        self.assertEqual(stale["error_code"],"M52_CLAIM_PROVENANCE_REVOKED")
        with self.queue._connection() as db:
            event=db.execute("""SELECT info_json FROM events
                WHERE job_id=? AND event_type='M52_RENDER_CLAIM_REVOKED'
                ORDER BY happened_at DESC LIMIT 1""",(job_id,)).fetchone()
        self.assertIsNotNone(event)
        self.assertEqual(json.loads(event["info_json"])["reason"],reason)
        self.assertEqual(self.queue.status()["counts"]["QUEUED"],0)

    def test_m52_valid_deferred_final_montage_receives_one_lease(self):
        job_id=self._m52_queue_deferred_montage()
        leased=self.queue.claim(worker_id="mac-worker",
            capabilities=["episode_assemble"])
        self.assertIsNotNone(leased)
        self.assertEqual(leased["job_id"],job_id)
        self.assertEqual(leased["state"],"LEASED")
        self.assertEqual(leased["generation"],1)
        self.assertEqual(self.queue.claim(worker_id="mac-worker",
            capabilities=["episode_assemble"]),None)

    def test_m52_frozen_catalogue_mutation_after_enqueue_blocks_mac_claim(self):
        job_id=self._m52_queue_deferred_montage()
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_orchestrator_assembly_bindings
                SET catalogue_sha256=? WHERE series_id='colors-ar'
                AND ordinal=1""",("f"*64,))
        self._m52_assert_claim_revoked(job_id,"M52_ASSEMBLY_BINDING_CHANGED")

    def test_m52_scene_qa_mutation_after_enqueue_blocks_mac_claim(self):
        job_id=self._m52_queue_deferred_montage()
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET artifact_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1 AND scene=2
                AND stage='ltx_animate'""",("f"*64,))
        self._m52_assert_claim_revoked(
            job_id,"M52_RENDER_PROVENANCE_UNVERIFIABLE")

    def test_m52_render_recipe_contract_mutation_after_enqueue_is_rejected(self):
        job_id=self._m52_queue_deferred_montage()
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_orchestrator_render_contracts
                SET recipe_id=? WHERE series_id='colors-ar'
                AND ordinal=1""",("swapped_recipe",))
        self._m52_assert_claim_revoked(job_id,
            "M52_ORCHESTRATION_CONTRACT_CHANGED")

    def test_m52_unlinked_direct_queue_job_cannot_bypass_m32_claim(self):
        self._complete_deferred_scene_stages()
        raw=self.queue.enqueue(kind="episode_assemble",
            request_key="orphan:render:episode_assemble",
            payload={"recipe_id":"assembly_one",
                     "script_sha256":sha(self.parent),
                     "catalogue_sha256":"d"*64},max_attempts=1)
        self._m52_assert_claim_revoked(raw["job_id"],
            "M52_UNLINKED_MONTAGE_JOB")

    def test_m53_fresh_leased_montage_passes_before_ffmpeg(self):
        job_id=self._m52_queue_deferred_montage()
        leased=self.queue.claim(worker_id="mac-worker",
                                capabilities=["episode_assemble"])
        payload=json.loads(leased["payload"])
        proof=self.queue.pre_execute_montage(
            job_id=job_id,worker_id="mac-worker",
            generation=leased["generation"],payload=payload)
        self.assertEqual(proof["status"],
            "M53_CURRENT_PRIVATE_MONTAGE_LEASE_NOT_EXECUTED")
        self.assertEqual(proof["payload"],payload)
        self.assertIs(proof["render_started"],False)
        self.assertIs(proof["publication_approved"],False)
        self.assertEqual(self.queue.get(job_id)["state"],"LEASED")

    def test_m53_m49_binding_mutates_after_lease_and_pre_exec_revokes(self):
        job_id=self._m52_queue_deferred_montage()
        leased=self.queue.claim(worker_id="mac-worker",
                                capabilities=["episode_assemble"])
        payload=json.loads(leased["payload"])
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_orchestrator_assembly_bindings
                SET catalogue_sha256=? WHERE series_id='colors-ar'
                AND ordinal=1""",("f"*64,))
        proof=self.queue.pre_execute_montage(
            job_id=job_id,worker_id="mac-worker",
            generation=leased["generation"],payload=payload)
        self.assertEqual(proof["status"],"M53_PRE_EXEC_DENIED_NO_RENDER")
        self.assertEqual(self.queue.get(job_id)["state"],"FAILED")
        self.assertEqual(self.queue.get(job_id)["error_code"],
                         "M53_PRE_EXEC_PROVENANCE_REVOKED")
        with self.queue._connection() as db:
            event=db.execute("""SELECT info_json FROM events
                WHERE job_id=? AND event_type='M53_RENDER_PRE_EXEC_REVOKED'
                ORDER BY happened_at DESC LIMIT 1""",(job_id,)).fetchone()
        self.assertEqual(json.loads(event["info_json"])["reason"],
                         "M52_ASSEMBLY_BINDING_CHANGED")
        with self.assertRaises(Exception):
            self.queue.complete(job_id=job_id,worker_id="mac-worker",
                generation=leased["generation"],result={"status":"fake"})

    def test_m53_queue_pause_after_lease_blocks_render(self):
        job_id=self._m52_queue_deferred_montage()
        leased=self.queue.claim(worker_id="mac-worker",
                                capabilities=["episode_assemble"])
        self.queue.set_paused(True)
        proof=self.queue.pre_execute_montage(
            job_id=job_id,worker_id="mac-worker",
            generation=leased["generation"],
            payload=json.loads(leased["payload"]))
        self.assertEqual(proof["status"],"M53_PRE_EXEC_DENIED_NO_RENDER")
        self.assertEqual(self.queue.get(job_id)["state"],"FAILED")

    def test_m53_wrong_worker_generation_and_payload_fail_closed(self):
        from kidsstudio.studio_queue import QueueError
        job_id=self._m52_queue_deferred_montage()
        leased=self.queue.claim(worker_id="mac-worker",
                                capabilities=["episode_assemble"])
        payload=json.loads(leased["payload"])
        for worker,gen in (("other-worker",leased["generation"]),
                           ("mac-worker",leased["generation"]+1)):
            with self.assertRaises(QueueError):
                self.queue.pre_execute_montage(
                    job_id=job_id,worker_id=worker,generation=gen,
                    payload=payload)
        self.assertEqual(self.queue.get(job_id)["state"],"LEASED")
        altered=dict(payload); altered["catalogue_sha256"]="a"*64
        proof=self.queue.pre_execute_montage(
            job_id=job_id,worker_id="mac-worker",
            generation=leased["generation"],payload=altered)
        self.assertEqual(proof["status"],"M53_PRE_EXEC_DENIED_NO_RENDER")
        self.assertEqual(self.queue.get(job_id)["state"],"FAILED")

    def test_m54_heartbeat_revokes_changed_catalogue_while_rendering(self):
        job_id=self._m52_queue_deferred_montage()
        lease=self.queue.claim(worker_id="mac-worker",
                               capabilities=["episode_assemble"])
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_orchestrator_assembly_bindings
                SET catalogue_sha256=? WHERE series_id='colors-ar'
                AND ordinal=1""",("f"*64,))
        response=self.queue.heartbeat(job_id=job_id,worker_id="mac-worker",
            generation=lease["generation"],lease_seconds=600)
        self.assertEqual(response["state"],"FAILED")
        self.assertEqual(response["error_code"],"M54_MONTAGE_LEASE_REVOKED")
        with self.queue._connection() as db:
            e=db.execute("""SELECT info_json FROM events
                WHERE job_id=? AND event_type='M54_MONTAGE_HEARTBEAT_REVOKED'
                LIMIT 1""",(job_id,)).fetchone()
        self.assertEqual(json.loads(e["info_json"])["reason"],
                         "M52_ASSEMBLY_BINDING_CHANGED")

    def test_m54_pausing_after_claim_revokes_heartbeat(self):
        job_id=self._m52_queue_deferred_montage()
        lease=self.queue.claim(worker_id="mac-worker",
                               capabilities=["episode_assemble"])
        self.queue.set_paused(True)
        response=self.queue.heartbeat(job_id=job_id,worker_id="mac-worker",
            generation=lease["generation"],lease_seconds=600)
        self.assertEqual(response["state"],"FAILED")
        self.assertEqual(response["error_code"],"M54_MONTAGE_LEASE_REVOKED")
        with self.queue._connection() as db:
            e=db.execute("""SELECT info_json FROM events WHERE job_id=?
                AND event_type='M54_MONTAGE_HEARTBEAT_REVOKED' LIMIT 1""",
                (job_id,)).fetchone()
        self.assertEqual(json.loads(e["info_json"])["reason"],
                         "M54_STUDIO_PAUSED")

    def _m57_failed_two_scene_montage(self):
        from kidsstudio.recovery_intake import RecoveryIntake, _original_request_sha
        original=self._m52_queue_deferred_montage()
        lease=self.queue.claim(worker_id="mac-worker",
                               capabilities=["episode_assemble"])
        self.assertEqual(lease["job_id"],original)
        self.queue.fail(job_id=original,worker_id="mac-worker",
            generation=lease["generation"],retryable=False,
            error_code="MEDIA_RECONCILIATION_REQUIRED")
        self.assertEqual(self.manager.reconcile(),1)
        with self.queue._connection() as db:
            ep=db.execute("""SELECT state,source_sha256 FROM
                studio_episodes WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
            self.assertEqual(ep["state"],"BLOCKED")
            from kidsstudio.studio_scenes import assert_scenes_ready
            scene=assert_scenes_ready(db,"colors-ar",1,ep["source_sha256"])
        old=json.loads(lease["payload"])
        old_digest=hashlib.sha256(json.dumps({
            "kind":"episode_assemble","payload":old
        },sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(_original_request_sha(old),old_digest)
        sid="colors-ar"
        proposal={
            "schema_version":1,
            "status":"M56_FRESH_ATTEMPT_PROPOSED_NOT_QUEUED",
            "proposal_id":"a"*32,
            "original_job_id":original,
            "original_request_sha256":_original_request_sha(old),
            "frozen_inspection_sha256":"b"*64,
            "original_assembly_recipe_sha256":"c"*64,
            "original_script_sha256":old["script_sha256"],
            "series_id":sid,"episode_number":1,
            "scene_count":2,
            "scenes":[{
                "scene":i,"strategy":(
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
                    if i==1 else "USE_ORIGINAL_APPROVED_LTX_SOURCE"),
                "source_sha256":item["ltx_sha256"],
                "source_face_cleanup":"none",
                "candidate_path":str(self.root/f"candidate_{i}.mp4"),
                "candidate_sha256":("f"*64 if i==1
                                    else item["ltx_sha256"]),
                "candidate_technical_status":(
                    "M7_TECH_PASS_NOT_FINAL_QA" if i==1 else "NOT_REUSED"),
                "requires_new_scene_provenance_review":True,
                "candidate_approved_for_publication":False,
            } for i,item in enumerate(scene,1)],
            "verified_normalized_candidates":1,
            "original_scene_fallback_count":1,
            "proposed_pi_job_id":None,
            "source_catalogue_sha256":old["catalogue_sha256"],
            "requires_new_catalogue_and_scene_provenance":True,
            "requires_new_pi_authorized_job_and_lease":True,
            "requires_new_final_m7_full_decode_and_quality_reviews":True,
            "owner_private_preview_required":True,
            "auto_retry_allowed":False,
            "auto_execute_allowed":False,
            "auto_reuse_allowed":False,
            "public_release_authorized":False,
        }
        intake=RecoveryIntake(self.queue)
        intake.initialize()
        return original,proposal,intake

    def _m57_write_proposal(self,proposal):
        from kidsstudio.recovery_intake import _sha_json
        body={"schema_version":1,"proposal":proposal,
              "proposal_sha256":_sha_json(proposal)}
        path=self.root/"m56_copied_pi_proposal.json"
        path.write_text(json.dumps(body))
        return path,sha(path)

    def test_m57_pi_intake_pins_new_attempt_identity_without_queueing(self):
        original,proposal,intake=self._m57_failed_two_scene_montage()
        path,digest=self._m57_write_proposal(proposal)
        before=self.queue.status()["counts"].get("QUEUED",0)
        result=intake.pin(path,sha256=digest)
        self.assertEqual(result["status"],
            "M57_PRIVATE_RECOVERY_INTENT_PINNED_NO_JOB_QUEUED")
        self.assertEqual(result["original_job_id"],original)
        self.assertEqual(result["proposal_id"],"a"*32)
        self.assertEqual(result["recovered_candidates"],1)
        self.assertEqual(result["fallbacks"],1)
        self.assertIsNone(result["new_pi_job_id"])
        self.assertIs(result["mac_media_verified_by_pi"],False)
        self.assertIs(result["auto_execute_allowed"],False)
        self.assertIs(result["public_release_authorized"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),before)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state,proposal_sha256,original_job_id
                FROM studio_recovery_intents WHERE proposal_id=?""",
                ("a"*32,)).fetchone()
        self.assertEqual(row["state"],"M57_RECONCILIATION_REQUIRED_NO_QUEUE")
        self.assertEqual(row["original_job_id"],original)
        from kidsstudio.recovery_intake import RecoveryIntakeError
        with self.assertRaises(RecoveryIntakeError):
            intake.pin(path,sha256=digest)

    def test_m57_forged_scene_candidate_and_approval_metadata_fail_closed(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        original,proposal,intake=self._m57_failed_two_scene_montage()
        for change in ("wrong_ltx","auto_publish","false_m7","wrong_count"):
            candidate=json.loads(json.dumps(proposal))
            if change=="wrong_ltx":
                candidate["scenes"][1]["source_sha256"]="e"*64
            elif change=="auto_publish":
                candidate["public_release_authorized"]=True
            elif change=="false_m7":
                candidate["scenes"][0]["candidate_technical_status"]="NOT_REUSED"
            else:
                candidate["verified_normalized_candidates"]=2
            path,digest=self._m57_write_proposal(candidate)
            with self.assertRaises(RecoveryIntakeError):
                intake.pin(path,sha256=digest)
        with self.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM studio_recovery_intents").fetchone()[0],0)

    def test_m57_forged_bytes_or_changed_failed_job_status_are_refused(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        old,proposal,intake=self._m57_failed_two_scene_montage()
        path,digest=self._m57_write_proposal(proposal)
        with self.assertRaises(RecoveryIntakeError):
            intake.pin(path,sha256="d"*64)
        with self.queue._connection(write=True) as db:
            db.execute("UPDATE jobs SET state='COMPLETED' WHERE job_id=?",
                       (old,))
        with self.assertRaises(RecoveryIntakeError):
            intake.pin(path,sha256=digest)
        with self.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM studio_recovery_intents").fetchone()[0],0)

    def test_m57_unreconciled_episode_or_unapproved_scene_rejected(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        old,proposal,intake=self._m57_failed_two_scene_montage()
        path,digest=self._m57_write_proposal(proposal)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='RENDER_QUEUED'
                WHERE series_id='colors-ar' AND ordinal=1""")
        with self.assertRaises(RecoveryIntakeError):
            intake.pin(path,sha256=digest)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='BLOCKED'
                WHERE series_id='colors-ar' AND ordinal=1""")
            db.execute("""UPDATE studio_scene_stages SET state='PENDING_QA'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
        with self.assertRaises(RecoveryIntakeError):
            intake.pin(path,sha256=digest)

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
