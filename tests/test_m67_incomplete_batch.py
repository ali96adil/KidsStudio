"""Regression: an incomplete worker batch cannot report generation success."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_produce import prepare, generate, ProductionStageError

STORYBOARD = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class IncompleteBatchTests(unittest.TestCase):
    def test_missing_image_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "episode"
            prepare(json.loads(STORYBOARD.read_text(encoding="utf-8")), root)

            def image_fn(packet, workflow, folder, **kwargs):
                (folder / "comfy_batch_report.json").write_text("{}")
                return {"images": [None] * 5}

            def voice_fn(packet, folder, **kwargs):
                (folder / "voice_batch_report.json").write_text("{}")
                return {"voices": [None] * 6}

            with self.assertRaises(ProductionStageError):
                generate(root, workflow={}, text_node="1", voice="Arabic",
                         image_fn=image_fn, voice_fn=voice_fn)
