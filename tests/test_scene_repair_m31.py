"""M31 synthetic database integration: bounded scene rework and preservation.

Fake media hashes and stored AI-negative receipts are deliberate fixtures;
these tests do not claim a real model rendered/reviewed any media.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.scene_ai_qa import SceneAIGate
from kidsstudio.scene_repair import SceneRepair,RepairError
from kidsstudio.studio_scenes import SceneLedger,SceneError
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class Repair31(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m31-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.q=StudioQueue(self.root/"brain.sqlite")
        self.q.initialize()
        self.manager=SeriesManager(self.q);self.manager.initialize()
        self.manager.create_series("colors-ar","Colors","ar",
            [{"title":"Colors","objective":"Distinguish a red and blue toy"}],
            activate=True)
        self.parent=self.root/"script.txt"
        self.parent.write_text("Two friends teach red and blue using balls",
                               encoding="utf-8")
        self.scripts=[]
        for i in (1,2):
            file=self.root/f"scene{i}.txt"
            file.write_text("Scene "+str(i)+" has different original educational plot")
            self.scripts.append(file)
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET
                state='SCRIPT_APPROVED',source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",
                (digest(self.parent),))
        plan=self.root/"plan.json"
        plan.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "episode_script_sha256":digest(self.parent),
            "scenes":[{"scene":i,"script_sha256":digest(self.scripts[i-1]),
                       "objective":"Identify colors in scene "+str(i)}
                      for i in (1,2)]}))
        self.ledger=SceneLedger(self.q);self.ledger.initialize()
        self.ledger.register_plan(plan)
        SceneAIGate(self.q).initialize()
        self.repair=SceneRepair(self.q);self.repair.initialize()
        self.jobs={}

    def render(self,scene=1,stage="voice_synthesize",recipe=None,artifact=None):
        recipe=recipe or f"first_{stage}_{scene}"
        job=self.ledger.queue_stage("colors-ar",1,scene,stage,recipe)
        return self.finish(job,scene,stage,artifact)

    def finish(self,job,scene,stage,artifact=None):
        claimed=self.q.claim(worker_id="mac",capabilities=[stage])
        self.assertEqual(claimed["job_id"],job)
        artifact=artifact or (str(scene)+stage+job[:6]).encode("ascii")
        sha=hashlib.sha256(artifact).hexdigest()
        is_voice=stage=="voice_synthesize"
        self.q.complete(job_id=job,worker_id="mac",
            generation=claimed["generation"],result={
                "status":"VOICE_RENDERED_PENDING_QA" if is_voice
                  else "A2V_RENDERED_PENDING_QA",
                "artifact_sha256":sha,
                "artifact_type":"wav" if is_voice else "mp4",
                "artifact_bytes":len(artifact),
                "publication_approved":False})
        self.ledger.reconcile()
        with self.q._connection(write=True) as db:
            if is_voice:
                db.execute("""INSERT INTO studio_scene_voice_checks
                    VALUES (?,?,?,?,?,?,?,?)""",
                    ("colors-ar",1,scene,job,sha,"3"*64,
                     "TECH_PASS_OWNER_LISTENING_PENDING",self.q.clock()))
            else:
                voice=db.execute("""SELECT artifact_sha256 FROM
                    studio_scene_stages WHERE series_id='colors-ar'
                    AND ordinal=1 AND scene=?
                    AND stage='voice_synthesize'""",(scene,)).fetchone()
                db.execute("""INSERT INTO studio_scene_audio_checks
                    VALUES (?,?,?,?,?,?,?,?)""",
                    ("colors-ar",1,scene,job,"4"*64,
                     voice["artifact_sha256"],sha,
                     "TECH_COMPATIBLE_HUMAN_QA_REQUIRED"))
        self.jobs[(scene,stage)]=(job,sha)
        return job,sha

    def fail_ai(self,scene=1,stage="voice_synthesize"):
        job,sha=self.jobs[(scene,stage)]
        with self.q._connection(write=True) as db:
            source=db.execute("""SELECT scene_script_sha256 FROM
                studio_scene_stages WHERE series_id='colors-ar' AND ordinal=1
                AND scene=? AND stage=?""",(scene,stage)).fetchone()[0]
            db.execute("""INSERT INTO studio_scene_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,scene,stage,job,sha,source,
                 "a"*64,"b"*64,"c"*64,
                 "3"*64 if stage=="voice_synthesize" else "4"*64,
                 "provider_abc","provider_xyz",
                 "AI_SCENE_NEEDS_FIX",0.6,self.q.clock()))

    def plan(self,scene=1,stage="voice_synthesize",
             recipes=None,source=None,filename=None):
        path=self.root/(filename or "repair_plan.json")
        path.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"scene":scene,"stage":stage,
            "script_sha256":source or digest(self.scripts[scene-1]),
            "recipes":recipes or ["new_recipe_01","new_recipe_02"],
            "public_release_authorized":False
        }))
        return path

    def test_only_rejected_voice_repaired_other_approved_scene_untouched(self):
        first,old_sha=self.render()
        self.fail_ai()
        other,other_sha=self.render(scene=2)
        self.ledger.approve("colors-ar",1,2,"voice_synthesize",other_sha,
                            "Synthetic legacy scene 2 was accepted for test")
        pinned=self.repair.register_plan(self.plan())
        self.assertFalse(pinned["public_release_authorized"])
        state=self.repair.run_once()
        self.assertEqual(state["status"],"M31_BOUNDED_SCENE_REPAIR_QUEUED")
        self.assertEqual(state["repair_attempt"],1)
        self.assertTrue(state["retained_other_scenes"])
        self.assertEqual(state["previous_job_id"],first)
        new=self.q.get(state["new_job_id"])
        self.assertEqual(new["state"],"QUEUED")
        self.assertEqual(json.loads(new["payload"]),{
            "recipe_id":"new_recipe_01",
            "script_sha256":digest(self.scripts[0])})
        self.assertEqual(self.repair.run_once()["status"],
                         "M31_NO_ELIGIBLE_REPAIRS")
        with self.q._connection() as db:
            unrelated=db.execute("""SELECT job_id,state,artifact_sha256 FROM
                studio_scene_stages WHERE series_id='colors-ar' AND ordinal=1
                AND scene=2 AND stage='voice_synthesize'""").fetchone()
            self.assertEqual(tuple(unrelated),
                             (other,"QA_APPROVED",other_sha))
            old_job=db.execute("SELECT state FROM jobs WHERE job_id=?",
                               (first,)).fetchone()[0]
            self.assertEqual(old_job,"COMPLETED")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM studio_scene_repair_attempts").fetchone()[0],1)

    def test_two_repair_limit_and_reject_auto_third_replay(self):
        self.render()
        self.fail_ai()
        self.repair.register_plan(self.plan())
        first=self.repair.run_once()
        self.finish(first["new_job_id"],1,"voice_synthesize")
        self.fail_ai()
        second=self.repair.run_once()
        self.assertEqual(second["repair_attempt"],2)
        self.assertNotEqual(first["new_job_id"],second["new_job_id"])
        self.finish(second["new_job_id"],1,"voice_synthesize")
        self.fail_ai()
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")
        with self.q._connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM studio_scene_repair_attempts").fetchone()[0],2)

    def test_plan_requires_changed_recipe_and_remains_immutable(self):
        self.render()
        with self.assertRaises(RepairError):
            self.repair.register_plan(self.plan(recipes=[
                "first_voice_synthesize_1"],filename="original.json"))
        self.repair.register_plan(self.plan(filename="first.json"))
        with self.assertRaises(RepairError):
            self.repair.register_plan(self.plan(filename="second.json"))

    def test_only_signed_negative_current_ai_result_can_repair(self):
        self.render()
        self.repair.register_plan(self.plan())
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")
        self.fail_ai()
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_ai_reviews
                SET state='AI_SCENE_READY_PRIVATE_ONLY'""")
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")

    def test_paused_queue_or_inactive_series_cannot_dispatch(self):
        self.render();self.fail_ai();self.repair.register_plan(self.plan())
        self.q.set_paused(True)
        self.assertEqual(self.repair.run_once()["status"],"M31_PAUSED_NO_REPAIR")
        self.q.set_paused(False)
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_series SET state='PAUSED'
                WHERE series_id='colors-ar'""")
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")

    def test_voice_repair_refused_once_ltx_exists(self):
        self.render()
        self.fail_ai()
        self.repair.register_plan(self.plan())
        # Deliberately populate an existing dependent job in test DB.
        self.ledger.queue_stage("colors-ar",1,1,"ltx_animate",
                                "dependent_ltx_first")
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")

    def test_ltx_retry_keeps_current_accepted_voice(self):
        vjob,vsha=self.render()
        self.ledger.approve("colors-ar",1,1,"voice_synthesize",vsha,
                            "Original voice kept for the final LTX repair")
        old,old_sha=self.render(stage="ltx_animate")
        self.fail_ai(stage="ltx_animate")
        self.repair.register_plan(self.plan(stage="ltx_animate",recipes=[
            "corrected_ltx_variant_01"],filename="ltx_plan.json"))
        repair=self.repair.run_once()
        self.assertEqual(repair["stage"],"ltx_animate")
        self.assertEqual(repair["repair_attempt"],1)
        payload=json.loads(self.q.get(repair["new_job_id"])["payload"])
        self.assertEqual(payload["voice_sha256"],vsha)
        with self.q._connection() as db:
            voice=db.execute("""SELECT job_id,state,artifact_sha256 FROM
                studio_scene_stages WHERE series_id='colors-ar' AND ordinal=1
                AND scene=1 AND stage='voice_synthesize'""").fetchone()
        self.assertEqual(tuple(voice),(vjob,"QA_APPROVED",vsha))
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")

    def test_different_current_sha_or_mismatched_job_receipt_blocks(self):
        self.render();self.fail_ai();self.repair.register_plan(self.plan())
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_scenes SET script_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1 AND scene=1""",
                ("d"*64,))
        self.assertEqual(self.repair.run_once()["status"],"M31_NO_ELIGIBLE_REPAIRS")


if __name__=="__main__":
    unittest.main()
