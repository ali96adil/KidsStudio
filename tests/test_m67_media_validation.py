"""M67 media job and structural validation tests."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from kidsstudio.m67_media_jobs import make_jobs
from kidsstudio.m67_media_validation import inspect_media_jobs

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67MediaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_job_count_and_no_approval(self):
        jobs = make_jobs(self.storyboard)
        self.assertEqual(len(jobs["jobs"]), 6)
        self.assertEqual(jobs["status"], "MEDIA_JOBS_PREPARED_NOT_GENERATED")
        self.assertFalse(jobs["youtube_upload_authorized"])

    def test_missing_media_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            report = inspect_media_jobs(make_jobs(self.storyboard), Path(temp))
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(len(report["results"]), 6)

    def test_structural_media_never_grants_qa(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet = make_jobs(self.storyboard)
            for job in packet["jobs"]:
                png = root / job["visual"]["output"]
                wav = root / job["voice"]["output"]
                png.parent.mkdir(exist_ok=True)
                wav.parent.mkdir(exist_ok=True)
                png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                                + struct.pack(">II", 1280, 720))
                with wave.open(str(wav), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(48000)
                    audio.writeframes(b"\x00\x00" * 4800)
            report = inspect_media_jobs(packet, root)
            self.assertEqual(report["status"], "MEDIA_STRUCTURALLY_READY_PENDING_QA")
            self.assertEqual(report["visual_qa"], "PENDING")
            self.assertFalse(report["youtube_upload_authorized"])


if __name__ == "__main__":
    unittest.main()
