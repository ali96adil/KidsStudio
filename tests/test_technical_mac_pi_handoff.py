"""PRIVATE-first Mac→Pi QA handoff; mock SSH only, no owner review required."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shlex
import tempfile
import types
import unittest

from kidsstudio.mac_pilot_evidence import record_mac_pilot_review
from kidsstudio.pi_transfer_receive import receive_private_video
from kidsstudio.technical_mac_pi_handoff import (
    TechnicalPrivateHandoffError, inspect_technical_private_candidate,
    transfer_technical_private_pilot, main,
)


class TechnicalPrivateHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.ready = base / "ready"
        self.proof = base / "qualification"
        self.pi = base / "pi"
        for folder in (self.ready, self.proof, self.pi):
            folder.mkdir(mode=0o700)
        self.movie = self.ready / "colors_ar_01_test_technical.mp4"
        self.movie.write_bytes(b"CI_TEST_NOT_AN_EPISODE" * 1000)
        self.movie.chmod(0o600)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.name = self.movie.stem + ".evidence.json"
        self.sidecar = {
            "schema_version": 1,
            "status": "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
            "episode_id": "colors_ar_01",
            "video_name": self.movie.name,
            "video_sha256": self.sha,
            "video_bytes": self.movie.stat().st_size,
            "duration_seconds": 24.0,
            "technical_preflight": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
            "faststart_moov_before_mdat": True,
            "video_samples_decoded": 3,
            "audio_samples_decoded": 2,
            "source_commit": "c" * 40,
            "source_checkout_clean": True,
            "host_role": "mac-render",
            "reported_host_system": "Darwin",
            "host_qualification": "SUPERVISED_TESTS_READY",
            "full_video_owner_review_pending": True,
            "arabic_voice_owner_review_pending": True,
            "reviewer_identity_authenticated": False,
            "actual_host_identity_authenticated": False,
            "real_mac_pi_transfer_test": "NOT_RUN",
            "real_youtube_upload_test": "NOT_RUN",
            "production_approved": False,
            "publication_approved": False,
        }
        self.write_sidecar()
        self.calls = []

    def write_sidecar(self):
        path = self.proof / self.name
        path.write_text(json.dumps(self.sidecar), encoding="utf8")
        path.chmod(0o600)

    def proof_report(self):
        return inspect_technical_private_candidate(
            video_root=str(self.ready), evidence_root=str(self.proof),
            evidence_name=self.name)

    def fake_ssh(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertEqual(argv[:2], ["ssh", "-T"])
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("BatchMode=yes", argv)
        cmd = shlex.split(argv[-1])
        self.assertEqual(cmd[:3], [
            "python3", "-m", "kidsstudio.pi_transfer_receive"])
        def val(flag):
            return cmd[cmd.index(flag) + 1]
        result = receive_private_video(
            destination_root=self.pi,
            destination_name=val("--destination-name"),
            expected_sha256=val("--expected-sha256"),
            expected_bytes=int(val("--expected-bytes")),
            source=kwargs["stdin"])
        kwargs["stdout"].write(json.dumps(result).encode("utf8"))
        return types.SimpleNamespace(returncode=0)

    def transfer(self, **change):
        args = dict(
            video_root=str(self.ready), evidence_root=str(self.proof),
            evidence_name=self.name, pi_host="pi.local",
            pi_user="pi", runner=self.fake_ssh)
        args.update(change)
        return transfer_technical_private_pilot(**args)

    def test_unreviewed_but_technically_qualified_video_is_eligible(self):
        self.assertEqual(len(list(self.proof.glob("*.review.*.json"))), 0)
        proof = self.proof_report()
        self.assertEqual(proof["status"],
                         "MAC_PI_TECHNICAL_QA_VERIFIED_OWNER_REVIEW_PENDING")
        self.assertTrue(proof["owner_full_video_review_pending"])
        self.assertTrue(proof["owner_arabic_voice_review_pending"])
        self.assertFalse(proof["publication_approved"])

    def test_default_transfer_is_preview_with_zero_ssh(self):
        report = self.transfer()
        self.assertEqual(report["status"], "MAC_PI_QA_ONLY_TRANSFER_PREVIEW_NO_SSH")
        self.assertFalse(report["ssh_connection_performed"])
        self.assertTrue(report["owner_review_pending_until_youtube_private_draft"])
        self.assertFalse(report["local_acceptance_required_before_private_transfer"])
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.pi.iterdir()), [])

    def test_explicit_ssh_uses_real_atomic_pi_receiver_in_local_simulation(self):
        report = self.transfer(execute=True)
        self.assertEqual(report["status"], "MAC_PI_QA_ONLY_PRIVATE_TRANSFER_VERIFIED")
        self.assertTrue(report["ssh_connection_performed"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.pi / self.movie.name).read_bytes(),
                         self.movie.read_bytes())
        self.assertFalse(report["youtube_upload_submitted"])
        self.assertFalse(report["publication_approved"])

    def test_local_revision_note_does_not_require_pre_upload_human_acceptance(self):
        record_mac_pilot_review(
            evidence_root=str(self.proof), evidence_name=self.name,
            video_root=str(self.ready), video_name=self.movie.name,
            expected_sha256=self.sha,
            review_outcome="REVISION_REQUIRED",
            reviewer_notes="Optional prior local note", reviewed_full_video=False,
            reviewed_arabic_voice=False)
        report = self.transfer()
        self.assertEqual(report["status"], "MAC_PI_QA_ONLY_TRANSFER_PREVIEW_NO_SSH")
        self.assertEqual(self.calls, [])

    def test_missing_source_proof_blocks_before_ssh(self):
        (self.proof / self.name).unlink()
        with self.assertRaises(TechnicalPrivateHandoffError):
            self.transfer(execute=True)
        self.assertEqual(self.calls, [])

    def test_video_mutated_after_qualification_blocks_before_ssh(self):
        self.movie.write_bytes(b"modified")
        with self.assertRaises(TechnicalPrivateHandoffError):
            self.transfer(execute=True)
        self.assertEqual(self.calls, [])

    def test_wrong_digest_and_size_fail_closed(self):
        for field, bad in (("video_sha256", "0"*64),
                           ("video_bytes", 5)):
            with self.subTest(field=field):
                before = self.sidecar[field]
                self.sidecar[field] = bad
                self.write_sidecar()
                with self.assertRaises(TechnicalPrivateHandoffError):
                    self.proof_report()
                self.sidecar[field] = before
                self.write_sidecar()

    def test_missing_media_codec_or_host_checks_block(self):
        baseline = dict(self.sidecar)
        for field, bad in (
            ("host_role", "pi-private-handoff"),
            ("reported_host_system", "Linux"),
            ("host_qualification", "SUPERVISED_TESTS_BLOCKED"),
            ("faststart_moov_before_mdat", False),
            ("video_samples_decoded", 0),
            ("audio_samples_decoded", 1),
            ("full_video_owner_review_pending", False),
            ("arabic_voice_owner_review_pending", False),
            ("actual_host_identity_authenticated", True),
            ("reviewer_identity_authenticated", True),
            ("technical_preflight", "FAILED"),
            ("source_checkout_clean", False),
            ("source_commit", "not-40-hex"),
            ("production_approved", True),
        ):
            with self.subTest(field=field):
                self.sidecar[field] = bad
                self.write_sidecar()
                with self.assertRaises(TechnicalPrivateHandoffError):
                    self.proof_report()
                self.sidecar = dict(baseline)
                self.write_sidecar()

    def test_private_path_checks_reject_public_or_symlink_sidecar(self):
        path = self.proof / self.name
        path.chmod(0o644)
        with self.assertRaises(TechnicalPrivateHandoffError):
            self.proof_report()
        path.chmod(0o600)
        saved = self.proof / "private-original.json"
        path.rename(saved)
        path.symlink_to(saved)
        with self.assertRaises(TechnicalPrivateHandoffError):
            self.proof_report()

    def test_different_pi_destination_does_not_invoke_ssh(self):
        with self.assertRaises(ValueError):
            self.transfer(execute=True, pi_host="pi;evil")
        self.assertEqual(self.calls, [])

    def test_execute_must_be_strict_boolean(self):
        with self.assertRaises(TechnicalPrivateHandoffError):
            self.transfer(execute=1)

    def test_cli_preview_does_not_call_network_or_leak_local_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([
                "--video-root", str(self.ready),
                "--evidence-root", str(self.proof),
                "--evidence-name", self.name,
                "--pi-host", "pi.local", "--pi-user", "pi"])
        self.assertEqual(exit_code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"],
                         "MAC_PI_QA_ONLY_TRANSFER_PREVIEW_NO_SSH")
        self.assertFalse(report["ssh_connection_performed"])
        self.assertNotIn(str(self.ready), output.getvalue())

    def test_cli_invalid_proof_blocks_without_network(self):
        self.movie.write_bytes(b"tampered")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([
                "--video-root", str(self.ready),
                "--evidence-root", str(self.proof),
                "--evidence-name", self.name,
                "--pi-host", "pi.local", "--pi-user", "pi"])
        self.assertEqual(exit_code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"],
                         "MAC_PI_QA_ONLY_TRANSFER_BLOCKED_OR_UNCERTAIN")
        self.assertEqual(report["ssh_connection_performed"], False)
        self.assertNotIn(str(self.ready), output.getvalue())


if __name__ == "__main__":
    unittest.main()
