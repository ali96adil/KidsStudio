"""Mac review shortcut tests: exact private SHA matching, no network/upload."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.mac_pilot_review_shortcut import (
    MacPilotShortcutError, list_mac_pilot_evidence,
    record_mac_pilot_review_shortcut, main,
)


class MacPilotShortcutTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.videos = self.base / "ready"
        self.proof = self.base / "qualification"
        self.videos.mkdir(mode=0o700)
        self.proof.mkdir(mode=0o700)
        self.movie = self.videos / "colors_ar_01_test_001.mp4"
        self.movie.write_bytes(b"test synthetic media, not an actual video")
        self.movie.chmod(0o600)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.name = "colors_ar_01_test_001.evidence.json"
        self.payload = {
            "schema_version": 1,
            "status": "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
            "episode_id": "colors_ar_01",
            "video_name": self.movie.name,
            "video_sha256": self.sha,
            "video_bytes": self.movie.stat().st_size,
            "duration_seconds": 24.0,
            "source_commit": "b" * 40,
            "source_checkout_clean": True,
            "technical_preflight": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
            "production_approved": False,
            "publication_approved": False,
            "real_mac_pi_transfer_test": "NOT_RUN",
            "real_youtube_upload_test": "NOT_RUN",
        }
        self.save()
        self.args = {
            "video_root": str(self.videos),
            "evidence_root": str(self.proof),
        }

    def save(self):
        sidecar = self.proof / self.name
        sidecar.write_text(json.dumps(self.payload), encoding="utf8")
        sidecar.chmod(0o600)

    def list(self):
        return list_mac_pilot_evidence(**self.args)

    def record(self, outcome="REVISION_REQUIRED", **kwargs):
        return record_mac_pilot_review_shortcut(
            **self.args, evidence_name=self.name,
            review_outcome=outcome, **kwargs)

    def test_listing_is_read_only_and_returns_sha_bound_video(self):
        before = list(self.proof.iterdir())
        result = self.list()
        self.assertEqual(result["status"], "MAC_PILOT_REVIEW_CHOICES_READ_ONLY")
        self.assertEqual(len(result["pilots"]), 1)
        item = result["pilots"][0]
        self.assertEqual(item["evidence_name"], self.name)
        self.assertEqual(item["video_sha256"], self.sha)
        self.assertTrue(item["technical_evidence_verified"])
        self.assertFalse(item["owner_review_recorded_by_this_command"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(before, list(self.proof.iterdir()))

    def test_revision_required_creates_append_only_private_review(self):
        result = self.record(reviewer_notes="نطق الأزرق غير صحيح")
        self.assertEqual(result["review_outcome"], "REVISION_REQUIRED")
        self.assertFalse(result["youtube_upload_performed"])
        saved = self.proof / result["review_evidence_name"]
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.stat().st_mode & 0o077, 0)
        data = json.loads(saved.read_text())
        self.assertEqual(data["video_sha256"], self.sha)
        self.assertEqual(data["source_evidence_name"], self.name)
        self.assertFalse(data["publication_approved"])

    def test_accept_private_without_explicit_two_checks_is_blocked(self):
        before = sorted(self.proof.iterdir())
        for checks in ({}, {"reviewed_full_video": True},
                       {"reviewed_arabic_voice": True}):
            with self.subTest(checks=checks), self.assertRaises(ValueError):
                self.record("ACCEPTED_PRIVATE", **checks)
        self.assertEqual(before, sorted(self.proof.iterdir()))

    def test_accept_private_with_two_explicit_checks_still_no_upload(self):
        result = self.record(
            "ACCEPTED_PRIVATE", reviewed_full_video=True,
            reviewed_arabic_voice=True, reviewer_notes="Local draft only")
        self.assertEqual(result["review_outcome"], "ACCEPTED_PRIVATE")
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertTrue((self.proof / result["review_evidence_name"]).is_file())

    def test_no_implicit_latest_selection(self):
        with self.assertRaises(TypeError):
            record_mac_pilot_review_shortcut(
                **self.args, review_outcome="ACCEPTED_PRIVATE",
                reviewed_full_video=True, reviewed_arabic_voice=True)

    def test_tampered_video_never_appears_or_records(self):
        self.movie.write_bytes(b"changed content")
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(MacPilotShortcutError):
            self.record()
        self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_bad_video_size_in_sidecar_blocks_even_if_sha_matches(self):
        self.payload["video_bytes"] += 1
        self.save()
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(MacPilotShortcutError):
            self.record()

    def test_tampered_sidecar_provenance_blocks(self):
        for field, value in (
            ("source_checkout_clean", False),
            ("source_commit", "short"),
            ("technical_preflight", "FAILED"),
            ("production_approved", True),
            ("publication_approved", True),
            ("real_youtube_upload_test", "SUCCESS"),
            ("real_mac_pi_transfer_test", "SUCCESS"),
            ("status", "MAC_PILOT_FAKE"),
            ("episode_id", "other"),
        ):
            with self.subTest(field=field):
                self.payload[field] = value
                self.save()
                self.assertEqual(self.list()["pilots"], [])
                with self.assertRaises(MacPilotShortcutError):
                    self.record()
                self.payload = {**self.payload, field: {
                    "source_checkout_clean": True,
                    "source_commit": "b" * 40,
                    "technical_preflight": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
                    "production_approved": False,
                    "publication_approved": False,
                    "real_youtube_upload_test": "NOT_RUN",
                    "real_mac_pi_transfer_test": "NOT_RUN",
                    "status": "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
                    "episode_id": "colors_ar_01",
                }[field]}
                self.save()

    def test_sidecar_rename_to_different_video_blocks(self):
        self.name = "renamed.evidence.json"
        self.save()
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(MacPilotShortcutError):
            self.record()

    def test_public_sidecar_rejected(self):
        sidecar = self.proof / self.name
        sidecar.chmod(0o644)
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(ValueError):
            self.record()

    def test_symlink_sidecar_rejected(self):
        sidecar = self.proof / self.name
        sidecar.rename(self.proof / "original-private.json")
        sidecar.symlink_to(self.proof / "original-private.json")
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(ValueError):
            self.record()

    def test_malformed_json_skipped_and_record_blocked(self):
        (self.proof / self.name).write_text("{broken")
        (self.proof / self.name).chmod(0o600)
        self.assertEqual(self.list()["pilots"], [])
        with self.assertRaises(ValueError):
            self.record()

    def test_unrelated_private_json_is_not_listed(self):
        extra = self.proof / "unrelated.json"
        extra.write_text('{"status":"some-secret"}')
        extra.chmod(0o600)
        self.assertEqual(len(self.list()["pilots"]), 1)

    def test_limit_validation_and_empty_directory(self):
        with self.assertRaises(MacPilotShortcutError):
            list_mac_pilot_evidence(**self.args, limit=0)
        with self.assertRaises(MacPilotShortcutError):
            list_mac_pilot_evidence(**self.args, limit=21)
        (self.proof / self.name).unlink()
        self.assertEqual(self.list()["pilots"], [])

    def test_cli_list_uses_private_roots_without_writing(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["list", "--video-root", str(self.videos),
                         "--evidence-root", str(self.proof)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["pilots"][0]["evidence_name"],
                         self.name)

    def test_cli_record_requires_exact_evidence_name(self):
        with self.assertRaises(SystemExit):
            main(["record", "--review-outcome", "ACCEPTED_PRIVATE"])

    def test_cli_error_redacts_private_paths(self):
        output = io.StringIO()
        with patch(
            "kidsstudio.mac_pilot_review_shortcut.list_mac_pilot_evidence",
            side_effect=ValueError("/private/secret/unsafe")
        ), contextlib.redirect_stdout(output):
            code = main(["list"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "MAC_PILOT_REVIEW_SHORTCUT_BLOCKED")
        self.assertNotIn("secret", output.getvalue())

    def test_no_network_or_upload_calls_in_review_shortcut(self):
        with patch("kidsstudio.mac_pilot_review_shortcut.record_mac_pilot_review",
                   wraps=None) as storage:
            storage.return_value = {
                "review_outcome": "REVISION_REQUIRED", "publication_approved": False}
            self.record()
        storage.assert_called_once()
        self.assertNotIn("youtube", str(storage.call_args.kwargs).lower())


if __name__ == "__main__":
    unittest.main()
