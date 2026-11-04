"""Offline M66 checks; synthetic bytes only."""
import tempfile
import unittest
from pathlib import Path
from kidsstudio.m66_transfer_integrity import verify

class TransferIntegrityTests(unittest.TestCase):
    def test_identical(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a",Path(d)/"b"
            a.write_bytes(b"synthetic-video-data")
            b.write_bytes(a.read_bytes())
            self.assertEqual(verify(a,b)["status"],"PASS")

    def test_corrupted(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a",Path(d)/"b"
            a.write_bytes(b"abcd")
            b.write_bytes(b"abce")
            with self.assertRaises(ValueError):
                verify(a,b)

    def test_symlink_denied(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a",Path(d)/"b"
            a.write_bytes(b"test")
            b.symlink_to(a)
            with self.assertRaises(ValueError):
                verify(a,b)

    def test_missing_denied(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a",Path(d)/"b"
            a.write_bytes(b"test")
            with self.assertRaises(ValueError):
                verify(a,b)

if __name__=="__main__":
    unittest.main()
