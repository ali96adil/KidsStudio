"""Integrated owner-controlled first art trial: no real GPU/network calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from kidsstudio.first_run import first_bunny_run, load_first_run_config, FirstRunError
from kidsstudio.cli import main as cli_main


READY = "READY_TO_REQUEST_MANUAL_TWO_PART_PROBE"


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.out = self.private / "runs"
        self.out.mkdir()
        self.files = {}
        for kind in ("workflow", "profile", "reference", "blueprint"):
            path = self.private / (kind + ".json")
            path.write_text(kind)
            self.files[kind] = str(path)
        self.cfg = self.private / "station_private.json"
        self.configuration = {
            "schema_version": 1,
            **self.files,
            "review_model": "local-vision:8b",
            "output_root": str(self.out),
            "timeout_seconds": 40,
            "min_free_gb": 10,
        }
        self.cfg.write_text(json.dumps(self.configuration))
        self.calls = []

    def write(self):
        self.cfg.write_text(json.dumps(self.configuration))

    def fake_doctor(self, **kwargs):
        self.calls.append("doctor")
        self.assertEqual(kwargs["connect"], True)
        self.assertEqual(kwargs["output_root"], str(self.out))
        return {
            "status": READY,
            "no_generation_submitted": True,
            "no_image_uploaded": True,
            "full_rig_production_authorized": False,
        }

    def fake_generator(self, *args, **kwargs):
        self.calls.append("probe")
        self.assertEqual(kwargs["timeout_seconds"], 40)
        self.assertEqual(args[0], self.files["blueprint"])
        directory = Path(args[4])
        directory.mkdir()
        (directory / "probe_report.json").write_text('{"valid":true}')
        return {"status": "PROBE_READY_FOR_VISUAL_INSPECTION"}

    def fake_review(self, *args, **kwargs):
        self.calls.append("vision")
        self.assertEqual(kwargs["model"], "local-vision:8b")
        self.assertEqual(Path(args[0]).name, "probe")
        return {"status": "PROBE_PRELIMINARY_ART_PASS", "verdict": "PASS"}

    def run_trial(self, name="bunny_trial_001", **kwargs):
        return first_bunny_run(
            self.cfg, name, execute=True,
            doctor=kwargs.pop("doctor", self.fake_doctor),
            part_generator=kwargs.pop("part_generator", self.fake_generator),
            vision_reviewer=kwargs.pop("vision_reviewer", self.fake_review),
            comfy_client=object(), vision_client=object(),
            **kwargs,
        )

    def test_one_command_strict_stage_order_and_owner_gate(self):
        result = self.run_trial()
        self.assertEqual(self.calls, ["doctor", "probe", "vision"])
        self.assertEqual(result["status"], "PRELIMINARY_ART_PASS_NEEDS_OWNER")
        self.assertFalse(result["full_rig_generation_authorized"])
        self.assertFalse(result["public_release_authorized"])
        self.assertTrue(result["owner_visual_signoff_required"])
        self.assertEqual(result["local_gpu_part_budget"], 2)
        path = self.out / "bunny_trial_001" / "first_run.json"
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text())["review_status"],
                         "PROBE_PRELIMINARY_ART_PASS")
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_preflight_block_stops_before_any_gpu_request(self):
        def blocked(**kwargs):
            self.calls.append("doctor")
            return {"status": "BLOCKED", "blockers": ["NO_CHECKPOINT"]}
        result = self.run_trial(doctor=blocked)
        self.assertEqual(result["status"], "BLOCKED_AT_PREFLIGHT")
        self.assertEqual(self.calls, ["doctor"])
        self.assertFalse((self.out / "bunny_trial_001" / "probe").exists())

    def test_shoulders_do_not_overlap_so_vision_never_called(self):
        def no_overlap(*args, **kwargs):
            self.calls.append("probe")
            return {"status": "PROBE_BLOCKED_NO_SHOULDER_OVERLAP"}
        result = self.run_trial(part_generator=no_overlap)
        self.assertEqual(result["status"], "BLOCKED_AT_GEOMETRY")
        self.assertEqual(self.calls, ["doctor", "probe"])

    def test_revision_after_art_review_never_starts_full_character(self):
        def revise(*args, **kwargs):
            self.calls.append("vision")
            return {"status": "PROBE_ART_REVISION_REQUIRED", "verdict": "REVISE"}
        result = self.run_trial(vision_reviewer=revise)
        self.assertEqual(result["status"], "ART_REVISION_REQUIRED")
        self.assertEqual(self.calls, ["doctor", "probe", "vision"])
        self.assertFalse(result["full_rig_generation_authorized"])

    def test_rejected_art_is_terminal_without_regeneration(self):
        def rejected(*args, **kwargs):
            self.calls.append("vision")
            return {"status": "PROBE_ART_REJECTED", "verdict": "FAIL"}
        result = self.run_trial(vision_reviewer=rejected)
        self.assertEqual(result["status"], "ART_REJECTED")
        self.assertEqual(self.calls, ["doctor", "probe", "vision"])

    def test_failed_generation_never_retries_or_leaks_private_exception(self):
        def crash(*args, **kwargs):
            self.calls.append("probe")
            raise RuntimeError("secret private /Users/owner/token; GPU crashed")
        result = self.run_trial(part_generator=crash)
        self.assertEqual(result["status"], "STOPPED_UNCERTAIN_NO_AUTORETRY")
        self.assertEqual(result["failure_class"], "RuntimeError")
        self.assertEqual(self.calls, ["doctor", "probe"])
        raw = (self.out / "bunny_trial_001" / "first_run.json").read_text()
        self.assertNotIn("secret private", raw)
        self.assertFalse(result["public_release_authorized"])

    def test_failed_review_does_not_repeat_gpu_or_hide_partial_art(self):
        def crash(*args, **kwargs):
            self.calls.append("vision")
            raise RuntimeError("local Ollama unavailable")
        result = self.run_trial(vision_reviewer=crash)
        self.assertEqual(result["failed_stage"], "VISION_REVIEW_IN_PROGRESS")
        self.assertEqual(result["status"], "STOPPED_UNCERTAIN_NO_AUTORETRY")
        self.assertTrue((self.out / "bunny_trial_001" / "probe" /
                         "probe_report.json").is_file())
        self.assertEqual(self.calls, ["doctor", "probe", "vision"])

    def test_same_run_version_is_not_reused_for_rerender(self):
        self.run_trial()
        with self.assertRaises(FileExistsError):
            self.run_trial()
        self.assertEqual(self.calls, ["doctor", "probe", "vision"])

    def test_execute_required_even_when_directly_calling_python(self):
        with self.assertRaises(FirstRunError):
            first_bunny_run(self.cfg, "noconfirm", execute=False)
        self.assertFalse((self.out / "noconfirm").exists())
        result = cli_main([
            "first-bunny-run", "--config", str(self.cfg),
            "--run-name", "noconfirm",
        ])
        self.assertEqual(result, 2)
        self.assertFalse((self.out / "noconfirm").exists())

    def test_extra_keys_and_secret_fields_are_not_accepted(self):
        self.configuration["api_key"] = "do-not-ever-store"
        self.write()
        with self.assertRaises(FirstRunError):
            load_first_run_config(self.cfg)

    def test_private_config_must_stay_outside_git(self):
        (self.private / ".git").mkdir()
        with self.assertRaises(FirstRunError):
            load_first_run_config(self.cfg)

    def test_bad_version_and_relative_path_block_before_network(self):
        with self.assertRaises(FirstRunError):
            self.run_trial(name="../bad")
        self.assertFalse((self.out / "..").is_file())
        self.configuration["workflow"] = "relative.json"
        self.write()
        with self.assertRaises(FirstRunError):
            load_first_run_config(self.cfg)

    def test_explicit_config_has_no_auto_retries_or_paid_endpoints(self):
        cfg = load_first_run_config(self.cfg)
        self.assertNotIn("api_key", cfg)
        self.assertNotIn("provider_url", cfg)
        self.assertEqual(cfg["timeout_seconds"], 40)


if __name__ == "__main__":
    unittest.main()
