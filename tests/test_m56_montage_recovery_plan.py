"""M56 synthetic candidate selection and immutable new-attempt proposal.

No Pi queue, real inference, owner media, network or publication.
Unit tests inject synthetic QA results; production defaults to real M7
FFprobe and FFmpeg full decode before a candidate may be recommended.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

from kidsstudio.episode_assembly import EpisodeAssembler, EpisodeAssemblyError
from kidsstudio.episode_quality import CHECKS
from kidsstudio.media_worker import MediaJournal, MediaRecipes
from kidsstudio.montage_recovery import (
    RecoveryJournal, freeze_recovery_inspection
)
from kidsstudio.montage_recovery_plan import (
    RecoveryPlanError, plan_private_montage_recovery,
    freeze_private_montage_recovery
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class M56RecoveryPlanTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m56-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.old_id="1"*32
        self.proposal_id="2"*32
        self.script=self.root/"script.txt"
        self.script.write_text("Learn red and blue from two synthetic scenes")
        self.media=[]
        for i in (1,2):
            file=self.root/f"source_{i}.mp4"
            file.write_bytes((f"local synthetic original scene {i}").encode()*8)
            self.media.append(file)
        self.face=self.root/"face.py"
        self.face.write_text("# fake face adapter\n")
        self.recipe_path=self.root/"assembly_recipe.json"
        self.recipe={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.root),
            "output_root":str(self.root/"rendered"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(self.script),"sha256":sha(self.script)},
            "tools":{"ffmpeg":sys.executable,"ffprobe":sys.executable,
                     "face_python":sys.executable,
                     "face_v06":str(self.face),"face_v06_sha256":sha(self.face),
                     "face_v07":str(self.face),"face_v07_sha256":sha(self.face)},
            "clips":[{"video":str(f),"sha256":sha(f),"face_cleanup":"none"}
                      for f in self.media],
        }
        self.recipe_path.write_text(json.dumps(self.recipe))
        self.catalogue=self.root/"media_catalogue.json"
        self.catalogue.write_text(json.dumps({
            "schema_version":1,
            "recipes":{"assembly_one":{
                "kind":"episode_assemble",
                "output_root":str(self.root/"rendered"),
                "inputs":{"episode_recipe":str(self.recipe_path)},
                "sha256":{"episode_recipe":sha(self.recipe_path)}
            }}}))
        self.recipes=MediaRecipes(self.catalogue)
        self.payload={"recipe_id":"assembly_one",
                      "script_sha256":sha(self.script)}
        self.journal=MediaJournal(self.root/"journal.sqlite")
        request_sha=hashlib.sha256(json.dumps(
            {"kind":"episode_assemble","payload":self.payload},
            sort_keys=True).encode("utf-8")).hexdigest()
        self.journal.begin(self.old_id,request_sha,
                           "episode_assemble","assembly_one")
        self.cancel=threading.Event()
        def fake_runner(args,*,timeout=1200):
            Path(args[-1]).write_bytes(
                (b"synthetic nonreal MP4 normalized first scene"*10))
            self.cancel.set()
        assembler=EpisodeAssembler(self.recipe_path,
            runner=fake_runner,prober=self.fake_prober)
        with self.assertRaises(EpisodeAssemblyError):
            assembler.execute(run_id=self.old_id,abort_event=self.cancel)
        self.report=freeze_recovery_inspection(
            self.recipes,self.journal,job_id=self.old_id,
            payload=self.payload,prober=self.fake_prober)
        self.frozen_file=self.root/"rendered"/"_recovery_evidence"/(
            self.old_id+".json")
        self.locator=RecoveryJournal(self.journal.path)
        self.qa_calls=[]

    @staticmethod
    def fake_prober(file,exe):
        name=Path(file).name
        valid=("_normalized" in name or "master" in name)
        return {"width":1280 if valid else 384,
                "height":720 if valid else 384,
                "duration":2.5,"audio_streams":1}

    def tech_pass(self,path,expected):
        self.qa_calls.append((Path(path).name,expected))
        return {
            "status":"TECH_PASS_OWNER_REVIEW_PENDING",
            "media_sha256":expected,
            "expected_media_sha256":expected,
            "checks":{key:True for key in CHECKS},
            "publishing_approved":False,
            "rights_verified":False,
            "subjective_checks_performed":False
        }

    def make(self,**kwargs):
        return plan_private_montage_recovery(
            self.recipes,self.locator,original_job_id=self.old_id,
            payload=self.payload,proposal_id=self.proposal_id,
            prober=self.fake_prober,full_qa=self.tech_pass,**kwargs)

    def test_m56_one_scene_reuse_other_scene_pinned_original(self):
        prior=sha(self.journal.path)
        p=self.make()
        self.assertEqual(p["status"],"M56_FRESH_ATTEMPT_PROPOSED_NOT_QUEUED")
        self.assertEqual(p["verified_normalized_candidates"],1)
        self.assertEqual(p["original_scene_fallback_count"],1)
        self.assertEqual(p["scenes"][0]["strategy"],
            "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS")
        self.assertEqual(p["scenes"][1]["strategy"],
            "USE_ORIGINAL_APPROVED_LTX_SOURCE")
        self.assertEqual(p["scenes"][1]["candidate_sha256"],sha(self.media[1]))
        self.assertEqual(len(self.qa_calls),1)
        self.assertIsNone(p["proposed_pi_job_id"])
        self.assertIs(p["auto_execute_allowed"],False)
        self.assertIs(p["auto_reuse_allowed"],False)
        self.assertIs(p["public_release_authorized"],False)
        self.assertEqual(sha(self.journal.path),prior)
        self.assertFalse((self.root/"rendered"/"_recovery_proposals").exists())
        self.assertFalse((self.root/"rendered"/self.proposal_id).exists())

    def test_m56_failed_full_decode_proposes_original_not_recovered(self):
        def failed(path,digest):
            result=self.tech_pass(path,digest)
            result["checks"]["full_decode_success"]=False
            result["status"]="TECH_FAILED"
            return result
        p=plan_private_montage_recovery(
            self.recipes,self.locator,original_job_id=self.old_id,
            payload=self.payload,proposal_id=self.proposal_id,
            prober=self.fake_prober,full_qa=failed)
        self.assertEqual(p["verified_normalized_candidates"],0)
        self.assertEqual(p["original_scene_fallback_count"],2)
        self.assertEqual(p["scenes"][0]["candidate_technical_status"],
                         "RECOVERED_CANDIDATE_FAILED_M7_USE_ORIGINAL")

    def test_m56_frozen_plan_is_immutable_no_render_or_queue(self):
        r=freeze_private_montage_recovery(
            self.recipes,self.locator,original_job_id=self.old_id,
            payload=self.payload,proposal_id=self.proposal_id,
            prober=self.fake_prober,full_qa=self.tech_pass)
        self.assertEqual(r["status"],
                         "M56_PRIVATE_PROPOSAL_FROZEN_NO_JOB_QUEUED")
        file=self.root/"rendered"/"_recovery_proposals"/(
            self.proposal_id+".json")
        self.assertTrue(file.is_file())
        envelope=json.loads(file.read_text())
        expected=hashlib.sha256(json.dumps(envelope["proposal"],
            ensure_ascii=False,sort_keys=True,
            separators=(",",":"),allow_nan=False).encode()).hexdigest()
        self.assertEqual(envelope["proposal_sha256"],expected)
        self.assertEqual(envelope["proposal"]["verified_normalized_candidates"],1)
        with self.assertRaises(RecoveryPlanError):
            freeze_private_montage_recovery(
                self.recipes,self.locator,original_job_id=self.old_id,
                payload=self.payload,proposal_id=self.proposal_id,
                prober=self.fake_prober,full_qa=self.tech_pass)
        self.assertFalse((self.root/"rendered"/self.proposal_id).exists())

    def test_m56_stale_m55_snapshot_or_changed_candidate_never_reused(self):
        candidate=self.root/"rendered"/self.old_id/"001_normalized.mp4"
        candidate.write_bytes(candidate.read_bytes()+b"tampered")
        with self.assertRaises(RecoveryPlanError):
            self.make()
        self.assertEqual(self.qa_calls,[])

    def test_m56_missing_or_modified_frozen_inspection_fails_closed(self):
        self.frozen_file.unlink()
        with self.assertRaises(RecoveryPlanError):
            self.make()
        self.assertFalse((self.root/"rendered"/"_recovery_proposals").exists())

    def test_m56_forged_snapshot_digest_fails_closed(self):
        data=json.loads(self.frozen_file.read_text())
        data["report"]["scene_count"]=100
        self.frozen_file.write_text(json.dumps(data))
        with self.assertRaises(RecoveryPlanError):
            self.make()

    def test_m56_wrong_original_journal_attempt_and_identity_fail(self):
        self.journal.done(self.old_id,{"status":"synthetic_done"})
        with self.assertRaises(RecoveryPlanError):
            self.make()
        with self.assertRaises(RecoveryPlanError):
            plan_private_montage_recovery(
                self.recipes,self.locator,original_job_id=self.old_id,
                payload=self.payload,proposal_id=self.old_id,
                prober=self.fake_prober,full_qa=self.tech_pass)

    def test_m56_unknown_extra_file_needs_manual_triage(self):
        folder=self.root/"rendered"/self.old_id
        (folder/"unexpected.txt").write_text("surprise")
        # M55 is now stale; no proposal from a changed directory.
        with self.assertRaises(RecoveryPlanError):
            self.make()

    def test_m56_qa_claim_needs_every_check_and_negative_publish_flags(self):
        def dishonest(path,digest):
            report=self.tech_pass(path,digest)
            report["publishing_approved"]=True
            return report
        plan=plan_private_montage_recovery(
            self.recipes,self.locator,original_job_id=self.old_id,
            payload=self.payload,proposal_id=self.proposal_id,
            prober=self.fake_prober,full_qa=dishonest)
        self.assertEqual(plan["verified_normalized_candidates"],0)
        self.assertEqual(plan["original_scene_fallback_count"],2)


if __name__=="__main__":
    unittest.main()
