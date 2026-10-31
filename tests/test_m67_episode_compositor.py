"""M67 FFmpeg compositor tests with injected process and asset integrity."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_episode_compositor import compose, EpisodeComposeError
from kidsstudio.m67_production_handoff import build_manifest

ROOT = Path(__file__).resolve().parents[1]


class M67EpisodeCompositorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        storyboard = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))
        self.manifest = build_manifest(storyboard)
        for item in self.manifest["assets"]:
            for kind in ("art", "voice"):
                file = self.root / item[kind]
                file.parent.mkdir(exist_ok=True)
                file.write_bytes((kind + str(item["beat"])).encode())
                item[kind + "_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            item["visual_qa"] = "PASS"
            item["voice_qa"] = "PASS"
        (self.root / "render").mkdir()
        self.output = self.root / "render" / "episode_qa_master.mp4"

    def test_builds_ffmpeg_graph_without_upload(self):
        def fake_run(command, **kwargs):
            self.assertIn("-filter_complex", command)
            self.assertIn("concat=n=6:v=1:a=1", " ".join(command))
            self.output.write_bytes(b"test-only-mp4")
        with patch("kidsstudio.m67_episode_compositor.shutil.which",
                   return_value="/usr/bin/ffmpeg"):
            with patch("kidsstudio.m67_episode_compositor.subprocess.run",
                       side_effect=fake_run):
                result = compose(self.manifest, self.root, self.output)
        self.assertFalse(result["pi_transfer_authorized"])
        self.assertFalse(result["youtube_upload_authorized"])
        self.assertEqual(result["render_qa"], "PENDING")

    def test_bad_qa_blocks_before_ffmpeg(self):
        self.manifest["assets"][0]["voice_qa"] = "PENDING"
        with self.assertRaises(EpisodeComposeError):
            compose(self.manifest, self.root, self.output)

    def test_existing_output_not_overwritten(self):
        self.output.write_bytes(b"old")
        with self.assertRaises(EpisodeComposeError):
            compose(self.manifest, self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
