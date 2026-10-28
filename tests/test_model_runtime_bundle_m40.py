"""M40 tests: real FFmpeg and exact local adapter SHA binding with mock AI.

The stand-ins return PASS but have no trained audio/visual perception.
Nothing in this test qualifies educational suitability, model quality,
license rights, a real Mac/Pi or YouTube release.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.model_runtime_bundle import LocalModelBundle, ModelBundleError, main
from kidsstudio.real_media_evidence import digest
from test_synchronized_av_m37 import SynchronizedAV37


class PrivateModelBundle40(unittest.TestCase):
    def setUp(self):
        source=SynchronizedAV37(
            "test_actual_soundtrack_real_pcm_and_frames_bound_to_two_mock_AV_models")
        source.setUp();self.addCleanup(source.doCleanups)
        self.av=source
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m40-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        models=self.root/"models"
        models.mkdir()
        self.models=models

        def runner(binary,model,provider,model_id,index):
            dst=models/(str(index)+"_"+Path(model).name)
            shutil.copyfile(model,dst)
            return {"binary":str(binary),"binary_sha256":digest(Path(binary)),
                "model":str(dst),"model_sha256":digest(dst),
                "provider_id":provider,"model_id":model_id}

        audio=source.audio
        roles={
            "asr_whispercpp":runner(audio.whisper,audio.whisper_model,
                                   "asr_whispercpp","whisper-pinned-test",0),
            "audio_pronunciation":runner(
                audio.runners[0].binary,audio.runners[0].model,
                audio.runners[0].provider_id,audio.runners[0].model_id,1),
            "audio_child_safety":runner(
                audio.runners[1].binary,audio.runners[1].model,
                audio.runners[1].provider_id,audio.runners[1].model_id,2),
            "av_motion_sync":runner(
                source.runners[0].binary,source.runners[0].model,
                source.runners[0].provider_id,source.runners[0].model_id,3),
            "av_visual_child_safety":runner(
                source.runners[1].binary,source.runners[1].model,
                source.runners[1].provider_id,source.runners[1].model_id,4)
        }
        self.config={
            "schema_version":1,"deployment":"local_offline",
            "private_root":str(self.root),
            "network_required":False,"model_quality_qualified":False,
            "execution_authorized":False,"public_release_authorized":False,
            "tools":{"ffmpeg":{"binary":source.ffmpeg,
                                "sha256":digest(Path(source.ffmpeg))},
                     "ffprobe":{"binary":source.ffprobe,
                                "sha256":digest(Path(source.ffprobe))}},
            "reviewers":roles
        }
        self.file=self.root/"model_bundle.json"
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.config,ensure_ascii=False))

    def load(self):
        return LocalModelBundle(self.file,digest(self.file))

    def test_pin_real_binaries_and_five_roles_but_never_claim_model_quality(self):
        b=self.load()
        snapshot=b.public_status()
        self.assertEqual(snapshot["status"],
                         "M40_LOCAL_MODEL_BYTES_PINNED_NOT_QUALIFIED")
        self.assertEqual(snapshot["reviewer_role_count"],5)
        self.assertFalse(snapshot["model_capabilities_verified"])
        self.assertFalse(snapshot["real_model_inference_tested"])
        self.assertFalse(snapshot["mac_pi_hardware_qualified"])
        self.assertFalse(snapshot["pi_scene_approved"])
        self.assertFalse(snapshot["public_release_authorized"])
        self.assertNotIn(str(self.root),json.dumps(snapshot))
        self.assertFalse((self.root/"reports").exists())

    def test_manifest_sha_and_missing_model_cannot_change_into_approval(self):
        old=digest(self.file)
        self.config["reviewers"]["av_motion_sync"]["model_sha256"]="f"*64
        self.save()
        with self.assertRaises(ModelBundleError):
            LocalModelBundle(self.file,old)
        with self.assertRaises(ModelBundleError):
            self.load()
        self.assertFalse((self.root/"reports").exists())

    def test_same_provider_or_binary_or_weights_are_not_independent(self):
        cases=[
            ("provider_id",
             self.config["reviewers"]["audio_pronunciation"]["provider_id"]),
            ("binary_sha256",
             self.config["reviewers"]["audio_pronunciation"]["binary_sha256"]),
            ("model_sha256",
             self.config["reviewers"]["audio_pronunciation"]["model_sha256"])]
        for key, value in cases:
            with self.subTest(key=key):
                changed=copy.deepcopy(self.config)
                changed["reviewers"]["av_motion_sync"][key]=value
                self.file.write_text(json.dumps(changed))
                with self.assertRaises(ModelBundleError):
                    self.load()
        self.save()

    def test_checkpoint_escape_symlink_or_other_bundle_policy_denied(self):
        changed=copy.deepcopy(self.config)
        changed["reviewers"]["av_motion_sync"]["model"]=str(
            self.av.runners[0].model)
        self.file.write_text(json.dumps(changed))
        with self.assertRaises(ModelBundleError):
            self.load()
        changed=copy.deepcopy(self.config)
        link=self.root/"alias_model.gguf"
        link.symlink_to(self.models/"3_mock_model_0.gguf")
        changed["reviewers"]["av_motion_sync"]["model"]=str(link)
        self.file.write_text(json.dumps(changed))
        with self.assertRaises(ModelBundleError):
            self.load()
        for field in ("network_required","model_quality_qualified",
                      "execution_authorized","public_release_authorized"):
            changed=copy.deepcopy(self.config)
            changed[field]=True
            self.file.write_text(json.dumps(changed))
            with self.assertRaises(ModelBundleError):
                self.load()
        self.save()

    def test_bundle_manifest_cannot_be_outside_private_root_or_shared(self):
        # A separately pinned manifest still must live in the same
        # owner-private model root, not a shared temporary directory.
        other=self.av.root/"foreign_model_bundle.json"
        other.write_bytes(self.file.read_bytes())
        with self.assertRaises(ModelBundleError):
            LocalModelBundle(other,digest(other))
        before=self.root.stat().st_mode
        try:
            self.root.chmod(0o777)
            with self.assertRaises(ModelBundleError):
                self.load()
        finally:
            self.root.chmod(before & 0o777)

    def test_no_execute_voice_cli_is_read_only_and_ignores_fake_m34_results(self):
        argv=["--manifest",str(self.file),
              "--manifest-sha256",digest(self.file),
              "voice","--series","colors-ar","--episode","1","--scene","1",
              "--job-id","a"*32,"--wav",str(self.av.audio.wav),
              "--wav-sha256",digest(self.av.audio.wav),
              "--script",str(self.av.audio.script),
              "--script-sha256",digest(self.av.audio.script),
              "--rights",str(self.av.audio.rights),
              "--out",str(self.root/"not_created"),"--language","ar"]
        with patch("kidsstudio.model_runtime_bundle.review_voice",
                   side_effect=AssertionError("No model execution without --execute")):
            rc=main(argv)
        self.assertEqual(rc,0)
        self.assertFalse((self.root/"not_created").exists())

    def test_explicit_voice_adapter_reuses_genuine_m34_ffmpeg_and_mock_ai(self):
        b=self.load()
        audio=self.av.audio
        out=self.root/"voice_review"
        result=b.execute_review(kind="voice_synthesize",
            series_id="colors-ar",episode=1,scene=1,job_id="a"*32,
            wav=audio.wav,wav_sha=digest(audio.wav),
            script=audio.script,script_sha=digest(audio.script),
            rights_file=audio.rights,out_dir=out,
            runner_key=audio.key,language="ar")
        self.assertTrue((out/"signed_voice_m28.json").is_file())
        self.assertEqual(result["m40_manifest_sha256"],digest(self.file))
        self.assertEqual(result["model_runner_calls"],2)
        self.assertFalse(result["real_model_competence_proven_by_m40"])
        self.assertFalse(result["pi_scene_approved"])
        self.assertFalse(result["private_upload_permitted"])
        self.assertFalse(result["public_release_authorized"])

    def test_explicit_video_adapter_uses_real_synchronized_mp4_and_mock_ai(self):
        b=self.load()
        out=self.root/"video_review"
        result=b.execute_review(kind="ltx_animate",
            series_id="colors-ar",episode=1,scene=1,job_id="a"*32,
            wav=self.av.wav,wav_sha=digest(self.av.wav),
            script=self.av.script,script_sha=digest(self.av.script),
            rights_file=self.av.rights,out_dir=out,
            mp4=self.av.mp4,mp4_sha=digest(self.av.mp4),
            m10_report=self.av.m10,runner_key=self.av.key)
        self.assertTrue((out/"signed_av_m28.json").is_file())
        self.assertEqual(result["m40_manifest_sha256"],digest(self.file))
        self.assertTrue(result["all_model_checks_pass"])
        self.assertFalse(result["real_model_competence_proven_by_m40"])
        self.assertFalse(result["pi_scene_approved"])
        self.assertFalse(result["public_release_authorized"])


if __name__=="__main__":
    unittest.main()
