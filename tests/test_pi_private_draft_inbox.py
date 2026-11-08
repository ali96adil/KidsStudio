"""Offline Pi PRIVATE draft review queue unit tests; NO real Pi or YouTube."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.pi_private_draft_inbox import (
    PrivateDraftInboxError, build_private_draft_inbox,
    format_inbox_table, main,
)
from kidsstudio.pi_private_draft_review import record_post_private_draft_review
from kidsstudio.pi_youtube_private_upload import _save_journal


class PrivateDraftInboxTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.inbox, self.journals, self.reviews = (
            base / "inbox", base / "journals", base / "reviews")
        for directory in (self.inbox, self.journals, self.reviews):
            directory.mkdir(mode=0o700)
        self.video_id = "ciVideoB6401"
        self.movie = self.inbox / "colors_ar_01_v1.mp4"
        self.movie.write_bytes(b"CI_PRIVATE_MP4_NOT_REAL" * 128)
        self.movie.chmod(0o600)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()
        self.journal = self.journals / "colors-v1.json"
        self.upload_state = {
            "schema_version": 1,
            "state": "PRIVATE_UPLOAD_CONFIRMED",
            "intent_sha256": "b"*64,
            "media_sha256": self.sha,
            "media_bytes": self.movie.stat().st_size,
            "media_name": self.movie.name,
            "episode_id": "colors_ar_01",
            "video_id": self.video_id,
        }
        _save_journal(self.journal, self.upload_state, create=True)

    def report(self, **changes):
        params = dict(
            journal_root=str(self.journals), private_root=str(self.inbox),
            review_root=str(self.reviews),
        )
        params.update(changes)
        return build_private_draft_inbox(**params)

    def save_note(self, outcome, message="CI simulated note", *,
                  reviewed=True):
        return record_post_private_draft_review(
            private_root=str(self.inbox),
            relative_path=self.movie.name,
            expected_sha256=self.sha,
            episode_id="colors_ar_01",
            journal_file=str(self.journal),
            video_id=self.video_id,
            review_root=str(self.reviews),
            review_outcome=outcome,
            reviewer_notes=message,
            reviewed_private_youtube_draft=True,
            reviewed_full_video=reviewed,
            reviewed_arabic_voice=reviewed,
            save_review=True,
        )

    def test_confirmed_private_draft_with_no_review_is_pending(self):
        result = self.report()
        self.assertEqual(result["status"], "PI_PRIVATE_DRAFT_INBOX_READ_ONLY")
        self.assertEqual(result["scanned_journals"], 1)
        self.assertEqual(result["counts"]["NEEDS_OWNER_REVIEW_PRIVATE"], 1)
        item = result["items"][0]
        self.assertEqual(item["status"], "NEEDS_OWNER_REVIEW_PRIVATE")
        self.assertEqual(item["episode_id"], "colors_ar_01")
        self.assertEqual(item["video_name"], self.movie.name)
        self.assertIsNone(item["youtube_video_id"])
        self.assertTrue(item["local_video_sha_verified"])
        self.assertFalse(result["youtube_current_privacy_live_rechecked"])
        self.assertFalse(result["ssh_or_google_network_called"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(list(self.reviews.iterdir()), [])

    def test_explicit_video_id_display_for_owner_only(self):
        result = self.report(show_video_ids=True)
        self.assertEqual(result["items"][0]["youtube_video_id"], self.video_id)
        self.assertFalse(result["youtube_current_privacy_live_rechecked"])

    def test_no_note_text_exposed_in_any_report_or_table(self):
        private = "USER_PRIVATE_NOTE_SHOULD_NOT_BE_EXPOSED"
        self.save_note("REVISION_REQUIRED", private)
        result = self.report()
        self.assertNotIn(private, json.dumps(result))
        self.assertNotIn(private, format_inbox_table(result))

    def test_revision_note_has_priority_over_an_older_acceptance(self):
        self.save_note("ACCEPTED_PRIVATE")
        self.save_note("REVISION_REQUIRED", "New revision after another watch")
        row = self.report()["items"][0]
        self.assertEqual(row["status"], "REVISION_REQUIRED_PRIVATE")
        self.assertEqual(row["matching_acceptance_notes"], 1)
        self.assertEqual(row["matching_revision_notes"], 1)

    def test_accepted_private_only_is_not_publication_approval(self):
        self.save_note("ACCEPTED_PRIVATE")
        result = self.report()
        self.assertEqual(result["counts"]["ACCEPTED_PRIVATE_ONLY"], 1)
        self.assertEqual(result["items"][0]["status"], "ACCEPTED_PRIVATE_ONLY")
        self.assertFalse(result["publication_approved"])

    def test_two_versions_of_same_episode_stay_separate(self):
        v2 = self.inbox / "colors_ar_01_v2.mp4"
        v2.write_bytes(b"VERSION2_ONLY" * 500)
        v2.chmod(0o600)
        sha2 = hashlib.sha256(v2.read_bytes()).hexdigest()
        journal2 = self.journals / "colors-v2.json"
        _save_journal(journal2, {
            **self.upload_state,
            "media_name": v2.name,
            "media_sha256": sha2,
            "media_bytes": v2.stat().st_size,
            "video_id": "ciVideoB6402",
            "intent_sha256": "c"*64,
        }, create=True)
        self.save_note("REVISION_REQUIRED")
        result = self.report()
        self.assertEqual(result["scanned_journals"], 2)
        self.assertEqual(result["counts"]["REVISION_REQUIRED_PRIVATE"], 1)
        self.assertEqual(result["counts"]["NEEDS_OWNER_REVIEW_PRIVATE"], 1)
        self.assertEqual(
            [v["journal_name"] for v in result["items"]],
            ["colors-v1.json", "colors-v2.json"],
        )

    def test_unconfirmed_upload_never_looks_review_ready(self):
        for state in ("INITIATION_UNCERTAIN", "SESSION_ACTIVE",
                      "REMOTE_COMPLETED_UNVERIFIED"):
            with self.subTest(state=state):
                data = dict(self.upload_state, state=state)
                if state == "SESSION_ACTIVE":
                    data["session_url"] = (
                        "https://www.googleapis.com/upload/youtube/v3/videos?"
                        "upload_id=CI_PRIVATE_TOKEN_DO_NOT_PRINT")
                _save_journal(self.journal, data)
                result = self.report(show_video_ids=True)
                row = result["items"][0]
                self.assertEqual(row["status"], "UPLOAD_UNCONFIRMED")
                self.assertIsNone(row["youtube_video_id"])
                self.assertIsNone(row["episode_id"])
                self.assertFalse(row["local_video_sha_verified"])
                self.assertNotIn("CI_PRIVATE_TOKEN_DO_NOT_PRINT",
                                 json.dumps(result))

    def test_invalid_local_journal_is_blocked_not_ignored(self):
        _save_journal(self.journal, dict(self.upload_state, state="PUBLIC"))
        result = self.report()
        self.assertEqual(result["counts"]["BLOCKED_LOCAL_EVIDENCE"], 1)
        self.assertIsNone(result["items"][0]["video_name"])
        self.assertFalse(result["items"][0]["local_video_sha_verified"])

    def test_legacy_confirmed_journal_without_exact_media_binding_is_blocked(self):
        for key in ("episode_id", "media_name", "media_bytes",
                    "media_sha256", "video_id", "intent_sha256"):
            with self.subTest(key=key):
                record = dict(self.upload_state)
                record.pop(key)
                _save_journal(self.journal, record)
                self.assertEqual(self.report()["items"][0]["status"],
                                 "BLOCKED_LOCAL_EVIDENCE")
        _save_journal(self.journal, self.upload_state)
        self.assertEqual(self.report()["items"][0]["status"],
                         "NEEDS_OWNER_REVIEW_PRIVATE")

    def test_changed_or_public_video_blocks_owner_review(self):
        self.movie.chmod(0o644)
        self.assertEqual(self.report()["items"][0]["status"],
                         "BLOCKED_LOCAL_EVIDENCE")
        self.movie.chmod(0o600)
        self.movie.write_bytes(b"CHANGED")
        self.assertEqual(self.report()["items"][0]["status"],
                         "BLOCKED_LOCAL_EVIDENCE")

    def test_unsafe_and_unrelated_review_notes_block_matching_draft(self):
        self.save_note("ACCEPTED_PRIVATE")
        saved = next(self.reviews.glob("*.json"))
        saved.chmod(0o644)
        self.assertEqual(self.report()["items"][0]["status"],
                         "BLOCKED_LOCAL_EVIDENCE")
        saved.chmod(0o600)
        saved.write_text("{}")
        saved.chmod(0o600)
        self.assertEqual(self.report()["items"][0]["status"],
                         "BLOCKED_LOCAL_EVIDENCE")

    def test_unrelated_episode_note_does_not_affect_original(self):
        self.save_note("REVISION_REQUIRED")
        irrelevant = self.reviews / "private_draft_otherCI_v2.review.1234567890abcdef.json"
        irrelevant.write_text("{not json}")
        irrelevant.chmod(0o600)
        self.assertEqual(self.report()["items"][0]["status"],
                         "REVISION_REQUIRED_PRIVATE")

    def test_journal_symlink_is_blocked_never_followed(self):
        other = self.journals / "hidden-private.json.saved"
        self.journal.rename(other)
        self.journal.symlink_to(other)
        self.assertEqual(self.report()["items"][0]["status"],
                         "BLOCKED_LOCAL_EVIDENCE")

    def test_missing_or_world_readable_root_fails_closed(self):
        self.reviews.chmod(0o755)
        with self.assertRaises(PrivateDraftInboxError):
            self.report()
        self.reviews.chmod(0o700)
        self.journals.chmod(0o755)
        with self.assertRaises(PrivateDraftInboxError):
            self.report()
        self.journals.chmod(0o700)
        self.inbox.chmod(0o755)
        with self.assertRaises(PrivateDraftInboxError):
            self.report()
        self.inbox.chmod(0o700)
        self.reviews.rmdir()
        with self.assertRaises(PrivateDraftInboxError):
            self.report()

    def test_too_many_journals_stop_scan_before_loading(self):
        for i in range(257):
            file = self.journals / f"extra-{i}.json"
            file.write_text("{}")
            file.chmod(0o600)
        with self.assertRaises(PrivateDraftInboxError):
            self.report()

    def test_table_shows_statuses_counts_but_no_tokens(self):
        self.save_note("REVISION_REQUIRED")
        view = format_inbox_table(self.report())
        self.assertIn("REVISION", view)
        self.assertIn("TOTAL=1", view)
        self.assertIn("NEVER publication approval", view)
        self.assertNotIn(self.video_id, view)
        self.assertNotIn(self.sha, view)

    def test_default_cli_is_read_only_table(self):
        output = io.StringIO()
        before = {p.name: p.read_bytes() for p in self.journals.iterdir()}
        with contextlib.redirect_stdout(output):
            result = main([
                "--journal-root", str(self.journals),
                "--private-root", str(self.inbox),
                "--review-root", str(self.reviews),
            ])
        self.assertEqual(result, 0)
        self.assertIn("NEEDS REVIEW", output.getvalue())
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.journals.iterdir()}, before
        )
        self.assertEqual(list(self.reviews.iterdir()), [])

    def test_json_cli_video_id_only_on_explicit_request(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--journal-root", str(self.journals),
                "--private-root", str(self.inbox),
                "--review-root", str(self.reviews), "--format", "json",
                "--show-video-ids",
            ])
        self.assertEqual(result, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["items"][0]["youtube_video_id"], self.video_id)

    def test_blocked_item_cli_exit_one_no_false_success(self):
        self.movie.write_bytes(b"MUTATED")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--journal-root", str(self.journals),
                "--private-root", str(self.inbox),
                "--review-root", str(self.reviews), "--format", "json",
            ])
        self.assertEqual(result, 1)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["counts"]["BLOCKED_LOCAL_EVIDENCE"], 1)
        self.assertFalse(parsed["publication_approved"])

    def test_root_error_cli_redacts_unsafe_paths(self):
        self.reviews.chmod(0o755)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--journal-root", str(self.journals),
                "--private-root", str(self.inbox),
                "--review-root", str(self.reviews),
            ])
        self.assertEqual(result, 2)
        self.assertNotIn(str(self.reviews), output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "PI_PRIVATE_DRAFT_INBOX_BLOCKED")


if __name__ == "__main__":
    unittest.main()
