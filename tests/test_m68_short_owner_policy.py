"""M68 owner policy bridge tests, no upload authorization."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_owner_policy import assess_short_policy


class ShortOwnerPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.queue = StudioQueue(Path(tmp.name) / "queue.sqlite")
        self.queue.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("CREATE TABLE studio_series(series_id TEXT PRIMARY KEY,state TEXT)")
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY, channel_id TEXT,state TEXT,
                allowed_made_for_kids INTEGER,allowed_synthetic_media INTEGER,
                revision INTEGER)""")
            db.execute("INSERT INTO studio_series VALUES('colors','ACTIVE')")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES('colors','UC1234567890123456789012','ENABLED',1,1,3)""")
        self.kwargs = dict(short_id="colors-short-01",
                           source_episode_id="colors-ep-01",
                           media_sha256="a" * 64,
                           series_id="colors",
                           channel_id="UC1234567890123456789012",
                           made_for_kids=True,
                           contains_synthetic_media=True)

    @patch("kidsstudio.m68_short_owner_policy.assess_short_review",
           return_value={"reasons": []})
    def test_valid_policy_still_does_not_authorize_upload(self, _review):
        result = assess_short_policy(self.queue, **self.kwargs)
        self.assertEqual(result["status"],
                         "SHORT_POLICY_PRECHECK_PASSED_UPLOAD_STILL_BLOCKED")
        self.assertEqual(result["policy_revision"], 3)
        self.assertFalse(result["youtube_upload_authorized"])

    @patch("kidsstudio.m68_short_owner_policy.assess_short_review",
           return_value={"reasons": []})
    def test_paused_owner_policy_blocks(self, _review):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_youtube_private_policies
                SET state='PAUSED' WHERE series_id='colors'""")
        result = assess_short_policy(self.queue, **self.kwargs)
        self.assertIn("OWNER_PRIVATE_POLICY_NOT_ENABLED", result["reasons"])

    @patch("kidsstudio.m68_short_owner_policy.assess_short_review",
           return_value={"reasons": ["CONTENT_REVIEW_MISSING"]})
    def test_missing_review_blocks_even_with_owner_policy(self, _review):
        result = assess_short_policy(self.queue, **self.kwargs)
        self.assertIn("CONTENT_REVIEW_MISSING", result["reasons"])

    @patch("kidsstudio.m68_short_owner_policy.assess_short_review",
           return_value={"reasons": []})
    def test_wrong_channel_blocks(self, _review):
        self.kwargs["channel_id"] = "UC0000000000000000000000"
        result = assess_short_policy(self.queue, **self.kwargs)
        self.assertIn("OWNER_PRIVATE_POLICY_FLAGS_MISMATCH", result["reasons"])
