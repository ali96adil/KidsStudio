import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from kidsstudio.craft_ui_pixel_compare import compare_craft_ui, main
from kidsstudio.optional_tool_evidence import ToolEvidenceError


class CraftUiPixelCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.baseline = self.make_manifest("baseline")
        self.candidate = self.make_manifest("candidate")

    def make_manifest(self, prefix):
        records = []
        for width, height in ((375, 440), (768, 500), (1280, 720)):
            name = f"{prefix}-{width}.png"
            path = self.root / name
            Image.new("RGB", (width, height), (width % 256, 40, 70)).save(path)
            path.chmod(0o600)
            records.append({
                "viewport_css_width": width,
                "relative_path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        return {
            "schema_version": 1,
            "tool": "craft-anything",
            "target": "kidsstudio-owned-dashboard",
            "screenshots": records,
        }

    def change(self, width, *, color=(255, 255, 255), dimensions=None):
        record = next(r for r in self.candidate["screenshots"]
                      if r["viewport_css_width"] == width)
        path = self.root / record["relative_path"]
        with Image.open(path) as image:
            size = image.size
            new_image = image.convert("RGB")
        if dimensions:
            size = dimensions
        if size != new_image.size:
            new_image = Image.new("RGB", size, color)
        else:
            for x in range(new_image.width):
                for y in range(new_image.height):
                    new_image.putpixel((x, y), color)
        new_image.save(path)
        path.chmod(0o600)
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def report(self, **kwargs):
        return compare_craft_ui(
            evidence_root=str(self.root),
            baseline_manifest=self.baseline,
            candidate_manifest=self.candidate, **kwargs)

    def test_identical_images_pass_but_not_approved(self):
        r = self.report()
        self.assertEqual(r["status"], "CRAFT_PIXEL_COMPARE_WITHIN_LIMITS_UNREVIEWED")
        self.assertTrue(r["full_png_decoding_performed"])
        self.assertTrue(r["pixel_difference_measured"])
        self.assertEqual(len(r["viewports"]), 3)
        self.assertTrue(all(v["mean_rgb_absolute_difference"] == 0 for v in r["viewports"]))
        self.assertFalse(r["layout_functionality_verified"])
        self.assertFalse(r["publication_approved"])

    def test_large_visual_change_flagged_without_publication(self):
        self.change(375)
        r = self.report()
        self.assertEqual(r["status"], "CRAFT_PIXEL_COMPARE_DIFFERENT_REVIEW_REQUIRED")
        self.assertGreater(r["viewports"][0]["changed_pixel_fraction"], 0.95)
        self.assertFalse(r["production_approved"])

    def test_dimension_mismatch_rejected(self):
        self.change(768, dimensions=(770, 500))
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_changed_bytes_without_updated_sha_rejected(self):
        (self.root / "candidate-375.png").write_bytes(b"tampered")
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_valid_header_but_truncated_png_rejected(self):
        record = self.candidate["screenshots"][0]
        path = self.root / record["relative_path"]
        data = path.read_bytes()[:28]
        path.write_bytes(data)
        record["sha256"] = hashlib.sha256(data).hexdigest()
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_reject_invalid_thresholds(self):
        with self.assertRaises(ToolEvidenceError):
            self.report(mean_diff_limit=1.01)
        with self.assertRaises(ToolEvidenceError):
            self.report(changed_pixel_limit=True)
        with self.assertRaises(ToolEvidenceError):
            self.report(channel_threshold=256)

    def test_mismatched_manifest_target_rejected(self):
        self.candidate["target"] = "third-party"
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_reject_public_candidate_file(self):
        (self.root / "candidate-768.png").chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_reject_symlink_candidate(self):
        source = self.root / "candidate-1280.png"
        (self.root / "link.png").symlink_to(source)
        self.candidate["screenshots"][2]["relative_path"] = "link.png"
        with self.assertRaises(ToolEvidenceError):
            self.report()

    def test_cli_private_files_redacts_paths(self):
        for filename, data in (("baseline.json", self.baseline),
                               ("candidate.json", self.candidate)):
            path = self.root / filename
            path.write_text(json.dumps(data), encoding="utf-8")
            path.chmod(0o600)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--evidence-root", str(self.root),
                         "--baseline-manifest", "baseline.json",
                         "--candidate-manifest", "candidate.json"])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(json.loads(out.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
