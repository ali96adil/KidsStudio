import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.transfer_verify import verify_staged_file, main


class TransferVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "staged"
        self.root.mkdir()
        self.file = self.root / "episode.mp4"
        self.data = b"synthetic video bytes" * 1024
        self.file.write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def test_valid_staged_file_is_read_only(self):
        report = verify_staged_file(root=self.root, relative_path="episode.mp4",
                                    expected_sha256=self.sha)
        self.assertEqual(report["status"], "VERIFIED")
        self.assertEqual(self.file.read_bytes(), self.data)
        self.assertFalse(report["upload_approved"])
        self.assertFalse(report["transfer_performed"])

    def test_tamper_detected(self):
        self.file.write_bytes(self.data + b"tampered")
        report = verify_staged_file(root=self.root, relative_path="episode.mp4",
                                    expected_sha256=self.sha)
        self.assertEqual(report["status"], "HASH_MISMATCH")

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):
            verify_staged_file(root=self.root, relative_path="../other",
                               expected_sha256=self.sha)

    def test_symlink_escape_rejected(self):
        outside = Path(self.tmp.name) / "outside.mp4"
        outside.write_bytes(self.data)
        (self.root / "linked.mp4").symlink_to(outside)
        with self.assertRaises(ValueError):
            verify_staged_file(root=self.root, relative_path="linked.mp4",
                               expected_sha256=self.sha)

    def test_size_limit_rejected(self):
        with self.assertRaises(ValueError):
            verify_staged_file(root=self.root, relative_path="episode.mp4",
                               expected_sha256=self.sha, max_bytes=10)

    def test_cli_error_does_not_leak_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--root", str(self.root),
                           "--relative-path", "../private",
                           "--expected-sha256", self.sha])
        self.assertEqual(status, 2)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
