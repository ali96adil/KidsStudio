"""Production gating: no GPU calls and no personal art in CI."""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from kidsstudio.comfy import ComfySafetyError
from kidsstudio.factory import FactoryError, LocalComfyClient
from kidsstudio.workflow_audit import audit_character_workflow
from kidsstudio.cli import main as kidsstudio_main
from kidsstudio.media_worker import MediaRecipes


class WorkflowProductionAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.blueprint = self.base / "blueprint.json"
        self.workflow = self.base / "workflow.json"
        self.profile = self.base / "profile.json"
        self.reference = self.base / "original.png"
        self.parts = ["body", "head", "arm_left", "arm_right",
                      "leg_left", "leg_right"]
        self.blueprint.write_text(json.dumps({
            "schema_version": 1,
            "character_id": "bunny_v02",
            "identity_prompt": "Original pastel bunny",
            "canvas": {"width": 64, "height": 64},
            "parts": [
                {"id": ident, "instruction": "isolated art part",
                 "pivot": [32, 32], "z": index}
                for index, ident in enumerate(self.parts)
            ],
        }))
        Image.new("RGBA", (64, 64), (230, 180, 170, 255)).save(self.reference)
        self.graph = {
            "1": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "insert-specific-part"}},
            "2": {"class_type": "LoadImage",
                  "inputs": {"image": "original.png"}},
            "3": {"class_type": "ReferenceConditioning",
                  "inputs": {"reference": ["2", 0]}},
            "4": {"class_type": "KSampler",
                  "inputs": {"conditioning": ["3", 0],
                             "positive": ["1", 0]}},
            "5": {"class_type": "VAEDecode",
                  "inputs": {"samples": ["4", 0]}},
            "6": {"class_type": "AlphaMatte",
                  "inputs": {"pixels": ["5", 0]}},
            "7": {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0],
                             "filename_prefix": "temp"}},
        }
        self.profile_data = {
            "approved_workflow_sha256": "",
            "allowed_node_classes": [
                "CLIPTextEncode", "LoadImage", "ReferenceConditioning",
                "KSampler", "VAEDecode", "AlphaMatte", "SaveImage",
            ],
            "approved_model_names": [],
            "prompt_node_id": "1",
            "reference_node_id": "2",
            "filename_node_id": "7",
            "production_contract": {
                "conditioning_node_id": "3",
                "sampler_node_id": "4",
                "matting_node_id": "6",
            },
        }
        self.save()

    def save(self):
        raw = json.dumps(self.graph).encode("utf-8")
        self.workflow.write_bytes(raw)
        self.profile_data["approved_workflow_sha256"] = hashlib.sha256(raw).hexdigest()
        self.profile.write_text(json.dumps(self.profile_data))

    def audit(self):
        return audit_character_workflow(
            self.blueprint, self.workflow, self.profile, self.reference
        )

    def test_explicit_connected_sampler_and_alpha_path_pass_offline(self):
        result = self.audit()
        self.assertEqual(result["status"], "GRAPH_READY_NOT_GENERATED")
        self.assertEqual(result["output_node_id"], "7")
        self.assertEqual(result["node_count"], 7)
        self.assertTrue(result["visual_and_alpha_output_still_unverified"])

    def test_cli_offline_preflight_does_not_queue_ai_job(self):
        status = kidsstudio_main([
            "audit-character-workflow", str(self.blueprint),
            "--workflow", str(self.workflow), "--profile", str(self.profile),
            "--reference", str(self.reference),
        ])
        self.assertEqual(status, 0)

    def test_missing_production_contract_fails(self):
        self.profile_data.pop("production_contract")
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "Production requires"):
            self.audit()

    def test_reference_only_composited_after_sampling_is_rejected(self):
        self.graph["3"]["inputs"] = {"constant": "not reference-conditioned"}
        self.graph["8"] = {
            "class_type": "ImageComposite",
            "inputs": {"background": ["6", 0], "foreground": ["2", 0]},
        }
        self.graph["7"]["inputs"]["images"] = ["8", 0]
        self.profile_data["allowed_node_classes"].append("ImageComposite")
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "identity reference"):
            self.audit()

    def test_text_prompt_bypasses_sampler_is_rejected(self):
        self.graph["4"]["inputs"]["positive"] = "generic locked text"
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "part-specific text"):
            self.audit()

    def test_sampler_bypasses_alpha_stage_is_rejected(self):
        self.graph["7"]["inputs"]["images"] = ["5", 0]
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "alpha/matting output"):
            self.audit()

    def test_conditioning_bypassed_by_sampler_is_rejected(self):
        self.graph["4"]["inputs"]["conditioning"] = ["1", 0]
        # A cosmetic reference image composited downstream would pass the
        # older "LoadImage reaches SaveImage" check. The new contract
        # must still detect that conditioning never reached the sampler.
        self.graph["8"] = {
            "class_type": "ImageComposite",
            "inputs": {"generated": ["6", 0], "decorative_ref": ["2", 0]},
        }
        self.graph["7"]["inputs"]["images"] = ["8", 0]
        self.profile_data["allowed_node_classes"].append("ImageComposite")
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "Image conditioning"):
            self.audit()

    def test_unapproved_workflow_mutation_is_rejected(self):
        self.graph["4"]["inputs"]["steps"] = 99
        self.workflow.write_text(json.dumps(self.graph))
        with self.assertRaisesRegex(ComfySafetyError, "SHA-256"):
            self.audit()

    def test_cyclic_graph_is_rejected(self):
        self.graph["3"]["inputs"]["loop"] = ["4", 0]
        self.save()
        with self.assertRaisesRegex(ComfySafetyError, "Cyclic"):
            self.audit()

    def test_media_recipe_requires_full_workflow_contract_before_gpu(self):
        config = self.base / "recipes.json"
        files = {
            "blueprint": self.blueprint,
            "workflow": self.workflow,
            "profile": self.profile,
            "reference": self.reference,
        }
        recipe = {
            "kind": "character_generate",
            "output_root": str(self.base / "private-outputs"),
            "inputs": {k: str(v) for k, v in files.items()},
            "sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest()
                       for k, v in files.items()},
            "review_model": "approved-local-vision:8b",
        }
        config.write_text(json.dumps({
            "schema_version": 1, "recipes": {"bunny_first": recipe}
        }))
        recipes = MediaRecipes(config)
        self.assertEqual(
            recipes.resolve("character_generate", "bunny_first")["kind"],
            "character_generate",
        )
        self.profile_data.pop("production_contract")
        self.save()
        recipe["sha256"]["profile"] = hashlib.sha256(
            self.profile.read_bytes()
        ).hexdigest()
        config.write_text(json.dumps({
            "schema_version": 1, "recipes": {"bunny_first": recipe}
        }))
        recipes = MediaRecipes(config)
        with self.assertRaises(ComfySafetyError):
            recipes.resolve("character_generate", "bunny_first")


