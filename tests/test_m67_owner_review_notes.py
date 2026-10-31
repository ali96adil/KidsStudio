"""M67 owner private video review tests."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_owner_review_notes import record, OwnerReviewError


class OwnerReviewTests(unittest.TestCase):
    def test_append_only_revisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = record(root, episode_id="colors-ar-001",
                       video_id="abcdefghijk", decision="REQUEST_CHANGES",
                       notes="The bunny changes color unexpectedly.")
            b = record(root, episode_id="colors-ar-001",
                       video_id="abcdefghijk", decision="ACCEPT_WITH_NOTES",
                       notes="Keep the final transition shorter.")
            self.assertNotEqual(a["review_file"], b["review_file"])
            self.assertFalse(b["public_release_authorized"])
            self.assertTrue(Path(a["review_file"]).exists())

    def test_notes_required_for_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OwnerReviewError):
                record(temp, episode_id="colors-ar-001",
                       video_id="abcdefghijk", decision="REJECT", notes="")
