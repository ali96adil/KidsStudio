from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.factory import FactoryError, LocalComfyClient, build_character


class FakeClient:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def queue(self, prepared):
        self.calls.append(prepared["prompt"]["1"]["inputs"]["text"])
        return "test-" + str(len(self.calls))

    def await_image(self, prompt_id, *, timeout_seconds):
        return {"filename": prompt_id + ".png", "subfolder": "", "type": "output"}

    def download_png(self, image_ref):
        return self.payload


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.blueprint = self.root / "blueprint.json"
        self.workflow = self.root / "workflow_api.json"
        self.profile = self.root / "profile.json"
        parts = [
            {"id": name, "instruction": "standalone piece",
             "pivot": [32, 32], "z": i}
            for i, name in enumerate((
                "body", "head", "arm_left", "arm_right", "leg_left", "leg_right"
            ))
        ]
        self.blueprint.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny_v02",
            "canvas": {"width": 64, "height": 64},
            "identity_prompt": "Original cartoon bunny",
            "parts": parts,
        }))
        graph = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder"}},
            "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI"}}
        }
        raw = json.dumps(graph).encode()
        self.workflow.write_bytes(raw)
        self.profile.write_text(json.dumps({
            "approved_workflow_sha256": hashlib.sha256(raw).hexdigest(),
            "allowed_node_classes": ["CLIPTextEncode", "SaveImage"],
            "approved_model_names": [],
            "prompt_node_id": "1", "filename_node_id": "2",
        }))
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((12, 12, 52, 52), fill=(239, 184, 179, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        self.valid_png = buf.getvalue()

    def test_complete_pipeline_creates_manifest_preview_and_status(self):
        client = FakeClient(self.valid_png)
        dest = self.root / "batch"
        state = build_character(
            self.blueprint, self.workflow, self.profile, dest,
            client=client, preview_side=96
        )
        self.assertEqual(state["status"], "NEEDS_INDEPENDENT_VISUAL_REVIEW")
        self.assertEqual(len(client.calls), 6)
        self.assertTrue((dest / "rig.json").exists())
        self.assertTrue((dest / "review" / "motion_contact_sheet.png").exists())
        self.assertTrue((dest / "review" / "motion_preview.gif").exists())
        self.assertTrue((dest / "factory_report.json").exists())

    def test_opaque_png_fails_closed_before_second_job(self):
        img = Image.new("RGB", (64, 64), (255, 255, 255))
        buf = BytesIO()
        img.save(buf, "PNG")
        client = FakeClient(buf.getvalue())
        dest = self.root / "broken"
        with self.assertRaises(FactoryError):
            build_character(
                self.blueprint, self.workflow, self.profile, dest,
                client=client, preview_side=96
            )
        self.assertEqual(len(client.calls), 1)
        state = json.loads((dest / "factory_report.json").read_text())
        self.assertEqual(state["status"], "FAILED")
        self.assertEqual(state["error_type"], "FactoryError")

    def test_preexisting_directory_never_overwritten(self):
        folder = self.root / "existing"
        folder.mkdir()
        with self.assertRaises(FileExistsError):
            build_character(
                self.blueprint, self.workflow, self.profile, folder,
                client=FakeClient(self.valid_png)
            )

    def test_unsafe_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            LocalComfyClient("http://example.com:8188")

    def test_unsafe_image_reference_rejected_before_request(self):
        client = LocalComfyClient()
        for name in ("../secret.png", "/etc/passwd.png", "picture.jpg"):
            with self.subTest(name=name), self.assertRaises(FactoryError):
                client.download_png({
                    "filename": name, "subfolder": "", "type": "output"
                })


if __name__ == "__main__":
    unittest.main()
