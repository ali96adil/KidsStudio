"""M45 evidence inventory: actual FFmpeg sources, synthetic AI canaries.

A signed owner claim and synthetically perfect scores NEVER grant model
competence, YouTube PRIVATE upload or PUBLIC release. No on-device AI.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from kidsstudio.model_evidence_readiness import (
    EvidenceReadinessError,assess_model_evidence,main
)
from kidsstudio.real_media_evidence import digest
from test_model_pilot_probe_m43 import MacProbe43
from test_av_model_calibration_m39 import AVCrisisCanaries39


class OfflineEvidence45(unittest.TestCase):
    def setUp(self):
        owner=MacProbe43(
            "test_strict_default_checks_every_source_without_starting_a_model")
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        self.o=owner
        self.root=owner.root
        self.extra=dict(
            model=owner.x.model,model_sha256=owner.x.sha,
            origin_receipt=owner.origin_receipt,
            origin_sha256=digest(owner.origin_receipt),
            owner_key=owner.origin_key,
            resource_screen=owner.screen)

    def assess(self,**kw):
        args=self.extra.copy()
        args.update(kw)
        return assess_model_evidence(**args)

    def observed(self,*,video=False):
        if video:
            self.o.video(execute=True)
        else:
            self.o.call(execute=True)
        args=dict(adapter=self.o.adapter,
            pilot_metrics=self.o.probe_root/"pilot_metrics.json",
            pilot_metrics_sha256=digest(self.o.probe_root/"pilot_metrics.json"),
            model_diagnostic=self.o.probe_root/"m42_diagnostic.json",
            model_diagnostic_sha256=digest(
                self.o.probe_root/"m42_diagnostic.json"),
            script=self.o.x.av.script,wav=self.o.x.av.wav)
        if video:
            args.update(mp4=self.o.x.av.mp4,frames_manifest=self.o.x.frames,
                ffprobe=self.o.x.av.ffprobe)
        else:
            args.update(transcript=self.o.x.transcript)
        return args

    def test_base_offline_snapshot_never_implies_public_or_local_readiness(self):
        report=self.assess()
        self.assertEqual(report["status"],
                         "M45_EVIDENCE_INVENTORY_NOT_PRODUCTION_READY")
        self.assertTrue(report["owner_origin_attestation_checked"])
        self.assertTrue(report["resource_screen_passed_without_inference"])
        self.assertFalse(report["exact_pilot_observation_bytes_checked"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["source_provenance_independently_verified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertFalse(report["public_release_authorized"])
        self.assertIn("INDEPENDENT_CANARY_GROUND_TRUTH",report["blockers"])
        self.assertIn("EXPLICIT_OWNER_PUBLIC_RELEASE",report["blockers"])
        self.assertFalse(report["writes_performed"])
        self.assertNotIn(str(self.root),json.dumps(report))

    def test_voice_real_wav_fake_model_result_revalidated_bytes_only(self):
        report=self.assess(**self.observed())
        self.assertTrue(report["exact_pilot_observation_bytes_checked"])
        self.assertEqual(report["pilot_role"],"pronunciation")
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["mac_pi_hardware_qualified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertIn("REAL_ARABIC_VOICE_AND_VISUAL_COMPETENCE",report["blockers"])

    def test_video_real_soundbearing_mp4_and_frames_revalidated_bytes_only(self):
        report=self.assess(**self.observed(video=True))
        self.assertEqual(report["pilot_role"],"motion_sync")
        self.assertTrue(report["exact_pilot_observation_bytes_checked"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["public_release_authorized"])

    def test_mutated_source_or_forged_green_receipt_denied(self):
        args=self.observed()
        self.o.x.transcript.write_text("Tampered original transcript")
        with self.assertRaises(EvidenceReadinessError):
            self.assess(**args)
        self.o.x.transcript.write_text("هذه الكرة حمراء. لون الكرة أحمر.")
        metrics=Path(args["pilot_metrics"])
        record=json.loads(metrics.read_text())
        record["public_release_authorized"]=True
        metrics.write_text(json.dumps(record))
        args["pilot_metrics_sha256"]=digest(metrics)
        with self.assertRaises(EvidenceReadinessError):
            self.assess(**args)

    def test_mismatched_or_missing_owner_provenance_denied(self):
        args=self.observed()
        with self.assertRaises(EvidenceReadinessError):
            self.assess(**{**args,"owner_key":b"wrong"*10})
        with self.assertRaises(EvidenceReadinessError):
            self.assess(**{**args,"origin_receipt":None,
                           "origin_sha256":None,"owner_key":None})
        self.o.license.write_text(self.o.license.read_text()+" changed")
        with self.assertRaises(ValueError):
            self.assess(**args)

    def test_unrelated_pilot_paths_and_model_sha_cannot_replay(self):
        args=self.observed()
        with self.assertRaises(ValueError):
            self.assess(**{**args,"script":self.o.x.transcript})
        with self.assertRaises(ValueError):
            self.assess(**{**args,"model_sha256":"a"*64})

    def test_optional_canary_result_never_establishes_ground_truth(self):
        c=AVCrisisCanaries39(
            "test_readonly_checks_exact_media_without_running_models")
        c.setUp()
        self.addCleanup(c.doCleanups)
        score=c.evaluate(execute=True)
        score_file=self.root/"synthetic_canary_score.json"
        score_file.write_text(json.dumps(score))
        report=self.assess(av_canary_report=score_file,
            av_canary_sha256=digest(score_file),
            av_canary_manifest=c.manifest)
        self.assertTrue(report["four_canary_source_bytes_checked"])
        self.assertFalse(report["independent_canary_truth_qualified"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertIn("INDEPENDENT_CANARY_GROUND_TRUTH",report["blockers"])
        score["model_quality_qualified"]=True
        score_file.write_text(json.dumps(score))
        with self.assertRaises(EvidenceReadinessError):
            self.assess(av_canary_report=score_file,
                av_canary_sha256=digest(score_file),
                av_canary_manifest=c.manifest)

    def test_explicit_write_creates_private_not_ready_snapshot_once(self):
        target=self.root/"readiness_m45.json"
        before=self.assess(out=target)
        self.assertFalse(before["writes_performed"])
        self.assertFalse(target.exists())
        record=self.assess(out=target,execute=True)
        self.assertTrue(record["writes_performed"])
        self.assertEqual(record["qualified_gate_count"],0)
        self.assertTrue(target.is_file())
        self.assertEqual(record["report_sha256"],digest(target))
        self.assertEqual(json.loads(target.read_text())["status"],
            "M45_EVIDENCE_INVENTORY_NOT_PRODUCTION_READY")
        with self.assertRaises(EvidenceReadinessError):
            self.assess(out=target,execute=True)


if __name__=="__main__":
    unittest.main()
