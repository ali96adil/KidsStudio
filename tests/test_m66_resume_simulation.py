"""M66 local resume acceptance tests with synthetic bytes only."""
import tempfile
import unittest
from pathlib import Path
from kidsstudio.m66_resume_simulation import stage


class ResumeSimulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.src, self.dst = root / "source.mp4", root / "inbox.mp4"
        self.src.write_bytes(bytes(range(256)) * 4096)

    def test_interruption_then_resume(self):
        self.assertEqual(stage(self.src, self.dst, interrupt_after=12345), "INTERRUPTED")
        self.assertFalse(self.dst.exists())
        self.assertEqual(stage(self.src, self.dst), "COMPLETE")
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())
        self.assertFalse(self.dst.with_name("inbox.mp4.part").exists())

    def test_replay_idempotent(self):
        self.assertEqual(stage(self.src, self.dst), "COMPLETE")
        self.assertEqual(stage(self.src, self.dst), "COMPLETE")

    def test_corrupt_partial_blocked(self):
        self.assertEqual(stage(self.src, self.dst, interrupt_after=20), "INTERRUPTED")
        self.dst.with_name("inbox.mp4.part").write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            stage(self.src, self.dst)

    def test_existing_final_mismatch_blocked(self):
        self.dst.write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            stage(self.src, self.dst)

    def test_symlink_partial_blocked(self):
        self.dst.with_name("inbox.mp4.part").symlink_to(self.src)
        with self.assertRaises(ValueError):
            stage(self.src, self.dst)

    def test_source_changed_after_interrupt_blocked(self):
        stage(self.src, self.dst, interrupt_after=20)
        self.src.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            stage(self.src, self.dst)


if __name__ == "__main__":
    unittest.main()
