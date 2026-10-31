"""M30 two real model-routing calls tested offline with independent fake adapters.

Fixtures are explicitly not live LLM inference or legal clearance.
Tests verify stable current Studio Brain draft and review lineage,
fail-closed two-provider diversity and no Public authorization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.studio_scenes import SceneLedger,SceneError
from kidsstudio.script_ai_quality import ScriptAIQuality, ScriptReviewError, CRITERIA


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class FakeModels:
    def __init__(self,verdict="PASS",same=False):
        self.verdict=verdict;self.same=same;self.calls=[]
    def complete(self,**kwargs):
        self.calls.append(kwargs)
        excluded=kwargs.get("exclude_providers",set())
        provider=("model_beta" if self.same or "model_beta" not in excluded
                  else "model_gamma")
        content={"criteria":{key:{
            "decision":self.verdict,
            "evidence":"Synthetic-only model response to test the evidence contract: "+key
        } for key in CRITERIA},
        "summary":"This is a test double, not actual child-learning or originality assessment."}
        return {"provider_id":provider,"model":provider+"-synthetic-model",
                "answer":json.dumps(content)}


class ScriptAIQualityTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m30-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.queue=StudioQueue(self.root/"pi.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.objective="Learn the difference between red and blue objects"
        self.series.create_series("colors-ar","Colors","ar",
            [{"title":"Red and blue","objective":self.objective}],activate=True)
        draft=self.queue.enqueue(kind="script_draft",request_key="draft_m30",
            payload={"topic":"Original colors in Iraq","language":"ar",
                     "auto_review":True})
        self.draft_job=draft["job_id"]
        review=self.queue.enqueue(kind="editorial_review",request_key="review_m30",
            payload={"source_job_id":self.draft_job,
                     "original_provider_id":"original_writer",
                     "source_answer_sha256":"0"*64,"language":"ar"})
        self.review_job=review["job_id"]
        self.artifacts=self.root/"private_artifacts"
        attempt=self.artifacts/self.draft_job/"attempt_001"
        attempt.mkdir(parents=True)
        self.script=("المعلم يرفع الكرة الحمراء ثم يشرح اللون الأحمر. "
                     "تسأل الطفلة عن الكرة الزرقاء ويميزان اللونين. "
                     "تكرر الشخصيتان المثال بأشياء أصلية من الصف "
                     "ثم تطلبان من الطفل أن يختار لون الكرة الصحيح.")
        (attempt/"answer.txt").write_text(self.script,encoding="utf-8")
        (attempt/"result.json").write_text("{}")
        self.script_sha=sha(attempt/"answer.txt")
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE jobs SET state='COMPLETED',result_json=?
                WHERE job_id=?""",(json.dumps({
                "status":"DRAFTED_UNREVIEWED","provider_id":"original_writer",
                "artifact_sha256":self.script_sha,
                "artifact_manifest":str(attempt/"result.json"),
                "publication_approved":False,
                "next_review_job_id":self.review_job}),self.draft_job))
            db.execute("""UPDATE jobs SET state='COMPLETED',payload=?,result_json=?
                WHERE job_id=?""",(json.dumps({
                "source_job_id":self.draft_job,
                "original_provider_id":"original_writer",
                "source_answer_sha256":self.script_sha,
                "language":"ar"}),json.dumps({
                "status":"EDITORIAL_REVIEW_UNVERIFIED",
                "provider_id":"first_editor",
                "publication_approved":False}),self.review_job))
            db.execute("""UPDATE studio_episodes SET
                state='OWNER_SCRIPT_REVIEW',source_sha256=?,
                draft_job_id=?,review_job_id=? WHERE series_id='colors-ar'
                AND ordinal=1""",
                (self.script_sha,self.draft_job,self.review_job))
        self.models=FakeModels()
        self.gate=ScriptAIQuality(self.queue,self.models,self.root)
        self.gate.initialize()

    def evaluate(self):
        return self.gate.evaluate("colors-ar",1,language="ar",
                                  objective=self.objective)

    def test_two_model_reviewer_approves_script_for_private_internal_only(self):
        result=self.evaluate()
        self.assertEqual(result["status"],"AI_SCRIPT_PRIVATE_READY")
        self.assertEqual(result["independent_model_calls"],2)
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(len(self.models.calls),2)
        self.assertEqual(self.models.calls[0]["exclude_providers"],
                         {"original_writer"})
        self.assertIn("model_beta",self.models.calls[1]["exclude_providers"])
        with self.queue._connection() as db:
            ep=db.execute("""SELECT state,owner_review_note FROM
                studio_episodes WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
            self.assertEqual(ep["state"],"SCRIPT_APPROVED")
            self.assertIn("AI_INTERNAL_PRIVATE_ONLY",ep["owner_review_note"])
            self.assertIsNone(db.execute("""SELECT 1 FROM studio_series_audit
                WHERE action='SCRIPT_APPROVED_BY_OWNER'""").fetchone())
            ai=db.execute("SELECT * FROM studio_script_ai_reviews").fetchone()
            self.assertEqual(ai["first_provider"],"model_beta")
            self.assertEqual(ai["second_provider"],"model_gamma")
            self.assertEqual(ai["verdict"],"AI_SCRIPT_PRIVATE_READY")
        with self.assertRaises(ScriptReviewError):
            self.evaluate()

    def test_current_ai_script_unlocks_only_pinned_two_scene_pilot(self):
        self.evaluate()
        scenes=SceneLedger(self.queue)
        scenes.initialize()
        plan=self.root/"two_scene_plan.json"
        plan.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "episode_script_sha256":self.script_sha,
            "scenes":[
                {"scene":1,"script_sha256":"a"*64,
                 "objective":"Recognize the red ball"},
                {"scene":2,"script_sha256":"b"*64,
                 "objective":"Recognize a blue ball"}]
        }))
        registered=scenes.register_plan(plan)
        self.assertEqual(registered["scene_count"],2)
        with self.queue._connection() as db:
            self.assertIsNone(db.execute("""SELECT 1 FROM studio_series_audit
                WHERE action='SCRIPT_APPROVED_BY_OWNER'""").fetchone())
        pilot=scenes.queue_first_voice_ai(
            "colors-ar",1,"first_synthetic_voice",
            registered["plan_sha256"])
        self.assertEqual(len(pilot),32)
        with self.assertRaises(SceneError):
            scenes.queue_first_voice_ai("colors-ar",1,"other_recipe",
                 registered["plan_sha256"])

    def test_second_reviewer_must_not_be_same_provider(self):
        self.models=FakeModels(same=True)
        self.gate.router=self.models
        with self.assertRaises(ScriptReviewError):
            self.evaluate()
        with self.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()[0],
                "OWNER_SCRIPT_REVIEW")

    def test_unsure_or_needs_fix_records_note_without_approval(self):
        self.models=FakeModels(verdict="UNSURE")
        self.gate.router=self.models
        report=self.evaluate()
        self.assertEqual(report["status"],"AI_SCRIPT_REQUIRES_REVISION")
        self.assertEqual(len(self.models.calls),2)
        with self.queue._connection() as db:
            state=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()[0]
            note=db.execute("""SELECT note FROM studio_series_notes
                WHERE series_id='colors-ar' ORDER BY note_id DESC LIMIT 1""").fetchone()[0]
        self.assertEqual(state,"OWNER_SCRIPT_REVIEW")
        self.assertIn("M30 AI script needs revision",note)
        with self.assertRaises(ScriptReviewError):
            self.evaluate()

    def test_changed_draft_or_source_sha_fails_before_model_call(self):
        file=self.artifacts/self.draft_job/"attempt_001"/"answer.txt"
        file.write_text("changed screenplay")
        with self.assertRaises(ScriptReviewError):
            self.evaluate()
        self.assertEqual(self.models.calls,[])

    def test_missing_source_editorial_link_fails(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE jobs SET result_json=? WHERE job_id=?""",
                (json.dumps({"status":"EDITORIAL_REVIEW_UNVERIFIED",
                    "provider_id":"original_writer",
                    "publication_approved":False}),self.review_job))
        with self.assertRaises(ScriptReviewError):
            self.evaluate()
        self.assertEqual(self.models.calls,[])

    def test_script_objective_cannot_be_replaced(self):
        with self.assertRaises(ScriptReviewError):
            self.gate.evaluate("colors-ar",1,language="ar",
                objective="Choose shapes not the approved objective")
        self.assertEqual(self.models.calls,[])


if __name__=="__main__":
    unittest.main()
