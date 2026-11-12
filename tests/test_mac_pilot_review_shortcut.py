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
    record_mac_pilot_review_shortcut, guided_mac_pilot_review, main,
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

    def test_internal_mux_candidate_is_not_offered_for_owner_review(self):
        old_movie = self.movie
        self.movie = self.videos / "verified-candidate.mp4"
        old_movie.rename(self.movie)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.name = "verified-candidate.evidence.json"
        self.payload.update({
            "video_name": self.movie.name,
            "video_sha256": self.sha,
            "video_bytes": self.movie.stat().st_size,
        })
        (self.proof / "colors_ar_01_test_001.evidence.json").unlink()
        self.save()

        self.assertEqual(self.list()["pilots"], [])

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
        # Move the ORIGINAL sidecar instead of creating a second file:
        # a valid original copy would (correctly) remain selectable.
        previous = self.proof / self.name
        self.name = "renamed.evidence.json"
        previous.rename(self.proof / self.name)
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


    def guided(self, answers, *, terminal=True):
        stream = io.StringIO()
        with patch("kidsstudio.mac_pilot_review_shortcut._interactive_terminal",
                   return_value=terminal), \
             patch("builtins.input", side_effect=answers), \
             contextlib.redirect_stdout(stream):
            result = guided_mac_pilot_review(**self.args)
        return result, stream.getvalue()

    def test_guided_requires_a_real_interactive_tty(self):
        with patch("kidsstudio.mac_pilot_review_shortcut._interactive_terminal",
                   return_value=False), \
             patch("builtins.input") as read:
            with self.assertRaises(MacPilotShortcutError):
                guided_mac_pilot_review(**self.args)
        read.assert_not_called()
        self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_guided_revision_uses_exact_selected_sidecar_and_notes(self):
        result, output = self.guided(["1", "R", "صوت الأزرق يحتاج تعديل", "SAVE"])
        self.assertEqual(result["review_outcome"], "REVISION_REQUIRED")
        self.assertEqual(json.loads(
            (self.proof / result["review_evidence_name"]).read_text()
        )["reviewer_notes"], "صوت الأزرق يحتاج تعديل")
        self.assertIn(self.movie.name, output)
        self.assertFalse(result["youtube_upload_performed"])

    def test_guided_private_accept_requires_both_explicit_truthful_yes_and_save(self):
        result, _ = self.guided(["1", "A", "مقبول للمراجعة الخاصة",
                                 "YES", "YES", "SAVE"])
        self.assertEqual(result["review_outcome"], "ACCEPTED_PRIVATE")
        note = json.loads((self.proof / result["review_evidence_name"]).read_text())
        self.assertTrue(note["reported_full_video_reviewed"])
        self.assertTrue(note["reported_arabic_voice_reviewed"])
        self.assertFalse(note["local_acceptance_is_upload_permission"])
        self.assertFalse(note["publication_approved"])

    def test_guided_accept_without_any_required_attestation_is_cancelled(self):
        for answers in (
            ["1", "A", "ok", "NO"],
            ["1", "A", "ok", "YES", "NO"],
            ["1", "A", "ok", "YES", "YES", "no"],
            ["1", "R", "اللون غلط", "no"],
        ):
            with self.subTest(answers=answers):
                result, _ = self.guided(answers)
                self.assertEqual(result["status"],
                                 "MAC_PILOT_GUIDED_REVIEW_CANCELLED_NO_WRITE")
                self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_guided_rejects_implicit_or_out_of_range_selection(self):
        for answers in (["0"], ["2"], ["latest"], [""], ["1", "C"],
                        ["1", "R", "", "SAVE"], ["-1"]):
            with self.subTest(answers=answers):
                result, _ = self.guided(answers)
                self.assertFalse(result["review_recorded"])
                self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_guided_empty_private_list_does_not_prompt(self):
        (self.proof / self.name).unlink()
        with patch("kidsstudio.mac_pilot_review_shortcut._interactive_terminal",
                   return_value=True), \
             patch("builtins.input") as read:
            report = guided_mac_pilot_review(**self.args)
        self.assertEqual(report["status"],
                         "MAC_PILOT_GUIDED_NO_VALID_PRIVATE_PILOTS")
        read.assert_not_called()

    def test_guided_abort_on_eof_does_not_save(self):
        report, _ = self.guided([EOFError()])
        self.assertFalse(report["review_recorded"])
        self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_guided_tamper_between_selection_and_save_fails_closed(self):
        prompts = iter(["1", "R", "نطق يحتاج تعديل", "SAVE"])

        def mutate_when_saving(prompt):
            answer = next(prompts)
            if answer == "SAVE":
                self.movie.write_bytes(b"changed after initial display")
            return answer

        with patch("kidsstudio.mac_pilot_review_shortcut._interactive_terminal",
                   return_value=True), patch("builtins.input",
                   side_effect=mutate_when_saving), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(MacPilotShortcutError):
                guided_mac_pilot_review(**self.args)
        self.assertEqual(len(list(self.proof.iterdir())), 1)

    def test_guided_cli_returns_cancel_without_recording(self):
        output = io.StringIO()
        with patch("kidsstudio.mac_pilot_review_shortcut._interactive_terminal",
                   return_value=True), patch("builtins.input",
                   return_value="0"), contextlib.redirect_stdout(output):
            code = main(["guided", "--video-root", str(self.videos),
                         "--evidence-root", str(self.proof)])
        self.assertEqual(code, 0)
        self.assertIn("MAC_PILOT_GUIDED_REVIEW_CANCELLED_NO_WRITE",
                      output.getvalue())
        self.assertEqual(len(list(self.proof.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
