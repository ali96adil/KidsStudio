"""M55 private synthetic recovery inspection; never dispatch or publish."""
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
from kidsstudio.media_worker import MediaJournal, MediaRecipes
from kidsstudio.montage_recovery import (
    RecoveryError, RecoveryJournal, inspect_quarantined_montage,
    freeze_recovery_inspection,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class M55RecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m55-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.job_id="3"*32
        self.script=self.root/"script.txt"
        self.script.write_text("Colors education: synthetic approved scene")
        self.video=self.root/"original.mp4"
        self.video.write_bytes(b"synthetic-source-asset"*50)
        self.face=self.root/"face.py"
        self.face.write_text("# dummy; never executed\n")
        self.recipe_path=self.root/"episode.json"
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
            "clips":[{"video":str(self.video),"sha256":sha(self.video),
                      "face_cleanup":"none"}],
        }
        self.recipe_path.write_text(json.dumps(self.recipe))
        self.catalogue=self.root/"catalogue.json"
        self.catalogue.write_text(json.dumps({
            "schema_version":1,
            "recipes":{"approved_montage":{
                "kind":"episode_assemble","output_root":str(self.root/"rendered"),
                "inputs":{"episode_recipe":str(self.recipe_path)},
                "sha256":{"episode_recipe":sha(self.recipe_path)}
            }}
        }))
        self.recipes=MediaRecipes(self.catalogue)
        self.payload={"recipe_id":"approved_montage",
                      "script_sha256":sha(self.script)}
        self.journal=MediaJournal(self.root/"journal.sqlite")
        request_sha=hashlib.sha256(json.dumps(
            {"kind":"episode_assemble","payload":self.payload},
            sort_keys=True).encode("utf-8")).hexdigest()
        state,_=self.journal.begin(self.job_id,request_sha,
                                   "episode_assemble","approved_montage")
        self.assertEqual(state,"NEW")
        abort=threading.Event()
        def fake_runner(args,*,timeout=1200):
            Path(args[-1]).write_bytes(b"synthetic partial, not real video")
            abort.set()
        self.assembler=EpisodeAssembler(self.recipe_path,
            runner=fake_runner,prober=self.fake_probe)
        with self.assertRaises(EpisodeAssemblyError):
            self.assembler.execute(run_id=self.job_id,abort_event=abort)
        self.run_dir=self.root/"rendered"/self.job_id
        self.report_path=self.run_dir/"qa_report.json"
        self.original_hash=sha(self.video)

    @staticmethod
    def fake_probe(path,executable):
        name=Path(path).name
        return {"width":1280 if "_normalized" in name or "master" in name
                else 384,
                "height":720 if "_normalized" in name or "master" in name
                else 384,
                "duration":1.5,"audio_streams":1}

    def inspect(self):
        return inspect_quarantined_montage(
            self.recipes,self.journal,job_id=self.job_id,
            payload=self.payload,prober=self.fake_probe)

    def test_m55_exact_started_journal_partial_is_only_a_candidate(self):
        report=self.inspect()
        self.assertEqual(report["status"],"M55_QUARANTINED_INSPECTION_ONLY")
        self.assertEqual(report["normalized_candidate_count"],1)
        self.assertEqual(report["manifest_state"],
                         "FAILED_REQUIRES_MANUAL_RECONCILIATION")
        self.assertEqual(report["artifacts"][0]["status"],
                         "NORMALIZED_CANDIDATE_NOT_APPROVED_FOR_REUSE")
        self.assertIs(report["auto_reuse_allowed"],False)
        self.assertIs(report["auto_retry_allowed"],False)
        self.assertIs(report["public_release_authorized"],False)
        self.assertEqual(sha(self.video),self.original_hash)
        self.assertEqual(json.loads(self.report_path.read_text())["status"],
                         "FAILED_REQUIRES_MANUAL_RECONCILIATION")

    def test_m55_freezes_exact_report_without_changing_journal_or_sources(self):
        before=sha(self.journal.path)
        frozen=freeze_recovery_inspection(self.recipes,self.journal,
            job_id=self.job_id,payload=self.payload,prober=self.fake_probe)
        self.assertEqual(frozen["status"],
                         "M55_INSPECTION_EVIDENCE_FROZEN_NO_ACTUATION")
        self.assertFalse(frozen["auto_reuse_allowed"])
        file=self.root/"rendered"/"_recovery_evidence"/(self.job_id+".json")
        self.assertTrue(file.is_file())
        envelope=json.loads(file.read_text())
        assert_sha=hashlib.sha256(json.dumps(envelope["report"],
            ensure_ascii=False,sort_keys=True,
            separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(envelope["report_sha256"],assert_sha)
        with self.assertRaisesRegex(RecoveryError,"already frozen"):
            freeze_recovery_inspection(self.recipes,self.journal,
                job_id=self.job_id,payload=self.payload,prober=self.fake_probe)
        self.assertEqual(sha(self.journal.path),before)
        self.assertEqual(sha(self.video),self.original_hash)

    def test_m55_rejects_wrong_payload_and_completed_or_missing_attempt(self):
        wrong=dict(self.payload)
        wrong["script_sha256"]="a"*64
        with self.assertRaises(RecoveryError):
            inspect_quarantined_montage(self.recipes,self.journal,
                job_id=self.job_id,payload=wrong,prober=self.fake_probe)
        with self.assertRaises(RecoveryError):
            inspect_quarantined_montage(self.recipes,self.journal,
                job_id="4"*32,payload=self.payload,prober=self.fake_probe)
        self.journal.done(self.job_id,{"status":"fake"})
        with self.assertRaises(RecoveryError):
            self.inspect()

    def test_m55_rejects_changed_original_or_recipe_report(self):
        self.script.write_text("Tampered script")
        with self.assertRaises(RecoveryError):
            self.inspect()
        self.script.write_text("Colors education: synthetic approved scene")
        changed=json.loads(self.report_path.read_text())
        changed["recipe_sha256"]="b"*64
        self.report_path.write_text(json.dumps(changed))
        with self.assertRaises(RecoveryError):
            self.inspect()

    def test_m55_rejects_symlink_and_untrusted_render_directory_entry(self):
        extra=self.run_dir/"link.mp4"
        extra.symlink_to(self.video)
        with self.assertRaisesRegex(RecoveryError,"symlink"):
            self.inspect()
        extra.unlink()
        (self.run_dir/"unexpected.bin").write_bytes(b"no approval")
        report=self.inspect()
        self.assertIn("UNEXPECTED_FILE_REQUIRES_REVIEW",report["warnings"])
        self.assertFalse(report["auto_reuse_allowed"])

    def test_m55_unprobeable_or_incomplete_master_never_auto_approved(self):
        master=self.run_dir/"episode_qa_master.mp4"
        master.write_bytes(b"incomplete mp4 data"*20)
        def fake_bad_probe(path,executable):
            if Path(path).name=="episode_qa_master.mp4":
                raise EpisodeAssemblyError("corrupt mp4")
            return self.fake_probe(path,executable)
        report=inspect_quarantined_montage(
            self.recipes,self.journal,job_id=self.job_id,
            payload=self.payload,prober=fake_bad_probe)
        self.assertIn("UNPROBEABLE_NOT_REUSABLE",
                      [x["status"] for x in report["artifacts"]])
        self.assertIs(report["auto_reuse_allowed"],False)
        self.assertIs(report["public_release_authorized"],False)

    def test_m55_read_only_locator_does_not_create_journal(self):
        nonexistent=self.root/"does_not_exist.sqlite"
        locator=RecoveryJournal(nonexistent)
        with self.assertRaises(RecoveryError):
            inspect_quarantined_montage(
                self.recipes,locator,job_id=self.job_id,
                payload=self.payload,prober=self.fake_probe)
        self.assertFalse(nonexistent.exists())


if __name__=="__main__":
    unittest.main()
