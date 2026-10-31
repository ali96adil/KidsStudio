"""Operator CLI must not mutate queue or trigger Google transport."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.m68_pi_check import main


class PiCheckCLITests(unittest.TestCase):
    def test_missing_db_rejected_without_creating_it(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "missing.sqlite"
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--db", str(db), "--short-id", "short-01",
                          "--series-id", "colors", "--media", str(Path(root) / "a.mp4")])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(db.exists())

    def test_blocked_report_returns_exit_two(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "queue.sqlite"
            db.touch()
            result = {"status": "BLOCKED", "reasons": ["SOURCE_MASTER_NOT_APPROVED"],
                      "youtube_upload_authorized": False,
                      "public_release_authorized": False}
            with patch("kidsstudio.m68_pi_check.assess", return_value=result) as assess:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--db", str(db), "--short-id", "short-01",
                                 "--series-id", "colors", "--media", str(Path(root) / "a.mp4")])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue()), result)
            assess.assert_called_once()
