"""Offline Mac pilot preflight tests, no real system voice or writes."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from kidsstudio.first_colors_episode import EpisodeMuxError
from kidsstudio.mac_colors_preflight import inspect_mac_colors_preflight, main


def ready():
    return {
        "ready_for_supervised_tests": True,
        "host_system": "Darwin",
        "machine": "arm64",
    }


class MacColorsPreflightTests(unittest.TestCase):
    def simulate(self, *, os_name="Darwin", host=None, revision=None,
                 installed=True, binaries=True, voice_error=False,
                 expected_voice=None):
        calls = []
        def check_voice(name):
            calls.append(name)
            if voice_error:
                raise EpisodeMuxError("unavailable voice")
            return "OriginalArabic"
        with patch("kidsstudio.mac_colors_preflight.platform.system",
                   return_value=os_name), patch(
                     "kidsstudio.mac_colors_preflight.inspect_host",
                     return_value=ready() if host is None else host
                   ) as inspect, patch(
                     "kidsstudio.mac_colors_preflight._source_checkout",
                     return_value=("a" * 40, True) if revision is None else revision
                   ), patch(
                     "kidsstudio.mac_colors_preflight.shutil.which",
                     side_effect=lambda _: "/usr/bin/ok" if binaries else None
                   ), patch(
                     "kidsstudio.mac_colors_preflight._arabic_voice",
                     side_effect=check_voice
                   ):
            result = inspect_mac_colors_preflight(
                artifact_root="/private/ready", mac_voice=expected_voice)
        inspect.assert_called_once()
        return result, calls

    def test_ready_mac_reports_no_actions_and_full_commit(self):
        report, voices = self.simulate(expected_voice="OriginalArabic")
        self.assertEqual(report["status"], "MAC_COLORS_PREFLIGHT_READY")
        self.assertEqual(report["source_commit"], "a" * 40)
        self.assertTrue(report["local_arabic_voice_available"])
        self.assertEqual(voices, ["OriginalArabic"])
        for key in ("video_render_executed", "speech_generated",
                    "pi_transfer_performed", "youtube_upload_performed",
                    "publication_approved"):
            self.assertFalse(report[key])

    def test_wrong_os_blocks_and_does_not_query_macos_voice(self):
        report, voices = self.simulate(os_name="Linux")
        self.assertIn("macos_required", report["blockers"])
        self.assertEqual(voices, [])
        self.assertFalse(report["local_arabic_voice_available"])

    def test_private_root_not_ready_is_blocked(self):
        obj = ready()
        obj["ready_for_supervised_tests"] = False
        report, _ = self.simulate(host=obj)
        self.assertIn("private_artifact_root_or_host_unready",
                      report["blockers"])

    def test_wrong_machine_blocks(self):
        obj = ready()
        obj["machine"] = "x86-linux"
        report, _ = self.simulate(host=obj)
        self.assertIn("mac_platform_architecture_mismatch",
                      report["blockers"])

    def test_missing_git_or_ffmpeg_blocks_before_voice_probe(self):
        report, voices = self.simulate(binaries=False)
        self.assertIn("local_media_or_git_executable_missing",
                      report["blockers"])
        self.assertEqual(voices, [])

    def test_dirty_source_checkout_blocks(self):
        report, _ = self.simulate(revision=("a" * 40, False))
        self.assertIn("pinned_clean_git_checkout_required",
                      report["blockers"])

    def test_invalid_source_sha_blocks(self):
        report, _ = self.simulate(revision=("short", True))
        self.assertIsNone(report["source_commit"])
        self.assertIn("pinned_clean_git_checkout_required",
                      report["blockers"])

    def test_arabic_voice_missing_blocks_no_synthesis(self):
        report, voices = self.simulate(voice_error=True)
        self.assertIn("installed_arabic_voice_missing_or_invalid",
                      report["blockers"])
        self.assertFalse(report["local_arabic_voice_available"])
        self.assertEqual(voices, [None])

    def test_cli_errors_redact_paths(self):
        output = io.StringIO()
        with patch("kidsstudio.mac_colors_preflight.inspect_mac_colors_preflight",
                   side_effect=OSError("/secret/media/failure")):
            with contextlib.redirect_stdout(output):
                code = main(["--artifact-root", "/secret/media"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "MAC_COLORS_PREFLIGHT_ERROR")
        self.assertNotIn("secret", output.getvalue())

    def test_cli_blocked_has_exit_one(self):
        output = io.StringIO()
        with patch("kidsstudio.mac_colors_preflight.inspect_mac_colors_preflight",
                   return_value={"status": "MAC_COLORS_PREFLIGHT_BLOCKED",
                                 "publication_approved": False}):
            with contextlib.redirect_stdout(output):
                code = main(["--artifact-root", "/private/ready"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
