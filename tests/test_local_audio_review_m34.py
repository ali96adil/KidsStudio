"""M34 WAV source through real FFmpeg + mock Whisper/audio adapter contracts.

The two small local executables in these tests are MOCKS that read WAV
bytes, not actual trained audio models. Never infer audio suitability from
a passing CI fixture, even if its synthetic model report returns PASS.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from unittest.mock import patch
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

from kidsstudio.local_audio_review import (
    AudioRunner,AudioModelError,review_voice
)
from kidsstudio.real_media_evidence import digest
from kidsstudio.scene_ai_qa import SceneAIGate
from kidsstudio.studio_scenes import SceneLedger

def executable(path:Path,source:str):
    path.write_text("#!"+sys.executable+"\n"+source,encoding="utf-8")
    path.chmod(0o700)
    return path

class AudioWorker34(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m34-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.ffmpeg=str(Path(shutil.which("ffmpeg")).resolve())
        self.ffprobe=str(Path(shutil.which("ffprobe")).resolve())
        self.wav=self.root/"narration.wav"
        with wave.open(str(self.wav),"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
            w.writeframes(b"".join(struct.pack("<h",
                round(7000*math.sin(2*math.pi*220*i/16000)))
                for i in range(24000)))
        self.script=self.root/"scene01.txt"
        self.script.write_text("هذه الكرة حمراء. لون الكرة أحمر.",
                               encoding="utf-8")
        self.whisper_model=self.root/"whisper.bin"
        self.whisper_model.write_bytes(b"SYNTHETIC ASR MODEL"*20)
        # Mock model executable, explicitly NOT an audio ASR engine.
        self.whisper=executable(self.root/"mock-whisper",(
            "import sys,os\nfrom pathlib import Path\n"
            "a=sys.argv\n"
            "assert 'KIDS_STUDIO_SCENE_QA_RUNNER_KEY' not in os.environ\n"
            "assert '-m' in a and '-f' in a and '-of' in a\n"
            "out=Path(a[a.index('-of')+1]+'.txt')\n"
            "out.write_text('هذه الكرة حمراء. لون الكرة أحمر.',encoding='utf-8')\n"
        ))
        self.model_files=[]
        self.runners=[]
        for index,role in enumerate(("pronunciation","child_audio_safety")):
            model=self.root/f"fake_checkpoint_{index}.bin"
            model.write_bytes((b"SYNTHETIC NOT REAL CHECKPOINT"+bytes([index]))*12)
            self.model_files.append(model)
            source=(
                "import argparse,json,hashlib,os\nfrom pathlib import Path\n"
                "assert 'KIDS_STUDIO_SCENE_QA_RUNNER_KEY' not in os.environ\n"
                "assert 'GOOGLE_CLIENT_SECRET' not in os.environ\n"
                "p=argparse.ArgumentParser()\n"
                "for k in ('wav','script','transcript','model','language','role','output'):\n"
                " p.add_argument('--'+k,required=True)\n"
                "a=p.parse_args()\n"
                "def d(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
                "raw=Path(a.wav).read_bytes()\n"
                "assert raw[:4]==b'RIFF' and len(raw)>10000\n"
                "roles={'pronunciation':['pronunciation','clarity','script_fidelity'],"
                "'child_audio_safety':['age_appropriate','emotional_tone','audio_content_safety']}\n"
                "assert a.role in roles\n"
                "decision='UNSURE' if os.environ.get('M34_TEST_UNSURE')=='1' and "
                "a.role=='child_audio_safety' else 'PASS'\n"
                "result={'role':a.role,'audio_sha256':d(a.wav),"
                "'script_sha256':d(a.script),'transcript_sha256':d(a.transcript),"
                "'model_sha256':d(a.model),"
                "'summary':'Synthetic mock audio reviewer. The WAV bytes were read, "
                "but no AI voice or child-safety inference occurred.',"
                "'checks':{key:{'decision':decision,"
                "'evidence':'Synthetic-only model fixture; not a real listening review: '+key}"
                " for key in roles[a.role]}}\n"
                "Path(a.output).write_text(json.dumps(result))\n"
            )
            binary=executable(self.root/f"fake_model_{index}",source+f"# {index}\n")
            self.runners.append(AudioRunner(
                binary=str(binary),expected_binary_sha=digest(binary),
                model=model,expected_model_sha=digest(model),
                provider_id="audio_model_a" if index==0 else "audio_model_b",
                model_id="audio-model-a" if index==0 else "audio-model-b"))
        self.proof=self.root/"source_proof.txt"
        self.proof.write_text(
            "SYNTHETIC ORIGINAL OWNER RIGHTS NOTE FOR TEST ONLY. "
            "This sample is not legal evidence of commercial licensing.",
            encoding="utf-8")
        self.rights=self.root/"rights.json"
        self.rights.write_text(json.dumps({
            "schema_version":1,"artifact_sha256":digest(self.wav),
            "source_kind":"original_created",
            "source_proof_sha256":digest(self.proof),
            "source_proof_file":str(self.proof),
            "usage_scope":"commercial_youtube_kids",
            "documented":True,"rights_adjudicated":False,
            "publication_approved":False}))
        self.key=b"SYNTHETIC_TEST_KEY_ONLY_NOT_MAC_PRODUCTION_KEY___"
        self.job_id="a"*32

    def run_review(self,**kwargs):
        args=dict(
            series_id="colors-ar",episode=1,scene=1,job_id=self.job_id,
            wav=self.wav,wav_sha=digest(self.wav),
            script=self.script,script_sha=digest(self.script),
            language="ar",rights_file=self.rights,
            whisper_binary=str(self.whisper),
            whisper_model=self.whisper_model,
            whisper_model_sha=digest(self.whisper_model),
            ffmpeg=self.ffmpeg,ffprobe=self.ffprobe,
            first=self.runners[0],second=self.runners[1],
            runner_key=self.key,out_dir=self.root/"run01")
        args.update(kwargs)
        return review_voice(**args)

    def test_actual_WAV_is_decoded_and_two_mock_audio_adapters_produce_signed_m28(self):
        out=self.run_review()
        self.assertEqual(out["model_runner_calls"],2)
        self.assertFalse(out["pi_scene_approved"])
        self.assertFalse(out["public_release_authorized"])
        self.assertTrue(out["all_audio_model_checks_pass"])
        report=json.loads(Path(out["signed_report_file"]).read_text())
        self.assertEqual(report["technical_sha256"],
                         digest(self.root/"run01"/"voice_technical.json"))
        self.assertEqual(report["artifact_sha256"],digest(self.wav))
        self.assertEqual(len(report["reviewers"]),2)
        self.assertEqual({r["role"] for r in report["reviewers"]},
                         {"pronunciation","child_audio_safety"})
        observed=json.loads((self.root/"run01"/"observations.json").read_text())
        self.assertEqual(observed["asr_provider_id"],"asr_whispercpp")
        self.assertEqual(Path(observed["asr_file"]).read_text(),
                         self.script.read_text())
        self.assertTrue(observed["model_execution_verified"])
        self.assertEqual(self.wav.read_bytes()[:4],b"RIFF")

    def test_pi_exact_source_m23_m28_bridge_enables_next_ltx_not_owner_upload(self):
        # A full Pi database gate, but synthetic audio reviewers.
        from test_studio_orchestrator_m32 import Orchestration32
        h=Orchestration32("test_plan_cannot_advertise_public_permission")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.coord.pin(h.plan)
        voice=h.coord.tick(h.plan)
        self.assertEqual(voice["action"],"FIRST_AI_VOICE")
        leased=h.queue.claim(worker_id="fake-mac-audio",
                             capabilities=["voice_synthesize"])
        self.assertEqual(leased["job_id"],voice["job_id"])
        h.queue.complete(job_id=leased["job_id"],worker_id="fake-mac-audio",
            generation=leased["generation"],result={
                "status":"VOICE_RENDERED_PENDING_QA",
                "artifact_type":"wav","artifact_sha256":digest(self.wav),
                "artifact_bytes":self.wav.stat().st_size,
                "publication_approved":False})
        h.scenes.reconcile()
        local_script=h.scripts[0]
        # The fake ASR must return the EXACT scene's words to exercise
        # deterministic WER, without pretending to understand test tone.
        local_whisper=executable(self.root/"fake-voice-scene-asr",
            "import sys\nfrom pathlib import Path\n"
            "a=sys.argv\n"
            "Path(a[a.index('-of')+1]+'.txt').write_text("+
            repr(local_script.read_text(encoding="utf-8"))+")\n")
        output=self.run_review(
            job_id=voice["job_id"],script=local_script,
            script_sha=digest(local_script),
            whisper_binary=str(local_whisper))
        # Exact SHA of this independently run FFmpeg M23 report must be
        # registered in the Pi before the signed M28 model report.
        tech=h.scenes.register_voice_technical(
            "colors-ar",1,1,self.root/"run01"/"voice_technical.json")
        self.assertFalse(tech["owner_listening_performed"])
        gate=SceneAIGate(h.queue,attestation_key=self.key)
        gate.initialize()
        checked=gate.register("colors-ar",1,1,"voice_synthesize",
            report_file=output["signed_report_file"],
            observation_file=self.root/"run01"/"observations.json",
            rights_file=self.rights)
        self.assertEqual(checked["status"],"AI_SCENE_READY_PRIVATE_ONLY")
        self.assertFalse(checked["public_release_authorized"])
        decision=gate.auto_approve("colors-ar",1,1,"voice_synthesize")
        self.assertEqual(decision["status"],"AI_STAGE_APPROVED_INTERNAL_ONLY")
        self.assertEqual(h.coord.status(h.plan)["next_action"],"NEXT_LTX")
        self.assertEqual(h.queue.status()["counts"]["QUEUED"],0)

    def test_child_audio_models_and_whisper_never_inherit_private_keys(self):
        with patch.dict(os.environ,{
            "KIDS_STUDIO_SCENE_QA_RUNNER_KEY":
                "MOCK_PROCESS_MUST_NOT_RECEIVE_THIS_SIGNING_KEY",
            "GOOGLE_CLIENT_SECRET":"SYNTHETIC_OAUTH_SECRET_NOT_FOR_CHILD"
        }):
            result=self.run_review()
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse(result["pi_scene_approved"])

    def test_wrong_source_or_rights_rejected_without_new_output(self):
        with self.assertRaises(AudioModelError):
            self.run_review(wav_sha="0"*64)
        self.assertFalse((self.root/"run01").exists())
        self.rights.write_text("{}")
        with self.assertRaises(AudioModelError):
            self.run_review()
        self.assertFalse((self.root/"run01").exists())

    def test_two_checkpoints_and_executables_must_be_distinct(self):
        with self.assertRaises(AudioModelError):
            self.run_review(second=self.runners[0])
        self.assertFalse((self.root/"run01").exists())

    def test_unsigned_or_short_key_not_accepted(self):
        with self.assertRaises(AudioModelError):
            self.run_review(runner_key=b"not-a-secret")
        self.assertFalse((self.root/"run01").exists())

    def test_report_cannot_be_reused_or_overwritten(self):
        self.run_review()
        with self.assertRaises(Exception):
            self.run_review()
        self.assertTrue((self.root/"run01"/"signed_voice_m28.json").exists())


if __name__=="__main__":
    unittest.main()
