"""M41 sharded model packages: rehash every member, reject added files.

Tests use real local files, FFmpeg MP4+WAV and a MOCK AV adapter.
They are not proof of AI competence, training, rights or Mac/Pi readiness.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from kidsstudio.model_package import (
    ModelPackageError, PACKAGE_FORMAT, checkpoint_digest, verify_checkpoint,
    freeze_model_directory, main as package_main
)
from kidsstudio.model_runtime_bundle import LocalModelBundle, ModelBundleError
from kidsstudio.synchronized_av_review import AVRunner
from kidsstudio.real_media_evidence import digest
from test_model_runtime_bundle_m40 import PrivateModelBundle40
from test_local_audio_review_m34 import executable


class ShardedCheckpoint41(unittest.TestCase):
    def setUp(self):
        h=PrivateModelBundle40(
            "test_pin_real_binaries_and_five_roles_but_never_claim_model_quality")
        h.setUp();self.addCleanup(h.doCleanups)
        self.h=h
        self.root=h.root
        self.dir=h.models/"av_multifile"
        self.dir.mkdir()
        self.weights=self.dir/"weights-00001.safetensors"
        self.weights.write_bytes(b"SYNTHETIC MULTI FILE MODEL WEIGHTS "*10)
        self.settings=self.dir/"config.json"
        self.settings.write_text('{"architecture": "not-a-real-ai"}')
        self.package=self.dir/"model_files.json"
        self.items=[
            {"path":str(p.relative_to(self.dir)),
             "sha256":digest(p),"bytes":p.stat().st_size}
            for p in (self.weights,self.settings)
        ]
        self.doc={"schema_version":1,"format":PACKAGE_FORMAT,
                  "files":self.items,"inference_qualified":False,
                  "public_release_authorized":False}
        self.save()

    def save(self):
        self.package.write_text(json.dumps(self.doc,sort_keys=True))
        return digest(self.package)

    def enabled_bundle(self):
        cfg=copy.deepcopy(self.h.config)
        cfg["reviewers"]["av_motion_sync"]["model"]=str(self.dir)
        cfg["reviewers"]["av_motion_sync"]["model_sha256"]=digest(self.package)
        self.h.file.write_text(json.dumps(cfg))
        return LocalModelBundle(self.h.file,digest(self.h.file))

    def test_freeze_is_readonly_by_default_and_exclusive_when_authorized(self):
        self.package.unlink()
        dry=freeze_model_directory(self.dir)
        self.assertEqual(dry["status"],"M41_PACKAGE_PREPARED_NOT_WRITTEN")
        self.assertEqual(dry["member_count"],2)
        self.assertFalse((self.dir/"model_files.json").exists())
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,dry["package_sha256"])
        actual=freeze_model_directory(self.dir,execute=True)
        self.assertEqual(actual["status"],
                         "M41_IMMUTABLE_PACKAGE_MANIFEST_CREATED")
        self.assertTrue(actual["write_performed"])
        self.assertEqual(actual["package_sha256"],dry["package_sha256"])
        self.assertEqual(checkpoint_digest(self.dir),dry["package_sha256"])
        with self.assertRaises(ModelPackageError):
            freeze_model_directory(self.dir,execute=True)

    def test_freeze_rejects_unapproved_script_and_hidden_files(self):
        self.package.unlink()
        script=self.dir/"remote_code.py"
        script.write_text("raise RuntimeError('never execute this')")
        with self.assertRaises(ModelPackageError):
            freeze_model_directory(self.dir,execute=True)
        script.unlink()
        hidden=self.dir/".secret.json"
        hidden.write_text('{"api_key":"synthetic"}')
        with self.assertRaises(ModelPackageError):
            freeze_model_directory(self.dir,execute=True)
        self.assertFalse(self.package.exists())

    def test_freeze_cli_without_execute_never_writes_a_manifest(self):
        self.package.unlink()
        self.assertEqual(package_main(["--directory",str(self.dir)]),0)
        self.assertFalse(self.package.exists())
        self.assertEqual(package_main(
            ["--directory",str(self.dir),"--execute"]),0)
        self.assertTrue(self.package.exists())

    def test_approved_package_and_runtime_preflight_rehash_real_members(self):
        value=digest(self.package)
        self.assertEqual(verify_checkpoint(self.dir,value),self.dir)
        self.assertEqual(checkpoint_digest(self.dir),value)
        b=self.enabled_bundle()
        self.assertEqual(b.reviewers["av_motion_sync"]["model"],str(self.dir))
        self.assertEqual(b.reviewers["av_motion_sync"]["model_sha256"],value)
        self.assertFalse(b.public_status()["model_capabilities_verified"])
        self.assertFalse(b.public_status()["public_release_authorized"])

    def test_added_or_deleted_files_fail_even_if_package_manifest_unchanged(self):
        value=digest(self.package)
        extra=self.dir/"unlisted.json"
        extra.write_text('{"secret": "no"}')
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,value)
        with self.assertRaises(ModelPackageError):
            checkpoint_digest(self.dir)
        extra.unlink()
        self.weights.unlink()
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,value)

    def test_changed_shard_fails_even_if_manifest_hash_is_correct(self):
        original_sha=digest(self.package)
        self.weights.write_bytes(b"SYNTHETIC MODIFIED FILE CONTENT "*12)
        self.assertEqual(digest(self.package),original_sha)
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,original_sha)
        with self.assertRaises(ModelBundleError):
            self.enabled_bundle()

    def test_symlink_escape_and_unlisted_symlink_are_blocked(self):
        original=digest(self.package)
        link=self.dir/"foreign.json"
        link.symlink_to(self.settings)
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,original)
        link.unlink()
        self.settings.unlink()
        self.settings.symlink_to(self.weights)
        with self.assertRaises(ModelPackageError):
            verify_checkpoint(self.dir,original)

    def test_relative_path_traversal_and_uncertified_manifest_rejected(self):
        original=digest(self.package)
        for bad in ("../config.json","/tmp/evil.bin",
                    "nested/../../config.json",".git/config","config.py",
                    "config//extra.json"):
            with self.subTest(bad=bad):
                cfg=copy.deepcopy(self.doc)
                cfg["files"][1]["path"]=bad
                self.package.write_text(json.dumps(cfg))
                with self.assertRaises(ModelPackageError):
                    verify_checkpoint(self.dir,digest(self.package))
        for value in (True,"yes"):
            cfg=copy.deepcopy(self.doc)
            cfg["inference_qualified"]=value
            self.package.write_text(json.dumps(cfg))
            with self.assertRaises(ModelPackageError):
                verify_checkpoint(self.dir,digest(self.package))
        self.assertNotEqual(digest(self.package),original)
        self.save()

    def test_whisper_cpp_cannot_be_replaced_with_a_directory(self):
        cfg=copy.deepcopy(self.h.config)
        cfg["reviewers"]["asr_whispercpp"]["model"]=str(self.dir)
        cfg["reviewers"]["asr_whispercpp"]["model_sha256"]=digest(self.package)
        self.h.file.write_text(json.dumps(cfg))
        with self.assertRaises(ModelBundleError):
            LocalModelBundle(self.h.file,digest(self.h.file))

    def test_package_adapter_accepts_model_directory_with_real_mp4_and_mock_av(self):
        # The mock binary receives a real model directory and calculates
        # the exact package manifest SHA; no actual visual AI ran.
        script=(
            "import argparse,json,hashlib,os\nfrom pathlib import Path\n"
            "assert 'KIDS_STUDIO_SCENE_QA_RUNNER_KEY' not in os.environ\n"
            "p=argparse.ArgumentParser()\n"
            "for key in ('mp4','wav','script','frames-manifest','model','role','output'):\n"
            " p.add_argument('--'+key,required=True)\n"
            "a=p.parse_args()\n"
            "def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
            "assert Path(a.model).is_dir()\n"
            "data=json.loads((Path(a.model)/'model_files.json').read_text())\n"
            "assert len(data['files'])==2\n"
            "for entry in data['files']:\n"
            " assert sha(Path(a.model)/entry['path'])==entry['sha256']\n"
            "keys=('lip_sync','voice_continuity','character_motion')\n"
            "out={'role':a.role,'mp4_sha256':sha(a.mp4),'wav_sha256':sha(a.wav),"
            "'script_sha256':sha(a.script),"
            "'frames_manifest_sha256':sha(a.frames_manifest),"
            "'model_sha256':sha(Path(a.model)/'model_files.json'),"
            "'checks':{k:{'decision':'UNSURE',"
            "'evidence':'SYNTHETIC MODEL PACKAGE RUNNER DOES NOT ASSESS VIDEO: '+k}"
            " for k in keys},"
            "'summary':'Synthetic-only directory-aware executable; does no actual audiovisual perception.'}\n"
            "Path(a.output).write_text(json.dumps(out))\n"
        )
        binary=executable(self.root/"mock_dir_av",script)
        runner=AVRunner(binary=str(binary),binary_sha=digest(binary),
            model=self.dir,model_sha=digest(self.package),
            provider_id="mock_directory_av",model_id="mock-m41-checkpoint")
        self.assertEqual(runner.model_sha,checkpoint_digest(self.dir))
        result=self.h.av.review(first=runner,
            out_dir=self.root/"model_directory_review")
        self.assertFalse(result["all_model_checks_pass"])
        self.assertTrue((self.root/"model_directory_review"/
            "signed_av_m28.json").is_file())
        report=json.loads((self.root/"model_directory_review"/
            "signed_av_m28.json").read_text())
        self.assertEqual(report["reviewers"][0]["checks"]["lip_sync"]["decision"],
                         "UNSURE")
        self.assertFalse(report["publication_approved"])
        self.assertFalse(result["public_release_authorized"])


if __name__=="__main__":
    unittest.main()
