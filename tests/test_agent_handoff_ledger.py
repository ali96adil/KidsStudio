import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kidsstudio.agent_handoff_ledger import read_handoffs, record_handoff
from kidsstudio.episode_stage_checkpoints import initialize


class HandoffLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        initialize(self.root, "colors_001", "animated_explainer")

    def test_records_are_private_and_persistent(self):
        record_handoff(self.root, "colors_001", "script", "writer-1",
                       "assigned", "Draft simple Arabic lesson")
        result = read_handoffs(self.root, "colors_001")
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["events"][0]["agent_id"], "writer-1")
        self.assertFalse(result["youtube_uploaded"])
        self.assertFalse(result["public_release_authorized"])
        path = self.root / "colors_001.checkpoints.handoffs.jsonl"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_writers_preserve_all_records(self):
        def write(i):
            return record_handoff(self.root, "colors_001", "assets",
                                  "agent-" + str(i), "assigned")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(24)))
        self.assertEqual(read_handoffs(self.root, "colors_001")["event_count"], 24)

    def test_reject_invalid_stage_agent_and_event(self):
        for args in (("unknown", "writer", "assigned"),
                     ("script", "../bad", "assigned"),
                     ("script", "writer", "public_release")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                record_handoff(self.root, "colors_001", *args)

    def test_symlink_ledger_rejected(self):
        path = self.root / "colors_001.checkpoints.handoffs.jsonl"
        path.symlink_to(self.root / "colors_001.checkpoints.json")
        with self.assertRaises(ValueError):
            read_handoffs(self.root, "colors_001")
        with self.assertRaises(ValueError):
            record_handoff(self.root, "colors_001", "script", "writer", "assigned")


if __name__ == "__main__":
    unittest.main()
