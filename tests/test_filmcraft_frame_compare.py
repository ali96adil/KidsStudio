import contextlib
import hashlib
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image

from kidsstudio.filmcraft_frame_compare import (
    _frame_at, compare_filmcraft_frames, main,
)
from kidsstudio.optional_tool_evidence import ToolEvidenceError


def probe(*, fps="30/1", duration="12.00", audio="aac"):
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280,
             "height": 720, "pix_fmt": "yuv420p", "avg_frame_rate": fps},
            {"codec_type": "audio", "codec_name": audio, "sample_rate": "48000",
             "channels": 2},
        ],
    }


def png(color, *, size=(320, 180)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeProbe:
    def __init__(self, base=None, candidate=None):
        self.base = probe() if base is None else base
        self.candidate = probe() if candidate is None else candidate
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        file = argv[-1]
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps(
                self.base if str(file).endswith("godot.mp4") else self.candidate),
            stderr="")


class FakeFrame:
    def __init__(self, candidate_color=(20, 40, 60), on_call=None):
        self.calls = []
        self.candidate_color = candidate_color
        self.on_call = on_call

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.on_call is not None:
            self.on_call(len(self.calls))
        file = argv[argv.index("-i") + 1]
        color = self.candidate_color if str(file).endswith("filmcraft.mp4") else (20, 40, 60)
        return types.SimpleNamespace(returncode=0, stdout=png(color), stderr=b"")


class FilmCraftFrameCompareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.base = self.root / "godot.mp4"
        self.candidate = self.root / "filmcraft.mp4"
        self.base.write_bytes(b"fake Godot for mocked probe and decode")
        self.candidate.write_bytes(b"fake FilmCraft for mocked probe and decode")
        for file in (self.base, self.candidate):
            file.chmod(0o600)
        self.base_sha = hashlib.sha256(self.base.read_bytes()).hexdigest()
        self.candidate_sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()

    def compare(self, *, probe_runner=None, frame_runner=None, **kwargs):
        settings = {
            "evidence_root": str(self.root),
            "baseline_relative_path": "godot.mp4",
            "baseline_sha256": self.base_sha,
            "candidate_relative_path": "filmcraft.mp4",
            "candidate_sha256": self.candidate_sha,
            "probe_runner": probe_runner or FakeProbe(),
            "frame_runner": frame_runner or FakeFrame(),
        }
        settings.update(kwargs)
        return compare_filmcraft_frames(**settings)

    def test_six_decoded_samples_within_limits_are_not_approval(self):
        runner = FakeFrame()
        result = self.compare(frame_runner=runner)
        self.assertEqual(result["status"],
                         "FILMCRAFT_SAMPLED_FRAMES_WITHIN_LIMITS_UNREVIEWED")
        self.assertEqual(result["sampled_frames_decoded"], 6)
        self.assertEqual(len(runner.calls), 6)
        self.assertEqual([s["relative_position"] for s in result["samples"]],
                         [0.25, 0.5, 0.75])
        self.assertTrue(all(s["within_limits"] for s in result["samples"]))
        self.assertFalse(result["entire_video_visually_verified"])
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["audio_quality_compared"])
        self.assertEqual(result["real_filmcraft_mac_run"], "NOT_RUN")
        self.assertEqual(runner.calls[0][0][0], "ffmpeg")
        self.assertNotIn("shell", runner.calls[0][1])

    def test_different_color_frames_are_flagged(self):
        result = self.compare(frame_runner=FakeFrame(candidate_color=(250, 100, 5)))
        self.assertEqual(result["status"],
                         "FILMCRAFT_SAMPLED_FRAMES_DIFFER_REVIEW_REQUIRED")
        self.assertGreater(result["samples"][0]["changed_pixel_fraction"], 0.99)

    def test_audio_metadata_failure_prevents_frame_decoding(self):
        frame = FakeFrame()
        p = FakeProbe(candidate=probe(audio="none"))
        with self.assertRaises(ToolEvidenceError):
            self.compare(probe_runner=p, frame_runner=frame)
        self.assertEqual(frame.calls, [])

    def test_different_frame_rates_prevent_frame_decoding(self):
        frame = FakeFrame()
        p = FakeProbe(candidate=probe(fps="25/1"))
        with self.assertRaises(ToolEvidenceError):
            self.compare(probe_runner=p, frame_runner=frame)
        self.assertEqual(frame.calls, [])

    def test_wrong_sha_prevents_frame_decoding(self):
        frame = FakeFrame()
        with self.assertRaises(ToolEvidenceError):
            self.compare(frame_runner=frame, candidate_sha256="0" * 64)
        self.assertEqual(frame.calls, [])

    def test_media_tampering_during_decoding_fails_closed(self):
        def tamper(count):
            if count == 4:
                self.candidate.write_bytes(b"mutated movie after verifying")
        with self.assertRaises(ToolEvidenceError):
            self.compare(frame_runner=FakeFrame(on_call=tamper))

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ToolEvidenceError):
            self.compare(mean_diff_limit=-1)
        with self.assertRaises(ToolEvidenceError):
            self.compare(channel_threshold="high")

    def test_decoder_rejects_garbled_png(self):
        class Broken:
            def __call__(self, argv, **kwargs):
                return types.SimpleNamespace(returncode=0, stdout=b"invalid" * 5)
        with self.assertRaises(ToolEvidenceError):
            _frame_at(self.base, 3.0, runner=Broken())

    def test_decoder_rejects_wrong_png_dimensions(self):
        class Wrong:
            def __call__(self, argv, **kwargs):
                return types.SimpleNamespace(
                    returncode=0, stdout=png((0, 0, 0), size=(100, 100)))
        with self.assertRaises(ToolEvidenceError):
            _frame_at(self.base, 3.0, runner=Wrong())

    def test_private_cli_returns_no_media_bytes(self):
        out = StringIO()
        with patch("kidsstudio.filmcraft_export_check._read_probe",
                   side_effect=lambda path, *, runner: probe()), \
             patch("kidsstudio.filmcraft_frame_compare._frame_at",
                   side_effect=lambda file, second, *, runner:
                   Image.new("RGB", (320, 180), (20, 40, 60))):
            with contextlib.redirect_stdout(out):
                code = main([
                    "--evidence-root", str(self.root),
                    "--baseline-relative-path", "godot.mp4",
                    "--baseline-sha256", self.base_sha,
                    "--candidate-relative-path", "filmcraft.mp4",
                    "--candidate-sha256", self.candidate_sha,
                ])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(json.loads(out.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
