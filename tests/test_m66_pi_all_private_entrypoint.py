"""M66 acceptance regressions against the actual M65 Pi entrypoint.

No Pi, OAuth, network or YouTube access. The default CLI must remain
dry-run and must not touch supplied paths or create an upload journal.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.pi_all_private_uploader import main


class PiAllPrivateUploadDryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "missing.sqlite"
        self.inbox = root / "missing-inbox"
        self.journal = root / "missing-journal.json"
        self.args = [
            "--db", str(self.db),
            "--inbox-root", str(self.inbox),
            "--journal", str(self.journal),
        ]

    def test_default_dry_run_has_no_side_effects(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(self.args)
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "M65_PI_PRIVATE_UPLOADER_DRY_RUN")
        self.assertIs(report["network_used"], False)
        self.assertIs(report["public_release_authorized"], False)
        self.assertIs(report["mac_youtube_upload_enabled"], False)
        for path in (self.db, self.inbox, self.journal):
            self.assertFalse(path.exists())

    def test_dry_run_does_not_read_google_credentials(self):
        with patch.dict("os.environ", {
            "KIDSSTUDIO_PI_YT_CLIENT_ID": "bad",
            "KIDSSTUDIO_PI_YT_CLIENT_SECRET": "bad",
            "KIDSSTUDIO_PI_YT_REFRESH_TOKEN": "bad",
        }):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(self.args), 0)
        self.assertEqual(json.loads(output.getvalue())["network_used"], False)

    def test_execute_with_missing_credentials_fails_closed(self):
        errors = io.StringIO()
        with patch.dict("os.environ", {
            "KIDSSTUDIO_PI_YT_CLIENT_ID": "",
            "KIDSSTUDIO_PI_YT_CLIENT_SECRET": "",
            "KIDSSTUDIO_PI_YT_REFRESH_TOKEN": "",
        }), contextlib.redirect_stderr(errors):
            code = main([*self.args, "--execute"])
        self.assertEqual(code, 2)
        self.assertIn("M65_PI_PRIVATE_UPLOAD_BLOCKED", errors.getvalue())
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
