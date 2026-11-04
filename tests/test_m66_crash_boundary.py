"""M66 subprocess crash durability of production Pi upload journal."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kidsstudio.youtube_private_upload import UploadJournal, YouTubePrivateError


class CrashBoundaryTests(unittest.TestCase):
    def test_abrupt_exit_keeps_one_shot_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / "upload.sqlite"
            job, sha, plan = "a" * 32, "b" * 64, "c" * 64
            code = ("import os,sys\n"
                    "from kidsstudio.youtube_private_upload import UploadJournal\n"
                    "UploadJournal(sys.argv[1]).reserve(sys.argv[2],sys.argv[3],sys.argv[4])\n"
                    "os._exit(37)\n")
            run = subprocess.run(
                [sys.executable, "-c", code, str(journal), job, sha, plan],
                cwd=str(Path(__file__).resolve().parents[1]), timeout=20,
                check=False)
            self.assertEqual(run.returncode, 37)
            reopened = UploadJournal(journal)
            self.assertEqual(reopened.status(job)["state"], "STARTED")
            with self.assertRaises(YouTubePrivateError):
                reopened.reserve(job, sha, plan)
            with self.assertRaises(YouTubePrivateError):
                reopened.reserve("d" * 32, sha, plan)


if __name__ == "__main__":
    unittest.main()
