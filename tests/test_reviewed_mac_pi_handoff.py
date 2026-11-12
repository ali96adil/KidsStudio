"""Tests for the operator-reviewed private Mac -> Pi handoff.

Every byte is local synthetic test data. SSH is replaced by a local fake
receiver; there is no network, Pi, OAuth, real child media or YouTube call.
"""
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
from unittest.mock import patch

from kidsstudio.mac_pilot_evidence import record_mac_pilot_review
from kidsstudio.pi_transfer_receive import receive_private_video
from kidsstudio.reviewed_mac_pi_handoff import (
    MacPiReviewGateError, inspect_reviewed_transfer_candidate,
    transfer_reviewed_mac_pilot, main,
)


class ReviewedHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.ready, self.proof, self.pi = (
            base / "ready", base / "proof", base / "pi")
        for directory in (self.ready, self.proof, self.pi):
            directory.mkdir(mode=0o700)
        self.video = self.ready / "colors_ar_01_test_xyz.mp4"
        self.video.write_bytes(b"synthetic video for a local test only" * 100)
        self.video.chmod(0o600)
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.evidence_name = "colors_ar_01_test_xyz.evidence.json"
        self.sidecar = {
            "schema_version": 1,
            "status": "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
            "episode_id": "colors_ar_01",
            "video_name": self.video.name,
            "video_sha256": self.sha,
            "video_bytes": self.video.stat().st_size,
            "duration_seconds": 24.0,
            "source_commit": "a" * 40,
            "source_checkout_clean": True,
            "technical_preflight": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
            "production_approved": False,
            "publication_approved": False,
            "real_mac_pi_transfer_test": "NOT_RUN",
            "real_youtube_upload_test": "NOT_RUN",
        }
        self.write_evidence()
        self.ssh_calls = []

    def write_evidence(self):
        file = self.proof / self.evidence_name
        file.write_text(json.dumps(self.sidecar), encoding="utf8")
        file.chmod(0o600)

    def review(self, outcome="ACCEPTED_PRIVATE", *,
               watched=True, listened=True):
        return record_mac_pilot_review(
            evidence_root=str(self.proof),
            evidence_name=self.evidence_name,
            video_root=str(self.ready), video_name=self.video.name,
            expected_sha256=self.sha, review_outcome=outcome,
            reviewer_notes="Owner's explicit local review assertion",
            reviewed_full_video=watched, reviewed_arabic_voice=listened,
        )

    def gate(self):
        return inspect_reviewed_transfer_candidate(
            video_root=str(self.ready), evidence_root=str(self.proof),
            evidence_name=self.evidence_name)

    def ssh_runner(self, argv, **kwargs):
        self.ssh_calls.append(argv)
        self.assertEqual(argv[:2], ["ssh", "-T"])
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("BatchMode=yes", argv)
        cmd = shlex.split(argv[-1])
        self.assertEqual(cmd[:3], [
            "python3", "-m", "kidsstudio.pi_transfer_receive"])
        name = cmd[cmd.index("--destination-name") + 1]
        expected_sha = cmd[cmd.index("--expected-sha256") + 1]
        expected_bytes = int(cmd[cmd.index("--expected-bytes") + 1])
        report = receive_private_video(
            destination_root=self.pi, destination_name=name,
            expected_sha256=expected_sha, expected_bytes=expected_bytes,
            source=kwargs["stdin"])
        kwargs["stdout"].write(json.dumps(report).encode("utf8"))
        return types.SimpleNamespace(returncode=0)

    def transfer(self, *, execute=False):
        return transfer_reviewed_mac_pilot(
            video_root=str(self.ready), evidence_root=str(self.proof),
            evidence_name=self.evidence_name,
            pi_host="pi.local", pi_user="pi", execute=execute,
            runner=self.ssh_runner)

    def test_no_review_blocks_preview_and_ssh(self):
        with self.assertRaises(MacPiReviewGateError):
            self.transfer()
        with self.assertRaises(MacPiReviewGateError):
            self.transfer(execute=True)
        self.assertEqual(self.ssh_calls, [])

    def test_accepted_private_review_passes_offline_gate(self):
        self.review()
        proof = self.gate()
        self.assertEqual(proof["status"], "MAC_PI_PRIVATE_ACCEPTANCE_PROOF_CHECKED")
        self.assertEqual(proof["matching_private_acceptances"], 1)
        self.assertEqual(proof["video_name"], self.video.name)
        self.assertEqual(proof["video_sha256"], self.sha)
        self.assertFalse(proof["reviewer_identity_authenticated"])
        self.assertFalse(proof["publication_approved"])

    def test_approved_preview_is_offline_and_uses_exact_source(self):
        self.review()
        result = self.transfer()
        self.assertEqual(result["status"], "MAC_PI_REVIEWED_TRANSFER_PREVIEW_ONLY")
        self.assertEqual(result["sha256"], self.sha)
        self.assertEqual(result["source_evidence_name"], self.evidence_name)
        self.assertFalse(result["ssh_connection_performed"])
        self.assertFalse(result["youtube_upload_submitted"])
        self.assertTrue(result["private_acceptance_is_not_upload_permission"])
        self.assertEqual(self.ssh_calls, [])
        self.assertEqual(list(self.pi.iterdir()), [])

    def test_explicit_reviewed_transfer_reaches_private_receiver_only(self):
        self.review()
        result = self.transfer(execute=True)
        self.assertEqual(result["status"], "MAC_PI_REVIEWED_PRIVATE_TRANSFER_VERIFIED")
        self.assertTrue(result["ssh_connection_performed"])
        self.assertEqual(len(self.ssh_calls), 1)
        self.assertEqual((self.pi / self.video.name).read_bytes(),
                         self.video.read_bytes())
        self.assertFalse(result["youtube_upload_submitted"])
        self.assertFalse(result["publication_approved"])

    def test_revision_required_blocks_even_with_older_acceptance(self):
        self.review()
        self.review("REVISION_REQUIRED", watched=False, listened=False)
        with self.assertRaises(MacPiReviewGateError):
            self.transfer(execute=True)
        self.assertEqual(self.ssh_calls, [])

    def test_later_acceptance_does_not_cancel_revision_for_same_file(self):
        self.review("REVISION_REQUIRED", watched=False, listened=False)
        self.review()
        with self.assertRaises(MacPiReviewGateError):
            self.gate()

    def test_revision_only_blocks_even_if_audio_attested(self):
        self.review("REVISION_REQUIRED", watched=True, listened=True)
        with self.assertRaises(MacPiReviewGateError):
            self.gate()

    def test_change_to_video_after_review_blocks_before_ssh(self):
        self.review()
        self.video.write_bytes(b"tampered after private acceptance")
        with self.assertRaises(MacPiReviewGateError):
            self.gate()
        self.assertEqual(self.ssh_calls, [])

    def test_sidecar_tampering_blocks_even_with_review_present(self):
        self.review()
        for key, invalid in (
            ("source_commit", "bad"), ("video_bytes", 999),
            ("source_checkout_clean", False),
            ("technical_preflight", "FAILED"),
            ("publication_approved", True),
        ):
            with self.subTest(key=key):
                original = self.sidecar[key]
                self.sidecar[key] = invalid
                self.write_evidence()
                with self.assertRaises(MacPiReviewGateError):
                    self.gate()
                self.sidecar[key] = original
                self.write_evidence()

    def test_review_modified_sha_source_commit_or_bytes_blocks(self):
        note = self.review()["review_evidence_name"]
        path = self.proof / note
        original = json.loads(path.read_text())
        for key, value in (
            ("video_sha256", "0" * 64),
            ("source_commit", "0" * 40),
            ("video_bytes", 999),
            ("source_evidence_name", "different.evidence.json"),
            ("local_acceptance_is_upload_permission", True),
            ("reported_arabic_voice_reviewed", False),
            ("publication_approved", True),
        ):
            with self.subTest(key=key):
                bad = dict(original)
                bad[key] = value
                path.write_text(json.dumps(bad))
                path.chmod(0o600)
                with self.assertRaises(MacPiReviewGateError):
                    self.transfer()
        path.write_text(json.dumps(original))
        path.chmod(0o600)
        self.assertEqual(self.gate()["matching_private_acceptances"], 1)

    def test_public_or_symlink_review_is_rejected(self):
        note = self.review()["review_evidence_name"]
        path = self.proof / note
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.gate()
        path.chmod(0o600)
        renamed = self.proof / "relocated-private.json"
        path.rename(renamed)
        path.symlink_to(renamed)
        with self.assertRaises(ValueError):
            self.gate()

    def test_malformed_review_name_blocks_even_with_good_acceptance(self):
        self.review()
        malformed = self.proof / (
            self.evidence_name.removesuffix(".json") +
            ".review.not-a-hex-name.json")
        malformed.write_text("{}")
        malformed.chmod(0o600)
        with self.assertRaises(MacPiReviewGateError):
            self.gate()

    def test_no_implicit_newest_source_evidence_selection(self):
        self.review()
        with self.assertRaises(TypeError):
            inspect_reviewed_transfer_candidate(
                video_root=str(self.ready), evidence_root=str(self.proof))

    def test_invalid_destination_blocks_before_ssh(self):
        self.review()
        with self.assertRaises(ValueError):
            transfer_reviewed_mac_pilot(
                video_root=str(self.ready), evidence_root=str(self.proof),
                evidence_name=self.evidence_name,
                pi_host="pi;touch hacked", pi_user="pi", execute=True,
                runner=self.ssh_runner)
        self.assertEqual(self.ssh_calls, [])

    def test_explicit_execute_must_be_boolean(self):
        self.review()
        with self.assertRaises(MacPiReviewGateError):
            transfer_reviewed_mac_pilot(
                video_root=str(self.ready), evidence_root=str(self.proof),
                evidence_name=self.evidence_name, pi_host="pi.local",
                pi_user="pi", execute=1, runner=self.ssh_runner)

    def test_cli_preview_no_ssh_and_safe_json(self):
        self.review()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "--video-root", str(self.ready), "--evidence-root", str(self.proof),
                "--evidence-name", self.evidence_name,
                "--pi-host", "pi.local", "--pi-user", "pi"])
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "MAC_PI_REVIEWED_TRANSFER_PREVIEW_ONLY")
        self.assertFalse(report["publication_approved"])
        self.assertNotIn(str(self.ready), output.getvalue())
        self.assertEqual(self.ssh_calls, [])

    def test_cli_denies_review_missing_without_leaking_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "--video-root", str(self.ready), "--evidence-root", str(self.proof),
                "--evidence-name", self.evidence_name,
                "--pi-host", "pi.local", "--pi-user", "pi"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "MAC_PI_REVIEWED_TRANSFER_BLOCKED_OR_UNCERTAIN")
        self.assertNotIn(str(self.ready), output.getvalue())
        self.assertEqual(self.ssh_calls, [])


if __name__ == "__main__":
    unittest.main()
