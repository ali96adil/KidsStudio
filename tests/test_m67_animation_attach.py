"""M67 animation attach requires explicit independent QA."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_animation_attach import attach_animations, AnimationManifestError
from kidsstudio.m67_production_handoff import build_manifest, _sha

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67AnimationAttachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_attach_all_six_without_qa_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "batch"
            workspace.mkdir()
            entries = []
            for number in range(1, 7):
                video = workspace / f"beat_{number:02d}.mp4"
                video.write_bytes(f"synthetic-{number}".encode())
                entries.append({"beat": number, "status": "RENDERED_PENDING_QA",
                                "video": video.name, "sha256": _sha(video)})
            batch = {"status": "ALL_BEATS_RENDERED_PENDING_QA",
                     "episode_id": "colors-ar-001", "beats": entries}
            manifest = build_manifest(self.storyboard)
            result = attach_animations(manifest, batch, root, workspace)
            self.assertEqual(len(result["assets"]), 6)
            self.assertTrue(all(x["godot_animation_qa"] == "PENDING"
                                for x in result["assets"]))
            self.assertNotIn("godot_animation", manifest["assets"][0])

    def test_incomplete_batch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(AnimationManifestError):
                attach_animations(build_manifest(self.storyboard),
                                  {"status": "BLOCKED"}, Path(temp), Path(temp))


if __name__ == "__main__":
    unittest.main()
