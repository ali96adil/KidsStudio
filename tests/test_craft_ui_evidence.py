import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from kidsstudio.craft_ui_evidence import audit_craft_ui_evidence, main
from kidsstudio.optional_tool_evidence import ToolEvidenceError


def screenshot(width: int, height: int, unique: bytes) -> bytes:
    # Synthetic header-only fixture: NOT an image suitable for visual analysis.
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00" + b"\x00\x00\x00\x00" + unique
    )


class CraftUiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.records = []
        for width, height in ((375, 812), (768, 1024), (1280, 720)):
            name = f"dashboard-{width}.png"
            data = screenshot(width, height, str(width).encode())
            file = self.root / name
            file.write_bytes(data)
            file.chmod(0o600)
            self.records.append({
                "viewport_css_width": width,
                "relative_path": name,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        self.manifest = {
            "schema_version": 1,
            "tool": "craft-anything",
            "target": "kidsstudio-owned-dashboard",
            "screenshots": self.records,
        }

    def evaluate(self, manifest=None):
        return audit_craft_ui_evidence(
            root=str(self.root), manifest=manifest or self.manifest)

    def test_three_private_hash_verified_screenshots(self):
        report = self.evaluate()
        self.assertEqual(report["status"],
                         "CRAFT_UI_EVIDENCE_HASH_VERIFIED_VISUAL_UNREVIEWED")
        self.assertEqual(
            [s["viewport_css_width_reported"] for s in report["screenshots"]],
            [375, 768, 1280])
        self.assertFalse(report["pixel_similarity_measured"])
        self.assertFalse(report["tool_provenance_authenticated"])
        self.assertFalse(report["production_approved"])
        self.assertFalse(report["publication_approved"])

    def test_changed_screenshot_rejected(self):
        (self.root / "dashboard-768.png").write_bytes(b"tampered")
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_missing_viewport_rejected(self):
        self.manifest["screenshots"] = self.records[:2]
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_duplicate_viewport_rejected(self):
        self.records[1]["viewport_css_width"] = 375
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_pixel_dimensions_mismatch_rejected(self):
        self.records[0]["viewport_css_width"] = 1280
        self.records[2]["viewport_css_width"] = 375
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_wrong_target_rejected(self):
        self.manifest["target"] = "some-other-company-app"
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_invalid_png_header_rejected(self):
        png = self.root / "dashboard-375.png"
        data = b"not a PNG" * 10
        png.write_bytes(data)
        self.records[0]["sha256"] = hashlib.sha256(data).hexdigest()
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_absolute_path_rejected(self):
        self.records[0]["relative_path"] = str(self.root / "dashboard-375.png")
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_symlink_path_rejected(self):
        link = self.root / "linked.png"
        link.symlink_to(self.root / "dashboard-375.png")
        self.records[0]["relative_path"] = link.name
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_public_screenshot_rejected(self):
        (self.root / "dashboard-1280.png").chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_git_directory_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaises(ToolEvidenceError):
            self.evaluate()

    def test_private_cli_does_not_output_path_or_content(self):
        manifest_file = self.root / "craft.json"
        manifest_file.write_text(json.dumps(self.manifest), encoding="utf-8")
        manifest_file.chmod(0o600)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--evidence-root", str(self.root),
                         "--manifest", "craft.json"])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(json.loads(out.getvalue())["mcp_or_agent_invoked"])

    def test_cli_invalid_evidence_errors_safely(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--evidence-root", str(self.root),
                         "--manifest", "missing.json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "CRAFT_UI_EVIDENCE_REJECTED")


if __name__ == "__main__":
    unittest.main()
