"""M36 synthetic Pi/real FFmpeg frames/mock Ollama unsigned-audio negative tests.

The true M10 report in this fixture is SYNTHETIC; the MP4 contains video
only. These tests must never claim actual lip-sync or qualified model QA.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import unittest

from kidsstudio.real_media_evidence import digest
from kidsstudio.local_vision_review import sign_after_m10, LocalVisionError
from kidsstudio.visual_review_import import import_visual_review, VisionImportError
from test_audio_review_import_m35 import AudioReviewImport35
from test_local_vision_m29 import VisionBridgeTests


class PiVisualReviewBridge36(unittest.TestCase):
    def setUp(self):
        audio = AudioReviewImport35(
            "test_read_only_preflight_then_exact_signed_import_then_idempotent_replay")
        audio.setUp()
        self.addCleanup(audio.doCleanups)
        self.audio = audio
        audio.run_import(execute=True)
        self.host = audio.host
        self.voice_sha = digest(audio.audio.wav)

        vision = VisionBridgeTests("test_real_source_frames_go_to_two_independent_local_models")
        vision.setUp()
        self.addCleanup(vision.doCleanups)
        self.vision = vision
        self.job_id = self.host.scenes.queue_stage(
            "colors-ar",1,1,"ltx_animate","synthetic_ltx_recipe")
        leased = self.host.queue.claim(worker_id="synthetic-m36-mac",
            capabilities=["ltx_animate"])
        self.assertEqual(leased["job_id"],self.job_id)
        self.host.queue.complete(job_id=self.job_id,worker_id="synthetic-m36-mac",
            generation=leased["generation"],result={
                "status":"A2V_RENDERED_PENDING_QA",
                "artifact_type":"mp4",
                "artifact_sha256":digest(vision.mp4),
                "artifact_bytes":vision.mp4.stat().st_size,
                "publication_approved":False})
        self.host.scenes.reconcile()
        # This report is synthetic: M10 signal correlation is NOT computed
        # from an actual soundtrack. M36 must keep AV quality unapproved.
        m10 = json.loads(vision.m10.read_text())
        m10["voice_sha256"] = self.voice_sha
        vision.m10.write_text(json.dumps(m10))
        source = self.host.scripts[0]
        vision.execute_review(job_id=self.job_id,script=source,
            script_sha=digest(source),voice_sha=self.voice_sha)
        sign_after_m10(
            pending_report=vision.root/"vision"/"model_report_pending_m10.json",
            m10_report=vision.m10, expected_m10_sha=digest(vision.m10),
            rights_file=vision.rights,
            observation_file=vision.root/"vision"/"observations.json",
            attestation_key=vision.key,
            out_file=vision.root/"vision"/"signed_m28.json")

    def invoke(self,execute=False,**overrides):
        options=dict(queue=self.host.queue,series_id="colors-ar",
            episode=1,scene=1,report_dir=self.vision.root/"vision",
            m10_report=self.vision.m10,rights_file=self.vision.rights,
            runner_key=self.vision.key,execute=execute)
        options.update(overrides)
        return import_visual_review(**options)

    def technical_count(self):
        with self.host.queue._connection() as db:
            return db.execute("SELECT count(*) FROM studio_scene_audio_checks").fetchone()[0]

    def test_read_only_then_import_only_technical_m10_not_fake_lip_approval(self):
        pre=self.invoke()
        self.assertEqual(pre["status"],"M36_SIGNED_CURRENT_VISUAL_PREFLIGHT_NO_WRITES")
        self.assertEqual(self.technical_count(),0)
        out=self.invoke(execute=True)
        self.assertEqual(out["status"],"M36_VISUAL_REVIEW_AV_EVIDENCE_REQUIRED")
        self.assertTrue(out["technical_receipt_registered"])
        self.assertEqual(self.technical_count(),1)
        self.assertEqual(self.host.coord.status(self.host.plan)["next_action"],
                         "SCENE_LTX_PENDING_QA")
        snapshot=self.host.scenes.snapshot("colors-ar",1)
        self.assertEqual(snapshot["scenes"][0]["stages"]["ltx_animate"]["state"],
                         "PENDING_QA")
        with self.host.queue._connection() as db:
            present=db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                    AND name='studio_scene_ai_reviews'""").fetchone()
            if present:
                self.assertEqual(db.execute("""SELECT count(*) FROM studio_scene_ai_reviews
                    WHERE stage='ltx_animate'""").fetchone()[0],0)
        self.assertFalse(out["m31_repair_queued"])
        with self.host.queue._connection() as db:
            evidence=db.execute("""SELECT state, report_sha256, technical_sha256
                FROM studio_scene_visual_observations
                WHERE scene=1 AND ltx_job_id=?""",(self.job_id,)).fetchone()
            self.assertEqual(evidence["state"],"AV_AUDIO_REVIEW_REQUIRED")
            self.assertEqual(evidence["technical_sha256"],digest(self.vision.m10))
            self.assertEqual(evidence["report_sha256"],
                digest(self.vision.root/"vision"/"signed_m28.json"))
        from kidsstudio.studio_dashboard import build_snapshot
        overview=build_snapshot(self.host.queue)
        episode=next(e for e in overview["episodes"]
                     if e["series_id"]=="colors-ar" and e["ordinal"]==1)
        visual=episode["visual_av_review"]
        self.assertEqual(visual["state"],"M36_AV_AUDIO_REVIEW_REQUIRED")
        self.assertEqual(visual["scenes_waiting_audio_video"],1)
        self.assertFalse(visual["lip_sync_verified"])
        self.assertFalse(out["public_release_authorized"])

    def test_exact_m10_replay_no_duplicate_receipt(self):
        self.invoke(execute=True)
        another=self.invoke(execute=True)
        self.assertTrue(another["technical_receipt_registered"])
        self.assertEqual(self.technical_count(),1)
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute("""SELECT count(*) FROM
                studio_scene_visual_observations""").fetchone()[0],1)

    def test_changed_m10_bytes_or_rights_block_before_mutation(self):
        with self.assertRaises(VisionImportError):
            self.invoke(runner_key=b"other_valid_32_byte_key_for_tests_1234",
                        execute=True)
        assert self.technical_count()==0
        self.vision.m10.write_text("{}")
        with self.assertRaises(VisionImportError):
            self.invoke(execute=True)
        self.assertEqual(self.technical_count(),0)

    def test_live_job_and_pause_guard(self):
        self.host.queue.set_paused(True)
        with self.assertRaises(VisionImportError):
            self.invoke(execute=True)
        self.host.queue.set_paused(False)
        with self.assertRaises(VisionImportError):
            self.invoke(scene=2,execute=True)
        self.assertEqual(self.technical_count(),0)

    def test_forced_signed_lipsync_pass_is_rejected(self):
        signed_path=self.vision.root/"vision"/"signed_m28.json"
        doc=json.loads(signed_path.read_text())
        doc["reviewers"][0]["checks"]["lip_sync"]["decision"]="PASS"
        unsigned={k:v for k,v in doc.items() if k!="runner_attestation"}
        canonical=json.dumps(unsigned,sort_keys=True,ensure_ascii=False,
            separators=(",",":"),allow_nan=False).encode()
        doc["runner_attestation"]["hmac_sha256"]=hmac.new(
            self.vision.key,canonical,hashlib.sha256).hexdigest()
        signed_path.write_text(json.dumps(doc,ensure_ascii=False))
        with self.assertRaises(VisionImportError):
            self.invoke(execute=True)
        self.assertEqual(self.technical_count(),0)


if __name__=="__main__":
    unittest.main()
