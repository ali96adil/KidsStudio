"""M67 animated compositor: preserve fail-closed behavior."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_animated_compositor import compose_animated
from kidsstudio.m67_episode_compositor import EpisodeComposeError
from kidsstudio.m67_production_handoff import build_manifest

ROOT = Path(__file__).resolve().parents[1]


class M67AnimatedCompositorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))
        self.manifest = build_manifest(source)
        for beat in self.manifest["assets"]:
            for kind in ("art", "voice"):
                path = self.root / beat[kind]
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(f"{kind}-{beat['beat']}".encode())
                beat[kind + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            beat["visual_qa"] = beat["voice_qa"] = "PASS"
        (self.root / "render").mkdir()
        self.output = self.root / "render" / "episode.mp4"

    def test_unapproved_animation_blocks(self):
        self.manifest["assets"][0]["godot_animation"] = "godot/beat_01.mp4"
        with patch("kidsstudio.m67_animated_compositor.shutil.which",
                   return_value="/usr/bin/tool"):
            with self.assertRaises(EpisodeComposeError):
                compose_animated(self.manifest, self.root, self.output)

    def test_animation_hash_mismatch_blocks(self):
        path = self.root / "godot/beat_01.mp4"
        path.parent.mkdir()
        path.write_bytes(b"example")
        beat = self.manifest["assets"][0]
        beat["godot_animation"] = "godot/beat_01.mp4"
        beat["godot_animation_qa"] = "PASS"
        beat["godot_animation_sha256"] = "0" * 64
        with patch("kidsstudio.m67_animated_compositor.shutil.which",
                   return_value="/usr/bin/tool"):
            with self.assertRaises(EpisodeComposeError):
                compose_animated(self.manifest, self.root, self.output)

    def test_static_fallback_can_compose(self):
        def fake_run(cmd, **kwargs):
            self.output.write_bytes(b"test-video")
        with patch("kidsstudio.m67_animated_compositor.shutil.which",
                   return_value="/usr/bin/ffmpeg"):
            with patch("kidsstudio.m67_animated_compositor.subprocess.run",
                       side_effect=fake_run):
                result = compose_animated(self.manifest, self.root, self.output)
        self.assertEqual(result["animated_beats"], 0)
        self.assertFalse(result["youtube_upload_authorized"])


if __name__ == "__main__":
    unittest.main()
