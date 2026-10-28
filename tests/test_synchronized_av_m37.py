"""M37 tests: REAL WAV+audio-bearing MP4/FFmpeg, MOCK AV model binaries.

These Python fixtures check source binding and exact Pi SQLite transitions.
They DO NOT prove lip-sync perceptual quality or trained-model capability.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.audio_continuity import compare_voice_to_a2v
from kidsstudio.real_media_evidence import digest
from kidsstudio.synchronized_av_review import AVRunner, AVReviewError, review_synchronized
from kidsstudio.synchronized_av_import import import_synchronized, AVImportError
from kidsstudio.audio_review_import import import_voice_review
from test_local_audio_review_m34 import AudioWorker34, executable
from test_studio_orchestrator_m32 import Orchestration32


class SynchronizedAV37(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="kidsstudio-m37-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.ffmpeg=str(Path(shutil.which("ffmpeg")).resolve())
        self.ffprobe=str(Path(shutil.which("ffprobe")).resolve())
        audio=AudioWorker34(
            "test_actual_WAV_is_decoded_and_two_mock_audio_adapters_produce_signed_m28")
        audio.setUp();self.addCleanup(audio.doCleanups)
        self.audio=audio
        # 3 seconds, modulated amplitude. Not speech; synthetic signal only.
        with wave.open(str(audio.wav),"wb") as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
            frames=[]
            for i in range(48000):
                t=i/16000
                gain=.45+.35*math.sin(2*math.pi*1.4*t)
                v=round(14000*gain*math.sin(2*math.pi*270*t))
                frames.append(struct.pack("<h",v))
            wav.writeframes(b"".join(frames))
        doc=json.loads(audio.rights.read_text())
        doc["artifact_sha256"]=digest(audio.wav)
        audio.rights.write_text(json.dumps(doc))
        self.wav=audio.wav
        self.mp4=self.root/"real-audio.mp4"
        subprocess.run([
            self.ffmpeg,"-v","error","-nostdin","-y",
            "-f","lavfi","-i","testsrc=size=384x216:rate=10:duration=3",
            "-i",str(self.wav),"-c:v","libx264","-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","160k","-shortest",str(self.mp4)],
            check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        self.wav_sha=digest(self.wav);self.mp4_sha=digest(self.mp4)
        m10=compare_voice_to_a2v(self.wav,self.mp4,voice_sha256=self.wav_sha,
            a2v_sha256=self.mp4_sha,ffmpeg=self.ffmpeg)
        self.assertEqual(m10["status"],
                         "AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED")
        self.m10=self.root/"m10.json"
        self.m10.write_text(json.dumps(m10))
        self.proof=self.root/"av_origin_proof.txt"
        self.proof.write_text("SYNTHETIC original artwork/video rights fixture only. "
                              "This is not evidence of actual commercial rights.")
        self.rights=self.root/"av_rights.json"
        self.rights.write_text(json.dumps({
            "schema_version":1,"artifact_sha256":self.mp4_sha,
            "source_kind":"original_created",
            "source_proof_sha256":digest(self.proof),
            "source_proof_file":str(self.proof),
            "usage_scope":"commercial_youtube_kids",
            "documented":True,"rights_adjudicated":False,
            "publication_approved":False
        }))
        self.runners=[]
        for index,role in enumerate(("motion_sync","visual_child_safety")):
            model=self.root/f"mock_model_{index}.gguf"
            model.write_bytes((b"MOCK-AV-MODEL-NOT-TRAINED"+bytes([index]))*20)
            src=(
                "import argparse,json,hashlib,os\nfrom pathlib import Path\n"
                "assert 'KIDS_STUDIO_SCENE_QA_RUNNER_KEY' not in os.environ\n"
                "assert 'GOOGLE_CLIENT_SECRET' not in os.environ\n"
                "p=argparse.ArgumentParser()\n"
                "for k in ('mp4','wav','script','frames-manifest','model','role','output'):\n"
                " p.add_argument('--'+k,required=True)\n"
                "a=p.parse_args()\n"
                "def d(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
                "assert Path(a.mp4).stat().st_size>5000\n"
                "assert Path(a.wav).read_bytes()[:4]==b'RIFF'\n"
                "assert len(json.loads(Path(a.frames_manifest).read_text())['frames'])>=3\n"
                "criteria={'motion_sync':['lip_sync','voice_continuity','character_motion'],"
                "'visual_child_safety':['age_appropriate','visual_consistency','no_unsafe_content']}\n"
                "out={'role':a.role,'mp4_sha256':d(a.mp4),'wav_sha256':d(a.wav),"
                "'script_sha256':d(a.script),'frames_manifest_sha256':d(a.frames_manifest),"
                "'model_sha256':d(a.model),"
                "'checks':{c:{'decision':'PASS','evidence':"
                "'MOCK ONLY: no trained model inference; original MP4 and WAV examined: '+c}"
                " for c in criteria[a.role]},"
                "'summary':'Synthetic audiovisual model adapter. No actual lip-sync assessment.'}\n"
                "Path(a.output).write_text(json.dumps(out))\n"
            )
            binary=executable(self.root/f"mock_av_{index}",src+f"# runner {index}\n")
            self.runners.append(AVRunner(binary=str(binary),binary_sha=digest(binary),
                model=model,model_sha=digest(model),
                provider_id=f"mock_av_{index}",model_id=f"mock-av-model-{index}"))
        self.key=b"M37_SYNTHETIC_TEST_ONLY_SIGNER_DO_NOT_USE_IN_PRODUCTION_"
        self.script=self.root/"current_scene_script.txt"
        self.script.write_text("الكرة الحمراء تتحرك، ونتعلم اللون الأحمر.",
                               encoding="utf-8")
        self.job="a"*32

    def review(self,**changes):
        args=dict(series_id="colors-ar",episode=1,scene=1,job_id=self.job,
            mp4=self.mp4,mp4_sha=self.mp4_sha,wav=self.wav,wav_sha=self.wav_sha,
            script=self.script,script_sha=digest(self.script),
            m10_report=self.m10,rights_file=self.rights,
            ffmpeg=self.ffmpeg,ffprobe=self.ffprobe,
            first=self.runners[0],second=self.runners[1],
            runner_key=self.key,out_dir=self.root/"review",frames=3)
        args.update(changes)
        return review_synchronized(**args)

    def test_actual_soundtrack_real_pcm_and_frames_bound_to_two_mock_AV_models(self):
        with patch.dict(os.environ,{
            "KIDS_STUDIO_SCENE_QA_RUNNER_KEY":"PRIVATE_SYNTHETIC_SIGNING_KEY",
            "GOOGLE_CLIENT_SECRET":"PRIVATE_MOCK_OAUTH_SECRET"}):
            result=self.review()
        self.assertTrue(result["all_model_checks_pass"])
        self.assertFalse(result["pi_scene_approved"])
        self.assertFalse(result["models_qualified_for_real_child_qa_by_this_test"])
        doc=json.loads(Path(result["signed_report_file"]).read_text())
        self.assertEqual(doc["technical_sha256"],digest(self.m10))
        self.assertEqual(doc["artifact_sha256"],self.mp4_sha)
        self.assertEqual([r["role"] for r in doc["reviewers"]],
                         ["motion_sync","visual_child_safety"])
        self.assertFalse(doc["publication_approved"])

    def test_fake_technical_report_even_with_matching_hash_is_rejected(self):
        doc=json.loads(self.m10.read_text())
        doc["envelope_correlation"]=0.0
        self.m10.write_text(json.dumps(doc))
        with self.assertRaises(AVReviewError):
            self.review()
        self.assertFalse((self.root/"review").exists())

    def test_wrong_video_hash_or_same_checkpoint_never_runs_models(self):
        with self.assertRaises(AVReviewError):
            self.review(mp4_sha="e"*64)
        with self.assertRaises(AVReviewError):
            self.review(second=self.runners[0])
        self.assertFalse((self.root/"review").exists())

    def test_real_mp4_without_audio_is_rejected(self):
        silent=self.root/"video-only.mp4"
        subprocess.run([self.ffmpeg,"-v","error","-nostdin","-y",
            "-f","lavfi","-i","testsrc=size=384x216:rate=10:duration=3",
            "-an","-c:v","libx264","-pix_fmt","yuv420p",str(silent)],
            check=True,timeout=60,capture_output=True)
        with self.assertRaises(Exception):
            self.review(mp4=silent,mp4_sha=digest(silent))

    def test_current_pi_m10_m28_private_LTX_import_and_replay(self):
        h=Orchestration32("test_plan_cannot_advertise_public_permission")
        h.setUp();self.addCleanup(h.doCleanups)
        h.coord.pin(h.plan)
        voice=h.coord.tick(h.plan)
        leased=h.queue.claim(worker_id="fake-m37-voice",capabilities=["voice_synthesize"])
        self.assertEqual(leased["job_id"],voice["job_id"])
        h.queue.complete(job_id=leased["job_id"],worker_id="fake-m37-voice",
            generation=leased["generation"],result={
              "status":"VOICE_RENDERED_PENDING_QA","artifact_type":"wav",
              "artifact_sha256":self.wav_sha,
              "artifact_bytes":self.wav.stat().st_size,"publication_approved":False})
        h.scenes.reconcile()
        local_script=h.scripts[0]
        whisper=executable(self.root/"mock-m37-whisper",
            "import sys\nfrom pathlib import Path\na=sys.argv\n"
            "Path(a[a.index('-of')+1]+'.txt').write_text("+
            repr(local_script.read_text())+",encoding='utf-8')\n")
        self.audio.run_review(job_id=leased["job_id"],script=local_script,
            script_sha=digest(local_script),whisper_binary=str(whisper),
            out_dir=self.root/"voice-review",wav=self.wav,wav_sha=self.wav_sha)
        voice_decision=import_voice_review(queue=h.queue,series_id="colors-ar",
            episode=1,scene=1,report_dir=self.root/"voice-review",
            rights_file=self.audio.rights,runner_key=self.audio.key,execute=True)
        self.assertEqual(voice_decision["status"],
                         "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY")
        ltx=h.scenes.queue_stage("colors-ar",1,1,"ltx_animate","mock_m37_ltx")
        claimed=h.queue.claim(worker_id="fake-m37-video",capabilities=["ltx_animate"])
        self.assertEqual(claimed["job_id"],ltx)
        h.queue.complete(job_id=ltx,worker_id="fake-m37-video",
             generation=claimed["generation"],result={
                 "status":"A2V_RENDERED_PENDING_QA","artifact_type":"mp4",
                 "artifact_sha256":self.mp4_sha,"artifact_bytes":self.mp4.stat().st_size,
                 "publication_approved":False})
        h.scenes.reconcile()
        result=self.review(job_id=ltx,script=local_script,
            script_sha=digest(local_script))
        folder=self.root/"review"
        dry=import_synchronized(queue=h.queue,series_id="colors-ar",
            episode=1,scene=1,report_dir=folder,m10_report=self.m10,
            rights_file=self.rights,runner_key=self.key)
        self.assertEqual(dry["status"],"M37_SIGNED_CURRENT_PI_PREFLIGHT_NO_WRITES")
        with self.assertRaises(AVImportError):
            import_synchronized(queue=h.queue,series_id="colors-ar",
                episode=1,scene=1,report_dir=folder,m10_report=self.m10,
                rights_file=self.rights,
                runner_key=b"BAD_PRIVATE_KEY_DIFFERENT_FROM_ORIGINAL_XXX",
                execute=True)
        h.queue.set_paused(True)
        with self.assertRaises(AVImportError):
            import_synchronized(queue=h.queue,series_id="colors-ar",
                episode=1,scene=1,report_dir=folder,m10_report=self.m10,
                rights_file=self.rights,runner_key=self.key,execute=True)
        h.queue.set_paused(False)
        lineage=folder/"av_runner_lineage.json"
        original=lineage.read_bytes()
        damaged=json.loads(original)
        damaged["reviewers"][0]["model_sha256"]="d"*64
        lineage.write_text(json.dumps(damaged))
        with self.assertRaises(AVImportError):
            import_synchronized(queue=h.queue,series_id="colors-ar",
                episode=1,scene=1,report_dir=folder,m10_report=self.m10,
                rights_file=self.rights,runner_key=self.key,execute=True)
        lineage.write_bytes(original)
        applied=import_synchronized(queue=h.queue,series_id="colors-ar",
            episode=1,scene=1,report_dir=folder,m10_report=self.m10,
            rights_file=self.rights,runner_key=self.key,execute=True)
        self.assertEqual(applied["status"],"M37_AI_LTX_APPROVED_INTERNAL_PRIVATE_ONLY")
        self.assertFalse(applied["public_release_authorized"])
        replay=import_synchronized(queue=h.queue,series_id="colors-ar",
            episode=1,scene=1,report_dir=folder,m10_report=self.m10,
            rights_file=self.rights,runner_key=self.key,execute=True)
        self.assertEqual(replay["status"],"M37_ALREADY_APPROVED_PRIVATE_ONLY")
        self.assertEqual(h.coord.status(h.plan)["next_action"],"NEXT_VOICE")
        with h.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_scene_ai_reviews WHERE stage='ltx_animate'""").fetchone()[0],1)


if __name__=="__main__":
    unittest.main()
