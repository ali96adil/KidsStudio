"""M27 offline independent AI-final-QA ledger and M8/M25/M26 fences.

Synthetic reports are *not* observations by real AI, real rights proof, or
real video. These tests validate bindings and fail-closed transitions only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.agent_final_qa import AgentFinalQA
from kidsstudio.episode_quality import CHECKS
from kidsstudio.private_archive import archive
from kidsstudio.private_release import check_readiness
from kidsstudio.private_upload_policy import PrivateUploadPolicy
from kidsstudio.private_preview_review import PreviewReview
from kidsstudio.studio_quality_ledger import QualityLedger, QualityGateError, CRITERIA
from kidsstudio.series_manager import SeriesManager, SeriesError
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.youtube_private_upload import validate_plan


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AgentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m27-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Original colors","ar",[
            {"title":"Red","objective":"Child identifies red objects"}],activate=True)
        self.script=self.root/"source.txt"
        self.script.write_text("The red ball is red.",encoding="utf-8")
        self.master=self.root/"final.mp4"
        self.master.write_bytes(b"SYNTHETIC-NOT-A-REAL-VIDEO"*400)
        job=self.queue.enqueue(kind="episode_assemble",
            request_key="synthetic-final-ep01",payload={"recipe_id":"dummy"},max_attempts=1)
        leased=self.queue.claim(worker_id="mac",capabilities=["episode_assemble"])
        self.queue.complete(job_id=job["job_id"],worker_id="mac",
            generation=leased["generation"],result={
                "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                "artifact_sha256":sha(self.master),
                "artifact_type":"mp4","publication_approved":False,
                "artifact_bytes":self.master.stat().st_size})
        self.job=job["job_id"]
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='RENDERED_QA_PENDING',
                render_job_id=?,source_sha256=? WHERE series_id='colors-ar'
                AND ordinal=1""",(self.job,sha(self.script)))
        self.quality=QualityLedger(self.queue)
        self.quality.initialize()
        self.ai=AgentFinalQA(self.queue)
        self.ai.initialize()
        self.technical=self.root/"technical.json"
        self.technical.write_text(json.dumps({
            "schema_version":1,"status":"TECH_PASS_OWNER_REVIEW_PENDING",
            "media_sha256":sha(self.master),
            "expected_media_sha256":sha(self.master),
            "file_bytes":self.master.stat().st_size,
            "duration_seconds":15.0,"checks":{key:True for key in CHECKS},
            "subjective_checks_performed":False,
            "rights_verified":False,"publishing_approved":False}))
        self.quality.register_technical("colors-ar",1,self.technical)
        self.evidence=self.root/"observed.json"
        self.evidence.write_text(json.dumps({
            "schema_version":1,"media_sha256":sha(self.master),
            "script_sha256":sha(self.script),
            "transcript_sha256":"1"*64,"frames_manifest_sha256":"2"*64,
            "audio_analysis_sha256":"3"*64,
            "sampling_complete":True,
            "subjective_quality_verified":False,"publishing_approved":False
        }))
        self.rights=self.root/"rights.json"
        self.rights.write_text(json.dumps({
            "schema_version":1,"media_sha256":sha(self.master),
            "assets":[{"asset_sha256":"4"*64,
                "provenance_kind":"original_created","proof_sha256":"5"*64,
                "use_scope":"commercial_youtube_kids",
                "rights_status":"DOCUMENTED_NOT_LEGALLY_ADJUDICATED"}],
            "all_assets_accounted_for":True,"publishing_approved":False
        }))
        self.review=self.root/"ai_review.json"
        self.review_data={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "render_job_id":self.job,"media_sha256":sha(self.master),
            "script_sha256":sha(self.script),
            "observed_evidence_sha256":sha(self.evidence),
            "rights_catalogue_sha256":sha(self.rights),
            "reviewers":[{
                "role":role,"provider_id":provider,"model_id":provider+"-local",
                "evidence_sha256":sha(self.evidence),
                "criteria":{k:{"decision":"PASS",
                    "evidence":"Synthetic evidence statement for QA contract and bounded source "+k}
                    for k in sorted(fields)},
                "summary":"Synthetic independent assessment of the supplied media evidence",
                "release_approved":False,
            } for role,provider,fields in (
                ("pedagogy_language","provider_abc",(
                    "learning_objective","age_appropriate_pedagogy",
                    "language_pronunciation","accessibility_and_subtitles",
                    "originality_and_attribution")),
                ("visual_child_safety","provider_xyz",(
                    "character_consistency","lip_sync_and_motion",
                    "audio_mix","child_safety","full_episode_watch"))
            )],
            "publishing_approved":False
        }
        self.review.write_text(json.dumps(self.review_data))
        self.target=self.root/"archives"/"colors-ar"/"ep001"/"episode-m27-v01"
        self.archive_plan=self.root/"archive_plan.json"

    def register(self):
        return self.ai.register("colors-ar",1,review_bundle=self.review,
            observed_media_evidence=self.evidence,rights_catalogue=self.rights)

    def write_bundle(self):
        self.review.write_text(json.dumps(self.review_data))

    def prepare_archive(self):
        plan={"schema_version":1,"series_id":"colors-ar","episode_number":1,
            "archive_id":"episode-m27-v01",
            "private_root":str(self.root),"archive_root":str(self.root/"archives"),
            "items":[{"role":role,"path":str(file),"sha256":sha(file)}
                for role,file in (("episode_master",self.master),
                ("approved_script",self.script),("technical_qa",self.technical),
                ("agent_qa",self.review))]}
        self.archive_plan.write_text(json.dumps(plan))
        return archive(self.archive_plan)

    def finalize(self):
        result=self.register()
        self.assertEqual(result["status"],"AI_INTERNAL_READY_PRIVATE_ONLY")
        self.assertFalse(result["publishing_approved"])
        approved=self.series.finalize_ai_private("colors-ar",1)
        self.assertFalse(approved["public_release_authorized"])
        return approved

    def test_two_independent_reviews_allow_only_private_readiness(self):
        with self.assertRaises(SeriesError):
            self.series.finalize_ai_private("colors-ar",1)
        self.finalize()
        packet=self.prepare_archive()
        self.assertFalse(packet["publishing_approved"])
        ready=check_readiness(self.queue,self.target,
                             series_id="colors-ar",ordinal=1)
        self.assertEqual(ready["status"],"READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED")
        self.assertFalse(ready["owner_final_qa"])
        self.assertTrue(ready["ai_internal_review_approved"])
        self.assertFalse(ready["public_release_authorized"])
        self.assertFalse(ready["upload_performed"])
        plan={"schema_version":1,"series_id":"colors-ar","episode_number":1,
            "render_job_id":self.job,"master_sha256":sha(self.master),
            "target_channel_id":"UC"+"z"*22,
            "title":"Original educational colors","description":"Original studio video",
            "category_id":"27","made_for_kids":True,
            "contains_synthetic_media":False}
        readyfile=self.root/"readiness.json"
        readyfile.write_text(json.dumps(ready))
        gate=validate_plan(plan,self.master,readyfile,sha(readyfile))
        self.assertFalse(gate["video_uploaded"])
        PreviewReview(self.queue).initialize()
        policy=PrivateUploadPolicy(self.queue)
        policy.initialize()
        policy.grant("colors-ar",channel_id=plan["target_channel_id"],
            max_uploads_24h=1,made_for_kids=True,
            contains_synthetic_media=False,
            owner_note="I authorize PRIVATE one-per-day only; final owner video review later")
        request=policy.enqueue_private("colors-ar",1,render_job_id=self.job,
            master_sha256=sha(self.master),plan_sha256="a"*64,
            readiness_sha256=sha(readyfile),
            channel_id=plan["target_channel_id"],made_for_kids=True,
            contains_synthetic_media=False)
        self.assertEqual(request["status"],"PRIVATE_UPLOAD_QUEUED_NOT_RUN")
        self.assertFalse(request["public_release_authorized"])

    def test_same_provider_even_with_two_roles_fails(self):
        self.review_data["reviewers"][1]["provider_id"]="provider_abc"
        self.write_bundle()
        with self.assertRaises(QualityGateError):
            self.register()

    def test_unverified_rights_missing_or_wrong_scope_fails(self):
        record=json.loads(self.rights.read_text())
        record["assets"][0]["use_scope"]="internal_only"
        self.rights.write_text(json.dumps(record))
        self.review_data["rights_catalogue_sha256"]=sha(self.rights)
        self.write_bundle()
        with self.assertRaises(QualityGateError):
            self.register()

    def test_failed_criteria_records_triage_and_blocks_private(self):
        self.review_data["reviewers"][0]["criteria"]["learning_objective"]["decision"]="UNSURE"
        self.write_bundle()
        result=self.register()
        self.assertEqual(result["status"],"AI_INTERNAL_CHANGES_REQUIRED")
        with self.assertRaises(SeriesError):
            self.series.finalize_ai_private("colors-ar",1)
        with self.queue._connection() as db:
            notes=db.execute("""SELECT note FROM studio_series_notes WHERE
                series_id='colors-ar' AND ordinal=1""").fetchall()
        self.assertIn("learning_objective",notes[0]["note"])

    def test_source_hash_drift_rejected(self):
        self.review_data["media_sha256"]="0"*64
        self.write_bundle()
        with self.assertRaises(QualityGateError):
            self.register()

    def test_duplicate_review_cannot_overwrite_or_upgrade(self):
        self.register()
        with self.assertRaises(QualityGateError):
            self.register()

    def test_missing_sampling_evidence_fails(self):
        item=json.loads(self.evidence.read_text())
        item["sampling_complete"]=False
        self.evidence.write_text(json.dumps(item))
        self.review_data["observed_evidence_sha256"]=sha(self.evidence)
        for r in self.review_data["reviewers"]:
            r["evidence_sha256"]=sha(self.evidence)
        self.write_bundle()
        with self.assertRaises(QualityGateError):
            self.register()

    def test_archive_owner_qa_not_substitute_for_agent_qa(self):
        self.finalize()
        self.prepare_archive()
        # Archive cannot be swapped to a different content digest/role.
        manifest=self.target/"archive_manifest.json"
        data=json.loads(manifest.read_text())
        for item in data["files"]:
            if item["role"]=="agent_qa":
                item["role"]="owner_qa"
        manifest.write_text(json.dumps(data))
        from kidsstudio.private_release import PrivateReleaseError
        with self.assertRaises(PrivateReleaseError):
            check_readiness(self.queue,self.target,
                            series_id="colors-ar",ordinal=1)


if __name__=="__main__":
    unittest.main()
