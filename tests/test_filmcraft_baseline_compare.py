import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from kidsstudio.filmcraft_baseline_compare import compare_filmcraft_baseline, main
from kidsstudio.optional_tool_evidence import ToolEvidenceError


def probe(duration="12.00", fps="30/1", codec="h264", audio="aac"):
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration},
        "streams": [
            {"codec_type": "video", "codec_name": codec,
             "width": 1280, "height": 720, "pix_fmt": "yuv420p",
             "avg_frame_rate": fps},
            {"codec_type": "audio", "codec_name": audio,
             "sample_rate": "48000", "channels": 2},
        ],
    }


class FakeProbeRunner:
    def __init__(self, baseline=None, candidate=None, tamper=None):
        self.baseline = probe() if baseline is None else baseline
        self.candidate = probe() if candidate is None else candidate
        self.calls = []
        self.tamper = tamper

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.tamper and len(self.calls) == 2:
            self.tamper()
        obj = self.baseline if str(argv[-1]).endswith("godot.mp4") else self.candidate
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps(obj), stderr="")


class FilmCraftBaselineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.baseline = self.root / "godot.mp4"
        self.candidate = self.root / "filmcraft.mp4"
        self.baseline.write_bytes(b"synthetic Godot baseline; ffprobe mocked")
        self.candidate.write_bytes(b"synthetic FilmCraft candidate; ffprobe mocked")
        for p in (self.baseline, self.candidate):
            p.chmod(0o600)
        self.g_sha = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        self.f_sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()

    def compare(self, runner=None, **kwargs):
        settings = dict(
            evidence_root=str(self.root),
            baseline_relative_path="godot.mp4",
            baseline_sha256=self.g_sha,
            candidate_relative_path="filmcraft.mp4",
            candidate_sha256=self.f_sha,
            runner=runner or FakeProbeRunner(),
        )
        settings.update(kwargs)
        return compare_filmcraft_baseline(**settings)

    def test_distinct_technically_matched_exports_not_content_approval(self):
        runner = FakeProbeRunner()
        r = self.compare(runner)
        self.assertEqual(r["status"],
                         "FILMCRAFT_BASELINE_TECHNICALLY_COMPARABLE_UNREVIEWED")
        self.assertTrue(all(r["checks"].values()))
        self.assertFalse(r["exact_frame_content_compared"])
        self.assertFalse(r["same_underlying_episode_verified"])
        self.assertFalse(r["audio_perceptual_quality_compared"])
        self.assertFalse(r["arabic_captions_compared"])
        self.assertFalse(r["publication_approved"])
        self.assertEqual(r["real_mac_filmcraft_run"], "NOT_RUN")
        self.assertEqual(len(runner.calls), 2)

    def test_wrong_fps_blocks_comparability(self):
        r = self.compare(FakeProbeRunner(candidate=probe(fps="25/1")))
        self.assertEqual(r["status"], "FILMCRAFT_BASELINE_COMPARISON_BLOCKED")
        self.assertFalse(r["checks"]["same_frame_rate"])

    def test_different_duration_blocks(self):
        r = self.compare(FakeProbeRunner(candidate=probe(duration="12.2")))
        self.assertFalse(r["checks"]["duration_delta_at_most_0_10_seconds"])

    def test_small_duration_padding_accepted(self):
        r = self.compare(FakeProbeRunner(candidate=probe(duration="12.05")))
        self.assertTrue(r["checks"]["duration_delta_at_most_0_10_seconds"])

    def test_missing_audio_blocks(self):
        p = probe()
        p["streams"].pop()
        r = self.compare(FakeProbeRunner(candidate=p))
        self.assertFalse(r["checks"]["both_independently_technically_pass"])

    def test_wrong_h264_blocks(self):
        r = self.compare(FakeProbeRunner(baseline=probe(codec="hevc")))
        self.assertEqual(r["status"], "FILMCRAFT_BASELINE_COMPARISON_BLOCKED")

    def test_identical_sha_blocks_independent_candidate(self):
        self.candidate.write_bytes(self.baseline.read_bytes())
        sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        r = self.compare(candidate_sha256=sha)
        self.assertFalse(r["checks"]["different_content_sha256"])

    def test_wrong_sha_does_not_start_probe(self):
        runner = FakeProbeRunner()
        with self.assertRaises(ToolEvidenceError):
            self.compare(runner=runner, candidate_sha256="0" * 64)
        self.assertEqual(len(runner.calls), 1)

    def test_tamper_during_probe_rejected(self):
        runner = FakeProbeRunner(tamper=lambda: self.candidate.write_bytes(b"changed"))
        with self.assertRaises(ToolEvidenceError):
            self.compare(runner=runner)

    def test_same_path_rejected(self):
        with self.assertRaises(ToolEvidenceError):
            self.compare(candidate_relative_path="godot.mp4")

    def test_public_candidate_rejected(self):
        self.candidate.chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            self.compare()

    def test_cli_redacts_private_paths(self):
        out = io.StringIO()
        with patch("kidsstudio.filmcraft_export_check._read_probe",
                   side_effect=lambda path, *, runner: probe()):
            with contextlib.redirect_stdout(out):
                code = main([
                    "--evidence-root", str(self.root),
                    "--baseline-relative-path", "godot.mp4",
                    "--baseline-sha256", self.g_sha,
                    "--candidate-relative-path", "filmcraft.mp4",
                    "--candidate-sha256", self.f_sha,
                ])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(json.loads(out.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
