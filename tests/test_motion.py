from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.motion import MOTIONS, compose_frame, create_motion_evidence, load_rig


class MotionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        parts = []
        for z, ident in enumerate(("body", "head", "arm_left",
                                   "arm_right", "leg_left", "leg_right")):
            path = self.root / "assets" / f"{ident}.png"
            image = Image.new("RGBA", (128, 128))
            draw = ImageDraw.Draw(image)
            draw.ellipse((30, 30, 100, 105), fill=(240, 172, 167, 255))
            # uniquely distinguish moving right arm
            if ident == "arm_right":
                draw.rectangle((70, 58, 107, 98), fill=(10, 10, 10, 255))
            image.save(path)
            parts.append({
                "id": ident, "file": f"assets/{ident}.png",
                "pivot": [65, 60], "z": z
            })
        self.manifest = self.root / "rig.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "dummy",
            "canvas": {"width": 128, "height": 128},
            "parts": parts
        }), encoding="utf-8")

    def test_sample_actions_generate_contact_sheet_and_gif(self):
        result = create_motion_evidence(self.manifest, self.root / "preview", side=128)
        self.assertTrue(Path(result["contact_sheet"]).is_file())
        self.assertTrue(Path(result["animation"]).is_file())
        self.assertEqual(result["motions"], list(MOTIONS))
        self.assertTrue(result["visual_review_required"])

    def test_arm_moves_independently(self):
        rig = load_rig(self.manifest)
        neutral = compose_frame(rig, "neutral", 0.5, max_side=128)
        wave = compose_frame(rig, "wave_right", 0.5, max_side=128)
        self.assertNotEqual(neutral.tobytes(), wave.tobytes())

    def test_invalid_motion_rejected(self):
        rig = load_rig(self.manifest)
        with self.assertRaises(ValueError):
            compose_frame(rig, "unknown", 0.5)

    def test_previews_not_overwritten(self):
        out = self.root / "preview"
        create_motion_evidence(self.manifest, out, side=128, gif=False)
        with self.assertRaises(FileExistsError):
            create_motion_evidence(self.manifest, out, side=128, gif=False)


if __name__ == "__main__":
    unittest.main()
