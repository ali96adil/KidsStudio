"""Mac art-station qualification: no GPU, no paid API, no private reports in Git."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from kidsstudio.mac_doctor import (
    MacDoctorError, _disk_info, _ollama_info, _tool_info, inspect_mac_station,
)
from kidsstudio.cli import main as cli_main


class FakeHTTPResponse:
    def __init__(self, obj):
        self.obj = obj
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, cap):
        return json.dumps(self.obj).encode("utf-8")


class OnlyOllamaTags:
    def __init__(self, names):
        self.names = names
        self.calls = []
    def open(self, req, timeout):
        self.calls.append((req.get_method(), req.full_url))
        if req.full_url != "http://127.0.0.1:11434/api/tags":
            raise AssertionError("Unexpected HTTP request")
        return FakeHTTPResponse({
            "models": [{"name": n} for n in self.names]
        })


class StationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workflow = self.root / "workflow.json"
        self.workflow.write_text(json.dumps({
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "private prompt"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
            "3": {"class_type": "ImageCondition", "inputs": {"image": ["2", 0]}},
            "4": {"class_type": "Sampler", "inputs": {"positive": ["1", 0],
                                                     "identity": ["3", 0]}},
            "5": {"class_type": "AlphaMatte", "inputs": {"samples": ["4", 0]}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0],
                                                     "filename_prefix": "private"}},
        }))
        self.reference = self.root / "bunny.png"
        Image.new("RGBA", (64, 64), (245, 190, 170, 255)).save(self.reference)
        self.blueprint = self.root / "blueprint.json"
        self.blueprint.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny",
            "identity_prompt": "Original small bunny",
            "canvas": {"width": 64, "height": 64},
            "parts": [
                {"id": key, "instruction": "isolated part",
                 "pivot": [32, 32], "z": i}
                for i, key in enumerate([
                    "body", "head", "arm_left", "arm_right", "leg_left", "leg_right"
                ])
            ],
        }))
        self.profile = self.root / "profile.json"
        self.profile.write_text('{"draft":true}')
        self.private = self.root / "private_output"
        self.private.mkdir()
        self.comfy_ready = {
            "status": "READY_FOR_TWO_PART_PROBE_NOT_GENERATED",
            "checks": {"local_registry": "PASS", "approved_graph": "PASS"},
            "generation_submitted": False,
        }
        self.tool_success = lambda name, binary: {
            "state": "FOUND",
            "version": "4.7.2" if name == "godot" else "7.1",
        }
        self.disk_success = lambda *_: {
            "state": "PASS", "minimum_free_gb": 10, "free_gb_floor": 30,
        }

    def run_station(self, *, report=None, vision=None, disk=None, **kwargs):
        with patch("kidsstudio.mac_doctor.inspect_mac_comfy",
                   return_value=(self.comfy_ready if report is None else report, None)), \
             patch("kidsstudio.mac_doctor._tool_info",
                   side_effect=self.tool_success), \
             patch("kidsstudio.mac_doctor._disk_info",
                   side_effect=self.disk_success if disk is None else (lambda *_: disk)), \
             patch("kidsstudio.mac_doctor._ollama_info",
                   return_value={"state": "FOUND", "model_registered": True,
                                 "vision_capability_verified": False}
                   if vision is None else vision):
            return inspect_mac_station(
                workflow_file=self.workflow, reference_file=self.reference,
                blueprint_file=self.blueprint, profile_file=self.profile,
                connect=True, ollama_model="local-vision:8b",
                output_root=self.private, **kwargs,
            )

    def test_all_prerequisites_allow_manual_probe_not_full_rig(self):
        result = self.run_station()
        self.assertEqual(result["status"], "READY_TO_REQUEST_MANUAL_TWO_PART_PROBE")
        self.assertFalse(result["full_rig_production_authorized"])
        self.assertFalse(result["public_release_authorized"])
        self.assertTrue(result["no_generation_submitted"])
        self.assertTrue(result["no_image_uploaded"])
        self.assertTrue(result["no_paid_ai_called"])
        self.assertEqual(result["canonical_reference"]["dimensions"], [64, 64])
        self.assertEqual(result["private_output_disk"]["state"], "PASS")

    def test_workflow_pass_but_missing_local_model_is_blocked(self):
        result = self.run_station(vision={
            "state": "MISSING", "model_registered": False,
            "vision_capability_verified": False,
        })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("LOCAL_VISION_MODEL_UNAVAILABLE", result["blockers"])

    def test_graph_not_owner_approved_not_ready(self):
        result = self.run_station(report={
            "status": "NEEDS_OWNER_WORKFLOW_APPROVAL",
            "checks": {"approved_graph": "NOT_RUN"},
        })
        self.assertEqual(result["status"], "NEEDS_LOCAL_PROVISIONING_OR_OWNER_APPROVAL")

    def test_workflow_failure_never_ready(self):
        result = self.run_station(report={
            "status": "BLOCKED", "issues": ["SELECTED_MODEL_NOT_AVAILABLE"],
        })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("COMFY_WORKFLOW_OR_INSTALLED_NODES", result["blockers"])

    def test_invalid_canonical_reference_prevents_readiness(self):
        self.reference.write_bytes(b"not a PNG")
        result = self.run_station()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("CANONICAL_REFERENCE", result["blockers"])
        self.assertNotIn("not a PNG", json.dumps(result))

    def test_low_free_space_blocks_manual_probe(self):
        result = self.run_station(disk={
            "state": "LOW_FREE_SPACE", "minimum_free_gb": 10, "free_gb_floor": 1,
        })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("PRIVATE_OUTPUT_DISK", result["blockers"])

    def test_offline_inspection_not_falsely_ready(self):
        with patch("kidsstudio.mac_doctor._tool_info",
                   side_effect=self.tool_success), \
             patch("kidsstudio.mac_doctor._disk_info",
                   side_effect=self.disk_success):
            result = inspect_mac_station(
                workflow_file=self.workflow, reference_file=self.reference,
                output_root=self.private, connect=False,
            )
        self.assertNotEqual(result["status"], "READY_TO_REQUEST_MANUAL_TWO_PART_PROBE")
        self.assertFalse(result["no_generation_submitted"] is False)

    def test_ollama_tags_only_and_not_vision_capability_proof(self):
        opener = OnlyOllamaTags(["local-vision:8b"])
        out = _ollama_info(model="local-vision:8b", connect=True, opener=opener)
        self.assertEqual(out["state"], "FOUND")
        self.assertFalse(out["vision_capability_verified"])
        self.assertEqual(opener.calls, [
            ("GET", "http://127.0.0.1:11434/api/tags")
        ])
        self.assertEqual(_ollama_info(model="other", connect=True,
                                      opener=opener)["state"], "MISSING")

    def test_disk_path_in_git_repo_rejected(self):
        (self.root / ".git").mkdir()
        result = _disk_info(self.root, 10)
        self.assertEqual(result["state"], "BLOCKED_GIT_OUTPUT_ROOT")

    def test_report_created_private_and_no_overwrite(self):
        report = self.root / "mac_doctor_report.json"
        with patch("kidsstudio.cli.inspect_mac_station",
                   return_value=self.run_station()):
            self.assertEqual(cli_main([
                "mac-doctor", "--workflow", str(self.workflow),
                "--reference", str(self.reference),
                "--report", str(report),
            ]), 0)
            self.assertEqual(
                json.loads(report.read_text())["no_generation_submitted"], True
            )
            if os.name == "posix":
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertEqual(cli_main([
                "mac-doctor", "--workflow", str(self.workflow),
                "--reference", str(self.reference),
                "--report", str(report),
            ]), 2)

    def test_tool_invocation_fixed_arguments_no_shell(self):
        completed = type("Completed", (), {
            "returncode": 0, "stdout": "4.7.2.stable.official.123\n",
        })()
        dummy = self.root / "godot"
        dummy.write_text("placeholder")
        dummy.chmod(0o700)
        with patch("kidsstudio.mac_doctor.subprocess.run",
                   return_value=completed) as run:
            info = _tool_info("godot", str(dummy))
        self.assertEqual(info["state"], "FOUND")
        self.assertEqual(run.call_args.args[0][1:], ["--version"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_bad_loopback_url_refused(self):
        with self.assertRaises(ValueError):
            inspect_mac_station(
                workflow_file=self.workflow, reference_file=self.reference,
                comfy_url="http://public.example:8188",
            )


if __name__ == "__main__":
    unittest.main()
