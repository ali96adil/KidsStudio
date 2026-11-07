from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

from PIL import Image

from kidsstudio.first_colors_episode import (
    CUES, DURATION, EpisodeMuxError, _arabic_voice, _render_silent,
    _synthesize_wav, main, run_first_colors_episode, scene_image,
)


def write_wav(path: Path, *, seconds=24, sample_rate=16000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * sample_rate * seconds)
    path.chmod(0o600)


class FirstColorsEpisodeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.private = self.base / "private"
        self.private.mkdir(mode=0o700)
        self.audio_root = self.base / "narration"
        self.audio_root.mkdir(mode=0o700)
        self.audio = self.audio_root / "colors_ar_01.wav"
        write_wav(self.audio)
        self.audio_sha = hashlib.sha256(self.audio.read_bytes()).hexdigest()

    def test_original_six_visuals_match_spoken_colors(self):
        self.assertEqual(len(CUES), 6)
        self.assertEqual(DURATION, 24)
        red = scene_image(2)
        yellow = scene_image(3)
        blue = scene_image(4)
        self.assertEqual(red.size, (1280, 720))
        self.assertEqual(red.getpixel((640, 400)), (227, 67, 69))
        self.assertEqual(yellow.getpixel((640, 365)), (255, 196, 48))
        self.assertEqual(blue.getpixel((640, 420)), (55, 134, 228))
        self.assertIn("التفاحة", CUES[2][1])
        self.assertIn("الشمس", CUES[3][1])
        self.assertIn("السماء", CUES[4][1])

    def test_out_of_bounds_scene_rejected(self):
        for number in (-1, 6, "2", True):
            with self.subTest(scene=number), self.assertRaises(EpisodeMuxError):
                scene_image(number)

    def test_default_preview_is_offline_and_no_write(self):
        with patch("kidsstudio.first_colors_episode._run") as command:
            result = run_first_colors_episode(output_root=str(self.private))
        self.assertEqual(result["status"], "COLORS_EPISODE_PREVIEW_ONLY")
        self.assertFalse(result["render_executed"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(list(self.private.iterdir()), [])
        command.assert_not_called()

    def test_supplied_wav_preview_checks_sha_and_duration(self):
        result = run_first_colors_episode(
            output_root=str(self.private), voice_mode="supplied_wav",
            narration_root=str(self.audio_root), narration_name=self.audio.name,
            narration_sha256=self.audio_sha)
        self.assertEqual(result["narration_source"], "supplied_wav")
        self.assertEqual(result["status"], "COLORS_EPISODE_PREVIEW_ONLY")
        self.assertFalse(result["full_episode_reviewed"])

    def test_changed_supplied_wav_rejected(self):
        self.audio.write_bytes(b"not a WAV")
        with self.assertRaises(EpisodeMuxError):
            run_first_colors_episode(
                output_root=str(self.private), voice_mode="supplied_wav",
                narration_root=str(self.audio_root), narration_name=self.audio.name,
                narration_sha256=self.audio_sha)

    def test_public_audio_directory_rejected(self):
        self.audio_root.chmod(0o755)
        with self.assertRaises(ValueError):
            run_first_colors_episode(
                output_root=str(self.private), voice_mode="supplied_wav",
                narration_root=str(self.audio_root), narration_name=self.audio.name,
                narration_sha256=self.audio_sha)

    def test_existing_target_never_overwritten(self):
        file = self.private / "colors_ar_01.mp4"
        file.write_bytes(b"existing trusted video")
        with self.assertRaises(FileExistsError):
            run_first_colors_episode(output_root=str(self.private), execute=True)
        self.assertEqual(file.read_bytes(), b"existing trusted video")

    def test_wrong_directory_privacy_blocks(self):
        self.private.chmod(0o755)
        with self.assertRaises(EpisodeMuxError):
            run_first_colors_episode(output_root=str(self.private))

    def test_local_apple_arabic_voice_discovery(self):
        with patch("kidsstudio.first_colors_episode.platform.system",
                   return_value="Darwin"), \
             patch("kidsstudio.first_colors_episode._run",
                   return_value=types.SimpleNamespace(stdout=(
                       "Samantha en_US # hello\n"
                       "Maged ar_SA # sample\n"
                       "Laila ar_SA # hello\n"))):
            self.assertEqual(_arabic_voice(None), "Maged")
            self.assertEqual(_arabic_voice("Laila"), "Laila")
            with self.assertRaises(EpisodeMuxError):
                _arabic_voice("Samantha")

    def test_arabic_voice_unavailable_is_blocked(self):
        with patch("kidsstudio.first_colors_episode.platform.system",
                   return_value="Darwin"), \
             patch("kidsstudio.first_colors_episode._run",
                   return_value=types.SimpleNamespace(
                       stdout="Samantha en_US # hello\n")):
            with self.assertRaises(EpisodeMuxError):
                _arabic_voice(None)

    def test_non_mac_cannot_claim_local_apple_voice(self):
        with patch("kidsstudio.first_colors_episode.platform.system",
                   return_value="Linux"):
            with self.assertRaises(EpisodeMuxError):
                _arabic_voice(None)

    def test_original_scenes_encode_as_local_silent_video(self):
        output = self.private / "stage"
        output.mkdir(mode=0o700)
        commands = []
        def fake_run(argv, **kwargs):
            commands.append(argv)
            Path(argv[-1]).write_bytes(b"mock valid video bytes")
            return types.SimpleNamespace(returncode=0)
        with patch("kidsstudio.first_colors_episode._run", side_effect=fake_run), \
             patch("kidsstudio.first_colors_episode._probe",
                   return_value={"streams": [], "format": {}}), \
             patch("kidsstudio.first_colors_episode._check_video",
                   return_value=24):
            movie = _render_silent(output)
        self.assertTrue(movie.is_file())
        self.assertEqual(movie.stat().st_mode & 0o077, 0)
        self.assertEqual(len(list(output.glob("scene-*.png"))), 6)
        for file in output.glob("scene-*.png"):
            with Image.open(file) as image:
                self.assertEqual(image.size, (1280, 720))
                self.assertEqual(image.format, "PNG")
        command = commands[0]
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("libx264", command)
        self.assertIn("yuv420p", command)
        self.assertEqual(command[command.index("-profile:v") + 1], "baseline")
        self.assertEqual(command[command.index("-level:v") + 1], "3.1")
        self.assertIn("concat=n=6:v=1:a=0[out]", " ".join(command))
        self.assertFalse(any("http" in arg for arg in command))

    def test_mac_voice_six_original_beats_do_not_get_truncated(self):
        stage = self.private / "speech"
        stage.mkdir(mode=0o700)
        commands = []
        def fake_run(argv, **kwargs):
            commands.append(argv)
            if argv[0] == "say":
                Path(argv[argv.index("-o")+1]).write_bytes(b"dummy aiff")
            else:
                write_wav(Path(argv[-1]), seconds=24, sample_rate=48000)
            return types.SimpleNamespace(returncode=0)
        with patch("kidsstudio.first_colors_episode._arabic_voice",
                   return_value="Maged"), \
             patch("kidsstudio.first_colors_episode._run", side_effect=fake_run), \
             patch("kidsstudio.first_colors_episode._probe",
                   return_value={"format": {"duration": "1.8"}}), \
             patch("kidsstudio.first_colors_episode.check_six_beat_pcm_energy",
                   return_value={"status": "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED"}) as energy:
            filename = _synthesize_wav(stage, voice=None)
        energy.assert_called_once_with(root=str(stage), relative_path="arabic_voice.wav")
        self.assertEqual(filename.name, "arabic_voice.wav")
        self.assertTrue(filename.is_file())
        self.assertEqual([x[0] for x in commands].count("say"), 6)
        self.assertEqual([x[0] for x in commands].count("ffmpeg"), 1)
        self.assertIn("concat=n=6:v=0:a=1[out]", " ".join(commands[-1]))
        self.assertFalse(any("https" in str(cmd) for cmd in commands))

    def test_silent_native_voice_blocks_final_mux(self):
        stage = self.private / "silent_speech"
        stage.mkdir(mode=0o700)
        def fake_run(argv, **kwargs):
            if argv[0] == "say":
                Path(argv[argv.index("-o")+1]).write_bytes(b"dummy aiff")
            else:
                write_wav(Path(argv[-1]), seconds=24, sample_rate=48000)
            return types.SimpleNamespace(returncode=0)
        with patch("kidsstudio.first_colors_episode._arabic_voice",
                   return_value="Maged"), \
             patch("kidsstudio.first_colors_episode._run", side_effect=fake_run), \
             patch("kidsstudio.first_colors_episode._probe",
                   return_value={"format": {"duration": "1.8"}}):
            with self.assertRaises(EpisodeMuxError):
                _synthesize_wav(stage, voice=None)

    def test_too_long_spoken_beat_fails_closed(self):
        stage = self.private / "speech2"
        stage.mkdir(mode=0o700)
        with patch("kidsstudio.first_colors_episode._arabic_voice",
                   return_value="Maged"), \
             patch("kidsstudio.first_colors_episode._run",
                   return_value=types.SimpleNamespace(returncode=0)), \
             patch("kidsstudio.first_colors_episode._probe",
                   return_value={"format": {"duration": "4.5"}}):
            with self.assertRaises(EpisodeMuxError):
                _synthesize_wav(stage, voice=None)

    def test_one_command_real_adapters_mocked_no_upload(self):
        def fake_visual(stage):
            dest = stage / "silent.mp4"
            dest.write_bytes(b"original synthetic video bytes")
            dest.chmod(0o600)
            return dest
        def fake_voice(stage, *, voice):
            dest = stage / "arabic_voice.wav"
            write_wav(dest)
            return dest
        with patch("kidsstudio.first_colors_episode._arabic_voice",
                   return_value="Maged"), \
             patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=fake_visual), \
             patch("kidsstudio.first_colors_episode._synthesize_wav",
                   side_effect=fake_voice), \
             patch("kidsstudio.first_colors_episode.mux_episode_pilot",
                   return_value={
                       "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                       "final_mp4_sha256": "b" * 64,
                       "final_mp4_bytes": 2400,
                   }) as mux:
            result = run_first_colors_episode(
                output_root=str(self.private), execute=True)
        self.assertEqual(result["status"], "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED")
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertFalse(result["pi_transfer_performed"])
        self.assertFalse(result["voice_pronunciation_reviewed"])
        self.assertEqual(result["final_mp4_sha256"], "b" * 64)
        self.assertTrue(mux.call_args.kwargs["execute"])
        self.assertEqual(mux.call_args.kwargs["narration_sha256"], hashlib.sha256(
            (self.private / "colors_ar_01-pilot-sources" /
             "arabic_voice.wav").read_bytes()).hexdigest())

    def test_cli_invalid_configuration_redacts_paths(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([
                "--output-root", str(self.private),
                "--voice-mode", "supplied_wav", "--execute",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "COLORS_EPISODE_BLOCKED")
        self.assertNotIn(str(self.private), out.getvalue())


if __name__ == "__main__":
    unittest.main()