class ExactSaveImageHistoryTests(unittest.TestCase):
    def setUp(self):
        self.client = LocalComfyClient()

    def _history(self, outputs, *, completed=True):
        return json.dumps({
            "job-10": {
                "status": {"completed": completed, "status_str": "success"},
                "outputs": outputs,
            }
        }).encode("utf-8")

    def test_selects_approved_save_node_not_first_preview(self):
        history = self._history({
            "2": {"images": [{"filename": "reference_preview.png",
                              "subfolder": "", "type": "output"}]},
            "7": {"images": [{"filename": "arm_right_00001_.png",
                              "subfolder": "KidsStudio/bunny",
                              "type": "output"}]},
        })
        with patch.object(self.client, "_read", return_value=history):
            result = self.client.await_image(
                "job-10", save_node_id="7", timeout_seconds=2
            )
        self.assertEqual(result["filename"], "arm_right_00001_.png")

    def test_missing_primary_node_fails_closed(self):
        history = self._history({
            "2": {"images": [{"filename": "background.png",
                              "type": "output"}]}
        })
        with patch.object(self.client, "_read", return_value=history):
            with self.assertRaisesRegex(FactoryError, "Approved SaveImage"):
                self.client.await_image(
                    "job-10", save_node_id="7", timeout_seconds=2
                )

    def test_multi_image_output_fails_closed(self):
        history = self._history({
            "7": {"images": [
                {"filename": "a.png", "type": "output"},
                {"filename": "b.png", "type": "output"},
            ]}
        })
        with patch.object(self.client, "_read", return_value=history):
            with self.assertRaisesRegex(FactoryError, "exactly one"):
                self.client.await_image(
                    "job-10", save_node_id="7", timeout_seconds=2
                )


if __name__ == "__main__":
    unittest.main()
