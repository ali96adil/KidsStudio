"""M29 local dual-vision execution contract: mock Ollama outputs + real frames.

Mock responses are *not* real model inference. We verify exactly what the
future real local model service receives, provenance and signing controls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib import request

from kidsstudio.local_vision_review import (
    OllamaVision,LocalVisionError,review_ltx,sign_after_m10
)
from kidsstudio.real_media_evidence import digest
from kidsstudio.scene_ai_qa import SceneAIGate,SceneError


class FakeResult:
    def __init__(self,bytes_out):
        self.bytes_out=bytes_out
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.bytes_out[:n]


class FakeOllamaOpener:
    def __init__(self):self.calls=[]
    def open(self,req,timeout=0):
        payload=json.loads(req.data)
        self.calls.append(payload)
        prompt=payload["messages"][0]["content"]
        if "lip_sync" in prompt:
            checks=["lip_sync","voice_continuity","character_motion"]
        else:
            checks=["age_appropriate","visual_consistency","no_unsafe_content"]
        answer={"summary":"Synthetic evaluator mock, not actual Ollama inference. Unit test only.",
                "checks":{key:{
                    "decision":"UNSURE" if key=="lip_sync" else "PASS",
                    "evidence":"Synthetic evaluation. This is mock output, not vision evidence: "+key
                } for key in checks}}
        return FakeResult(json.dumps({"done":True,
            "message":{"content":json.dumps(answer)}}).encode())


class VisionBridgeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m29-vision-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.ffmpeg=str(Path(shutil.which("ffmpeg")).resolve())
        self.ffprobe=str(Path(shutil.which("ffprobe")).resolve())
        self.mp4=self.root/"scene.mp4"
        subprocess.run([self.ffmpeg,"-hide_banner","-loglevel","error",
            "-nostdin","-y","-f","lavfi","-i",
            "testsrc=size=384x216:rate=10:duration=3",
            "-c:v","libx264","-pix_fmt","yuv420p",str(self.mp4)],
            timeout=60,check=True,capture_output=True)
        self.script=self.root/"script.txt"
        self.script.write_text("الكرة الحمراء تتحرك أمام الطفل لنتعلم اللون الأحمر.",
                               encoding="utf-8")
        self.proof=self.root/"source_proof.txt"
        self.proof.write_text(
            "SYNTHETIC rights declaration in a test fixture; not legal clearance.")
        self.rights=self.root/"rights.json"
        self.rights.write_text(json.dumps({
            "schema_version":1,"artifact_sha256":digest(self.mp4),
            "source_kind":"original_created",
            "source_proof_sha256":digest(self.proof),
            "source_proof_file":str(self.proof),
            "usage_scope":"commercial_youtube_kids",
            "documented":True,"rights_adjudicated":False,
            "publication_approved":False
        }))
        self.first_opener=FakeOllamaOpener()
        self.second_opener=FakeOllamaOpener()
        self.first=OllamaVision(
            "http://127.0.0.1:11434/api/chat",
            "model-one:latest","local_ollama_a",opener=self.first_opener)
        self.second=OllamaVision(
            "http://127.0.0.1:11435/api/chat",
            "model-two:latest","local_ollama_b",opener=self.second_opener)
        self.key=b"CI_SYNTHETIC_PRIVATE_RUNNER_KEY_NOT_A_PRODUCTION_SECRET"
        self.m10=self.root/"m10.json"
        self.m10.write_text(json.dumps({
            "schema_version":1,
            "status":"AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED",
            "voice_sha256":"b"*64,"a2v_sha256":digest(self.mp4),
            "voice_seconds":3,"a2v_audio_seconds":3,
            "duration_close":True,"energy_present":True,
            "envelope_correlation":0.95,"estimated_lag_seconds":0.03,
            "audio_content_identity_proven":False,
            "speaker_identity_proven":False,
            "lip_sync_verified":False,
            "owner_audiovisual_review_required":True,
            "publishing_approved":False
        }))

    def execute_review(self,**changes):
        opts=dict(series_id="colors-ar",episode=1,scene=1,
            job_id="a"*32,mp4=self.mp4,mp4_sha=digest(self.mp4),
            script=self.script,script_sha=digest(self.script),
            voice_sha="b"*64,rights_file=self.rights,
            ffmpeg=self.ffmpeg,ffprobe=self.ffprobe,
            objective="Teach red color by moving a red ball",
            first=self.first,second=self.second,
            runner_key=self.key,out_dir=self.root/"vision",frames=3)
        opts.update(changes)
        return review_ltx(**opts)

    def test_real_source_frames_go_to_two_independent_local_models(self):
        result=self.execute_review()
        self.assertTrue(result["runner_models_executed"])
        self.assertFalse(result["m28_stage_approved"])
        self.assertFalse(result["public_release_authorized"])
        self.assertTrue(result["needs_fix_or_unsure"])
        self.assertEqual(len(self.first_opener.calls),1)
        self.assertEqual(len(self.second_opener.calls),1)
        for call in self.first_opener.calls+self.second_opener.calls:
            images=call["messages"][1]["images"]
            self.assertEqual(len(images),3)
            self.assertTrue(all(len(i)>100 for i in images))
            self.assertIn("الكرة",call["messages"][1]["content"])
        self.assertNotEqual(self.first_opener.calls[0]["model"],
                            self.second_opener.calls[0]["model"])
        self.assertEqual(result["status"],
            "REAL_LOCAL_VISUAL_MODEL_REPORTS_PENDING_M10_BIND")
        signed=sign_after_m10(
            pending_report=self.root/"vision"/"model_report_pending_m10.json",
            m10_report=self.m10,expected_m10_sha=digest(self.m10),
            rights_file=self.rights,
            observation_file=self.root/"vision"/"observations.json",
            attestation_key=self.key,
            out_file=self.root/"vision"/"signed_m28.json")
        self.assertEqual(signed["status"],
                         "SIGNED_M28_VISUAL_REVIEW_READY_FOR_PI_IMPORT")
        bundle=json.loads((self.root/"vision"/"signed_m28.json").read_text())
        self.assertEqual(bundle["technical_sha256"],digest(self.m10))
        # Actual M28 gate will record UNSURE, not approve this LTX.
        self.assertEqual(bundle["reviewers"][0]["checks"]["lip_sync"]["decision"],
                         "UNSURE")

    def test_no_public_or_remote_endpoint_supported(self):
        for endpoint in ("https://127.0.0.1:11434/api/chat",
                         "http://somewhere.example/api/chat",
                         "http://127.0.0.1:11434/api/generate"):
            with self.assertRaises(LocalVisionError):
                OllamaVision(endpoint,"model-one:latest","provider_abc")
        with self.assertRaises(LocalVisionError):
            self.execute_review(second=self.first)
        self.assertEqual(self.first_opener.calls,[])

    def test_source_mutation_or_wrong_rights_prevent_calls(self):
        with self.assertRaises(LocalVisionError):
            self.execute_review(mp4_sha="0"*64)
        self.assertEqual(self.first_opener.calls,[])
        self.rights.write_text("{}")
        with self.assertRaises(LocalVisionError):
            self.execute_review()
        self.assertEqual(self.first_opener.calls,[])

    def test_cannot_sign_unpinned_m10_report(self):
        self.execute_review()
        with self.assertRaises(LocalVisionError):
            sign_after_m10(
                pending_report=self.root/"vision"/"model_report_pending_m10.json",
                m10_report=self.m10,expected_m10_sha="0"*64,
                rights_file=self.rights,
                observation_file=self.root/"vision"/"observations.json",
                attestation_key=self.key,
                out_file=self.root/"vision"/"signed_m28.json")
        self.assertFalse((self.root/"vision"/"signed_m28.json").exists())


if __name__=="__main__":
    unittest.main()
