"""Preproduction two-part bunny test: absolutely no real model/paid API in CI."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.part_probe import (
    run_two_part_probe, joint_overlap, ProbeError
)
from kidsstudio.factory import FactoryError
from kidsstudio.cli import main as kidsstudio_cli


class FakeComfy:
    def __init__(self, images):
        self.images = images
        self.queued = []
        self.uploaded = []
        self.output_ids = []

    def upload_reference(self, data, name):
        self.uploaded.append((name, hashlib.sha256(data).hexdigest()))
        return name

    def queue(self, prepared):
        self.queued.append(prepared)
        return f"local-{len(self.queued)}"

    def await_image(self, prompt_id, *, save_node_id, timeout_seconds):
        self.output_ids.append(save_node_id)
        return {"filename": prompt_id + ".png", "subfolder": "", "type": "output"}

    def download_png(self, ref):
        number = int(ref["filename"].split("-")[1].split(".")[0])
        return self.images[number - 1]


def part_png(name, *, overlap=True):
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if name == "body":
        draw.ellipse((20, 15, 87, 105), fill=(235, 178, 164, 255))
    elif overlap:
        draw.ellipse((69, 40, 107, 100), fill=(250, 172, 163, 255))
    else:
        draw.ellipse((89, 78, 113, 115), fill=(250, 172, 163, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.blueprint = self.root / "bunny.json"
        self.workflow = self.root / "comfy_api.json"
        self.profile = self.root / "profile.json"
        self.reference = self.root / "reference.png"
        Image.new("RGBA", (128, 128), (200, 130, 118, 255)).save(self.reference)
        ids = ["body", "arm_right", "head", "arm_left", "leg_left", "leg_right"]
        parts = []
        for z, name in enumerate(ids):
            region = ([12, 12, 92, 112] if name == "body"
                      else [65, 34, 120, 120] if name == "arm_right"
                      else [0, 0, 128, 128])
            parts.append({
                "id": name, "instruction": "isolated layer",
                "pivot": [77, 63] if name == "arm_right" else [60, 60],
                "z": z, "expected_region": region,
            })
        self.blueprint.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny_probe",
            "canvas": {"width": 128, "height": 128},
            "identity_prompt": "Original peach pastel bunny",
            "qa_policy": {
                "strict_parts": True,
                "max_outside_fraction": 0.18,
                "min_inside_fill_fraction": 0.003,
                "alpha_threshold": 32,
                "reject_identical_layers": True,
            },
            "parts": parts,
        }))
        self.graph = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "sample"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
            "3": {"class_type": "ApprovedCondition",
                  "inputs": {"image": ["2", 0]}},
            "4": {"class_type": "Sampler",
                  "inputs": {"positive": ["1", 0], "identity": ["3", 0]}},
            "5": {"class_type": "AlphaMatting",
                  "inputs": {"sample": ["4", 0]}},
            "6": {"class_type": "SaveImage",
                  "inputs": {"images": ["5", 0], "filename_prefix": "test"}},
        }
        self._save_graph()
        self.client = FakeComfy([part_png("body"), part_png("arm_right")])

    def _save_graph(self):
        raw = json.dumps(self.graph).encode()
        self.workflow.write_bytes(raw)
        self.profile.write_text(json.dumps({
            "approved_workflow_sha256": hashlib.sha256(raw).hexdigest(),
            "allowed_node_classes": [
                "CLIPTextEncode", "LoadImage", "ApprovedCondition",
                "Sampler", "AlphaMatting", "SaveImage",
            ],
            "approved_model_names": [],
            "prompt_node_id": "1", "reference_node_id": "2",
            "filename_node_id": "6",
            "production_contract": {
                "conditioning_node_id": "3",
                "sampler_node_id": "4", "matting_node_id": "5",
            },
        }))

    def run(self, name="probe", client=None):
        return run_two_part_probe(
            self.blueprint, self.workflow, self.profile,
            self.reference, self.root / name,
            client=self.client if client is None else client,
            preview_side=256,
        )

    def test_probe_runs_exactly_two_jobs_and_stages_evidence(self):
        state = self.run()
        self.assertEqual(state["status"], "PROBE_READY_FOR_VISUAL_INSPECTION")
        self.assertEqual([j["part_id"] for j in state["jobs"]],
                         ["body", "arm_right"])
        self.assertEqual(len(self.client.queued), 2)
        self.assertEqual(len(self.client.uploaded), 1)
        self.assertEqual(self.client.output_ids, ["6", "6"])
        overlap = state["qa"]["shoulder_neutral"]
        self.assertGreater(overlap["overlap_pixels"], 0)
        self.assertTrue(overlap["technical_overlap_found"])
        self.assertTrue((self.root / "probe" /
                         "probe_contact_sheet.png").is_file())
        self.assertEqual(len(list((self.root / "probe" / "parts").glob("*.png"))), 2)
        self.assertTrue(state["preview_is_not_publication_approval"])

    def test_no_joint_overlap_blocks_preproduction(self):
        fake = FakeComfy([part_png("body"), part_png("arm_right", overlap=False)])
        state = self.run("no_overlap", fake)
        self.assertEqual(state["status"], "PROBE_BLOCKED_NO_SHOULDER_OVERLAP")
        self.assertEqual(state["qa"]["shoulder_neutral"]["overlap_pixels"], 0)

    def test_opaque_png_fails_before_second_diffusion_job(self):
        img = Image.new("RGB", (128, 128), (255, 255, 255))
        out = BytesIO()
        img.save(out, "PNG")
        fake = FakeComfy([out.getvalue()])
        with self.assertRaises(FactoryError):
            self.run("opaque", fake)
        self.assertEqual(len(fake.queued), 1)
        state = json.loads((self.root / "opaque" / "probe_report.json").read_text())
        self.assertEqual(state["status"], "PROBE_FAILED")
        self.assertEqual(state["jobs"][0]["status"], "RUNNING")

    def test_unapproved_reference_flow_blocks_without_output_or_model_call(self):
        self.graph["4"]["inputs"].pop("identity")
        self._save_graph()
        with self.assertRaises(Exception):
            self.run("badgraph")
        self.assertFalse((self.root / "badgraph").exists())
        self.assertEqual(self.client.queued, [])
        self.assertEqual(self.client.uploaded, [])

    def test_geometry_wrong_position_aborts_before_second_generation(self):
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((92, 2, 125, 33),
                                    fill=(255, 170, 160, 255))
        b = BytesIO()
        img.save(b, "PNG")
        fake = FakeComfy([b.getvalue()])
        with self.assertRaises(FactoryError):
            self.run("wrong", fake)
        self.assertEqual(len(fake.queued), 1)

    def test_no_overwrite_and_cli_no_execute(self):
        self.run()
        with self.assertRaises(FileExistsError):
            self.run()
        status = kidsstudio_cli([
            "probe-bunny", str(self.blueprint),
            "--workflow", str(self.workflow),
            "--profile", str(self.profile),
            "--reference", str(self.reference),
            "--out", str(self.root / "cli-preview"),
        ])
        self.assertEqual(status, 2)
        self.assertFalse((self.root / "cli-preview").exists())

    def test_no_false_joint_claim_for_missing_arm_pixels(self):
        body = self.root / "body.png"
        arm = self.root / "arm.png"
        body.write_bytes(part_png("body"))
        Image.new("RGBA", (128, 128), (0, 0, 0, 0)).save(arm)
        data = joint_overlap(body, arm, [77, 63])
        self.assertFalse(data["technical_overlap_found"])
        self.assertEqual(data["arm_pixels"], 0)


if __name__ == "__main__":
    unittest.main()
