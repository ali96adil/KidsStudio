"""M67 owner review is append-only and never publishes."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_owner_review_notes import record, OwnerReviewError


class OwnerReviewTests(unittest.TestCase):
    def test_notes_append_without_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = record(root, episode_id="colors-ar-001",
                           video_id="abcdefghijk", decision="REQUEST_CHANGES",
                           notes="Improve pronunciation")
            second = record(root, episode_id="colors-ar-001",
                            video_id="abcdefghijk", decision="ACCEPT_WITH_NOTES",
                            notes="Accept after correction")
            self.assertNotEqual(first["review_file"], second["review_file"])
            self.assertFalse(second["public_release_authorized"])
            self.assertFalse(second["youtube_visibility_changed"])

    def test_changes_require_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OwnerReviewError):
                record(Path(tmp), episode_id="colors-ar-001",
                       video_id="abcdefghijk", decision="REQUEST_CHANGES",
                       notes="")
