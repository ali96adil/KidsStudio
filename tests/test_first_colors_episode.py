from __future__ import annotations

import contextlib
from array import array
import hashlib
import io
import math
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

from PIL import Image

from kidsstudio.first_colors_episode import (
    CUES, DURATION, SECONDS_PER_SCENE, EpisodeMuxError, _arabic_voice,
    _render_silent, _verify_final_audio_beats,
    _synthesize_wav, main, run_first_colors_episode, scene_image,
)


def write_wav(path: Path, *, seconds=24, sample_rate=16000, amplitude=0,
              silent_beats=()):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        if amplitude:
            audio.writeframes(array("h", (
                0 if i // (4 * sample_rate) in silent_beats else
                int(amplitude * math.sin(2 * math.pi * 440 * i / sample_rate))
                for i in range(sample_rate * seconds))).tobytes())
        else:
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

    def test_storyboard_text_and_timing_match_rendered_episode(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] /
                               "examples/colors_ar_01_pilot_cues.json"
                               ).read_text(encoding="utf-8"))
        beats = manifest["beats"]
        self.assertEqual(manifest["episode_id"], "colors_ar_01")
        self.assertEqual(manifest["scene_duration_seconds"], DURATION)
        self.assertEqual(tuple(beat["narration"] for beat in beats),
                         tuple(text for _, text in CUES))
        self.assertEqual(len(beats), len(CUES))
        for index, beat in enumerate(beats):
            with self.subTest(beat=index):
                self.assertEqual(beat["start"], index * SECONDS_PER_SCENE)
                self.assertEqual(beat["end"], (index + 1) * SECONDS_PER_SCENE)

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

    def test_supplied_wav_replaced_during_picture_encode_is_rejected(self):
        write_wav(self.audio, sample_rate=16000, amplitude=5000)
        self.audio_sha = hashlib.sha256(self.audio.read_bytes()).hexdigest()

        def render_and_replace_audio(stage):
            write_wav(self.audio, sample_rate=24000)
            movie = stage / "silent.mp4"
            movie.write_bytes(b"synthetic silent video")
            movie.chmod(0o600)
            return movie

        with patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=render_and_replace_audio), \
             patch("kidsstudio.mac_episode_audio._probe") as probe:
            with self.assertRaisesRegex(EpisodeMuxError, "Input checksum mismatch"):
                run_first_colors_episode(
                    output_root=str(self.private), voice_mode="supplied_wav",
                    narration_root=str(self.audio_root), narration_name=self.audio.name,
                    narration_sha256=self.audio_sha, execute=True)
        probe.assert_not_called()
        self.assertFalse((self.private / "colors_ar_01.mp4").exists())

    def test_silent_supplied_wav_is_rejected_before_picture_encode(self):
        def fake_visual(stage):
            target = stage / "silent.mp4"
            target.write_bytes(b"synthetic video")
            target.chmod(0o600)
            return target

        with patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=fake_visual) as render, patch(
                "kidsstudio.first_colors_episode.mux_episode_pilot") as mux:
            with self.assertRaises(EpisodeMuxError):
                run_first_colors_episode(
                    output_root=str(self.private), voice_mode="supplied_wav",
                    narration_root=str(self.audio_root),
                    narration_name=self.audio.name,
                    narration_sha256=self.audio_sha, execute=True)
        render.assert_not_called()
        mux.assert_not_called()

    def test_supplied_wav_with_presence_in_each_beat_can_render(self):
        write_wav(self.audio, amplitude=5000)
        digest = hashlib.sha256(self.audio.read_bytes()).hexdigest()

        def fake_visual(stage):
            target = stage / "silent.mp4"
            target.write_bytes(b"synthetic video")
            target.chmod(0o600)
            return target

        with patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=fake_visual) as render, patch(
                "kidsstudio.first_colors_episode.mux_episode_pilot",
                return_value={
                    "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                    "final_mp4_sha256": "c" * 64,
                    "final_mp4_bytes": 1234,
                }) as mux, patch(
                "kidsstudio.first_colors_episode._verify_final_audio_beats") as verify:
            result = run_first_colors_episode(
                output_root=str(self.private), voice_mode="supplied_wav",
                narration_root=str(self.audio_root),
                narration_name=self.audio.name,
                narration_sha256=digest, execute=True)
        self.assertEqual(result["status"],
                         "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED")
        render.assert_called_once()
        mux.assert_called_once()
        verify.assert_called_once()

    def test_final_audio_gate_failure_prevents_episode_success(self):
        write_wav(self.audio, amplitude=5000)
        digest = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        def fake_visual(stage):
            target = stage / "silent.mp4"
            target.write_bytes(b"synthetic video")
            target.chmod(0o600)
            return target
        with patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=fake_visual), patch(
                "kidsstudio.first_colors_episode.mux_episode_pilot",
                return_value={
                    "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                    "final_mp4_sha256": "c" * 64,
                    "final_mp4_bytes": 1234,
                }), patch(
                "kidsstudio.first_colors_episode._verify_final_audio_beats",
                side_effect=EpisodeMuxError("Final MP4 audio is missing energy")):
            with self.assertRaisesRegex(EpisodeMuxError, "Final MP4 audio"):
                run_first_colors_episode(
                    output_root=str(self.private), voice_mode="supplied_wav",
                    narration_root=str(self.audio_root),
                    narration_name=self.audio.name,
                    narration_sha256=digest, execute=True)

    def test_final_aac_decode_must_preserve_energy_in_each_beat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            movie = root / "episode.mp4"
            movie.write_bytes(b"synthetic final AAC container")
            movie.chmod(0o600)
            stage = root / "stage"
            stage.mkdir(mode=0o700)

            def decode_with_audio(command, **kwargs):
                # Model the bytes FFmpeg decodes from the final AAC stream.
                write_wav(Path(command[-1]), amplitude=5000)
                return subprocess.CompletedProcess(command, 0)

            with patch("kidsstudio.first_colors_episode._run",
                       side_effect=decode_with_audio):
                _verify_final_audio_beats(movie=movie, stage=stage)

            def decode_with_missing_beat(command, **kwargs):
                write_wav(Path(command[-1]), amplitude=5000, silent_beats=(3,))
                return subprocess.CompletedProcess(command, 0)

            failed_stage = root / "failed-stage"
            failed_stage.mkdir(mode=0o700)
            with patch("kidsstudio.first_colors_episode._run",
                       side_effect=decode_with_missing_beat):
                with self.assertRaisesRegex(EpisodeMuxError, "Final MP4 audio"):
                    _verify_final_audio_beats(movie=movie, stage=failed_stage)

    def test_retry_after_render_failure_uses_fresh_private_stage(self):
        write_wav(self.audio, amplitude=5000)
        digest = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        attempts = {"count": 0}

        def fail_then_render(stage):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise EpisodeMuxError("synthetic interruption during render")
            target = stage / "silent.mp4"
            target.write_bytes(b"synthetic video")
            target.chmod(0o600)
            return target

        with patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=fail_then_render), patch(
                "kidsstudio.first_colors_episode.mux_episode_pilot",
                return_value={
                    "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                    "final_mp4_sha256": "d" * 64,
                    "final_mp4_bytes": 1234,
                }), patch(
                "kidsstudio.first_colors_episode._verify_final_audio_beats") as verify:
            with self.assertRaisesRegex(EpisodeMuxError, "interruption"):
                run_first_colors_episode(
                    output_root=str(self.private), output_name="retry_after_render.mp4",
                    voice_mode="supplied_wav", narration_root=str(self.audio_root),
                    narration_name=self.audio.name, narration_sha256=digest, execute=True)
            resumed = run_first_colors_episode(
                output_root=str(self.private), output_name="retry_after_render.mp4",
                voice_mode="supplied_wav", narration_root=str(self.audio_root),
                narration_name=self.audio.name, narration_sha256=digest, execute=True)

        self.assertEqual(resumed["status"], "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED")
        self.assertEqual(attempts["count"], 2)
        verify.assert_called_once()
        stages = list(self.private.glob("retry_after_render-pilot-sources*"))
        self.assertEqual(len(stages), 2)
        self.assertTrue(all(stage.is_dir() and stage.stat().st_mode & 0o077 == 0
                            for stage in stages))

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
                   }) as mux, patch(
                   "kidsstudio.first_colors_episode._verify_final_audio_beats") as verify:
            result = run_first_colors_episode(
                output_root=str(self.private), execute=True)
        self.assertEqual(result["status"], "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED")
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertFalse(result["pi_transfer_performed"])
        self.assertFalse(result["voice_pronunciation_reviewed"])
        self.assertEqual(result["final_mp4_sha256"], "b" * 64)
        self.assertTrue(mux.call_args.kwargs["execute"])
        verify.assert_called_once()
        stage = next(self.private.glob("colors_ar_01-pilot-sources-*"))
        self.assertEqual(mux.call_args.kwargs["narration_sha256"], hashlib.sha256(
            (stage / "arabic_voice.wav").read_bytes()).hexdigest())

    def test_native_voice_is_verified_before_any_visual_encode(self):
        order = []
        def synthetic_voice(stage, *, voice):
            order.append("voice")
            target = stage / "arabic_voice.wav"
            write_wav(target)
            return target

        def synthetic_visual(stage):
            order.append("video")
            self.assertTrue((stage / "arabic_voice.wav").exists())
            target = stage / "silent.mp4"
            target.write_bytes(b"synthetic placeholder")
            target.chmod(0o600)
            return target

        with patch("kidsstudio.first_colors_episode._arabic_voice",
                   return_value="Maged"), \
             patch("kidsstudio.first_colors_episode._synthesize_wav",
                   side_effect=synthetic_voice), \
             patch("kidsstudio.first_colors_episode._render_silent",
                   side_effect=synthetic_visual), \
             patch("kidsstudio.first_colors_episode.mux_episode_pilot",
                   return_value={
                       "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                       "final_mp4_sha256": "b" * 64,
                       "final_mp4_bytes": 2400,
                   }), patch(
                   "kidsstudio.first_colors_episode._verify_final_audio_beats") as verify:
            result = run_first_colors_episode(
                output_root=str(self.private), execute=True)
        self.assertEqual(order, ["voice", "video"])
        self.assertTrue(result["render_executed"])
        self.assertFalse(result["publication_approved"])
        verify.assert_called_once()

    def test_missing_or_incomplete_native_voice_skips_visual_encode(self):
        for reason in ("silent cue", "beat too long", "cannot synthesize"):
            with self.subTest(reason=reason), patch(
                "kidsstudio.first_colors_episode._arabic_voice",
                return_value="Maged"), patch(
                "kidsstudio.first_colors_episode._synthesize_wav",
                side_effect=EpisodeMuxError(reason)), patch(
                "kidsstudio.first_colors_episode._render_silent"
            ) as render, patch(
                "kidsstudio.first_colors_episode.mux_episode_pilot"
            ) as mux:
                with self.assertRaises(EpisodeMuxError):
                    run_first_colors_episode(
                        output_root=str(self.private),
                        output_name=f"native_fails_{reason.replace(' ', '_')}.mp4",
                        execute=True)
                render.assert_not_called()
                mux.assert_not_called()

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
