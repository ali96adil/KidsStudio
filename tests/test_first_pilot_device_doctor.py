"""Device doctor regression tests; no physical Mac/Pi or network."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.first_pilot_device_doctor import (
    inspect_first_pilot_device, main,
)


def qualified(role: str = "mac", *, source_clean=True,
              source_valid=True, checks=None, pipeline=True):
    actual_checks = {
        "python_3_11_plus": True,
        "artifact_root_exists": True,
        "artifact_root_private": True,
        "role_matches_os_machine": True,
        "source_commit_sha40": source_valid,
        "source_checkout_clean": source_clean,
    }
    if role == "pi":
        actual_checks["raspberry_pi_model_confirmed"] = True
    actual_checks.update(checks or {})
    return {
        "status": ("SUPERVISED_TESTS_READY"
                   if all(actual_checks.values()) and pipeline
                   else "SUPERVISED_TESTS_BLOCKED"),
        "source_commit": "a" * 40 if source_valid else None,
        "source_checkout_clean": source_clean,
        "checks": actual_checks,
        "synthetic_review_pipeline": ("OFFLINE_REVIEW_PIPELINE_PASS"
                                      if pipeline else "OFFLINE_REVIEW_PIPELINE_FAIL"),
    }


def mac_voice(available=True, blockers=()):
    return {
        "status": ("MAC_COLORS_PREFLIGHT_READY"
                   if available and not blockers else "MAC_COLORS_PREFLIGHT_BLOCKED"),
        "blockers": list(blockers),
        "local_arabic_voice_available": available,
    }


class FirstPilotDoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def mac(self, *, host=None, voice=None, ssh=True):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified() if host is None else host) as chk, \
             patch("kidsstudio.first_pilot_device_doctor._mac_preflight",
                   return_value=mac_voice() if voice is None else voice) as speech, \
             patch("kidsstudio.first_pilot_device_doctor.shutil.which",
                   return_value="/usr/bin/ssh" if ssh else None):
            report = inspect_first_pilot_device(
                role="mac", artifact_root=str(self.root))
        chk.assert_called_once()
        speech.assert_called_once()
        return report

    def test_mac_ready_is_only_permission_to_begin_supervised_tests(self):
        report = self.mac()
        self.assertEqual(
            report["status"], "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY")
        self.assertEqual(report["failed_check_count"], 0)
        self.assertEqual(report["source_commit"], "a" * 40)
        self.assertTrue(report["installed_mac_arabic_voice_qualified"])
        for prop in ("same_revision_on_other_device_verified",
                     "actual_mac_arabic_speech_rendered",
                     "actual_pi_ssh_transfer_tested",
                     "real_youtube_oauth_or_upload_tested",
                     "real_ssh_or_google_network_called",
                     "files_created_or_modified", "publication_approved"):
            self.assertFalse(report[prop])

    def test_missing_arabic_voice_is_actionable_and_stops_ready(self):
        report = self.mac(voice=mac_voice(
            available=False,
            blockers=("installed_arabic_voice_missing_or_invalid",)))
        self.assertEqual(
            report["status"], "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_BLOCKED")
        self.assertEqual(report["blockers"][0]["code"],
                         "installed_arabic_voice_missing_or_invalid")
        self.assertIn("Arabic Apple say", report["blockers"][0]["suggested_fix"])
        self.assertFalse(report["installed_mac_arabic_voice_qualified"])

    def test_missing_pillow_gives_safe_stable_actionable_code(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified()), patch(
                "kidsstudio.first_pilot_device_doctor._mac_preflight",
                side_effect=ImportError("/private/user/secret/PIL.so")), patch(
                    "kidsstudio.first_pilot_device_doctor.shutil.which",
                    return_value="/usr/bin/ssh"):
            report = inspect_first_pilot_device(
                role="mac", artifact_root=str(self.root))
        self.assertIn(
            "pillow_or_audio_dependency_missing",
            [x["code"] for x in report["blockers"]])
        self.assertNotIn("secret", json.dumps(report))

    def test_host_dirty_checkout_never_returns_ready(self):
        host = qualified(source_clean=False)
        report = self.mac(host=host)
        self.assertEqual(report["status"],
                         "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_BLOCKED")
        self.assertIn("source_checkout_clean",
                      [row["code"] for row in report["blockers"]])

    def test_private_artifact_permissions_have_specific_hint(self):
        host = qualified(checks={
            "artifact_root_private": False,
            "free_space_threshold": False,
        })
        report = self.mac(host=host)
        codes = [item["code"] for item in report["blockers"]]
        self.assertIn("artifact_root_private", codes)
        self.assertIn("free_space_threshold", codes)
        self.assertEqual(report["failed_check_count"], 2)

    def test_mac_ssh_missing_blocks_device_ready(self):
        report = self.mac(ssh=False)
        self.assertEqual(report["blockers"][0]["code"], "ssh_client_missing")
        self.assertFalse(report["real_ssh_or_google_network_called"])

    def test_real_pi_hardware_qualification_not_same_as_actual_transfer(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified("pi")) as device, patch(
                    "kidsstudio.first_pilot_device_doctor._mac_preflight"
                ) as mac_voice_probe, patch(
                    "kidsstudio.first_pilot_device_doctor.shutil.which"
                ) as ssh_probe:
            report = inspect_first_pilot_device(
                role="pi", artifact_root=str(self.root))
        device.assert_called_once()
        self.assertEqual(device.call_args.kwargs["role"], "pi-private-handoff")
        mac_voice_probe.assert_not_called()
        ssh_probe.assert_not_called()
        self.assertEqual(report["status"],
                         "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY")
        self.assertIsNone(report["installed_mac_arabic_voice_qualified"])
        self.assertFalse(report["actual_pi_ssh_transfer_tested"])
        self.assertFalse(report["real_youtube_oauth_or_upload_tested"])

    def test_generic_linux_arm_cannot_claim_real_pi(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified(
                       "pi", checks={"raspberry_pi_model_confirmed": False})):
            report = inspect_first_pilot_device(
                role="pi", artifact_root=str(self.root))
        self.assertEqual(report["status"],
                         "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_BLOCKED")
        self.assertIn("raspberry_pi_model_confirmed",
                      [row["code"] for row in report["blockers"]])

    def test_review_selftest_failure_blocks_even_if_all_static_checks_pass(self):
        report = self.mac(host=qualified(pipeline=False))
        self.assertIn("offline_review_selftest_failed",
                      [row["code"] for row in report["blockers"]])

    def test_malformed_parameters_fail_before_device_probe(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host") as host:
            for role, voice in (("windows", None), ("pi", "Maged")):
                with self.subTest(role=role), self.assertRaises(ValueError):
                    inspect_first_pilot_device(
                        role=role, mac_voice=voice, artifact_root=str(self.root))
            host.assert_not_called()

    def test_explicit_original_wav_mode_does_not_require_apple_voice(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified()), patch(
                       "kidsstudio.first_pilot_device_doctor._mac_preflight",
                       return_value={
                           "status": "MAC_COLORS_PREFLIGHT_READY",
                           "blockers": [],
                           "local_arabic_voice_available": False,
                           "supplied_wav_six_beats_sha_verified": True,
                       }) as source, patch(
                           "kidsstudio.first_pilot_device_doctor.shutil.which",
                           return_value="/usr/bin/ssh"):
            report = inspect_first_pilot_device(
                role="mac", artifact_root=str(self.root),
                voice_mode="supplied_wav", narration_root="/private/narration",
                narration_name="original.wav", narration_sha256="a" * 64)
        self.assertEqual(report["status"],
                         "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY")
        self.assertFalse(report["installed_mac_arabic_voice_qualified"])
        self.assertTrue(report["original_supplied_wav_sha_energy_qualified"])
        self.assertEqual(source.call_args.kwargs["voice_mode"], "supplied_wav")
        self.assertEqual(source.call_args.kwargs["narration_name"], "original.wav")
        self.assertFalse(report["publication_approved"])

    def test_doctor_pi_rejects_mac_wav_arguments(self):
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host") as probe:
            with self.assertRaises(ValueError):
                inspect_first_pilot_device(
                    role="pi", artifact_root=str(self.root),
                    voice_mode="supplied_wav")
            probe.assert_not_called()

    def test_cli_redacts_exception_and_returns_error_code_without_side_effects(self):
        target = self.root / "secret-private"
        before = list(self.root.iterdir())
        output = io.StringIO()
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   side_effect=OSError(str(target))), \
             contextlib.redirect_stdout(output):
            code = main(["--role", "mac", "--artifact-root", str(target)])
        self.assertEqual(code, 2)
        self.assertNotIn("secret", output.getvalue())
        obj = json.loads(output.getvalue())
        self.assertEqual(
            obj["status"], "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_ERROR")
        self.assertFalse(obj["files_created_or_modified"])
        self.assertEqual(before, list(self.root.iterdir()))

    def test_cli_blocked_returns_one_and_false_network_flags(self):
        output = io.StringIO()
        with patch("kidsstudio.first_pilot_device_doctor.qualify_host",
                   return_value=qualified("pi", source_clean=False)), \
             contextlib.redirect_stdout(output):
            code = main(["--role", "pi", "--artifact-root", str(self.root)])
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report["real_ssh_or_google_network_called"])
        self.assertFalse(report["publication_approved"])


if __name__ == "__main__":
    unittest.main()
