"""M66.2 synthetic transfer interruption and corruption tests."""
import tempfile
from pathlib import Path
import unittest

from kidsstudio.m66_transfer_fault_lab import simulate, TransferSimulationError


class M66TransferFaultLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "sample.mp4"
        self.source.write_bytes(bytes(range(256)) * 200)
        self.destination = root / "inbox"
        self.destination.mkdir()

    def test_interrupt_resume_and_atomic_promotion(self):
        first = simulate(self.source, self.destination, interrupt_after=3000,
                         chunk_size=1024)
        self.assertEqual(first["status"], "INTERRUPTED")
        self.assertFalse((self.destination / "sample.mp4.ready").exists())
        second = simulate(self.source, self.destination, chunk_size=1024)
        self.assertEqual(second["status"], "VERIFIED_READY")
        self.assertEqual((self.destination / "sample.mp4.ready").read_bytes(),
                         self.source.read_bytes())
        self.assertFalse((self.destination / "sample.mp4.part").exists())

    def test_corrupt_partial_fails_closed(self):
        simulate(self.source, self.destination, interrupt_after=100)
        (self.destination / "sample.mp4.part").write_bytes(b"tampered")
        with self.assertRaises(TransferSimulationError):
            simulate(self.source, self.destination)

    def test_ready_deduplicates_and_mismatch_blocks(self):
        simulate(self.source, self.destination)
        self.assertEqual(simulate(self.source, self.destination)["status"],
                         "ALREADY_VERIFIED")
        (self.destination / "sample.mp4.ready").write_bytes(b"tampered")
        with self.assertRaises(TransferSimulationError):
            simulate(self.source, self.destination)

    def test_symlink_partial_rejected(self):
        (self.destination / "sample.mp4.part").symlink_to(self.source)
        with self.assertRaises(TransferSimulationError):
            simulate(self.source, self.destination)

    def test_oversized_partial_rejected(self):
        (self.destination / "sample.mp4.part").write_bytes(
            self.source.read_bytes() + b"extra")
        with self.assertRaises(TransferSimulationError):
            simulate(self.source, self.destination)


if __name__ == "__main__":
    unittest.main()
