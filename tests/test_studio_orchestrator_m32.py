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

    def _m58_synthetic_pi_contract(self,proposal):
        from kidsstudio.recovery_intake import _sha_json
        contract={
            "schema_version":1,
            "status":"M58_MAC_MEDIA_BYTES_RECHECKED_NOT_RENDERED",
            "proposal_id":proposal["proposal_id"],
            "proposal_sha256":_sha_json(proposal),
            "original_job_id":proposal["original_job_id"],
            "original_script_sha256":proposal["original_script_sha256"],
            "source_catalogue_sha256":proposal["source_catalogue_sha256"],
            "scene_count":proposal["scene_count"],
            "scenes":[{
                "scene":s["scene"],
                "strategy":s["strategy"],
                "original_ltx_sha256":s["source_sha256"],
                "selected_media_sha256":s["candidate_sha256"],
                "full_m7_decode_confirmed":s["strategy"]==
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS",
                "new_scene_provenance_required":True,
                "publication_approved":False,
            } for s in proposal["scenes"]],
            "recovered_candidates":proposal["verified_normalized_candidates"],
            "fallbacks":proposal["original_scene_fallback_count"],
            "new_pi_job_id":None,"pi_media_bytes_verified":False,
            "requires_new_execution_contract":True,
            "requires_fresh_mac_pre_execution_verification":True,
            "requires_final_master_m7_and_private_owner_preview":True,
            "auto_execute_allowed":False,
            "public_release_authorized":False,
        }
        path=self.root/"m58_copied_mac_media_contract.json"
        path.write_text(json.dumps({
            "schema_version":1,"contract":contract,
            "contract_sha256":_sha_json(contract)}))
        return path,sha(path)

    def test_m58_pi_media_binding_is_one_time_and_does_not_queue_render(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        original,proposal,intake=self._m57_failed_two_scene_montage()
        source,source_sha=self._m57_write_proposal(proposal)
        intake.pin(source,sha256=source_sha)
        media,media_sha=self._m58_synthetic_pi_contract(proposal)
        count=self.queue.status()["counts"].get("QUEUED",0)
        result=intake.bind_media_contract(
            source,proposal_sha256=source_sha,
            contract_file=media,contract_file_sha256=media_sha)
        self.assertEqual(result["status"],
            "M58_PRIVATE_MEDIA_BOUND_NO_JOB_QUEUED")
        self.assertEqual(result["recovered_candidates"],1)
        self.assertEqual(result["fallbacks"],1)
        self.assertIsNone(result["new_pi_job_id"])
        self.assertIs(result["pi_media_bytes_verified"],False)
        self.assertIs(result["auto_execute_allowed"],False)
        self.assertIs(result["public_release_authorized"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),count)
        with self.queue._connection() as db:
            pinned=db.execute("""SELECT state,contract_file_sha256
                FROM studio_recovery_media_contracts
                WHERE proposal_id=?""",(proposal["proposal_id"],)).fetchone()
        self.assertEqual(pinned["state"],
            "M58_MEDIA_BOUND_REQUIRES_FRESH_EXECUTION_CONTRACT")
        self.assertEqual(pinned["contract_file_sha256"],media_sha)
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_media_contract(source,proposal_sha256=source_sha,
                contract_file=media,contract_file_sha256=media_sha)

    def test_m58_pi_binding_rejects_changed_bytes_and_forged_media_flags(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError,_sha_json
        old,proposal,intake=self._m57_failed_two_scene_montage()
        source,source_sha=self._m57_write_proposal(proposal)
        intake.pin(source,sha256=source_sha)
        media,media_sha=self._m58_synthetic_pi_contract(proposal)
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_media_contract(source,proposal_sha256=source_sha,
                contract_file=media,contract_file_sha256="f"*64)
        for mutation in ("bad_source","claimed_pi_bytes","bad_decode",
                         "wrong_selected_sha","public","wrong_count"):
            value=json.loads(media.read_text())
            contract=value["contract"]
            if mutation=="bad_source":
                contract["scenes"][1]["original_ltx_sha256"]="e"*64
            elif mutation=="claimed_pi_bytes":
                contract["pi_media_bytes_verified"]=True
            elif mutation=="bad_decode":
                contract["scenes"][0]["full_m7_decode_confirmed"]=False
            elif mutation=="wrong_selected_sha":
                contract["scenes"][0]["selected_media_sha256"]="e"*64
            elif mutation=="public":
                contract["public_release_authorized"]=True
            else:
                contract["recovered_candidates"]=2
            value["contract_sha256"]=_sha_json(contract)
            media.write_text(json.dumps(value))
            with self.assertRaises(RecoveryIntakeError):
                intake.bind_media_contract(
                    source,proposal_sha256=source_sha,
                    contract_file=media,contract_file_sha256=sha(media))
            media,media_sha=self._m58_synthetic_pi_contract(proposal)
        with self.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM studio_recovery_media_contracts"
            ).fetchone()[0],0)

    def test_m58_pi_requires_m57_pinned_and_current_approved_scenes(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        old,proposal,intake=self._m57_failed_two_scene_montage()
        source,source_sha=self._m57_write_proposal(proposal)
        media,media_sha=self._m58_synthetic_pi_contract(proposal)
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_media_contract(source,proposal_sha256=source_sha,
                contract_file=media,contract_file_sha256=media_sha)
        intake.pin(source,sha256=source_sha)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET state='PENDING_QA'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_media_contract(source,proposal_sha256=source_sha,
                contract_file=media,contract_file_sha256=media_sha)

    def _m59_staged_pi_inputs(self):
        from kidsstudio.recovery_intake import _sha_json
        old,proposal,intake=self._m57_failed_two_scene_montage()
        pfile,psha=self._m57_write_proposal(proposal)
        intake.pin(pfile,sha256=psha)
        mfile,msha=self._m58_synthetic_pi_contract(proposal)
        bound=intake.bind_media_contract(
            pfile,proposal_sha256=psha,
            contract_file=mfile,contract_file_sha256=msha)
        self.assertEqual(bound["status"],
                         "M58_PRIVATE_MEDIA_BOUND_NO_JOB_QUEUED")
        media=json.loads(mfile.read_text())
        derived={
            "schema_version":2,
            "recovery_stage":"M59_STAGED_ONLY_NO_EXECUTION",
            "series_id":proposal["series_id"],
            "episode_number":proposal["episode_number"],
            "script":{"path":str(self.parent),
                      "sha256":sha(self.parent)},
            "private_root":str(self.root),
            "output_root":str(self.root/"assembled"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "tools":{"ffmpeg":"/usr/bin/ffmpeg","ffprobe":"/usr/bin/ffprobe",
                "face_python":"/usr/bin/python3",
                "face_v06":str(self.root/"face_v06.py"),
                "face_v06_sha256":"c"*64,
                "face_v07":str(self.root/"face_v07.py"),
                "face_v07_sha256":"d"*64},
            "clips":[{
                "video":scene["candidate_path"],
                "sha256":scene["candidate_sha256"],
                "face_cleanup":(
                    "none" if scene["strategy"]==
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
                    else scene["source_face_cleanup"]),
            } for scene in proposal["scenes"]],
        }
        recipe_path=self.root/"m59_copied_recipe.json"
        recipe_path.write_text(json.dumps(derived))
        manifest={
            "schema_version":2,
            "status":"M59_PRIVATE_RECOVERY_RECIPE_STAGED_NOT_EXECUTABLE",
            "proposal_id":proposal["proposal_id"],
            "original_job_id":old,
            "original_script_sha256":proposal["original_script_sha256"],
            "source_catalogue_sha256":proposal["source_catalogue_sha256"],
            "source_m58_contract_sha256":media["contract_sha256"],
            "source_m58_file_sha256":sha(mfile),
            "derived_recipe_sha256":sha(recipe_path),
            "new_recipe_id":"recovery_"+proposal["proposal_id"],
            "scene_count":proposal["scene_count"],
            "scenes":[{
                "scene":s["scene"],"strategy":s["strategy"],
                "original_ltx_sha256":s["source_sha256"],
                "selected_media_sha256":s["candidate_sha256"],
                "applied_face_cleanup":(
                    "none" if s["strategy"]==
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
                    else s["source_face_cleanup"]),
                "full_m7_decode_confirmed":s["strategy"]==
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS",
                "requires_new_scene_provenance_review":True,
                "publication_approved":False,
            } for s in proposal["scenes"]],
            "recovered_candidates":1,"fallbacks":1,
            "new_pi_job_id":None,
            "new_m14_m49_lineage_required":True,
            "fresh_m53_m54_lease_required":True,
            "new_final_m7_quality_and_owner_preview_required":True,
            "auto_execute_allowed":False,"auto_retry_allowed":False,
            "public_release_authorized":False,
        }
        manifest_path=self.root/"m59_copied_manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version":2,"manifest":manifest,
            "manifest_sha256":_sha_json(manifest)}))
        return (old,proposal,intake,pfile,psha,recipe_path,
                manifest_path)

    def test_m59_pi_binds_staged_recipe_only_and_never_queues(self):
        (old,proposal,intake,pfile,psha,recipe,manifest)=(
            self._m59_staged_pi_inputs())
        before=self.queue.status()["counts"].get("QUEUED",0)
        reply=intake.bind_execution_recipe(
            pfile,proposal_sha256=psha,
            recipe_file=recipe,recipe_sha256=sha(recipe),
            manifest_file=manifest,manifest_sha256=sha(manifest))
        self.assertEqual(reply["status"],
                         "M59_PRIVATE_RECOVERY_RECIPE_BOUND_NO_JOB")
        self.assertEqual(reply["derived_recipe_sha256"],sha(recipe))
        self.assertIsNone(reply["new_pi_job_id"])
        self.assertIs(reply["mac_bytes_verified_by_pi"],False)
        self.assertIs(reply["auto_execute_allowed"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),
                         before)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state,recipe_id FROM
                studio_recovery_execution_recipes WHERE proposal_id=?""",
                (proposal["proposal_id"],)).fetchone()
        self.assertEqual(row["state"],"M59_NONEXECUTABLE_RECIPE_BOUND")
        self.assertEqual(row["recipe_id"],"recovery_"+proposal["proposal_id"])
        from kidsstudio.recovery_intake import RecoveryIntakeError
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_execution_recipe(
                pfile,proposal_sha256=psha,recipe_file=recipe,
                recipe_sha256=sha(recipe),manifest_file=manifest,
                manifest_sha256=sha(manifest))

    def test_m59_pi_rejects_forged_scene_sha_flags_and_recipe_bytes(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError,_sha_json
        (old,proposal,intake,pfile,psha,recipe,manifest)=(
            self._m59_staged_pi_inputs())
        original=json.loads(manifest.read_text())
        original_recipe=json.loads(recipe.read_text())
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_execution_recipe(
                pfile,proposal_sha256=psha,recipe_file=recipe,
                recipe_sha256="0"*64,manifest_file=manifest,
                manifest_sha256=sha(manifest))
        for mutation in ("recovered_sha","fake_decode","wrong_face",
                         "allow_execution","wrong_old_job","forged_recipe"):
            candidate=json.loads(json.dumps(original))
            staged=json.loads(json.dumps(original_recipe))
            m=candidate["manifest"]
            if mutation=="recovered_sha":
                m["scenes"][0]["selected_media_sha256"]="0"*64
            elif mutation=="fake_decode":
                m["scenes"][0]["full_m7_decode_confirmed"]=False
            elif mutation=="wrong_face":
                m["scenes"][0]["applied_face_cleanup"]="bunny_v07"
                staged["clips"][0]["face_cleanup"]="bunny_v07"
            elif mutation=="allow_execution":
                m["auto_execute_allowed"]=True
            elif mutation=="wrong_old_job":
                m["original_job_id"]="0"*32
            else:
                staged["clips"][1]["sha256"]="e"*64
            recipe.write_text(json.dumps(staged))
            m["derived_recipe_sha256"]=sha(recipe)
            candidate["manifest_sha256"]=_sha_json(m)
            manifest.write_text(json.dumps(candidate))
            with self.assertRaises(RecoveryIntakeError,msg=mutation):
                intake.bind_execution_recipe(
                    pfile,proposal_sha256=psha,recipe_file=recipe,
                    recipe_sha256=sha(recipe),manifest_file=manifest,
                    manifest_sha256=sha(manifest))
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_recovery_execution_recipes""").fetchone()[0],0)

    def test_m59_pi_requires_still_failed_job_and_approved_scene_provenance(self):
        from kidsstudio.recovery_intake import RecoveryIntakeError
        (old,proposal,intake,pfile,psha,recipe,manifest)=(
            self._m59_staged_pi_inputs())
        with self.queue._connection(write=True) as db:
            db.execute("UPDATE jobs SET state='COMPLETED' WHERE job_id=?",
                       (old,))
        with self.assertRaises(RecoveryIntakeError):
            intake.bind_execution_recipe(
                pfile,proposal_sha256=psha,recipe_file=recipe,
                recipe_sha256=sha(recipe),manifest_file=manifest,
                manifest_sha256=sha(manifest))

    def _m60_ready_pi_reservation(self):
        from kidsstudio.recovery_execution_admission import RecoveryAdmission
        (old,proposal,intake,pfile,psha,recipe,manifest)=(
            self._m59_staged_pi_inputs())
        intake.bind_execution_recipe(
            pfile,proposal_sha256=psha,
            recipe_file=recipe,recipe_sha256=sha(recipe),
            manifest_file=manifest,manifest_sha256=sha(manifest))
        gate=RecoveryAdmission(self.queue)
        gate.initialize()
        return old,proposal,gate,pfile,psha,recipe,manifest

    def test_m60_reserves_fresh_unclaimable_job_identity_one_time(self):
        from kidsstudio.recovery_execution_admission import (
            RecoveryAdmissionError,STATE)
        old,proposal,gate,pfile,psha,recipe,manifest=(
            self._m60_ready_pi_reservation())
        count=self.queue.status()["counts"].get("QUEUED",0)
        result=gate.reserve(
            proposal_file=pfile,proposal_sha256=psha,
            recipe_file=recipe,recipe_sha256=sha(recipe),
            manifest_file=manifest,manifest_sha256=sha(manifest))
        self.assertEqual(result["status"],STATE)
        self.assertEqual(len(result["reserved_job_id"]),32)
        self.assertNotEqual(result["reserved_job_id"],old)
        self.assertIs(result["job_inserted_in_queue"],False)
        self.assertIs(result["worker_claimable"],False)
        self.assertIs(result["auto_execute_allowed"],False)
        self.assertIs(result["public_release_authorized"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),count)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state,reserved_job_id FROM
                studio_recovery_reservations WHERE proposal_id=?""",
                (proposal["proposal_id"],)).fetchone()
            queued=db.execute("SELECT 1 FROM jobs WHERE job_id=?",
                              (result["reserved_job_id"],)).fetchone()
        self.assertEqual(row["state"],STATE)
        self.assertEqual(row["reserved_job_id"],result["reserved_job_id"])
        self.assertIsNone(queued)
        with self.assertRaises(RecoveryAdmissionError):
            gate.reserve(
                proposal_file=pfile,proposal_sha256=psha,
                recipe_file=recipe,recipe_sha256=sha(recipe),
                manifest_file=manifest,manifest_sha256=sha(manifest))

    def test_m60_rejects_modified_m59_recipe_or_fake_publish_allowance(self):
        from kidsstudio.recovery_execution_admission import RecoveryAdmissionError
        old,proposal,gate,pfile,psha,recipe,manifest=(
            self._m60_ready_pi_reservation())
        staged=json.loads(recipe.read_text())
        staged["clips"][0]["sha256"]="0"*64
        recipe.write_text(json.dumps(staged))
        with self.assertRaises(RecoveryAdmissionError):
            gate.reserve(
                proposal_file=pfile,proposal_sha256=psha,
                recipe_file=recipe,recipe_sha256=sha(recipe),
                manifest_file=manifest,manifest_sha256=sha(manifest))
        # restore exact bound file and forge manifest negative flag.
        staged["clips"][0]["sha256"]=proposal["scenes"][0]["candidate_sha256"]
        recipe.write_text(json.dumps(staged))
        envelope=json.loads(manifest.read_text())
        envelope["manifest"]["auto_execute_allowed"]=True
        from kidsstudio.recovery_intake import _sha_json
        envelope["manifest_sha256"]=_sha_json(envelope["manifest"])
        manifest.write_text(json.dumps(envelope))
        with self.assertRaises(RecoveryAdmissionError):
            gate.reserve(
                proposal_file=pfile,proposal_sha256=psha,
                recipe_file=recipe,recipe_sha256=sha(recipe),
                manifest_file=manifest,manifest_sha256=sha(manifest))
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_recovery_reservations""").fetchone()[0],0)

    def test_m60_rejects_revoked_scene_qa_or_nonterminal_old_job(self):
        from kidsstudio.recovery_execution_admission import RecoveryAdmissionError
        old,proposal,gate,pfile,psha,recipe,manifest=(
            self._m60_ready_pi_reservation())
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET state='PENDING_QA'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
        with self.assertRaises(RecoveryAdmissionError):
            gate.reserve(
                proposal_file=pfile,proposal_sha256=psha,
                recipe_file=recipe,recipe_sha256=sha(recipe),
                manifest_file=manifest,manifest_sha256=sha(manifest))
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET state='QA_APPROVED'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
            db.execute("""UPDATE jobs SET state='COMPLETED'
                WHERE job_id=?""",(old,))
        with self.assertRaises(RecoveryAdmissionError):
            gate.reserve(
                proposal_file=pfile,proposal_sha256=psha,
                recipe_file=recipe,recipe_sha256=sha(recipe),
                manifest_file=manifest,manifest_sha256=sha(manifest))
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_recovery_reservations""").fetchone()[0],0)

    def _m61_ready_pi_lease(self):
        from kidsstudio.recovery_lease import RecoveryLeaseGate
        old,proposal,admission,pfile,psha,recipe,manifest=(
            self._m60_ready_pi_reservation())
        admitted=admission.reserve(
            proposal_file=pfile,proposal_sha256=psha,
            recipe_file=recipe,recipe_sha256=sha(recipe),
            manifest_file=manifest,manifest_sha256=sha(manifest))
        self.assertFalse(admitted["worker_claimable"])
        lease=RecoveryLeaseGate(self.queue)
        lease.initialize()
        lease.activate(pfile,sha256=psha)
        return old,proposal,admitted,lease,pfile,psha

    def test_m61_dedicated_lease_no_legacy_queue_and_technical_review_only(self):
        from kidsstudio.recovery_lease import READY,LEASED,DONE
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        regular_before=self.queue.status()["counts"].get("QUEUED",0)
        self.assertIsNone(self.queue.claim(worker_id="regular-worker",
            capabilities=["episode_assemble"]))
        self.assertIsNone(lease.claim(worker_id="mac-a",
            capability="recovery_assemble",proposal_id="c"*32))
        acquired=lease.claim(worker_id="mac-a",capability="recovery_assemble",
            proposal_id=proposal["proposal_id"])
        self.assertEqual(acquired["job_id"],admission["reserved_job_id"])
        self.assertNotEqual(acquired["job_id"],old)
        self.assertEqual(acquired["generation"],1)
        self.assertEqual(acquired["kind"],"recovery_assemble")
        self.assertIsNone(lease.claim(worker_id="mac-b",
            capability="recovery_assemble",proposal_id=proposal["proposal_id"]))
        proof=lease.check(job_id=acquired["job_id"],worker_id="mac-a",
            generation=1)
        self.assertEqual(proof["status"],"M61_CURRENT_PRIVATE_RECOVERY_LEASE")
        self.assertIs(proof["render_started"],False)
        renewal=lease.check(job_id=acquired["job_id"],worker_id="mac-a",
            generation=1,renew=True)
        self.assertEqual(renewal["recipe_sha256"],acquired["recipe_sha256"])
        result=lease.complete(job_id=acquired["job_id"],worker_id="mac-a",
            generation=1,result={
                "status":"M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW",
                "artifact_sha256":"f"*64,"artifact_bytes":4096,
                "final_m7_full_decode_passed":True,
                "publication_approved":False})
        self.assertEqual(result["status"],DONE)
        self.assertIs(result["owner_private_review_required"],True)
        self.assertIs(result["public_release_authorized"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),
                         regular_before)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state,result_sha256 FROM
                studio_recovery_leases WHERE proposal_id=?""",
                (proposal["proposal_id"],)).fetchone()
        self.assertEqual(row["state"],DONE)
        self.assertEqual(row["result_sha256"],"f"*64)
        self.assertIsNone(lease.claim(worker_id="mac-a",
            capability="recovery_assemble",proposal_id=proposal["proposal_id"]))

    def test_m61_expired_lease_is_terminal_no_hidden_retry(self):
        from kidsstudio.recovery_lease import (
            RecoveryLeaseError,FAILED)
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        obtained=lease.claim(worker_id="mac-a",capability="recovery_assemble",
            proposal_id=proposal["proposal_id"],lease_seconds=10)
        initial=self.queue.clock()
        self.queue.clock=lambda:initial+11
        self.assertEqual(lease.check(job_id=obtained["job_id"],
            worker_id="mac-a",generation=1)["status"],
            "M61_REVOKED_NO_EXECUTION")
        self.assertIsNone(lease.claim(worker_id="mac-a",
            capability="recovery_assemble",proposal_id=proposal["proposal_id"]))
        with self.queue._connection() as db:
            row=db.execute("""SELECT state,generation FROM
                studio_recovery_leases WHERE proposal_id=?""",
                (proposal["proposal_id"],)).fetchone()
        self.assertEqual(row["state"],FAILED)
        self.assertEqual(row["generation"],1)

    def test_m61_revoke_current_scene_qa_and_studio_pause(self):
        from kidsstudio.recovery_lease import FAILED
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        obtained=lease.claim(worker_id="mac-a",capability="recovery_assemble",
            proposal_id=proposal["proposal_id"])
        self.queue.set_paused(True)
        self.assertEqual(lease.check(job_id=obtained["job_id"],
            worker_id="mac-a",generation=1,renew=True)["status"],
            "M61_REVOKED_NO_EXECUTION")
        self.queue.set_paused(False)
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT state FROM
                studio_recovery_leases WHERE proposal_id=?""",
                (proposal["proposal_id"],)).fetchone()[0],FAILED)
    def test_m61_revokes_lease_when_scene_qa_changes_mid_render(self):
        from kidsstudio.recovery_lease import FAILED
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        claimed=lease.claim(worker_id="mac-a",capability="recovery_assemble",
                            proposal_id=proposal["proposal_id"])
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET state='PENDING_QA'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
        response=lease.check(job_id=claimed["job_id"],worker_id="mac-a",
                             generation=1,renew=True)
        self.assertEqual(response["status"],"M61_REVOKED_NO_EXECUTION")
        with self.queue._connection() as db:
            final=db.execute("""SELECT state FROM studio_recovery_leases
                WHERE proposal_id=?""",(proposal["proposal_id"],)).fetchone()
        self.assertEqual(final["state"],FAILED)
        self.assertIsNone(lease.claim(worker_id="mac-a",
            capability="recovery_assemble",proposal_id=proposal["proposal_id"]))

    def test_m61_tls_worker_capability_isolated_from_ordinary_claim(self):
        from kidsstudio.coordinator_api import Coordinator,TransportError
        from kidsstudio.recovery_lease import RecoveryLeaseGate
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        coordinator=Coordinator(self.queue,self.root/"m61-vault",{
            "mac-recovery":("x"*40,{"recovery_assemble"}),
            "mac-regular":("y"*40,{"episode_assemble"}),
        })
        with self.assertRaises(TransportError):
            coordinator.dispatch("recovery-claim",
                {"proposal_id":proposal["proposal_id"]},
                "mac-regular",frozenset({"episode_assemble"}))
        other=coordinator.dispatch("claim",{},"mac-recovery",
                                   frozenset({"recovery_assemble"}))
        self.assertIsNone(other["job"])
        got=coordinator.dispatch("recovery-claim",
            {"proposal_id":proposal["proposal_id"]},
            "mac-recovery",frozenset({"recovery_assemble"}))
        self.assertEqual(got["job"]["job_id"],admission["reserved_job_id"])
        check=coordinator.dispatch("recovery-pre-execution-check",
            {"job_id":got["job"]["job_id"],"generation":1},
            "mac-recovery",frozenset({"recovery_assemble"}))
        self.assertEqual(check["status"],"M61_CURRENT_PRIVATE_RECOVERY_LEASE")
        beat=coordinator.dispatch("recovery-heartbeat",
            {"job_id":got["job"]["job_id"],"generation":1},
            "mac-recovery",frozenset({"recovery_assemble"}))
        self.assertIs(beat["ok"],True)
        with self.assertRaises(TransportError):
            coordinator.dispatch("recovery-pre-execution-check",
                {"job_id":got["job"]["job_id"],"generation":2},
                "mac-recovery",frozenset({"recovery_assemble"}))

    def test_m61_dashboard_exposes_private_recovery_without_media_paths(self):
        from kidsstudio.studio_dashboard import build_snapshot
        old,proposal,admission,lease,pfile,psha=self._m61_ready_pi_lease()
        worker=lease.claim(worker_id="mac-a",capability="recovery_assemble",
            proposal_id=proposal["proposal_id"])
        snapshot=build_snapshot(self.queue)
        recovery=snapshot["recovery"]
        self.assertEqual(recovery["leased"],1)
        self.assertEqual(recovery["reserved"],0)
        self.assertIs(recovery["public_release_authorized"],False)
        ep=next(e for e in snapshot["episodes"]
                if e["series_id"]=="colors-ar" and e["ordinal"]==1)
        self.assertEqual(ep["recovery"]["state"],
                         "M61_LEASED_PRIVATE_RECOVERY")
        self.assertIs(ep["recovery"]["automatically_public"],False)
        self.assertNotIn(str(pfile),json.dumps(snapshot))
        self.assertNotIn(str(self.root/"m59_copied_recipe.json"),
                         json.dumps(snapshot))

    def _m62_completed_pi_and_evidence(self):
        from kidsstudio.recovery_final_qa import RecoveryFinalQA
        from kidsstudio.episode_quality import CHECKS
        old,proposal,admitted,lease,pfile,psha=self._m61_ready_pi_lease()
        claim=lease.claim(worker_id="mac-a",capability="recovery_assemble",
            proposal_id=proposal["proposal_id"])
        result=lease.complete(
            job_id=claim["job_id"],worker_id="mac-a",generation=1,
            result={"status":"M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW",
                    "artifact_sha256":"f"*64,"artifact_bytes":4096,
                    "final_m7_full_decode_passed":True,
                    "publication_approved":False})
        self.assertEqual(result["status"],
                         "M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW")
        gate=RecoveryFinalQA(self.queue)
        gate.initialize()
        technical=self.root/"m62_technical.json"
        tech={
            "schema_version":1,"status":"TECH_PASS_OWNER_REVIEW_PENDING",
            "media_sha256":"f"*64,"expected_media_sha256":"f"*64,
            "file_bytes":4096,"duration_seconds":14.0,
            "checks":{k:True for k in CHECKS},
            "subjective_checks_performed":False,
            "rights_verified":False,"publishing_approved":False}
        technical.write_text(json.dumps(tech))
        evidence=self.root/"m62_observations.json"
        evidence.write_text(json.dumps({
            "schema_version":1,"media_sha256":"f"*64,
            "script_sha256":sha(self.parent),
            "transcript_sha256":"1"*64,
            "frames_manifest_sha256":"2"*64,
            "audio_analysis_sha256":"3"*64,
            "sampling_complete":True,
            "subjective_quality_verified":False,
            "publishing_approved":False}))
        rights=self.root/"m62_rights.json"
        rights.write_text(json.dumps({
            "schema_version":1,"media_sha256":"f"*64,
            "assets":[{"asset_sha256":"4"*64,
                "provenance_kind":"original_created",
                "proof_sha256":"5"*64,
                "use_scope":"commercial_youtube_kids",
                "rights_status":"DOCUMENTED_NOT_LEGALLY_ADJUDICATED"}],
            "all_assets_accounted_for":True,
            "publishing_approved":False}))
        review_file=self.root/"m62_review.json"
        from kidsstudio.agent_final_qa import ROLE_CRITERIA
        review={
            "schema_version":1,
            "series_id":"colors-ar","episode_number":1,
            "render_job_id":admitted["reserved_job_id"],
            "media_sha256":"f"*64,"script_sha256":sha(self.parent),
            "observed_evidence_sha256":sha(evidence),
            "rights_catalogue_sha256":sha(rights),
            "reviewers":[{
                "role":role,"provider_id":provider,
                "model_id":"synthetic-"+provider,
                "evidence_sha256":sha(evidence),
                "criteria":{k:{
                    "decision":"PASS",
                    "evidence":"Synthetic evidence bounded to this fake video and scene "+k,
                } for k in sorted(fields)},
                "summary":"Synthetic independent educational and safety quality check",
                "release_approved":False,
            } for role,provider,fields in (
                ("pedagogy_language","pedagogy_provider",ROLE_CRITERIA["pedagogy_language"]),
                ("visual_child_safety","visual_provider",ROLE_CRITERIA["visual_child_safety"])
            )],
            "publishing_approved":False,
        }
        review_file.write_text(json.dumps(review))
        return proposal,admitted,gate,technical,evidence,rights,review_file

    def test_m62_independent_qa_ready_and_private_policy_handoff_no_upload(self):
        from kidsstudio.recovery_final_qa import TECH,READY,STAGED,RecoveryQualityError
        from kidsstudio.private_upload_policy import PrivateUploadPolicy
        proposal,admitted,gate,tech,evidence,rights,review=(
            self._m62_completed_pi_and_evidence())
        pid=proposal["proposal_id"]
        before=self.queue.status()["counts"].get("QUEUED",0)
        registered=gate.register_technical(pid,tech)
        self.assertEqual(registered["status"],TECH)
        self.assertIs(registered["pi_verified_mac_video_bytes"],False)
        with self.assertRaises(RecoveryQualityError):
            gate.register_technical(pid,tech)
        ai=gate.register_ai(pid,review_bundle=review,
            observed_media_evidence=evidence,rights_catalogue=rights)
        self.assertEqual(ai["status"],READY)
        self.assertEqual(ai["independent_provider_count"],2)
        self.assertIs(ai["rights_legal_certainty_proven"],False)
        with self.assertRaises(RecoveryQualityError):
            gate.stage_private_handoff(pid,channel_id="UC"+"a"*22,
                made_for_kids=True,contains_synthetic_media=True)
        policy=PrivateUploadPolicy(self.queue)
        policy.initialize()
        policy.grant("colors-ar",channel_id="UC"+"a"*22,
            max_uploads_24h=1,made_for_kids=True,
            contains_synthetic_media=True,
            owner_note="Private YouTube series approval only, no public release")
        self.queue.set_paused(True)
        with self.assertRaises(RecoveryQualityError):
            gate.stage_private_handoff(pid,channel_id="UC"+"a"*22,
                made_for_kids=True,contains_synthetic_media=True)
        self.queue.set_paused(False)
        handoff=gate.stage_private_handoff(pid,
            channel_id="UC"+"a"*22,
            made_for_kids=True,contains_synthetic_media=True)
        self.assertEqual(handoff["status"],STAGED)
        self.assertEqual(handoff["master_sha256"],"f"*64)
        self.assertEqual(handoff["recovery_job_id"],
                         admitted["reserved_job_id"])
        self.assertIs(handoff["youtube_upload_job_created"],False)
        self.assertIs(handoff["network_used"],False)
        self.assertIs(handoff["oauth_used"],False)
        self.assertIs(handoff["public_release_authorized"],False)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),before)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state FROM studio_recovery_private_handoffs
                WHERE proposal_id=?""",(pid,)).fetchone()
            ep=db.execute("""SELECT state,render_job_id FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
        self.assertEqual(row["state"],STAGED)
        from kidsstudio.studio_dashboard import build_snapshot
        dashboard=build_snapshot(self.queue)
        self.assertEqual(dashboard["recovery"]["private_handoff"],1)
        card=next(e for e in dashboard["episodes"]
                  if e["series_id"]=="colors-ar" and e["ordinal"]==1)
        self.assertEqual(card["recovery"]["state"],STAGED)
        self.assertIs(card["recovery"]["automatic_youtube_upload"],False)
        self.assertNotIn(str(self.root/"m62_rights.json"),
                         json.dumps(dashboard))
        self.assertEqual(ep["state"],"BLOCKED")
        self.assertEqual(ep["render_job_id"],proposal["original_job_id"])
        with self.assertRaises(RecoveryQualityError):
            gate.stage_private_handoff(pid,channel_id="UC"+"a"*22,
                made_for_kids=True,contains_synthetic_media=True)

    def test_m62_rejects_wrong_video_technical_report_and_same_provider(self):
        from kidsstudio.recovery_final_qa import RecoveryQualityError
        proposal,admitted,gate,tech,evidence,rights,review=(
            self._m62_completed_pi_and_evidence())
        pid=proposal["proposal_id"]
        data=json.loads(tech.read_text())
        data["media_sha256"]="b"*64
        tech.write_text(json.dumps(data))
        with self.assertRaises(RecoveryQualityError):
            gate.register_technical(pid,tech)
        data["media_sha256"]="f"*64
        tech.write_text(json.dumps(data))
        gate.register_technical(pid,tech)
        values=json.loads(review.read_text())
        values["reviewers"][1]["provider_id"]=values["reviewers"][0]["provider_id"]
        review.write_text(json.dumps(values))
        with self.assertRaises(RecoveryQualityError):
            gate.register_ai(pid,review_bundle=review,
                observed_media_evidence=evidence,rights_catalogue=rights)
        values["reviewers"][1]["provider_id"]="visual_provider"
        values["reviewers"][1]["criteria"]["child_safety"]["decision"]="UNSURE"
        review.write_text(json.dumps(values))
        result=gate.register_ai(pid,review_bundle=review,
            observed_media_evidence=evidence,rights_catalogue=rights)
        self.assertEqual(result["status"],"M62_AI_INTERNAL_CHANGES_REQUIRED")
        with self.assertRaises(RecoveryQualityError):
            gate.stage_private_handoff(pid,channel_id="UC"+"a"*22,
                made_for_kids=True,contains_synthetic_media=True)

    def test_m62_cli_defaults_to_no_ffmpeg_or_network(self):
        from kidsstudio.recovery_quality_cli import main
        import contextlib
        import io
        result=io.StringIO()
        with contextlib.redirect_stdout(result):
            code=main(["prepare-technical",
                "--video",str(self.root/"missing.mp4"),
                "--sha256","f"*64,
                "--report",str(self.root/"not-created.json")])
        self.assertEqual(code,0)
        self.assertIn("M62_EXPLICIT_EXECUTE_REQUIRED_NO_FFMPEG",
                      result.getvalue())
        self.assertFalse((self.root/"not-created.json").exists())

    def test_m62_revoked_source_qa_blocks_even_valid_AI_or_handoff(self):
        from kidsstudio.recovery_final_qa import RecoveryQualityError
        proposal,admitted,gate,tech,evidence,rights,review=(
            self._m62_completed_pi_and_evidence())
        pid=proposal["proposal_id"]
        gate.register_technical(pid,tech)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_stages SET state='PENDING_QA'
                WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='ltx_animate'""")
        with self.assertRaises(RecoveryQualityError):
            gate.register_ai(pid,review_bundle=review,
                observed_media_evidence=evidence,rights_catalogue=rights)
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT state FROM
                studio_recovery_final_qa WHERE proposal_id=?""",
                (pid,)).fetchone()[0],
                "M62_TECH_PASSED_AWAITING_INDEPENDENT_AI")

    def _m63_private_handoff_pi(self):
        from kidsstudio.private_upload_policy import PrivateUploadPolicy
        from kidsstudio.recovery_private_upload_gate import RecoveryPrivateUploadGate
        proposal,admitted,qa,tech,evidence,rights,review=(
            self._m62_completed_pi_and_evidence())
        pid=proposal["proposal_id"]
        qa.register_technical(pid,tech)
        self.assertEqual(qa.register_ai(pid,review_bundle=review,
            observed_media_evidence=evidence,rights_catalogue=rights)["status"],
            "M62_AI_INTERNAL_READY_PRIVATE_ONLY_NOT_UPLOADED")
        policy=PrivateUploadPolicy(self.queue)
        policy.initialize()
        policy.grant("colors-ar",channel_id="UC"+"a"*22,
            max_uploads_24h=1,made_for_kids=True,
            contains_synthetic_media=True,
            owner_note="Strict PRIVATE YouTube only for original educational series")
        qa.stage_private_handoff(pid,channel_id="UC"+"a"*22,
            made_for_kids=True,contains_synthetic_media=True)
        gate=RecoveryPrivateUploadGate(self.queue)
        gate.initialize()
        gate.activate(pid)
        return proposal,admitted,gate,policy

    def test_m63_recovery_upload_lease_private_receipt_owner_comment_and_decision(self):
        from kidsstudio.recovery_private_upload_gate import VERIFIED
        from kidsstudio.recovery_owner_review import (
            RecoveryOwnerReview,RecoveryOwnerReviewError)
        proposal,admitted,gate,policy=self._m63_private_handoff_pi()
        pid=proposal["proposal_id"]
        before=self.queue.status()["counts"].get("QUEUED",0)
        self.assertIsNone(gate.claim(proposal_id="0"*32,
            worker_id="mac-private",capability="recovery_private_upload"))
        claimed=gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload")
        self.assertEqual(claimed["kind"],"recovery_private_upload")
        self.assertEqual(claimed["job_id"],admitted["reserved_job_id"])
        self.assertEqual(claimed["generation"],1)
        self.assertIsNone(gate.claim(proposal_id=pid,worker_id="other",
            capability="recovery_private_upload"))
        current=gate.check(job_id=claimed["job_id"],worker_id="mac-private",
            generation=1,renew=True)
        self.assertEqual(current["status"],"M63_CURRENT_PRIVATE_UPLOAD_LEASE")
        self.assertIs(current["public_release_authorized"],False)
        receipt={"status":"YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
            "video_id":"abcdefghijk","channel_id":"UC"+"a"*22,
            "video_sha256":"f"*64,"youtube_privacy":"private",
            "processing_status":"succeeded","platform_privacy_verified":True,
            "ready_for_owner_review":True,
            "public_release_authorized":False}
        completed=gate.complete(job_id=claimed["job_id"],
            worker_id="mac-private",generation=1,receipt=receipt)
        self.assertEqual(completed["status"],VERIFIED)
        self.assertIs(completed["owner_review_available"],True)
        self.assertEqual(self.queue.status()["counts"].get("QUEUED",0),before)
        reviews=RecoveryOwnerReview(self.queue)
        item=reviews.snapshot()["previews"][0]
        self.assertEqual(item["video_id"],"abcdefghijk")
        self.assertTrue(item["platform_privacy_verified"])
        self.assertTrue(item["recovery"])
        saved=reviews.add_comment("abcdefghijk",
            text="ملاحظة على نطق اسم اللون في هذا المشهد",
            category="education",second=42)
        self.assertEqual(saved["status"],"OWNER_COMMENT_SAVED")
        accepted=reviews.decide("abcdefghijk",
            "APPROVE_WITH_NOTES",note="ملاحظة للمقاطع القادمة")
        self.assertEqual(accepted["status"],"APPROVED_WITH_NOTES")
        self.assertIs(accepted["youtube_visibility_changed"],False)
        self.assertIs(accepted["public_release_authorized"],False)
        with self.assertRaises(RecoveryOwnerReviewError):
            reviews.decide("abcdefghijk","APPROVE")
        view=reviews.snapshot()["previews"][0]
        self.assertEqual(view["state"],"APPROVED_WITH_NOTES")
        self.assertEqual(view["comments"][0]["second"],42)
        with self.queue._connection() as db:
            episode=db.execute("""SELECT state,render_job_id
                FROM studio_episodes WHERE series_id='colors-ar'
                AND ordinal=1""").fetchone()
        self.assertEqual(episode["state"],"BLOCKED")
        self.assertEqual(episode["render_job_id"],proposal["original_job_id"])

    def test_m63_revoked_owner_policy_forbids_upload_and_no_retry(self):
        from kidsstudio.recovery_private_upload_gate import (
            FAILED,RecoveryUploadError)
        proposal,admitted,gate,policy=self._m63_private_handoff_pi()
        pid=proposal["proposal_id"]
        claimed=gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload")
        policy.pause("colors-ar")
        status=gate.check(job_id=claimed["job_id"],
            worker_id="mac-private",generation=1,renew=True)
        self.assertEqual(status["status"],"M63_REVOKED_NO_UPLOAD")
        self.assertIsNone(gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload"))
        with self.queue._connection() as db:
            row=db.execute("""SELECT state FROM studio_recovery_uploads
                WHERE proposal_id=?""",(pid,)).fetchone()
        self.assertEqual(row["state"],FAILED)

    def test_m63_processing_pending_cannot_be_reviewed_or_reuploaded(self):
        from kidsstudio.recovery_private_upload_gate import PENDING
        from kidsstudio.recovery_owner_review import RecoveryOwnerReview
        proposal,admitted,gate,policy=self._m63_private_handoff_pi()
        pid=proposal["proposal_id"]
        c=gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload")
        response=gate.complete(job_id=c["job_id"],worker_id="mac-private",
            generation=1,receipt={
                "status":"YOUTUBE_PRIVATE_PROCESSING_PENDING",
                "video_id":"abcdefghijk","channel_id":"UC"+"a"*22,
                "video_sha256":"f"*64,"youtube_privacy":"private",
                "processing_status":"processing",
                "platform_privacy_verified":True,
                "ready_for_owner_review":False,
                "public_release_authorized":False})
        self.assertEqual(response["status"],PENDING)
        self.assertIs(response["owner_review_available"],False)
        self.assertFalse(RecoveryOwnerReview(self.queue).has_video("no_such_vid"))
        self.assertEqual(RecoveryOwnerReview(self.queue).snapshot()["previews"],[])
        self.assertIsNone(gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload"))

    def test_m63_rejects_wrong_channel_media_or_fake_privacy(self):
        from kidsstudio.recovery_private_upload_gate import RecoveryUploadError
        proposal,admitted,gate,policy=self._m63_private_handoff_pi()
        pid=proposal["proposal_id"]
        claim=gate.claim(proposal_id=pid,worker_id="mac-private",
            capability="recovery_private_upload")
        receipt={"status":"YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
            "video_id":"abcdefghijk","channel_id":"UC"+"a"*22,
            "video_sha256":"f"*64,"youtube_privacy":"private",
            "processing_status":"succeeded","platform_privacy_verified":True,
            "ready_for_owner_review":True,"public_release_authorized":False}
        for key,value in [("video_sha256","0"*64),
                          ("channel_id","UC"+"b"*22),
                          ("youtube_privacy","public"),
                          ("platform_privacy_verified",False),
                          ("ready_for_owner_review",False),
                          ("public_release_authorized",True)]:
            poisoned=dict(receipt)
            poisoned[key]=value
            with self.assertRaises(RecoveryUploadError,msg=key):
                gate.complete(job_id=claim["job_id"],
                    worker_id="mac-private",generation=1,receipt=poisoned)
        with self.queue._connection() as db:
            state=db.execute("""SELECT state FROM studio_recovery_uploads
                WHERE proposal_id=?""",(pid,)).fetchone()[0]
        self.assertEqual(state,"M63_PRIVATE_UPLOAD_LEASED")

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
