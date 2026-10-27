from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from kidsstudio.godot_export import export_godot
from kidsstudio.godot_render import GodotRenderError, render_godot_project


class GodotRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        assets = self.root / "assets"
        assets.mkdir()
        parts = []
        for i, name in enumerate([
            "body", "head", "arm_left", "arm_right", "leg_left", "leg_right"
        ]):
            image = Image.new("RGBA", (64, 64))
            ImageDraw.Draw(image).ellipse((8, 8, 56, 56),
                                         fill=(240, 185, 160, 255))
            image.save(assets / (name + ".png"))
            parts.append({
                "id": name, "file": "assets/" + name + ".png",
                "pivot": [32, 32], "z": i
            })
        self.manifest = self.root / "rig.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "test",
            "canvas": {"width": 64, "height": 64}, "parts": parts
        }))
        self.timeline = self.root / "scene_spec.json"
        self.timeline.write_text(json.dumps({
            "schema_version": 1, "fps": 30, "duration_seconds": 2,
            "beats": [{"start": 0, "end": 2, "motion": "wave_right"}]
        }))
        self.project = self.root / "project_export"
        export_godot(self.manifest, self.timeline, self.project)

    def test_mocked_native_render_produces_hashed_mp4(self):
        def fake_run(command, **kwargs):
            if "--write-movie" in command:
                target = Path(command[command.index("--write-movie") + 1])
                target.write_bytes(b"test avi")
            else:
                Path(command[-1]).write_bytes(b"test mp4")
        with patch("kidsstudio.godot_render.shutil.which", side_effect=lambda x: x), \
             patch("kidsstudio.godot_render.subprocess.run", side_effect=fake_run) as run:
            status = render_godot_project(self.project, self.root / "render")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(status["status"], "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW")
        self.assertTrue((self.root / "render" / "character_preview.mp4").exists())
        self.assertTrue(status["owner_publication_approval_required"])
        self.assertEqual(status["frames_expected"], 60)
        self.assertEqual(status["mp4_sha256"],
                         hashlib.sha256(b"test mp4").hexdigest())

    def test_script_tampering_blocks_execution(self):
        with (self.project / "scripts" / "rig_player.gd").open("a") as handle:
            handle.write("\n# Changed after project export\n")
        with self.assertRaises(GodotRenderError):
            render_godot_project(self.project, self.root / "tampered")

    def test_missing_executable_blocks(self):
        with patch("kidsstudio.godot_render.shutil.which", return_value=None):
            with self.assertRaises(GodotRenderError):
                render_godot_project(self.project, self.root / "noexec")

    def test_preexisting_output_cannot_be_reused(self):
        dest = self.root / "existing"
        dest.mkdir()
        with self.assertRaises(FileExistsError):
            render_godot_project(self.project, dest)


if __name__ == "__main__":
    unittest.main()
