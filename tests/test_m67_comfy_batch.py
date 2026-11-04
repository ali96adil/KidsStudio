"""M67 six-image ComfyUI batch tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_comfy_batch import render_images, ImageBatchError
from kidsstudio.m67_media_jobs import make_jobs

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67ComfyBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = make_jobs(json.loads(SOURCE.read_text(encoding="utf-8")))
        cls.workflow = {"1": {"class_type": "CLIPTextEncode",
                              "inputs": {"text": ""}},
                        "2": {"class_type": "SaveImage", "inputs": {}}}

    def test_six_jobs_with_pending_qa(self):
        prompts = []
        def worker(workflow, **kwargs):
            prompts.append(workflow["1"]["inputs"]["text"])
            return {"images": [{"filename": "out.png", "type": "output"}]}
        def collector(image, destination, **kwargs):
            destination.write_bytes(b"test-only")
            return {"sha256": "f" * 64}
        with tempfile.TemporaryDirectory() as temp:
            result = render_images(self.packet, self.workflow, Path(temp),
                                   text_node="1", worker=worker,
                                   collector=collector)
            self.assertEqual(len(result["images"]), 6)
            self.assertEqual(len(prompts), 6)
            self.assertEqual(result["status"], "IMAGES_GENERATED_PENDING_QA")
            self.assertFalse(result["youtube_upload_authorized"])

    def test_invalid_workflow_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ImageBatchError):
                render_images(self.packet, self.workflow, Path(temp),
                              text_node="nonexistent")


if __name__ == "__main__":
    unittest.main()
