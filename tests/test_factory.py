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

    def upload_reference(self, payload, filename):
        self.uploaded_reference = (payload, filename)
        return filename

    def queue(self, prepared):
        self.calls.append(prepared["prompt"]["1"]["inputs"]["text"])
        return "test-" + str(len(self.calls))

    def await_image(self, prompt_id, *, save_node_id, timeout_seconds):
        assert isinstance(save_node_id, str) and save_node_id
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

    def test_canonical_reference_is_uploaded_once_and_recorded(self):
        self.workflow_data = json.loads(self.workflow.read_text())
        self.workflow_data["3"] = {
            "class_type": "LoadImage",
            "inputs": {"image": "placeholder.png"},
        }
        self.workflow_data["2"]["inputs"]["images"] = ["3", 0]
        workflow_bytes = json.dumps(self.workflow_data).encode()
        self.workflow.write_bytes(workflow_bytes)
        profile = json.loads(self.profile.read_text())
        profile["approved_workflow_sha256"] = hashlib.sha256(workflow_bytes).hexdigest()
        profile["allowed_node_classes"].append("LoadImage")
        profile["reference_node_id"] = "3"
        self.profile.write_text(json.dumps(profile))
        reference = self.root / "canonical_bunny.png"
        reference.write_bytes(self.valid_png)
        client = FakeClient(self.valid_png)
        state = build_character(
            self.blueprint, self.workflow, self.profile,
            self.root / "ref_batch", client=client,
            preview_side=96, reference_image=reference,
        )
        self.assertEqual(state["status"], "NEEDS_INDEPENDENT_VISUAL_REVIEW")
        self.assertTrue(state["reference_conditioned"])
        self.assertEqual(state["canonical_reference_sha256"],
                         hashlib.sha256(self.valid_png).hexdigest())
        self.assertEqual(len(client.calls), 6)
        self.assertEqual(client.uploaded_reference[0], self.valid_png)
        for part_prompt in client.calls:
            self.assertIn("Original character:", part_prompt)

    def test_reference_upload_uses_real_multipart_crlf(self):
        from kidsstudio.factory import LocalComfyClient
        client = LocalComfyClient()
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *args):
                return b'{"name":"KidsStudio_reference_abc.png","subfolder":"","type":"input"}'
        class Opener:
            def open(self, request, timeout):
                self.req = request
                return Response()
        fake = Opener()
        client.opener = fake
        result = client.upload_reference(
            self.valid_png, "KidsStudio_reference_abc.png")
        self.assertEqual(result, "KidsStudio_reference_abc.png")
        self.assertIn(b"\r\n", fake.req.data)
        self.assertIn(b'Content-Disposition: form-data; name="image"', fake.req.data)

    def test_strict_geometry_stops_on_first_misplaced_part(self):
        blueprint = json.loads(self.blueprint.read_text())
        blueprint["qa_policy"] = {
            "strict_parts": True,
            "max_outside_fraction": 0.10,
            "min_inside_fill_fraction": 0.01,
            "alpha_threshold": 32,
            "reject_identical_layers": True,
        }
        # Every part is intentionally constrained to top-left, while fake
        # ComfyUI places a large circle in the middle of the canvas.
        for part in blueprint["parts"]:
            part["expected_region"] = [0, 0, 12, 12]
        self.blueprint.write_text(json.dumps(blueprint))
        client = FakeClient(self.valid_png)
        dest = self.root / "early_reject"
        with self.assertRaises(FactoryError) as error:
            build_character(
                self.blueprint, self.workflow, self.profile, dest,
                client=client, preview_side=96,
            )
        self.assertIn("GEOMETRY_FAIL", str(error.exception))
        self.assertEqual(len(client.calls), 1, "Bad art must abort before the next diffusion run.")
        state = json.loads((dest / "factory_report.json").read_text())
        self.assertEqual(state["status"], "FAILED")

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
