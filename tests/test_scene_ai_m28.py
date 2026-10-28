"""M28: actual FFmpeg WAV signal + synthetic ASR/vision receipts, no YouTube.

The source ASR and two reviewer receipts in these tests are deliberately
synthetic fixtures, NOT real model outputs. Real decoded WAV and live
Pi SQLite state are exercised. A separate Google/Mac qualification remains.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import wave

from kidsstudio.studio_scenes import SceneLedger, SceneError
from kidsstudio.scene_ai_qa import SceneAIGate, _word_error_rate, ROLE_CHECKS
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.voice_qa import inspect_voice


def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class SceneAIQA28(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m28-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        self.assertTrue(self.ffmpeg and self.ffprobe,"M28 requires actual FFmpeg/FFprobe")
        self.script=self.root/"scene1.txt"
        self.script.write_text("الكرة حمراء والولد يتعلم اللون الأحمر.",encoding="utf-8")
        self.script_sha=sha(self.script)
        self.episode=self.root/"episode.txt"
        self.episode.write_text("درس الألوان للأطفال: الأحمر ثم الأزرق.",encoding="utf-8")
        self.queue=StudioQueue(self.root/"pi.sqlite")
        self.queue.initialize()
        self.manager=SeriesManager(self.queue)
        self.manager.initialize()
        self.manager.create_series("colors-ar","Colors","ar",
            [{"title":"Red","objective":"Identify red objects"}],activate=True)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=?,owner_review_note=? WHERE series_id='colors-ar'
                AND ordinal=1""",(sha(self.episode),"Synthetic scene plan test only"))
            self.manager._audit(db,"colors-ar",1,"SCRIPT_APPROVED_BY_OWNER")
        self.scenes=SceneLedger(self.queue)
        self.scenes.initialize()
        plan=self.root/"plan.json"
        plan.write_text(json.dumps({"schema_version":1,
            "series_id":"colors-ar","episode_number":1,
            "episode_script_sha256":sha(self.episode),
            "scenes":[
                {"scene":1,"script_sha256":self.script_sha,
                 "objective":"Recognize red"},
                {"scene":2,"script_sha256":"e"*64,
                 "objective":"Recognize blue"}]
        }))
        self.scenes.register_plan(plan)
        self.ai=SceneAIGate(self.queue)
        self.ai.initialize()
        self.wav=self.root/"narration.wav"
        with wave.open(str(self.wav),"wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            buf=b"".join(struct.pack("<h",int(math.sin(2*math.pi*440*k/48000)*10000))
                for k in range(48000*2))
            w.writeframes(buf)
        self.voice_job=self.scenes.queue_first_voice_pilot(
            "colors-ar",1,"pilot_voice_original",sha(plan),
            "Synthetic first voice pilot authorized only inside offline test")
        lease=self.queue.claim(worker_id="mac-test",capabilities=["voice_synthesize"])
        self.queue.complete(job_id=lease["job_id"],worker_id="mac-test",
            generation=lease["generation"],result={
                "status":"VOICE_RENDERED_PENDING_QA",
                "artifact_sha256":sha(self.wav),"artifact_bytes":self.wav.stat().st_size,
                "artifact_type":"wav","publication_approved":False})
        self.scenes.reconcile()
        self.tech=self.root/"m23.json"
        tech=inspect_voice(self.wav,sha(self.wav),self.voice_job,self.script_sha,
                           ffprobe=self.ffprobe,ffmpeg=self.ffmpeg)
        self.assertEqual(tech["status"],"VOICE_TECH_PASS_OWNER_LISTENING_PENDING")
        self.tech.write_text(json.dumps(tech))
        self.scenes.register_voice_technical("colors-ar",1,1,self.tech)
        self.proof=self.root/"rights_proof.txt"
        self.proof.write_text("Synthetic production receipt (not a real voice license), created by test only.")
        self.rights=self.root/"stage_rights.json"
        self.obs=self.root/"observed.json"
        self.review=self.root/"reviews.json"
        self.asr=self.root/"asr.txt"
        self.asr.write_text(self.script.read_text(encoding="utf-8"),encoding="utf-8")
        self.stage="voice_synthesize"
        self.artifact_sha=sha(self.wav)
        self.job=self.voice_job
        self.technical_sha=sha(self.tech)
        self.source_voice_sha=None

    def make_evidence(self, stage=None, broken=None):
        stage=stage or self.stage
        rights={"schema_version":1,"artifact_sha256":self.artifact_sha,
            "source_kind":"original_created",
            "source_proof_sha256":sha(self.proof),
            "source_proof_file":str(self.proof),
            "usage_scope":"commercial_youtube_kids",
            "documented":True,"rights_adjudicated":False,
            "publication_approved":False}
        if broken=="rights":rights["usage_scope"]="unknown"
        self.rights.write_text(json.dumps(rights))
        observations={"schema_version":1,"stage":stage,
            "artifact_sha256":self.artifact_sha,
            "script_sha256":self.script_sha,
            "model_execution_verified":False,"publishing_approved":False}
        if stage=="voice_synthesize":
            observations.update({
                "script_file":str(self.script),"asr_file":str(self.asr),
                "asr_model_id":"not-really-asr-test-fixture",
                "asr_provider_id":"separate_asr_provider",
                "asr_job_id":"f"*32})
        else:
            observations.update({
                "source_voice_sha256":self.source_voice_sha,
                "frame_manifest_sha256":self.frame_manifest_sha,
                "frame_manifest_file":str(self.frame_manifest),
                "frame_count":3,
                "visual_review_model_id":"synthetic-model-only"})
        self.obs.write_text(json.dumps(observations))
        reviews=[]
        for i,(role,checks) in enumerate(ROLE_CHECKS[stage].items()):
            reviews.append({
                "role":role,"provider_id":("arabic_prov" if i==0 else "vision_prov"),
                "model_id":("test-ai-one" if i==0 else "test-ai-two"),
                "evidence_sha256":sha(self.obs),
                "checks":{c:{"decision":"PASS",
                             "evidence":"Simulated-only report in unit test, never real evaluation: "+c}
                          for c in sorted(checks)},
                "summary":"Synthetic unit-test observation only; real inference not performed",
                "publication_approved":False,
            })
        if broken=="provider":
            reviews[1]["provider_id"]=reviews[0]["provider_id"]
        if broken=="review":
            reviews[0]["checks"][next(iter(reviews[0]["checks"]))]["decision"]="UNSURE"
        result={"schema_version":1,"series_id":"colors-ar","episode_number":1,
            "scene":1,"stage":stage,"job_id":self.job,
            "script_sha256":self.script_sha,
            "artifact_sha256":self.artifact_sha,
            "observations_sha256":sha(self.obs),"rights_sha256":sha(self.rights),
            "technical_sha256":self.technical_sha,"reviewers":reviews,
            "publication_approved":False}
        if broken=="digest":result["artifact_sha256"]="0"*64
        self.review.write_text(json.dumps(result))
        return dict(report_file=self.review,observation_file=self.obs,rights_file=self.rights)

    def register(self, stage=None, broken=None):
        args=self.make_evidence(stage,broken)
        return self.ai.register("colors-ar",1,1,stage or self.stage,**args)

    def test_automatic_voice_gate_needs_independent_asr_and_no_human_flag(self):
        with self.assertRaises(SceneError):
            self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        data=self.register()
        self.assertEqual(data["status"],"AI_SCENE_READY_PRIVATE_ONLY")
        self.assertAlmostEqual(data["word_error_rate"],0.0,places=4)
        self.assertFalse(data["owner_stage_review_required"])
        result=self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        self.assertTrue(result["owner_post_private_video_review_required"])
        self.assertFalse(result["public_release_authorized"])
        status=self.scenes.snapshot("colors-ar",1)
        self.assertEqual(status["scenes"][0]["stages"]["voice_synthesize"]["state"],
                         "QA_APPROVED")
        # No --owner-listened was ever supplied.
        self.assertIsInstance(self.scenes.queue_stage(
            "colors-ar",1,1,"ltx_animate","ltx_test"),str)

    def test_arabic_normalization_and_bad_asr_word_coverage(self):
        self.assertEqual(_word_error_rate("الأحمر أزرق", "الاحمر ازرق"),0.0)
        self.asr.write_text("شيء مختلف تماماً عن النص المطلوب هنا",encoding="utf-8")
        data=self.register()
        self.assertEqual(data["status"],"AI_SCENE_NEEDS_FIX")
        self.assertGreater(data["word_error_rate"],0.1)
        with self.assertRaises(SceneError):
            self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        with self.assertRaises(SceneError):
            self.scenes.queue_stage("colors-ar",1,1,"ltx_animate","ltx_test")

    def test_independent_provider_required(self):
        with self.assertRaises(SceneError):
            self.register(broken="provider")

    def test_rights_proof_must_exist_and_have_commercial_scope(self):
        with self.assertRaises(SceneError):
            self.register(broken="rights")
        self.make_evidence()
        self.proof.unlink()
        with self.assertRaises(SceneError):
            self.ai.register("colors-ar",1,1,
                "voice_synthesize",report_file=self.review,
                observation_file=self.obs,rights_file=self.rights)

    def test_no_fake_ai_or_missing_models_can_sneak_through(self):
        with self.assertRaises(SceneError):
            self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        args=self.make_evidence()
        self.obs.unlink()
        with self.assertRaises(SceneError):
            self.ai.register("colors-ar",1,1,"voice_synthesize",**args)

    def test_unsure_blocks_without_owner_interrupt(self):
        data=self.register(broken="review")
        self.assertEqual(data["status"],"AI_SCENE_NEEDS_FIX")
        with self.assertRaises(SceneError):
            self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        self.assertFalse(data["public_release_authorized"])

    def test_wrong_sha_and_duplicate_report_denied(self):
        with self.assertRaises(SceneError):
            self.register(broken="digest")
        self.register()
        with self.assertRaises(SceneError):
            self.register()

    def ready_for_ltx(self):
        self.register()
        self.ai.auto_approve("colors-ar",1,1,"voice_synthesize")
        self.source_voice_sha=sha(self.wav)
        ltxjob=self.scenes.queue_stage("colors-ar",1,1,"ltx_animate","ltx_model_test")
        leased=self.queue.claim(worker_id="mac-stage",capabilities=["ltx_animate"])
        self.assertEqual(leased["job_id"],ltxjob)
        video=self.root/"a2v.mp4"
        video.write_bytes(b"SYNTHETIC-NONVIDEO"*400)
        self.queue.complete(job_id=ltxjob,worker_id="mac-stage",
            generation=leased["generation"],result={
                "status":"A2V_RENDERED_PENDING_QA","artifact_type":"mp4",
                "artifact_sha256":sha(video),"artifact_bytes":video.stat().st_size,
                "publication_approved":False})
        self.scenes.reconcile()
        aud=self.root/"m10_audio.json"
        aud.write_text(json.dumps({
            "schema_version":1,
            "status":"AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED",
            "voice_sha256":self.source_voice_sha,"a2v_sha256":sha(video),
            "voice_seconds":2.0,"a2v_audio_seconds":2.0,
            "duration_close":True,"envelope_correlation":0.96,
            "estimated_lag_seconds":0.01,"energy_present":True,
            "audio_content_identity_proven":False,"speaker_identity_proven":False,
            "lip_sync_verified":False,"owner_audiovisual_review_required":True,
            "publishing_approved":False}))
        self.scenes.register_audio("colors-ar",1,1,aud)
        self.stage="ltx_animate"
        self.job=ltxjob
        self.artifact_sha=sha(video)
        self.technical_sha=sha(aud)
        # Static test PNG files. Only the evidence binding is tested, NOT
        # actual video/PNG frames captured by ffmpeg or AI visual inference.
        frame_entries=[]
        for i in range(3):
            path=self.root/f"frame_{i}.png"
            path.write_bytes(bytes.fromhex("89504e470d0a1a0a")+bytes([i])*32)
            frame_entries.append({"timestamp_seconds":float(i),"file":str(path),
                                  "sha256":sha(path)})
        self.frame_manifest=self.root/"frames.json"
        self.frame_manifest.write_text(json.dumps({
            "schema_version":1,"a2v_sha256":sha(video),"frames":frame_entries}))
        self.frame_manifest_sha=sha(self.frame_manifest)

    def test_automatic_ltx_requires_m10_and_three_frames_no_owner_review(self):
        self.ready_for_ltx()
        result=self.register()
        self.assertEqual(result["status"],"AI_SCENE_READY_PRIVATE_ONLY")
        done=self.ai.auto_approve("colors-ar",1,1,"ltx_animate")
        self.assertTrue(done["owner_post_private_video_review_required"])
        s=self.scenes.snapshot("colors-ar",1)
        self.assertEqual(s["scenes"][0]["stages"]["ltx_animate"]["state"],
                         "QA_APPROVED")

    def test_missing_ltx_frame_file_rejected(self):
        self.ready_for_ltx()
        args=self.make_evidence()
        (self.root/"frame_1.png").unlink()
        with self.assertRaises(SceneError):
            self.ai.register("colors-ar",1,1,"ltx_animate",**args)

    def test_changed_ltx_audio_continuity_digest_rejected(self):
        self.ready_for_ltx()
        args=self.make_evidence()
        data=json.loads(self.review.read_text())
        data["technical_sha256"]="a"*64
        self.review.write_text(json.dumps(data))
        with self.assertRaises(SceneError):
            self.ai.register("colors-ar",1,1,"ltx_animate",**args)


if __name__=="__main__":
    unittest.main()
