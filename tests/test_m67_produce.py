"""M67 production command tests: lifecycle, immutable review, failure gates."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.m67_produce import prepare, generate, inspect, pin_reviewed, ProductionStageError
from kidsstudio.m67_media_validation import inspect_media_jobs

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class ProductionCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_prepare_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episode"
            result = prepare(self.storyboard, root)
            self.assertEqual(result["beats"], 6)
            self.assertEqual(len(json.loads((root / "jobs.json").read_text())["jobs"]), 6)
            with self.assertRaises(ProductionStageError):
                prepare(self.storyboard, root)

    def test_generate_uses_both_engines_and_refuses_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episode"
            prepare(self.storyboard, root)
            calls = []
            def image_fn(packet, workflow, folder, **kwargs):
                calls.append("images")
                (folder / "comfy_batch_report.json").write_text("{}")
                return {"images": [None] * 6}
            def voice_fn(packet, folder, **kwargs):
                calls.append("voices")
                (folder / "voice_batch_report.json").write_text("{}")
                return {"voices": [None] * 6}
            result = generate(root, workflow={}, text_node="1", voice="Arabic",
                              image_fn=image_fn, voice_fn=voice_fn)
            self.assertEqual(result["status"], "GENERATED_PENDING_MEDIA_INSPECTION")
            self.assertEqual(calls, ["images", "voices"])
            with self.assertRaises(ProductionStageError):
                generate(root, workflow={}, text_node="1", voice="Arabic",
                         image_fn=image_fn, voice_fn=voice_fn)

    def test_pin_requires_exact_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episode"
            prepare(self.storyboard, root)
            jobs = json.loads((root / "jobs.json").read_text())["jobs"]
            for job in jobs:
                png = root / job["visual"]["output"]
                wav = root / job["voice"]["output"]
                png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                                + struct.pack(">II", 1280, 720))
                with wave.open(str(wav), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(48000)
                    audio.writeframes(b"\x00\x00" * 4800)
            inspection = inspect_media_jobs(json.loads((root / "jobs.json").read_text()), root)
            approvals = {"episode_id": self.storyboard["episode_id"], "assets": [
                {"beat": r["beat"], "art_sha256": r["visual_sha256"],
                 "voice_sha256": r["voice_sha256"],
                 "visual_qa": "PASS", "voice_qa": "PASS"}
                for r in inspection["results"]]}
            approvals["assets"][0]["voice_sha256"] = "0" * 64
            decoded = {"status": "MEDIA_DECODED_PENDING_QA", "results": [
                {"beat": r["beat"], "visual_sha256": r["visual_sha256"],
                 "voice_sha256": r["voice_sha256"]}
                for r in inspection["results"]]}
            with patch("kidsstudio.m67_produce.decode_check", return_value=decoded):
                with self.assertRaises(ProductionStageError):
                    pin_reviewed(root, approvals)
            self.assertFalse((root / "reviewed_manifest.json").exists())
            approvals["assets"][0]["voice_sha256"] = inspection["results"][0]["voice_sha256"]
            with patch("kidsstudio.m67_produce.decode_check", return_value=decoded):
                result = pin_reviewed(root, approvals)
            self.assertEqual(result["status"], "ASSETS_QA_READY_FOR_RENDER")
            self.assertFalse(result["public_release_authorized"])


if __name__ == "__main__":
    unittest.main()
