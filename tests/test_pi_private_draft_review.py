"""Owner notes AFTER a PRIVATE YouTube upload (offline only, synthetic data)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.pi_youtube_private_upload import _save_journal
from kidsstudio.pi_private_draft_review import (
    PrivateDraftReviewError, inspect_uploaded_private_draft,
    record_post_private_draft_review, main,
)


class PostPrivateDraftReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.inbox, self.journals, self.notes = (
            base / "inbox", base / "journals", base / "reviews")
        for folder in (self.inbox, self.journals, self.notes):
            folder.mkdir(mode=0o700)
        self.movie = self.inbox / "colors_ar_01_v1.mp4"
        self.movie.write_bytes(b"CI_ONLY_original_video_bytes_" * 100)
        self.movie.chmod(0o600)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.video_id = "CIprivate01"
        self.journal = self.journals / "original-private.json"
        self.state = {
            "schema_version": 1,
            "state": "PRIVATE_UPLOAD_CONFIRMED",
            "intent_sha256": "b" * 64,
            "media_sha256": self.sha,
            "media_bytes": self.movie.stat().st_size,
            "media_name": self.movie.name,
            "episode_id": "colors_ar_01",
            "video_id": self.video_id,
        }
        _save_journal(self.journal, self.state, create=True)

    def update_journal(self, **changes):
        self.state.update(changes)
        _save_journal(self.journal, self.state)

    def params(self, **updates):
        values = dict(
            private_root=str(self.inbox),
            relative_path=self.movie.name,
            expected_sha256=self.sha,
            episode_id="colors_ar_01",
            journal_file=str(self.journal),
            video_id=self.video_id,
        )
        values.update(updates)
        return values

    def record(self, outcome="REVISION_REQUIRED", notes="لون السماء يحتاج مراجعة",
               **changes):
        extras = dict(reviewed_private_youtube_draft=True, save_review=True)
        extras.update(changes)
        return record_post_private_draft_review(
            **self.params(), review_root=str(self.notes),
            review_outcome=outcome, reviewer_notes=notes, **extras)

    def files(self):
        return list(self.notes.iterdir())

    def test_inspect_requires_exact_confirmed_sha_media_and_video(self):
        report = inspect_uploaded_private_draft(**self.params())
        self.assertEqual(report["status"],
                         "PI_PRIVATE_DRAFT_REVIEW_ELIGIBLE_OFFLINE")
        self.assertEqual(report["video_sha256"], self.sha)
        self.assertEqual(report["youtube_video_id"], self.video_id)
        self.assertTrue(
            report["youtube_private_historically_confirmed_in_local_journal"])
        self.assertFalse(report["youtube_current_privacy_live_rechecked"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual(self.files(), [])

    def test_a_pending_or_failed_private_upload_cannot_be_reviewed(self):
        for state in ("INITIATION_UNCERTAIN", "SESSION_ACTIVE",
                      "REMOTE_COMPLETED_UNVERIFIED", "failed", None):
            with self.subTest(state=state):
                self.update_journal(state=state)
                with self.assertRaises(PrivateDraftReviewError):
                    inspect_uploaded_private_draft(**self.params())
        self.assertEqual(self.files(), [])

    def test_wrong_video_id_cannot_bind_review_to_other_draft(self):
        with self.assertRaises(PrivateDraftReviewError):
            inspect_uploaded_private_draft(
                **self.params(video_id="otherVid002"))
        self.assertEqual(self.files(), [])

    def test_wrong_filename_episode_and_sha_rejected(self):
        for changed in (
            {"relative_path": "another_version.mp4"},
            {"relative_path": "../escape.mp4"},
            {"episode_id": "colors_ar_02"},
            {"expected_sha256": "0" * 64},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises((PrivateDraftReviewError, ValueError)):
                    inspect_uploaded_private_draft(**self.params(**changed))

    def test_missing_new_journal_context_blocks_binding(self):
        for key in ("media_name", "episode_id", "video_id",
                    "media_sha256", "media_bytes", "intent_sha256"):
            with self.subTest(key=key):
                old = dict(self.state)
                self.state.pop(key)
                _save_journal(self.journal, self.state)
                with self.assertRaises(PrivateDraftReviewError):
                    inspect_uploaded_private_draft(**self.params())
                self.state = old
                _save_journal(self.journal, self.state)

    def test_media_tampering_blocks_even_when_local_journal_says_confirmed(self):
        self.movie.write_bytes(b"CHANGED_AFTER_PRIVATE_UPLOAD")
        with self.assertRaises(PrivateDraftReviewError):
            inspect_uploaded_private_draft(**self.params())
        self.assertEqual(self.files(), [])

    def test_world_readable_media_and_symlink_block_before_notes(self):
        self.movie.chmod(0o644)
        with self.assertRaises(ValueError):
            inspect_uploaded_private_draft(**self.params())
        self.movie.chmod(0o600)
        moved = self.inbox / "actual-original.mp4"
        self.movie.rename(moved)
        self.movie.symlink_to(moved)
        with self.assertRaises(ValueError):
            inspect_uploaded_private_draft(**self.params())
        self.assertEqual(self.files(), [])

    def test_public_or_symlinked_journal_rejected(self):
        self.journal.chmod(0o644)
        with self.assertRaises(ValueError):
            inspect_uploaded_private_draft(**self.params())
        self.journal.chmod(0o600)
        renamed = self.journals / "saved.json"
        self.journal.rename(renamed)
        self.journal.symlink_to(renamed)
        with self.assertRaises(ValueError):
            inspect_uploaded_private_draft(**self.params())

    def test_explicit_revision_appends_0600_note_tied_to_exact_video(self):
        response = self.record()
        self.assertEqual(response["status"],
                         "PI_PRIVATE_DRAFT_REVIEW_RECORDED")
        self.assertEqual(response["review_outcome"], "REVISION_REQUIRED")
        self.assertEqual(len(self.files()), 1)
        item = self.files()[0]
        self.assertEqual(item.stat().st_mode & 0o077, 0)
        raw = item.read_text(encoding="utf8")
        saved = json.loads(raw)
        self.assertEqual(saved["video_sha256"], self.sha)
        self.assertEqual(saved["youtube_video_id"], self.video_id)
        self.assertEqual(saved["upload_intent_sha256"], self.state["intent_sha256"])
        self.assertTrue(saved["reported_youtube_private_draft_reviewed"])
        self.assertFalse(saved["youtube_current_privacy_live_rechecked"])
        self.assertFalse(saved["publication_approved"])
        self.assertNotIn("oauth", raw.lower())
        self.assertNotIn("session_url", raw)
        self.assertNotIn(str(self.journal), raw)

    def test_accept_private_only_after_full_video_and_arabic_attestations(self):
        result = self.record(
            outcome="ACCEPTED_PRIVATE", notes="مقبول كمسودة خاصة",
            reviewed_full_video=True, reviewed_arabic_voice=True)
        self.assertEqual(result["review_outcome"], "ACCEPTED_PRIVATE")
        saved = json.loads(self.files()[0].read_text())
        self.assertTrue(saved["reported_full_video_reviewed"])
        self.assertTrue(saved["reported_arabic_voice_reviewed"])
        self.assertFalse(saved["local_acceptance_is_publication_permission"])
        self.assertFalse(saved["publication_approved"])

    def test_acceptance_requires_both_separate_attestations(self):
        for flags in ({}, {"reviewed_full_video": True},
                      {"reviewed_arabic_voice": True}):
            with self.subTest(flags=flags):
                with self.assertRaises(PrivateDraftReviewError):
                    self.record(outcome="ACCEPTED_PRIVATE", notes="fine", **flags)
        self.assertEqual(self.files(), [])

    def test_revision_needs_notes_and_private_draft_review_assertion(self):
        for notes in ("", "   "):
            with self.subTest(notes=notes):
                with self.assertRaises(PrivateDraftReviewError):
                    self.record(notes=notes)
        with self.assertRaises(PrivateDraftReviewError):
            self.record(outcome="REVISION_REQUIRED",
                        notes="Need changes", reviewed_private_youtube_draft=False)
        self.assertEqual(self.files(), [])

    def test_no_implicit_record_save(self):
        with self.assertRaises(PrivateDraftReviewError):
            record_post_private_draft_review(
                **self.params(), review_root=str(self.notes),
                review_outcome="REVISION_REQUIRED",
                reviewer_notes="Missing explicit SAVE",
                reviewed_private_youtube_draft=True)
        self.assertEqual(self.files(), [])

    def test_revision_note_blocks_later_acceptance_for_same_uploaded_version(self):
        self.record()
        with self.assertRaises(PrivateDraftReviewError):
            self.record(outcome="ACCEPTED_PRIVATE", notes="override",
                        reviewed_full_video=True, reviewed_arabic_voice=True)
        self.assertEqual(len(self.files()), 1)

    def test_acceptance_then_revision_preserves_both_records(self):
        self.record(outcome="ACCEPTED_PRIVATE", notes="first",
                    reviewed_full_video=True, reviewed_arabic_voice=True)
        self.record(notes="Now needs revision after watching again")
        self.assertEqual(len(self.files()), 2)
        with self.assertRaises(PrivateDraftReviewError):
            self.record(outcome="ACCEPTED_PRIVATE", notes="second",
                        reviewed_full_video=True, reviewed_arabic_voice=True)

    def test_malformed_or_public_review_note_fails_closed(self):
        self.record(notes="needs a fix")
        record = self.files()[0]
        record.chmod(0o644)
        with self.assertRaises(ValueError):
            self.record(notes="second note")
        record.chmod(0o600)
        malformed = self.notes / (
            f"private_draft_{self.video_id}_{self.sha[:16]}.review.bad.json")
        malformed.write_text("{}")
        malformed.chmod(0o600)
        with self.assertRaises(PrivateDraftReviewError):
            self.record(notes="third note")
        self.assertEqual(len(self.files()), 2)

    def test_notes_over_2000_characters_are_rejected(self):
        with self.assertRaises(PrivateDraftReviewError):
            self.record(notes="x" * 2001)

    def test_rehash_before_save_detects_modified_media(self):
        from kidsstudio import pi_private_draft_review as mod
        original = inspect_uploaded_private_draft
        called = 0

        def mutate_at_second_read(**kwargs):
            nonlocal called
            called += 1
            if called == 2:
                self.movie.write_bytes(b"changed between explicit checks")
            return original(**kwargs)

        with patch.object(mod, "inspect_uploaded_private_draft",
                          side_effect=mutate_at_second_read):
            with self.assertRaises(PrivateDraftReviewError):
                self.record(notes="review before file change")
        self.assertEqual(self.files(), [])

    def test_cli_default_inspection_is_read_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "--private-root", str(self.inbox),
                "--relative-path", self.movie.name,
                "--expected-sha256", self.sha,
                "--episode-id", "colors_ar_01",
                "--journal", str(self.journal),
                "--video-id", self.video_id,
                "--review-root", str(self.notes),
            ])
        self.assertEqual(code, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"],
                         "PI_PRIVATE_DRAFT_REVIEW_ELIGIBLE_OFFLINE")
        self.assertEqual(self.files(), [])
        self.assertNotIn(str(self.inbox), output.getvalue())

    def test_cli_record_requires_explicit_save_and_attestation(self):
        base_args = [
            "--private-root", str(self.inbox),
            "--relative-path", self.movie.name,
            "--expected-sha256", self.sha,
            "--episode-id", "colors_ar_01",
            "--journal", str(self.journal),
            "--video-id", self.video_id,
            "--review-root", str(self.notes),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(base_args + [
                "--review-outcome", "REVISION_REQUIRED",
                "--reviewer-notes", "Fix the blue title",
                "--reviewed-private-draft", "--save-review",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.files()), 1)

    def test_cli_errors_redact_paths_and_do_not_touch_video(self):
        output = io.StringIO()
        original = self.movie.read_bytes()
        with contextlib.redirect_stdout(output):
            code = main([
                "--private-root", str(self.inbox),
                "--relative-path", self.movie.name,
                "--expected-sha256", "0" * 64,
                "--episode-id", "colors_ar_01",
                "--journal", str(self.journal),
                "--video-id", self.video_id,
                "--review-root", str(self.notes),
                "--reviewed-private-draft",
                "--review-outcome", "REVISION_REQUIRED",
                "--reviewer-notes", "bad", "--save-review",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(output.getvalue())["status"],
            "PI_PRIVATE_DRAFT_REVIEW_BLOCKED")
        self.assertNotIn(str(self.inbox), output.getvalue())
        self.assertEqual(self.movie.read_bytes(), original)
        self.assertEqual(self.files(), [])


if __name__ == "__main__":
    unittest.main()
