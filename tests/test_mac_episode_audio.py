from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.mac_episode_audio import EpisodeMuxError, main, mux_episode_pilot
from kidsstudio.optional_tool_evidence import ToolEvidenceError


def media_metadata(*, with_audio=False, duration="4.0", codec="h264",
                   fps="24/1", pix_fmt="yuv420p"):
    streams = [{
        "codec_type": "video", "codec_name": codec,
        "width": 1280, "height": 720, "pix_fmt": pix_fmt,
        "avg_frame_rate": fps,
    }]
    if with_audio:
        streams.append({
            "codec_type": "audio", "codec_name": "aac",
            "sample_rate": "48000", "channels": 2,
        })
    return {"streams": streams, "format": {"duration": duration}}


class MacEpisodeAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "private"
        self.out = base / "ready"
        self.root.mkdir(mode=0o700)
        self.out.mkdir(mode=0o700)
        self.video = self.root / "silent.mp4"
        self.video.write_bytes(b"MOCKED_VIDEO_BYTES_NOT_PLAYABLE" * 100)
        self.video.chmod(0o600)
        self.voice = self.root / "arabic.wav"
        with wave.open(str(self.voice), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 16000 * 4)
        self.voice.chmod(0o600)
        self.video_sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.voice_sha = hashlib.sha256(self.voice.read_bytes()).hexdigest()

    def args(self, **updates):
        kw = dict(
            video_root=str(self.root),
            video_name="silent.mp4",
            video_sha256=self.video_sha,
            narration_root=str(self.root),
            narration_name="arabic.wav",
            narration_sha256=self.voice_sha,
            output_root=str(self.out),
            output_name="colors_ar_01.mp4",
        )
        kw.update(updates)
        return kw

    def test_preview_is_read_only_and_never_calls_ffmpeg(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata()), \
             patch("kidsstudio.mac_episode_audio.subprocess.run") as runner:
            report = mux_episode_pilot(**self.args())
        self.assertEqual(report["status"], "MAC_EPISODE_PREVIEW_READY")
        self.assertFalse(report["ffmpeg_executed"])
        self.assertFalse(report["youtube_upload_performed"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual(list(self.out.iterdir()), [])
        runner.assert_not_called()

    def test_mux_preserves_inputs_and_private_output(self):
        def fake_probe(path):
            return media_metadata(with_audio=path.parent == self.out)
        def fake_ffmpeg(command, **kwargs):
            Path(command[-1]).write_bytes(b"VALID_MOCK_METADATA_FOR_OUTPUT")
            return type("Result", (), {"returncode": 0})()
        with patch("kidsstudio.mac_episode_audio._probe", side_effect=fake_probe), \
             patch("kidsstudio.mac_episode_audio.subprocess.run", side_effect=fake_ffmpeg) as run:
            result = mux_episode_pilot(**self.args(execute=True))
        target = self.out / "colors_ar_01.mp4"
        self.assertTrue(target.exists())
        self.assertEqual(result["status"], "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED")
        self.assertEqual(result["final_mp4_sha256"],
                         hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(target.stat().st_mode & 0o077, 0)
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(), self.video_sha)
        self.assertEqual(hashlib.sha256(self.voice.read_bytes()).hexdigest(), self.voice_sha)
        self.assertFalse(result["local_audio_visual_review_required"] is False)
        self.assertFalse(result["pi_transfer_performed"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertEqual(len(run.call_args_list), 1)
        command = run.call_args_list[0].args[0]
        self.assertIn("copy", command)
        self.assertIn("aac", command)
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertEqual(command[command.index("-ac") + 1], "2")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["colors_ar_01.mp4"])

    def test_mux_reports_checked_bytes_when_ready_filename_is_replaced(self):
        checked_bytes = b"verified mux output"
        link = os.link

        def fake_ffmpeg(command, **kwargs):
            Path(command[-1]).write_bytes(checked_bytes)
            return subprocess.CompletedProcess(command, 0)

        def link_then_replace(source, target, **kwargs):
            link(source, target, **kwargs)
            target.unlink()
            target.write_bytes(b"different file at ready name")

        with patch("kidsstudio.mac_episode_audio._probe",
                   side_effect=lambda path: media_metadata(with_audio=path.parent == self.out)), \
             patch("kidsstudio.mac_episode_audio.subprocess.run", side_effect=fake_ffmpeg), \
             patch("kidsstudio.mac_episode_audio.os.link", side_effect=link_then_replace):
            result = mux_episode_pilot(**self.args(execute=True))
        self.assertEqual(result["final_mp4_sha256"], hashlib.sha256(checked_bytes).hexdigest())
        self.assertEqual(result["final_mp4_bytes"], len(checked_bytes))

    def test_second_run_never_overwrites(self):
        (self.out / "colors_ar_01.mp4").write_bytes(b"original")
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata()):
            with self.assertRaises(FileExistsError):
                mux_episode_pilot(**self.args(execute=True))
        self.assertEqual((self.out / "colors_ar_01.mp4").read_bytes(), b"original")

    def test_changed_video_hash_rejected(self):
        self.video.write_bytes(b"changed")
        with self.assertRaises(EpisodeMuxError):
            mux_episode_pilot(**self.args())

    def test_changed_voice_hash_rejected(self):
        self.voice.write_bytes(self.voice.read_bytes() + b"x")
        with self.assertRaises(EpisodeMuxError):
            mux_episode_pilot(**self.args())

    def test_source_voice_must_be_pcm_wav(self):
        self.voice.write_bytes(b"not-wave" + b"x" * 100)
        sha = hashlib.sha256(self.voice.read_bytes()).hexdigest()
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata()):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args(narration_sha256=sha))

    def test_invalid_fps_rejected(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata(fps="23/1")):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args())

    def test_invalid_video_codec_rejected(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata(codec="hevc")):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args())

    def test_invalid_video_pixel_format_rejected(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata(pix_fmt="yuv444p")):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args())

    def test_refuses_silent_audio_duration_mismatch(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata(duration="6.0")):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args())

    def test_invalid_output_name_or_hash_rejected(self):
        with self.assertRaises(EpisodeMuxError):
            mux_episode_pilot(**self.args(output_name="../escape.mp4"))
        with self.assertRaises(EpisodeMuxError):
            mux_episode_pilot(**self.args(video_sha256="bad"))

    def test_private_output_directory_required(self):
        self.out.chmod(0o755)
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata()):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args())

    def test_public_source_media_rejected(self):
        self.video.chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            mux_episode_pilot(**self.args())

    def test_failed_ffmpeg_does_not_promote_output(self):
        with patch("kidsstudio.mac_episode_audio._probe",
                   return_value=media_metadata()), \
             patch("kidsstudio.mac_episode_audio.subprocess.run",
                   return_value=type("Result", (), {"returncode": 1})()):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args(execute=True))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_source_mutated_while_muxing_is_blocked(self):
        def fake_ffmpeg(command, **kwargs):
            Path(command[-1]).write_bytes(b"synthetic bytes")
            self.video.write_bytes(b"modified mid-mux")
            return type("Result", (), {"returncode": 0})()
        with patch("kidsstudio.mac_episode_audio._probe",
                   side_effect=lambda path: media_metadata(with_audio=path.parent == self.out)), \
             patch("kidsstudio.mac_episode_audio.subprocess.run", side_effect=fake_ffmpeg):
            with self.assertRaises(EpisodeMuxError):
                mux_episode_pilot(**self.args(execute=True))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_cli_fail_closed_invalid_inputs_no_leaks(self):
        out = io.StringIO()
        args = [
            "--video-root", str(self.root), "--video-name", "silent.mp4",
            "--video-sha256", "0" * 64,
            "--narration-root", str(self.root), "--narration-name", "arabic.wav",
            "--narration-sha256", self.voice_sha,
            "--output-root", str(self.out), "--output-name", "test.mp4",
            "--execute-mux",
        ]
        with contextlib.redirect_stdout(out):
            status = main(args)
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "MAC_EPISODE_MUX_REJECTED")
        self.assertNotIn(str(self.root), out.getvalue())

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "Optional actual FFmpeg/FFprobe integration")
    def test_real_ffmpeg_mux_round_trip(self):
        source = self.root / "real-silent.mp4"
        video_cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-f", "lavfi", "-i", "color=c=blue:s=1280x720:r=24",
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ]
        completed = subprocess.run(video_cmd, capture_output=True, timeout=90)
        if completed.returncode != 0:
            self.skipTest("Local FFmpeg lacks H.264 encoder; mocked tests still apply")
        source.chmod(0o600)
        result = mux_episode_pilot(**self.args(
            video_name=source.name,
            video_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            execute=True))
        self.assertEqual(result["status"], "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED")
        self.assertTrue((self.out / "colors_ar_01.mp4").is_file())
        self.assertTrue(result["final_mp4_bytes"] > 0)


if __name__ == "__main__":
    unittest.main()
