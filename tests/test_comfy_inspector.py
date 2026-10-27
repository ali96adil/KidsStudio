"""ComfyUI Mac readiness is strictly read-only and never falsely approved."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from kidsstudio.comfy_inspector import (
    ReadinessError, inspect_mac_comfy, draft_profile,
)
from kidsstudio.cli import main as kidsstudio_main


class FakeResponse:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *unused):
        return False
    def read(self, limit):
        return json.dumps(self.value).encode("utf-8")


class ReadOnlyOpener:
    def __init__(self, nodes=None, *, available=True):
        self.calls = []
        self.available = available
        self.nodes = nodes if nodes is not None else {
            "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}]}}},
            "LoadImage": {"input": {"required": {"image": [["ref.png"], {}]}}},
            "IdentityConditioning": {"input": {}},
            "KSampler": {"input": {}},
            "AlphaMatte": {"input": {}},
            "CheckpointLoaderSimple": {
                "input": {"required": {
                    "ckpt_name": [["flux_klein.safetensors", "other.safetensors"], {}]
                }}
            },
            "SaveImage": {"input": {"required": {"filename_prefix": ["STRING", {}]}}},
        }

    def open(self, req, timeout):
        self.calls.append((req.full_url, req.get_method(), timeout))
        if not self.available:
            raise URLError("connection refused")
        if req.full_url.endswith("/object_info"):
            return FakeResponse(self.nodes)
        if req.full_url.endswith("/system_stats"):
            return FakeResponse({
                "system": {"os": "macos", "python_version": "3.11"},
                "devices": [{"name": "private_device_name"}],
            })
        raise AssertionError("Inspector called an unauthorized endpoint!")


class InspectMacComfyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workflow_file = self.root / "workflow_api.json"
        self.workflow = {
            "1": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "private prompt text"}},
            "2": {"class_type": "LoadImage",
                  "inputs": {"image": "private_original.png"}},
            "3": {"class_type": "IdentityConditioning",
                  "inputs": {"reference": ["2", 0]}},
            "4": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "flux_klein.safetensors"}},
            "5": {"class_type": "KSampler",
                  "inputs": {"positive": ["1", 0],
                             "identity": ["3", 0], "model": ["4", 0]}},
            "6": {"class_type": "AlphaMatte",
                  "inputs": {"sample": ["5", 0]}},
            "7": {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0],
                             "filename_prefix": "private/dir"}},
        }
        self.write()

    def write(self):
        self.workflow_file.write_text(json.dumps(self.workflow))

    def inspect(self, **kwargs):
        return inspect_mac_comfy(self.workflow_file, **kwargs)

    def test_offline_inspection_is_informational_only(self):
        report, draft = self.inspect()
        self.assertEqual(report["status"], "NEEDS_OWNER_WORKFLOW_APPROVAL")
        self.assertEqual(report["checks"]["api_format"], "PASS")
        self.assertEqual(report["checks"]["approved_graph"], "NOT_RUN")
        self.assertEqual(report["candidates"]["prompt_node_id"], ["1"])
        self.assertEqual(report["candidates"]["sampler_node_id"], ["5"])
        self.assertFalse(report["production_approved"])
        self.assertFalse(report["generation_submitted"])
        self.assertFalse(report["api_tokens_or_original_art_uploaded"])
        self.assertTrue(draft["approved_workflow_sha256"].startswith(
            "OWNER_MUST_APPROVE_"
        ))
        self.assertNotIn("private prompt text", json.dumps(report))
        self.assertNotIn("private prompt text", json.dumps(draft))

    def test_live_registered_nodes_and_model_choices(self):
        opener = ReadOnlyOpener()
        report, draft = self.inspect(connect=True, opener=opener)
        self.assertEqual(report["checks"]["local_registry"], "PASS")
        self.assertEqual(report["checks"]["system_stats"], "RECEIVED")
        self.assertEqual(report["device_count"], 1)
        self.assertEqual(
            report["model_registration"][0]["status"],
            "AVAILABLE_IN_NODE_CHOICES"
        )
        self.assertEqual(
            [(url.split("/")[-1], method)
             for url, method, _ in opener.calls],
            [("object_info", "GET"), ("system_stats", "GET")]
        )
        self.assertFalse(report["production_approved"])
        self.assertEqual(draft["prompt_node_id"], "1")

    def test_missing_model_rejected_from_live_registry(self):
        self.workflow["4"]["inputs"]["ckpt_name"] = "missing_model.safetensors"
        self.write()
        report, _ = self.inspect(connect=True, opener=ReadOnlyOpener())
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("SELECTED_MODEL_NOT_AVAILABLE", report["issues"])
        self.assertFalse(report["generation_submitted"])

    def test_missing_custom_node_rejected(self):
        nodes = ReadOnlyOpener().nodes.copy()
        del nodes["IdentityConditioning"]
        report, _ = self.inspect(
            connect=True, opener=ReadOnlyOpener(nodes)
        )
        self.assertIn("IdentityConditioning",
                      report["unregistered_node_classes"])
        self.assertEqual(report["status"], "BLOCKED")

    def test_unreachable_local_comfy_returns_redacted_blocker(self):
        opener = ReadOnlyOpener(available=False)
        report, _ = self.inspect(connect=True, opener=opener)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("LOCAL_COMFYUI_UNAVAILABLE", report["issues"])
        self.assertNotIn("connection refused", json.dumps(report))

    def test_editor_format_is_not_mistaken_for_api_format(self):
        self.workflow = {"nodes": [{"id": 1}], "links": []}
        self.write()
        opener = ReadOnlyOpener()
        report, draft = self.inspect(connect=True, opener=opener)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("EDITOR_FORMAT_NOT_API", report["issues"])
        self.assertIsNone(draft)
        self.assertEqual(opener.calls, [])

    def test_unsafe_node_class_is_blocked_no_remote(self):
        self.workflow["5"]["class_type"] = "RemoteHTTPUpload"
        self.write()
        report, draft = self.inspect(connect=True, opener=ReadOnlyOpener())
        self.assertIn("UNSAFE_EXTERNAL_OR_EXECUTABLE_NODE", report["issues"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(draft)

    def test_missing_required_identity_reference_cannot_be_approved(self):
        del self.workflow["2"]
        del self.workflow["3"]
        self.workflow["5"]["inputs"].pop("identity")
        self.write()
        report, _ = self.inspect()
        self.assertIn("MISSING_LOAD_IMAGE", report["issues"])
        self.assertEqual(report["status"], "BLOCKED")

    def test_partial_profile_set_is_blocked(self):
        report, _ = self.inspect(profile_file=self.root / "dummy.json")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("NEED_PROFILE_BLUEPRINT_AND_REFERENCE_TOGETHER",
                      report["issues"])

    def test_full_profile_without_validated_graph_blocks(self):
        report, _ = self.inspect(
            profile_file=self.root / "no-profile.json",
            blueprint_file=self.root / "no-blueprint.json",
            reference_file=self.root / "no-ref.png",
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("APPROVED_GRAPH_AUDIT_FAILED", report["issues"])

    def test_connected_approved_graph_only_route_to_probe(self):
        with patch("kidsstudio.comfy_inspector.audit_character_workflow",
                   return_value={"workflow_sha256": "f" * 64}):
            report, _ = self.inspect(
                connect=True,
                profile_file=self.root / "profile.json",
                blueprint_file=self.root / "blueprint.json",
                reference_file=self.root / "reference.png",
                opener=ReadOnlyOpener(),
            )
        self.assertEqual(
            report["status"], "READY_FOR_TWO_PART_PROBE_NOT_GENERATED"
        )
        self.assertFalse(report["production_approved"])
        self.assertFalse(report["generation_submitted"])

    def test_draft_does_not_become_usable_approved_profile(self):
        report, draft = self.inspect()
        self.assertNotEqual(draft["approved_workflow_sha256"],
                            report["workflow_sha256"])
        self.assertIn("REQUIRES_HUMAN_GRAPH_INSPECTION",
                      draft["production_contract"].values())

    def test_cli_does_not_contact_mac_without_connect(self):
        output = self.root / "diagnostics.json"
        draft = self.root / "draft.json"
        code = kidsstudio_main([
            "inspect-mac-comfy", "--workflow", str(self.workflow_file),
            "--report", str(output), "--draft-profile", str(draft),
        ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text())["generation_submitted"],
                         False)
        self.assertTrue(draft.is_file())
        self.assertEqual(
            json.loads(draft.read_text())["prompt_node_id"], "1"
        )

    def test_existing_diagnostic_report_is_not_overwritten(self):
        output = self.root / "out.json"
        output.write_text("keep-me")
        with self.assertRaises(FileExistsError):
            kidsstudio_main([
                "inspect-mac-comfy", "--workflow", str(self.workflow_file),
                "--report", str(output),
            ])
        self.assertEqual(output.read_text(), "keep-me")

    def test_bad_remote_base_url_rejected_before_network(self):
        with self.assertRaises(ValueError):
            self.inspect(connect=True, base_url="http://public.example:8188")


if __name__ == "__main__":
    unittest.main()
