"""Playback preflight tests; all private evidence is locally synthesized."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kidsstudio.mp4_playback_preflight import (
    PlaybackPreflightError, _codec_profiles, _decode_sample,
    _faststart_atoms, inspect_mp4_playback, main,
)


def box(kind: bytes, data: bytes = b"abcd") -> bytes:
    return (8 + len(data)).to_bytes(4, "big") + kind + data


def sample_mp4() -> bytes:
    return box(b"ftyp", b"isom0000") + box(b"moov") + box(b"mdat", b"01234567")


def profile_response(video="Constrained Baseline", level=31, audio="LC"):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"streams": [
            {"codec_type": "video", "profile": video, "level": level},
            {"codec_type": "audio", "profile": audio},
        ]}).encode("utf-8"),
    )


class PlaybackPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.video = self.root / "clip.mp4"
        self.video.write_bytes(sample_mp4())
        self.video.chmod(0o600)

    @property
    def sha(self):
        return hashlib.sha256(self.video.read_bytes()).hexdigest()

    def test_faststart_header_valid(self):
        self.assertTrue(_faststart_atoms(self.video))

    def test_moov_after_mdat_rejected(self):
        self.video.write_bytes(box(b"ftyp") + box(b"mdat") + box(b"moov"))
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_missing_moov_rejected(self):
        self.video.write_bytes(box(b"ftyp") + box(b"mdat"))
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_multiple_media_data_boxes_rejected(self):
        self.video.write_bytes(
            box(b"ftyp") + box(b"moov") + box(b"mdat") + box(b"mdat"))
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_truncated_mp4_box_rejected(self):
        self.video.write_bytes(
            box(b"ftyp") + (1000).to_bytes(4, "big") + b"moov")
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_truncated_extended_box_rejected(self):
        self.video.write_bytes(box(b"ftyp") + b"\x00\x00\x00\x01moov123")
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_empty_top_level_unbounded_non_media_box_rejected(self):
        self.video.write_bytes(box(b"ftyp") + b"\x00\x00\x00\x00moov")
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_initial_box_must_be_ftyp(self):
        self.video.write_bytes(box(b"free") + sample_mp4())
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_excessive_mp4_box_count_rejected(self):
        self.video.write_bytes(box(b"ftyp") + box(b"moov")
                               + box(b"free") * 260 + box(b"mdat"))
        with self.assertRaises(PlaybackPreflightError):
            _faststart_atoms(self.video)

    def test_codec_profiles_accept_baseline_and_aac_lc(self):
        with patch("kidsstudio.mp4_playback_preflight.subprocess.run",
                   return_value=profile_response()) as proc:
            _codec_profiles(self.video)
        self.assertEqual(proc.call_args.args[0][0], "ffprobe")

    def test_codec_profiles_reject_high_level_and_he_aac(self):
        for response in (profile_response(level=40),
                         profile_response(video="High"),
                         profile_response(audio="HE-AAC"),
                         profile_response(level=True)):
            with self.subTest(response=response.stdout), patch(
                "kidsstudio.mp4_playback_preflight.subprocess.run",
                return_value=response,
            ):
                with self.assertRaises(PlaybackPreflightError):
                    _codec_profiles(self.video)

    def test_sample_decode_must_yield_a_real_frame_row(self):
        row = b"#stream: 0\n0, 0, 0, 1, 1024, 00112233\n"
        with patch("kidsstudio.mp4_playback_preflight.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=row)) as proc:
            _decode_sample(self.video, kind="video", second=12.0)
        self.assertIn("-frames:v", proc.call_args.args[0])
        with patch("kidsstudio.mp4_playback_preflight.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=b"#header only\n")):
            with self.assertRaises(PlaybackPreflightError):
                _decode_sample(self.video, kind="audio", second=12.0)

    def test_exact_sha_and_five_decodes_required_before_success(self):
        with patch("kidsstudio.mp4_playback_preflight._probe",
                   return_value={"streams": []}), patch(
                "kidsstudio.mp4_playback_preflight._check_video",
                return_value=24.0), patch(
                "kidsstudio.mp4_playback_preflight._codec_profiles"), patch(
                "kidsstudio.mp4_playback_preflight._decode_sample") as decoder:
            result = inspect_mp4_playback(
                root=str(self.root), relative_path="clip.mp4",
                expected_sha256=self.sha)
        self.assertEqual(result["status"], "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED")
        self.assertEqual(decoder.call_count, 5)
        self.assertTrue(result["faststart_moov_before_mdat"])
        self.assertFalse(result["entire_video_decoded"])
        self.assertFalse(result["owner_playback_reviewed"])
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])

    def test_wrong_sha_is_rejected_before_any_codec_decoding(self):
        with patch("kidsstudio.mp4_playback_preflight._decode_sample") as decoder:
            with self.assertRaises(PlaybackPreflightError):
                inspect_mp4_playback(
                    root=str(self.root), relative_path="clip.mp4",
                    expected_sha256="0" * 64)
        decoder.assert_not_called()

    def test_tampering_during_decodes_is_rejected(self):
        def mutate(*args, **kwargs):
            self.video.write_bytes(sample_mp4() + box(b"free"))
        with patch("kidsstudio.mp4_playback_preflight._probe",
                   return_value={"streams": []}), patch(
                "kidsstudio.mp4_playback_preflight._check_video",
                return_value=24.0), patch(
                "kidsstudio.mp4_playback_preflight._codec_profiles"), patch(
                "kidsstudio.mp4_playback_preflight._decode_sample",
                side_effect=mutate):
            before = self.sha
            with self.assertRaises(PlaybackPreflightError):
                inspect_mp4_playback(
                    root=str(self.root), relative_path="clip.mp4",
                    expected_sha256=before)

    def test_public_or_symlink_video_rejected(self):
        link = self.root / "linked.mp4"
        link.symlink_to(self.video)
        for name, sha in (("linked.mp4", self.sha),):
            with self.assertRaises(ValueError):
                inspect_mp4_playback(
                    root=str(self.root), relative_path=name,
                    expected_sha256=sha)
        self.video.chmod(0o644)
        with self.assertRaises(ValueError):
            inspect_mp4_playback(
                root=str(self.root), relative_path="clip.mp4",
                expected_sha256=self.sha)

    def test_cli_rejects_bad_mp4_without_leaking_path(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--root", str(self.root),
                         "--relative-path", "clip.mp4",
                         "--expected-sha256", "0" * 64])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "MP4_PLAYBACK_PREFLIGHT_BLOCKED")
        self.assertNotIn(str(self.root), out.getvalue())

    def test_only_mp4_extension_supported(self):
        with self.assertRaises(PlaybackPreflightError):
            inspect_mp4_playback(
                root=str(self.root), relative_path="clip.mov",
                expected_sha256=self.sha)


if __name__ == "__main__":
    unittest.main()
