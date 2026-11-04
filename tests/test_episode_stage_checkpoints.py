import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.episode_stage_checkpoints import initialize, status, transition


class StageCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        initialize(self.root, "colors_001", "animated_explainer")

    def test_resume_after_failure(self):
        self.assertEqual(status(self.root, "colors_001")["next_stage"], "curriculum")
        transition(self.root, "colors_001", "curriculum", "running")
        transition(self.root, "colors_001", "curriculum", "failed")
        self.assertEqual(status(self.root, "colors_001")["stages"]["curriculum"], "failed")
        transition(self.root, "colors_001", "curriculum", "running")
        transition(self.root, "colors_001", "curriculum", "passed")
        report = status(self.root, "colors_001")
        self.assertEqual(report["next_stage"], "script")
        self.assertFalse(report["public_release_authorized"])
        self.assertFalse(report["youtube_uploaded"])

    def test_order_and_invalid_transition(self):
        with self.assertRaises(ValueError):
            transition(self.root, "colors_001", "script", "running")
        with self.assertRaises(ValueError):
            transition(self.root, "colors_001", "curriculum", "passed")
        with self.assertRaises(ValueError):
            transition(self.root, "colors_001", "curriculum", "published")
        with self.assertRaises(FileExistsError):
            initialize(self.root, "colors_001", "animated_explainer")

    def test_checkpoint_file_private_and_tamper_rejected(self):
        path = self.root / "colors_001.checkpoints.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        payload = json.loads(path.read_text())
        payload["public_release_authorized"] = True
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            status(self.root, "colors_001")

    def test_symlink_and_unsafe_episode_id_rejected(self):
        with self.assertRaises(ValueError):
            status(self.root, "../other")
        link = self.root / "linked.checkpoints.json"
        link.symlink_to(self.root / "colors_001.checkpoints.json")
        with self.assertRaises(ValueError):
            status(self.root, "linked")


if __name__ == "__main__":
    unittest.main()
