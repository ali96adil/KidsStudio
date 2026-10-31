"""M67 ComfyUI collection validation tests."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_comfy_collect import collect_png
from kidsstudio.m67_comfy_worker import ComfyWorkerError


class FakeResponse:
    def __init__(self, blob):
        self.blob = blob
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.blob[:size]


class M67ComfyCollectTests(unittest.TestCase):
    def test_collect_requires_valid_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "scene.png"
            header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
            bad = header + struct.pack(">II", 512, 512)
            with patch("kidsstudio.m67_comfy_collect.urlopen",
                       return_value=FakeResponse(bad)):
                with self.assertRaises(ComfyWorkerError):
                    collect_png({"filename": "x.png", "type": "output"}, png)
            self.assertFalse(png.exists())

    def test_collect_does_not_grant_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "scene.png"
            blob = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                    + struct.pack(">II", 1280, 720))
            with patch("kidsstudio.m67_comfy_collect.urlopen",
                       return_value=FakeResponse(blob)):
                result = collect_png({"filename": "x.png", "type": "output"}, png)
            self.assertEqual(result["visual_qa"], "PENDING")
            self.assertTrue(png.exists())

    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ComfyWorkerError):
                collect_png({"filename": "../x.png", "type": "output"},
                            Path(tmp) / "scene.png")


if __name__ == "__main__":
    unittest.main()
