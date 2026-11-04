"""M68 portrait renderer safety regression tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_shorts_plan import derive
from kidsstudio.m68_shorts_render import render_short, ShortRenderError


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class ShortsRenderTests(unittest.TestCase):
    def test_unapproved_assets_never_render(self):
        storyboard = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        short = derive(storyboard)["shorts"][0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises((ShortRenderError, KeyError, ValueError)):
                render_short(short, {"episode_id": storyboard["episode_id"], "assets": []},
                             root, root / "short.mp4")
            self.assertFalse((root / "short.mp4").exists())

    def test_source_episode_mismatch_rejected(self):
        storyboard = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        short = derive(storyboard)["shorts"][0]
        short["source_episode_id"] = "wrong-episode"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises((ShortRenderError, KeyError, ValueError)):
                render_short(short, {"episode_id": storyboard["episode_id"], "assets": []},
                             root, root / "short.mp4")
