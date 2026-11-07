import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from kidsstudio.filmcraft_export_check import (
    _checks, qualify_filmcraft_export, main,
)
from kidsstudio.optional_tool_evidence import ToolEvidenceError


def fake_probe():
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.00"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264",
             "width": 1280, "height": 720, "pix_fmt": "yuv420p",
             "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
             "channels": 2},
        ],
    }


class FakeFFProbe:
    def __init__(self, probe=None, returncode=0, on_probe=None):
        self.calls = []
        self.probe = fake_probe() if probe is None else probe
        self.returncode = returncode
        self.on_probe = on_probe

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.on_probe is not None:
            self.on_probe()
        return types.SimpleNamespace(
            returncode=self.returncode,
            stdout=json.dumps(self.probe),
            stderr="",
        )


class FilmCraftExportCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.movie = self.root / "synthetic.mp4"
        self.movie.write_bytes(b"NOT A REAL MP4 -- use fake ffprobe in tests")
        self.movie.chmod(0o600)
        self.sha = hashlib.sha256(self.movie.read_bytes()).hexdigest()

    def check(self, runner=None, sha=None, relative_path="synthetic.mp4"):
        return qualify_filmcraft_export(
            evidence_root=str(self.root), relative_path=relative_path,
            expected_sha256=sha or self.sha, runner=runner or FakeFFProbe())

    def test_all_technical_checks_and_no_release_authority(self):
        runner = FakeFFProbe()
        report = self.check(runner)
        self.assertEqual(report["status"],
                         "FILMCRAFT_EXPORT_TECHNICAL_PASS_UNREVIEWED")
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["file_sha256"], self.sha)
        self.assertFalse(report["editor_origin_authenticated"])
        self.assertFalse(report["video_visual_quality_verified"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0][0][0], "ffprobe")
        self.assertEqual(runner.calls[0][0][-1], str(self.movie))
        self.assertNotIn("shell", runner.calls[0][1])
        self.assertTrue(runner.calls[0][1]["timeout"] <= 25)

    def test_video_codec_mismatch_blocked(self):
        probe = fake_probe()
        probe["streams"][0]["codec_name"] = "hevc"
        report = self.check(FakeFFProbe(probe))
        self.assertEqual(report["status"], "FILMCRAFT_EXPORT_TECHNICAL_BLOCKED")
        self.assertFalse(report["checks"]["video_h264"])

    def test_missing_audio_blocked(self):
        probe = fake_probe()
        probe["streams"].pop()
        report = self.check(FakeFFProbe(probe))
        self.assertFalse(report["checks"]["single_audio_stream"])

    def test_audio_sample_rate_blocked(self):
        probe = fake_probe()
        probe["streams"][1]["sample_rate"] = "44100"
        report = self.check(FakeFFProbe(probe))
        self.assertFalse(report["checks"]["audio_48000_hz"])

    def test_wrong_dimensions_blocked(self):
        probe = fake_probe()
        probe["streams"][0]["width"] = 1920
        report = self.check(FakeFFProbe(probe))
        self.assertFalse(report["checks"]["video_1280x720"])

    def test_fractional_fps_allowed(self):
        probe = fake_probe()
        probe["streams"][0]["avg_frame_rate"] = "30000/1001"
        report = self.check(FakeFFProbe(probe))
        self.assertTrue(report["checks"]["video_allowed_fps"])

    def test_wrong_expected_sha_never_invokes_probe(self):
        runner = FakeFFProbe()
        with self.assertRaises(ToolEvidenceError):
            self.check(runner, sha="0" * 64)
        self.assertEqual(len(runner.calls), 0)

    def test_media_changed_during_probe_fails_closed(self):
        runner = FakeFFProbe(on_probe=lambda: self.movie.write_bytes(b"changed"))
        with self.assertRaises(ToolEvidenceError):
            self.check(runner)

    def test_invalid_probe_json_rejected(self):
        runner = FakeFFProbe()
        original_call = runner.__call__
        class Malformed:
            def __call__(self, argv, **kwargs):
                return types.SimpleNamespace(returncode=0, stdout="{")
        with self.assertRaises(ToolEvidenceError):
            self.check(Malformed())

    def test_failed_probe_rejected_without_leaking_stderr(self):
        runner = FakeFFProbe(returncode=1)
        with self.assertRaises(ToolEvidenceError):
            self.check(runner)

    def test_public_media_file_rejected(self):
        self.movie.chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            self.check(FakeFFProbe())

    def test_symlink_media_rejected(self):
        link = self.root / "linked.mp4"
        link.symlink_to(self.movie)
        with self.assertRaises(ToolEvidenceError):
            self.check(FakeFFProbe(), relative_path="linked.mp4")

    def test_must_be_mp4(self):
        renamed = self.root / "synthetic.mov"
        renamed.write_bytes(self.movie.read_bytes())
        renamed.chmod(0o600)
        with self.assertRaises(ToolEvidenceError):
            self.check(FakeFFProbe(), relative_path="synthetic.mov")

    def test_cli_safe_report_no_paths_or_upload(self):
        with patch("kidsstudio.filmcraft_export_check._read_probe",
                   return_value=fake_probe()):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "--evidence-root", str(self.root),
                    "--relative-path", self.movie.name,
                    "--expected-sha256", self.sha,
                ])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(json.loads(out.getvalue())["publication_approved"])

    def test_cli_wrong_sha_fails_closed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([
                "--evidence-root", str(self.root),
                "--relative-path", self.movie.name,
                "--expected-sha256", "f" * 64,
            ])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "FILMCRAFT_EXPORT_CHECK_ERROR")


if __name__ == "__main__":
    unittest.main()
