"""M67 Godot batch and inspection smoke tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_batch_godot import batch_render, BatchRenderError
from kidsstudio.m67_batch_inspection import inspect_batch
from kidsstudio.m67_production_handoff import build_manifest

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_complete_batch_and_inspection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("rig.json", "review.json", "evidence.json"):
                (root / name).write_text("{}")
            def exporter(rig, scene, project, **kwargs):
                self.assertTrue(kwargs["require_reviewed"])
                project.mkdir()
            def renderer(project, output):
                output.mkdir()
                video = output / "character_preview.mp4"
                video.write_bytes(b"synthetic-only")
                return {"status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                        "mp4": str(video)}
            workspace = root / "batch"
            report = batch_render(
                self.storyboard, root / "rig.json", workspace,
                review_report=root / "review.json",
                evidence_path=root / "evidence.json",
                export_fn=exporter, render_fn=renderer)
            self.assertEqual(len(report["beats"]), 6)
            result = inspect_batch(build_manifest(self.storyboard), report,
                                   root, workspace)
            self.assertEqual(result["status"], "RENDERS_VERIFIED_PENDING_QA")
            self.assertFalse(result["upload_authorized"])

    def test_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("rig.json", "review.json", "evidence.json"):
                (root / name).write_text("{}")
            def exporter(rig, scene, project, **kwargs):
                project.mkdir()
            def renderer(project, output):
                raise RuntimeError("injected")
            with self.assertRaises(BatchRenderError):
                batch_render(self.storyboard, root / "rig.json", root / "batch",
                             review_report=root / "review.json",
                             evidence_path=root / "evidence.json",
                             export_fn=exporter, render_fn=renderer)
            report = json.loads((root / "batch/batch_report.json").read_text())
            self.assertEqual(report["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
