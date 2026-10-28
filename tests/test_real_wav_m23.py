"""M23 actual FFmpeg WAV integrity tests plus M22 owner QA ledger gating.

All PCM is synthesized from test tones on a disposable Linux CI worker.
No Chatterbox, personal audio, voice cloning, remote models or publication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from kidsstudio.voice_qa import CHECKS, VoiceQAError, inspect_voice
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_scenes import SceneLedger, SceneError


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealVoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kidsstudio-m23-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.assertTrue(self.ffmpeg and self.ffprobe,
                        "M23 CI needs real FFmpeg and FFprobe")
        self.job = "a" * 32
        self.script_sha = "b" * 64

    def make_wav(self, name="narration", kind="tone"):
        path=self.root/(name+".wav")
        src = {
            "tone": "sine=frequency=440:sample_rate=48000:duration=1.5",
            "silence": "anullsrc=r=48000:cl=mono:d=1.5",
            "clipped": "aevalsrc=sgn(sin(2*PI*440*t)):s=48000:d=1.5",
        }[kind]
        subprocess.run([
            self.ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-n",
            "-f","lavfi","-i",src,"-t","1.5","-ac","1",
            "-c:a","pcm_s16le",str(path),
        ],check=True,capture_output=True,timeout=40)
        return path

    def inspect(self,path,checksum=None):
        return inspect_voice(path,checksum or sha(path),self.job,self.script_sha,
                             ffprobe=self.ffprobe,ffmpeg=self.ffmpeg)

    def prepare_ledger(self, wav: Path):
        q=StudioQueue(self.root/"pi.sqlite")
        q.initialize()
        manager=SeriesManager(q)
        manager.initialize()
        manager.create_series("colors-ar","Original colors","ar",[
            {"title":"Red","objective":"Recognize red color"}],activate=True)
        with q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=?,owner_review_note=? WHERE
                series_id='colors-ar' AND ordinal=1""",
                ("c"*64,"Synthetic owner approval for unit-test only"))
            manager._audit(db,"colors-ar",1,"SCRIPT_APPROVED_BY_OWNER")
        scenes=SceneLedger(q)
        scenes.initialize()
        plan=self.root/"plan.json"
        plan.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"episode_script_sha256":"c"*64,
            "scenes":[
                {"scene":1,"script_sha256":self.script_sha,
                 "objective":"Recognize a red object"},
                {"scene":2,"script_sha256":"d"*64,
                 "objective":"Recognize a blue object"}
            ]
        }))
        scenes.register_plan(plan)
        job_id=scenes.queue_first_voice_pilot(
            "colors-ar",1,"original_voice_01",sha(plan),
            "Synthetic M23 owner approval for test fixture only")
        lease=q.claim(worker_id="mac-voice-test",
                      capabilities=["voice_synthesize"])
        self.assertEqual(lease["job_id"],job_id)
        q.complete(job_id=job_id,worker_id="mac-voice-test",
                   generation=lease["generation"],result={
            "status":"VOICE_RENDERED_PENDING_QA",
            "artifact_sha256":sha(wav),
            "artifact_bytes":wav.stat().st_size,
            "artifact_type":"wav",
            "publication_approved":False,
        })
        scenes.reconcile()
        return q,scenes,job_id

    def report_file(self, report, filename="qa.json"):
        path=self.root/filename
        path.write_text(json.dumps(report,sort_keys=True),encoding="utf-8")
        return path

    def test_real_pcm_tone_passes_all_m23_checks_but_no_human_review(self):
        path=self.make_wav()
        before=sha(path)
        result=self.inspect(path)
        self.assertEqual(result["status"],"VOICE_TECH_PASS_OWNER_LISTENING_PENDING",
                         json.dumps(result,sort_keys=True))
        self.assertEqual(set(result["checks"]),set(CHECKS))
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(result["owner_listening_performed"])
        self.assertFalse(result["commercial_rights_verified"])
        self.assertFalse(result["publishing_approved"])
        self.assertAlmostEqual(result["duration_seconds"],1.5,delta=0.1)
        self.assertEqual(sha(path),before)

    def test_silence_and_clipping_rejected_without_any_approval(self):
        silence=self.inspect(self.make_wav("silence","silence"))
        self.assertEqual(silence["status"],"VOICE_TECH_FAILED")
        self.assertFalse(silence["checks"]["audible_energy"])
        clipped=self.inspect(self.make_wav("clip","clipped"))
        self.assertEqual(clipped["status"],"VOICE_TECH_FAILED")
        self.assertFalse(clipped["checks"]["not_heavily_clipped"])
        self.assertFalse(clipped["publishing_approved"])

    def test_wrong_sha_never_decodes_and_corrupted_wav_errors(self):
        audio=self.make_wav()
        report=self.inspect(audio,checksum="0"*64)
        self.assertEqual(report["status"],"VOICE_TECH_FAILED")
        self.assertFalse(report["checks"]["media_sha256_matches"])
        self.assertFalse(report["checks"]["full_pcm_decode"])
        audio.write_bytes(b"invalid-wave-not-media"*15)
        with self.assertRaises(VoiceQAError):
            self.inspect(audio)

    def test_m22_scene1_cannot_approve_before_qa_and_human_listening(self):
        wav=self.make_wav()
        queue,ledger,job_id=self.prepare_ledger(wav)
        note="Owner listened in full and approved the narration after review"
        with self.assertRaises(SceneError):
            ledger.approve("colors-ar",1,1,"voice_synthesize",sha(wav),
                           note,owner_listened=True)
        report=self.inspect(wav)
        report["job_id"]=job_id
        report_file=self.report_file(report)
        status=ledger.register_voice_technical("colors-ar",1,1,report_file)
        self.assertEqual(status["status"],
                         "VOICE_TECH_REGISTERED_AWAITING_OWNER_LISTENING")
        with self.assertRaises(SceneError):
            ledger.approve("colors-ar",1,1,"voice_synthesize",sha(wav),note)
        with self.assertRaises(SceneError):
            ledger.register_voice_technical("colors-ar",1,1,report_file)
        # Synthetic owner event, not evidence of real acoustic inspection.
        ledger.approve("colors-ar",1,1,"voice_synthesize",sha(wav),
                       note,owner_listened=True)
        snapshot=ledger.snapshot("colors-ar",1)
        self.assertEqual(snapshot["scenes"][0]["stages"]["voice_synthesize"]["state"],
                         "QA_APPROVED")
        self.assertEqual(ledger.queue_stage(
            "colors-ar",1,1,"ltx_animate","synthetic_ltx_01") is not None, True)

    def test_mismatched_wav_technical_report_or_fabricated_status_denied(self):
        wav=self.make_wav()
        _,ledger,job_id=self.prepare_ledger(wav)
        report=self.inspect(wav)
        report["job_id"]=job_id
        report["voice_sha256"]="e"*64
        with self.assertRaises(SceneError):
            ledger.register_voice_technical(
                "colors-ar",1,1,self.report_file(report,"mismatch.json"))
        report["voice_sha256"]=sha(wav)
        report["checks"]["full_pcm_decode"]=False
        with self.assertRaises(SceneError):
            ledger.register_voice_technical(
                "colors-ar",1,1,self.report_file(report,"forged.json"))
        report["checks"]["full_pcm_decode"]=True
        report["owner_listening_performed"]=True
        with self.assertRaises(SceneError):
            ledger.register_voice_technical(
                "colors-ar",1,1,self.report_file(report,"human-faked.json"))

    def test_failed_silent_qa_never_unlocks_voice_or_animation(self):
        wav=self.make_wav("silence","silence")
        _,ledger,job_id=self.prepare_ledger(wav)
        report=self.inspect(wav)
        report["job_id"]=job_id
        with self.assertRaises(SceneError):
            ledger.register_voice_technical(
                "colors-ar",1,1,self.report_file(report))
        with self.assertRaises(SceneError):
            ledger.approve("colors-ar",1,1,"voice_synthesize",sha(wav),
                "Owner should not approve technically silent WAV",owner_listened=True)
        with self.assertRaises(SceneError):
            ledger.queue_stage("colors-ar",1,1,"ltx_animate","ltx_01")


if __name__=="__main__":
    unittest.main()
