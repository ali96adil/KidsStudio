"""M67 Pi import staging tests, isolated from live Pi credentials."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.m67_pi_ordinary_import import import_transferred, PiImportError
from kidsstudio.youtube_private_upload import file_sha256


class InboxStub:
    def __init__(self, queue, root):
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)

    def prepare(self, job):
        (self.root / job).mkdir(exist_ok=True)

    def _files(self, job, partial):
        names = ("episode_qa_master.mp4", "private_upload_plan.json",
                 "m8_readiness.json")
        return tuple(self.root / job / (name + ".part") for name in names)

    def accept(self, job):
        return {"master_sha256": file_sha256(self._files(job, True)[0])}


class ImportTests(unittest.TestCase):
    def test_staging_does_not_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [root / n for n in ("movie.mp4", "plan.json", "ready.json")]
            paths[0].write_bytes(b"fixture")
            paths[2].write_bytes(b"readiness")
            paths[1].write_text(json.dumps({"render_job_id": "a" * 32,
                "master_sha256": file_sha256(paths[0]),
                "readiness_sha256": file_sha256(paths[2])}))
            with patch("kidsstudio.m67_pi_ordinary_import.PiOrdinaryInbox", InboxStub):
                result = import_transferred(
                    object(), root / "inbox", render_job_id="a" * 32,
                    transferred_master=paths[0], plan_file=paths[1],
                    readiness_file=paths[2],
                    expected_sha256=file_sha256(paths[0]))
            self.assertFalse(result["youtube_uploaded"])

    def test_invalid_digest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [root / n for n in ("movie.mp4", "plan.json", "ready.json")]
            for path in paths:
                path.write_bytes(b"fixture")
            with self.assertRaises(PiImportError):
                import_transferred(
                    object(), root / "inbox", render_job_id="a" * 32,
                    transferred_master=paths[0], plan_file=paths[1],
                    readiness_file=paths[2], expected_sha256="0" * 64)
