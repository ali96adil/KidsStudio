"""M67 local runner review-gate tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_local_episode_runner import run_local, LocalRunError
from kidsstudio.m67_production_handoff import build_manifest

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67LocalRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_missing_assets_blocks_before_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises((LocalRunError, ValueError)):
                run_local(self.storyboard, build_manifest(self.storyboard),
                          root, root / "rig.json", root / "review.json",
                          root / "evidence.json", root / "batch")

    def test_review_gate_does_not_compose_without_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = build_manifest(self.storyboard)
            for item in manifest["assets"]:
                for kind in ("art", "voice"):
                    file = root / item[kind]
                    file.parent.mkdir(exist_ok=True)
                    file.write_bytes(f"{kind}{item['beat']}".encode())
                    item[kind + "_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
                item["visual_qa"] = item["voice_qa"] = "PASS"
            def fake_batch(storyboard, rig, workspace, **kwargs):
                workspace.mkdir()
                entries = []
                for i in range(1, 7):
                    video = workspace / f"beat_{i:02d}.mp4"
                    video.write_bytes(f"fake{i}".encode())
                    entries.append({"beat": i, "status": "RENDERED_PENDING_QA",
                                    "video": video.name,
                                    "sha256": hashlib.sha256(video.read_bytes()).hexdigest()})
                return {"status": "ALL_BEATS_RENDERED_PENDING_QA",
                        "episode_id": storyboard["episode_id"], "beats": entries}
            def should_not_compose(*args, **kwargs):
                self.fail("unreviewed video was composed")
            result = run_local(
                self.storyboard, manifest, root, root / "rig.json",
                root / "review.json", root / "evidence.json",
                root / "batch", batch_fn=fake_batch,
                compose_fn=should_not_compose)
            self.assertEqual(result["status"], "ANIMATIONS_PENDING_QA")
            self.assertFalse(result["youtube_upload_authorized"])


if __name__ == "__main__":
    unittest.main()
