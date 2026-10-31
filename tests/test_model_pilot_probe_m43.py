"""M43 actual FFmpeg source paths and a deliberately FAKE pinned reviewer.

The adapter is an executable mock that reads SHA-bound source files and
returns UNSURE. M43 records execution time/child RSS but never validates
real Apple GPU, trained audio/AV perception, child safety or publishing.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from kidsstudio.model_pilot_probe import PilotProbeError,run_probe,main
from kidsstudio.model_origin_attestation import sign_origin_draft
from kidsstudio.qwen_omni_local import inspect_local
from kidsstudio.real_media_evidence import digest
from test_qwen_omni_local_m42 import LocalOmni42
from test_local_audio_review_m34 import executable


class MacProbe43(unittest.TestCase):
    def setUp(self):
        x=LocalOmni42("test_mac_resource_presolve_does_not_claim_execution")
        x.setUp()
        self.addCleanup(x.doCleanups)
        self.x=x
        self.root=x.root
        self.adapter=executable(self.root/"fake_qwen_adapter",(
            "import argparse,hashlib,json,os\n"
            "from pathlib import Path\n"
            "assert 'KIDS_STUDIO_SCENE_QA_RUNNER_KEY' not in os.environ\n"
            "assert 'GOOGLE_CLIENT_SECRET' not in os.environ\n"
            "assert os.environ.get('HF_HUB_OFFLINE')=='1'\n"
            "p=argparse.ArgumentParser()\n"
            "for name in ('model','model-sha256','variant','role','wav',"
            "'script','output'):\n"
            " p.add_argument('--'+name,required=True)\n"
            "for name in ('transcript','mp4','frames-manifest','ffprobe'):\n"
            " p.add_argument('--'+name)\n"
            "p.add_argument('--execute',action='store_true')\n"
            "x=p.parse_args()\n"
            "assert x.execute\n"
            "def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
            "roles={'pronunciation':['pronunciation','clarity','script_fidelity'],"
            "'child_audio_safety':['age_appropriate','emotional_tone','audio_content_safety'],"
            "'motion_sync':['lip_sync','voice_continuity','character_motion'],"
            "'visual_child_safety':['age_appropriate','visual_consistency','no_unsafe_content']}\n"
            "checks={key:{'decision':'UNSURE','evidence':"
            "'SYNTHETIC FAKE ADAPTER: no actual model or child review: '+key}"
            " for key in roles[x.role]}\n"
            "result={'role':x.role,'model_sha256':sha(Path(x.model)/'model_files.json'),"
            "'script_sha256':sha(x.script),'checks':checks,"
            "'summary':'This is a synthetic model adapter. No true audio or AV "
            "perception occurred.'}\n"
            "assert result['model_sha256']==x.model_sha256\n"
            "if x.mp4:\n"
            " assert x.ffprobe and x.frames_manifest\n"
            " result.update({'mp4_sha256':sha(x.mp4),'wav_sha256':sha(x.wav),"
            "'frames_manifest_sha256':sha(x.frames_manifest)})\n"
            "else:\n"
            " result.update({'audio_sha256':sha(x.wav),"
            "'transcript_sha256':sha(x.transcript)})\n"
            "Path(x.output).write_text(json.dumps(result))\n"
        ))
        self.origin_key=b"M44_SYNTHETIC_OWNER_SIGNING_KEY_NOT_FOR_PRODUCTION___"
        self.license=self.root/"qwen_7b_license_COPY.txt"
        self.license.write_text(
            "Apache License\\nVersion 2.0, January 2004\\n"
            "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\\n"
            "This synthetic fixture is NOT actual licensed-source evidence. "
            "Its only purpose is to test a private HMAC record and byte binding. "
            "It must not be used for commercial production. "*3,encoding="utf-8")
        self.origin_draft=self.root/"model_origin_draft.json"
        self.origin_draft.write_text(json.dumps({
            "schema_version":1,
            "checkpoint_package_sha256":self.x.sha,
            "upstream_provider":"huggingface",
            "upstream_repository":"Qwen/Qwen2.5-Omni-7B",
            "upstream_revision":"a"*40,
            "source_identity":"official_repository_claim",
            "model_variant":"7b",
            "license_spdx_claim":"Apache-2.0",
            "license_copy_path":str(self.license),
            "license_copy_sha256":digest(self.license),
            "source_reviewed_by_owner":True,
            "license_reviewed_by_owner":True,
            "usage_scope":"local_diagnostic_only",
            "owner_review_note":"Synthetic review fixture, not a genuine owner source or commercial license review.",
            "model_quality_qualified":False,
            "youtube_private_upload_authorized":False,
            "public_release_authorized":False
        }),encoding="utf-8")
        self.origin_receipt=self.root/"model_origin_receipt.json"
        sign_origin_draft(model=self.x.model,model_sha256=self.x.sha,
            draft=self.origin_draft,draft_sha256=digest(self.origin_draft),
            out=self.origin_receipt,owner_key=self.origin_key,execute=True)
        self.probe_root=self.root/"one_pilot"
        self.base={
            "adapter":str(self.adapter),
            "adapter_sha256":digest(self.adapter),
            "model":self.x.model,
            "model_sha256":self.x.sha,
            "variant":"7b","role":"pronunciation",
            "wav":self.x.av.wav,
            "wav_sha256":digest(self.x.av.wav),
            "script":self.x.av.script,
            "script_sha256":digest(self.x.av.script),
            "transcript":self.x.transcript,
            "transcript_sha256":digest(self.x.transcript),
            "out_dir":self.probe_root,
            "resource_screen":self.screen,
            "origin_receipt":self.origin_receipt,
            "origin_receipt_sha256":digest(self.origin_receipt),
            "owner_origin_key":self.origin_key
        }

    def screen(self,*,model,expected_model_sha,variant):
        return inspect_local(model=model,expected_model_sha=expected_model_sha,
            variant=variant,system="Darwin",arch="arm64",
            ram_bytes=80*1024**3,free_bytes=60*1024**3,
            packages={"torch":True,"transformers":True,"torchvision":True})

    def call(self,**kw):
        args=self.base.copy()
        args.update(kw)
        return run_probe(**args)

    def video(self,**kw):
        args=dict(role="motion_sync",transcript=None,transcript_sha256=None,
            mp4=self.x.av.mp4,mp4_sha256=digest(self.x.av.mp4),
            frames_manifest=self.x.frames,
            frames_sha256=digest(self.x.frames),
            ffprobe=self.x.av.ffprobe,
            ffprobe_sha256=digest(Path(self.x.av.ffprobe)))
        args.update(kw)
        return self.call(**args)

    def test_strict_default_checks_every_source_without_starting_a_model(self):
        def launch(*a,**kw):
            raise AssertionError("Dry-run cannot run the model.")
        result=self.call(launcher=launch)
        self.assertEqual(result["status"],"M43_READ_ONLY_MODEL_PILOT_PREFLIGHT")
        self.assertEqual(result["model_calls"],0)
        self.assertFalse(result["files_written"])
        self.assertFalse(result["model_inference_proven"])
        self.assertFalse(result["model_quality_qualified"])
        self.assertFalse(result["private_upload_permitted"])
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse(self.probe_root.exists())

    def test_unsupported_linux_mac_screen_blocks_before_any_file_write(self):
        def blocked(*,model,expected_model_sha,variant):
            return inspect_local(model=model,expected_model_sha=expected_model_sha,
                variant=variant,system="Linux",arch="x86_64",
                ram_bytes=16*1024**3,free_bytes=30*1024**3,
                packages={"torch":True,"transformers":True,"torchvision":True})
        with self.assertRaises(PilotProbeError):
            self.call(execute=True,resource_screen=blocked)
        self.assertFalse(self.probe_root.exists())

    def test_explicit_mock_audio_run_keeps_all_criteria_unsure_and_metrics(self):
        report=self.call(execute=True)
        self.assertEqual(report["status"],"M43_OBSERVATION_ONLY_NOT_AI_QUALIFIED")
        self.assertEqual(report["model_calls"],1)
        self.assertGreaterEqual(report["elapsed_seconds"],0)
        self.assertIsInstance(report["observed_child_max_rss_bytes"],int)
        self.assertFalse(report["rss_measurement_is_total_mac_gpu_usage"])
        self.assertEqual(report["source_sha256"]["audio_sha256"],
                         digest(self.x.av.wav))
        self.assertFalse(report["model_inference_proven"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["child_safety_certified"])
        self.assertFalse(report["network_isolation_verified"])
        self.assertFalse(report["mac_pi_hardware_qualified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertFalse(report["public_release_authorized"])
        report_file=self.probe_root/"pilot_metrics.json"
        self.assertTrue(report_file.exists())
        self.assertEqual(json.loads(report_file.read_text())["model_calls"],1)
        verdict=json.loads((self.probe_root/"m42_diagnostic.json").read_text())
        self.assertTrue(all(x["decision"]=="UNSURE" for x in verdict["checks"].values()))
        with self.assertRaises(PilotProbeError):
            self.call(execute=True)

    def test_explicit_sound_bearing_mp4_and_frames_are_bound(self):
        report=self.video(execute=True)
        self.assertEqual(report["source_sha256"]["mp4_sha256"],
                         digest(self.x.av.mp4))
        self.assertEqual(report["source_sha256"]["frames_manifest_sha256"],
                         digest(self.x.frames))
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertTrue((self.probe_root/"m42_diagnostic.json").exists())

    def test_execute_without_owner_origin_record_never_launches(self):
        with self.assertRaises(PilotProbeError):
            self.call(execute=True,origin_receipt=None)
        self.assertFalse(self.probe_root.exists())

    def test_different_or_changed_license_record_cannot_launch(self):
        with self.assertRaises(ValueError):
            self.call(execute=True,origin_receipt_sha256="e"*64)
        self.license.write_text(self.license.read_text()+"MUTATED")
        with self.assertRaises(ValueError):
            self.call(execute=True)
        self.assertFalse(self.probe_root.exists())

    def test_malicious_pass_report_is_rejected_before_receipt(self):
        original=self.adapter.read_text()
        self.adapter.write_text(original.replace(
            "'decision':'UNSURE'","'decision':'PASS'"))
        sha=digest(self.adapter)
        with self.assertRaises(PilotProbeError):
            self.call(adapter_sha256=sha,execute=True)
        self.assertFalse((self.probe_root/"pilot_metrics.json").exists())

    def test_wrong_source_and_adapter_shas_fail_without_creating_directory(self):
        with self.assertRaises(PilotProbeError):
            self.call(execute=True,wav_sha256="b"*64)
        with self.assertRaises(PilotProbeError):
            self.call(execute=True,adapter_sha256="c"*64)
        with self.assertRaises(PilotProbeError):
            self.video(execute=True,frames_sha256="d"*64)
        with self.assertRaises(PilotProbeError):
            self.video(execute=True,ffprobe_sha256="e"*64)
        self.assertFalse(self.probe_root.exists())

    def test_subprocess_timeout_is_not_a_usable_model_receipt(self):
        def timeout(*args,**kwargs):
            raise subprocess.TimeoutExpired(args[0],1)
        with self.assertRaises(PilotProbeError):
            self.call(execute=True,launcher=timeout,timeout_seconds=1)
        self.assertFalse((self.probe_root/"pilot_metrics.json").exists())

    def test_cli_without_execute_is_readonly_when_hardware_is_blocked(self):
        # CLI gets its real Linux-resource screen. A blocked screen is still
        # useful information, and cannot authorize a run or create output.
        args=["--adapter",str(self.adapter),
              "--adapter-sha256",digest(self.adapter),
              "--model",str(self.x.model),
              "--model-sha256",self.x.sha,
              "--variant","7b","--role","pronunciation",
              "--wav",str(self.x.av.wav),
              "--wav-sha256",digest(self.x.av.wav),
              "--script",str(self.x.av.script),
              "--script-sha256",digest(self.x.av.script),
              "--transcript",str(self.x.transcript),
              "--transcript-sha256",digest(self.x.transcript),
              "--out",str(self.probe_root)]
        self.assertEqual(main(args),0)
        self.assertFalse(self.probe_root.exists())


if __name__=="__main__":
    unittest.main()
