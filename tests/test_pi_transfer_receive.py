from __future__ import annotations

import hashlib
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.pi_transfer_receive import (
    PiReceiveError, main, receive_private_video,
)


class PiTransferReceiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "inbox"
        self.root.mkdir(mode=0o700)
        self.data = b"synthetic original colors episode" * 4000
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.path = self.root / "colors_ar_001.mp4"

    def receive(self, data=None, **updates):
        args = dict(
            destination_root=self.root,
            destination_name="colors_ar_001.mp4",
            expected_sha256=self.sha,
            expected_bytes=len(self.data),
            source=BytesIO(self.data if data is None else data),
        )
        args.update(updates)
        return receive_private_video(**args)

    def test_success_verified_atomic_private_file(self):
        r = self.receive()
        self.assertEqual(r["status"], "PI_INBOX_RECEIVED_PRIVATE")
        self.assertEqual(r["sha256"], self.sha)
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)
        self.assertFalse(r["upload_submitted"])
        self.assertFalse(r["publication_approved"])
        self.assertEqual([p.name for p in self.root.iterdir()], ["colors_ar_001.mp4"])

    def test_identical_retry_consumes_all_input_and_never_overwrites(self):
        self.receive()
        inode = self.path.stat().st_ino
        source = BytesIO(self.data)
        r = self.receive(source=source)
        self.assertEqual(r["status"], "PI_INBOX_ALREADY_VERIFIED")
        self.assertEqual(source.tell(), len(self.data))
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_wrong_digest_rejected_without_output(self):
        with self.assertRaises(PiReceiveError):
            self.receive(expected_sha256="0" * 64)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_interrupted_stream_rejected_and_temp_removed(self):
        with self.assertRaises(PiReceiveError):
            self.receive(data=self.data[:31])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_extra_stream_data_rejected(self):
        with self.assertRaises(PiReceiveError):
            self.receive(data=self.data + b"EXTRA")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_different_file_is_never_replaced(self):
        self.path.write_bytes(b"previous trusted version")
        self.path.chmod(0o600)
        with self.assertRaises(PiReceiveError):
            self.receive()
        self.assertEqual(self.path.read_bytes(), b"previous trusted version")

    def test_symlink_destination_rejected(self):
        outside = self.root.parent / "outside.mp4"
        outside.write_bytes(b"untouched")
        self.path.symlink_to(outside)
        with self.assertRaises(PiReceiveError):
            self.receive()
        self.assertEqual(outside.read_bytes(), b"untouched")

    def test_public_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(PiReceiveError):
            self.receive()
        self.assertFalse(self.path.exists())

    def test_git_inbox_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaises(PiReceiveError):
            self.receive()

    def test_unsafe_names_rejected(self):
        for name in ("../evil.mp4", ".hidden.mp4", "movie.mkv", "bad name.mp4",
                     "other/file.mp4", "test.mp4;echo", "x" * 200 + ".mp4"):
            with self.subTest(name=name), self.assertRaises(PiReceiveError):
                self.receive(destination_name=name)

    def test_bad_sizes_fail_closed(self):
        for size in (-1, 0, True, "500", 20 * 1024**3 + 1):
            with self.subTest(size=size), self.assertRaises(PiReceiveError):
                self.receive(expected_bytes=size)

    def test_unexpected_existing_public_file_rejected(self):
        self.path.write_bytes(self.data)
        self.path.chmod(0o644)
        with self.assertRaises(PiReceiveError):
            self.receive()

    def test_cli_rejection_does_not_leak_private_details(self):
        out = StringIO()
        with patch("kidsstudio.pi_transfer_receive.Path.home",
                   return_value=self.root.parent):
            with patch("sys.stdout", out):
                code = main([
                    "--destination-name", "../bad.mp4",
                    "--expected-sha256", self.sha,
                    "--expected-bytes", str(len(self.data)),
                ])
        self.assertEqual(code, 2)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "PI_INBOX_TRANSFER_REJECTED")
        self.assertFalse(report["publication_approved"])


if __name__ == "__main__":
    unittest.main()
