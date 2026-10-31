"""M67 QA beat set must match the exact six storyboard beats."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.m67_produce import prepare, pin_reviewed, ProductionStageError
from kidsstudio.m67_media_validation import inspect_media_jobs

STORYBOARD = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class ExactBeatApprovalTests(unittest.TestCase):
    def test_decode_duplicate_beat_rejected(self):
        storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "episode"
            prepare(storyboard, root)
            packet = json.loads((root / "jobs.json").read_text())
            for job in packet["jobs"]:
                png = root / job["visual"]["output"]
                png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                                + struct.pack(">II", 1280, 720))
                wav = root / job["voice"]["output"]
                with wave.open(str(wav), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(48000)
                    audio.writeframes(b"\x00\x00" * 4800)
            inspection = inspect_media_jobs(packet, root)
            results = inspection["results"]
            approvals = {"episode_id": storyboard["episode_id"], "assets": [
                {"beat": row["beat"], "art_sha256": row["visual_sha256"],
                 "voice_sha256": row["voice_sha256"],
                 "visual_qa": "PASS", "voice_qa": "PASS"} for row in results]}
            decoded = {"status": "MEDIA_DECODED_PENDING_QA", "results": [
                {"beat": row["beat"], "visual_sha256": row["visual_sha256"],
                 "voice_sha256": row["voice_sha256"]} for row in results]}
            decoded["results"][-1]["beat"] = 1
            with patch("kidsstudio.m67_produce.decode_check", return_value=decoded):
                with self.assertRaises(ProductionStageError):
                    pin_reviewed(root, approvals)
            self.assertFalse((root / "reviewed_manifest.json").exists())
