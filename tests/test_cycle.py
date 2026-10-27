from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.cycle import CycleError, choose_repair_parts, run_character_cycle


class FakeComfy:
    def __init__(self, image):
        self.img = image
        self.jobs = []
        self.uploads = 0

    def upload_reference(self, payload, name):
        self.uploads += 1
        return name

    def queue(self, prepared):
        self.jobs.append(prepared["prompt"]["1"]["inputs"]["text"])
        return f"job-{len(self.jobs)}"

    def await_image(self, prompt_id, *, timeout_seconds):
        return {"filename": prompt_id + ".png", "subfolder": "", "type": "output"}

    def download_png(self, image_ref):
        return self.img


class FakeVision:
    def __init__(self, responses):
        self.responses = responses
        self.count = 0

    def review(self, model, images_b64):
        self.count += 1
        if not images_b64:
            raise AssertionError("Review received no contact sheet")
        return self.responses[min(self.count - 1, len(self.responses) - 1)]


def verdict(status, part="arm_right"):
    if status == "PASS":
        return {"verdict": "PASS", "confidence": 0.94, "issues": [],
                "reason": "All visible joints are continuous."}
    if status == "FAIL":
        return {"verdict": "FAIL", "confidence": 0.96, "issues": [
            {"motion": "wave_right", "part_id": part, "severity": "high",
             "description": "Fatal identity discontinuity"}
        ], "reason": "Art identity not suitable for the rig."}
    issue = {"motion": "wave_right", "severity": "medium",
             "description": "Shoulder edge visible when waving"}
    if part is not None:
        issue["part_id"] = part
    return {"verdict": "REVISE", "confidence": 0.91, "issues": [issue],
            "reason": "Repair the waving arm."}


class CharacterCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blueprint = self.root / "bunny.json"
        self.graph = self.root / "graph.json"
        self.profile = self.root / "profile.json"
        self.ref = self.root / "canonical.png"
        self.parts = (
            "body", "head", "arm_left", "arm_right", "leg_left", "leg_right",
        )
        self.blueprint.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny_test",
            "identity_prompt": "Original cream heart pastel bunny",
            "canvas": {"width": 64, "height": 64},
            "parts": [
                {"id": name, "instruction": "isolated part",
                 "pivot": [32, 32], "z": i}
                for i, name in enumerate(self.parts)
            ],
        }))
        graph = {
            "1": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "placeholder"}},
            "2": {"class_type": "SaveImage",
                  "inputs": {"filename_prefix": "temp", "images": ["3", 0]}},
            "3": {"class_type": "LoadImage", "inputs": {"image": "ref.png"}},
        }
        raw = json.dumps(graph).encode("utf-8")
        self.graph.write_bytes(raw)
        self.profile.write_text(json.dumps({
            "approved_workflow_sha256": hashlib.sha256(raw).hexdigest(),
            "allowed_node_classes": ["CLIPTextEncode", "SaveImage", "LoadImage"],
            "approved_model_names": [],
            "prompt_node_id": "1",
            "filename_node_id": "2",
            "reference_node_id": "3",
        }))
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse(
            (10, 10, 52, 52), fill=(247, 181, 160, 255)
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.ref.write_bytes(buffer.getvalue())
        self.comfy = FakeComfy(buffer.getvalue())

    def run_cycle(self, status_list, *, max_attempts=2):
        return run_character_cycle(
            self.blueprint, self.graph, self.profile, self.ref,
            self.root / "cycle",
            vision_model="local-vision:8b",
            max_attempts=max_attempts,
            comfy_client=self.comfy,
            vision_client=FakeVision(status_list),
            preview_side=96,
        )

    def test_revision_regenerates_only_cited_part(self):
        result = self.run_cycle([verdict("REVISE"), verdict("PASS")])
        self.assertEqual(result["status"], "INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION")
        self.assertEqual([i["generated_comfy_jobs"] for i in result["attempts"]], [6, 1])
        self.assertEqual(result["attempts"][1]["reused_parts"], 5)
        self.assertEqual(result["attempts"][1]["regenerated_parts"], ["arm_right"])
        self.assertEqual(len(self.comfy.jobs), 7)
        self.assertIn("Shoulder edge visible", self.comfy.jobs[-1])
        self.assertEqual(self.comfy.uploads, 2)
        a = self.root / "cycle" / "attempt_01"
        b = self.root / "cycle" / "attempt_02"
        self.assertEqual(
            (a / "assets" / "body.png").read_bytes(),
            (b / "assets" / "body.png").read_bytes()
        )
        self.assertTrue((b / "review" / "motion_contact_sheet.png").exists())
        self.assertTrue((b / "visual_review.json").exists())

    def test_clean_first_pass_never_retries(self):
        state = self.run_cycle([verdict("PASS")])
        self.assertEqual(len(state["attempts"]), 1)
        self.assertEqual(len(self.comfy.jobs), 6)

    def test_ambiguous_issue_escalates_without_regenerating(self):
        state = self.run_cycle([verdict("REVISE", part=None)])
        self.assertEqual(state["status"], "BLOCKED_MANUAL_TRIAGE")
        self.assertEqual(len(state["attempts"]), 1)
        self.assertFalse((self.root / "cycle" / "attempt_02").exists())

    def test_repair_limit_blocks_infinite_loops(self):
        state = self.run_cycle([verdict("REVISE"), verdict("REVISE")])
        self.assertEqual(state["status"], "REPAIR_BUDGET_EXHAUSTED")
        self.assertEqual(len(state["attempts"]), 2)
        self.assertEqual(len(self.comfy.jobs), 7)

    def test_hard_rejection_stops(self):
        state = self.run_cycle([verdict("FAIL")])
        self.assertEqual(state["status"], "REJECTED_FINAL")
        self.assertEqual(len(self.comfy.jobs), 6)

    def test_existing_output_is_not_overwritten(self):
        folder = self.root / "cycle"
        folder.mkdir()
        with self.assertRaises(FileExistsError):
            self.run_cycle([verdict("PASS")])

    def test_unapproved_local_workflow_cannot_start(self):
        self.graph.write_text("{}")
        with self.assertRaises(ValueError):
            self.run_cycle([verdict("PASS")])
        self.assertFalse((self.root / "cycle").exists())

    def test_no_unknown_or_ambiguous_target_selection(self):
        result = choose_repair_parts(
            {"verdict": "REVISE", "issues": [
                {"part_id": "unlisted", "description": "bad seam"}
            ]},
            valid_parts=set(self.parts)
        )
        self.assertIsNotNone(result[2])

    def test_three_retry_max(self):
        with self.assertRaises(CycleError):
            run_character_cycle(
                self.blueprint, self.graph, self.profile, self.ref,
                self.root / "cycle", vision_model="local-vision:8b",
                max_attempts=10
            )


if __name__ == "__main__":
    unittest.main()
