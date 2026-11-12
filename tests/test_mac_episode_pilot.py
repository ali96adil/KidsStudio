from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.mac_episode_pilot import (
    _verify_final_audio_beats, run_mac_episode_pilot, main,
)
from kidsstudio.mac_episode_audio import EpisodeMuxError


class MacEpisodePilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.project = base / "export"
        self.private = base / "private"
        self.out = base / "final"
        self.project.mkdir(mode=0o700)
        self.private.mkdir(mode=0o700)
        self.out.mkdir(mode=0o700)
        (self.project / "export_report.json").write_text(json.dumps({
            "status": "PREVIEW_ONLY_UNAPPROVED",
        }))
        (self.project / "scene_spec.json").write_text(json.dumps({
            "schema_version": 1, "fps": 24, "duration_seconds": 4,
            "beats": [{"start": 0, "end": 4, "motion": "wave_right"}],
        }))
        self.wav = self.private / "narration.wav"
        with wave.open(str(self.wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes((5000).to_bytes(2, "little", signed=True) * 4 * 16000)
        self.wav.chmod(0o600)
        self.digest = hashlib.sha256(self.wav.read_bytes()).hexdigest()

    def params(self, **updates):
        args = {
            "godot_project": str(self.project),
            "narration_root": str(self.private),
            "narration_name": "narration.wav",
            "narration_sha256": self.digest,
            "output_root": str(self.out),
        }
        args.update(updates)
        return args

    def test_default_preview_creates_no_files_or_renders(self):
        with patch("kidsstudio.mac_episode_pilot.render_godot_project") as render:
            result = run_mac_episode_pilot(**self.params())
        self.assertEqual(result["status"], "MAC_PILOT_READY_TO_RENDER")
        self.assertFalse(result["render_executed"])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertFalse(result["youtube_upload_performed"])
        render.assert_not_called()

    def test_explicit_one_command_calls_real_pipeline_adapters(self):
        fake_native = {
            "status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "mp4_sha256": "a" * 64,
        }
        def fake_renderer(_project, render_dir):
            render_dir.mkdir(mode=0o700)
            return fake_native

        def fake_mux(**kwargs):
            candidate = Path(kwargs["output_root"]) / kwargs["output_name"]
            candidate.write_bytes(b"synthetic candidate")
            candidate.chmod(0o600)
            return {
                "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                "final_mp4_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "final_mp4_bytes": candidate.stat().st_size,
            }

        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   side_effect=fake_renderer) as renderer, \
             patch("kidsstudio.mac_episode_pilot.mux_episode_pilot",
                   side_effect=fake_mux) as mux, \
             patch("kidsstudio.mac_episode_pilot._verify_final_audio_beats") as verify:
            result = run_mac_episode_pilot(**self.params(execute=True))
        self.assertEqual(result["status"], "MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED")
        self.assertTrue(result["narration_mixed"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(result["final_mp4_sha256"], hashlib.sha256(
            (self.out / "colors_ar_01.mp4").read_bytes()).hexdigest())
        renderer.assert_called_once()
        mux.assert_called_once()
        self.assertTrue(mux.call_args.kwargs["execute"])
        self.assertEqual(mux.call_args.kwargs["video_sha256"], "a" * 64)
        self.assertEqual(mux.call_args.kwargs["narration_sha256"], self.digest)
        self.assertEqual(mux.call_args.kwargs["output_root"], str(
            self.out / "colors_ar_01-godot-render"))
        self.assertEqual(mux.call_args.kwargs["output_name"], "verified-candidate.mp4")
        verify.assert_called_once_with(
            movie=self.out / "colors_ar_01-godot-render" / "verified-candidate.mp4",
            stage=self.out / "colors_ar_01-godot-render", beat_durations=[4])

    def test_failed_post_mux_aac_gate_does_not_publish_final_name(self):
        fake_native = {
            "status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "mp4_sha256": "a" * 64,
        }

        def fake_renderer(_project, render_dir):
            render_dir.mkdir(mode=0o700)
            return fake_native

        def fake_mux(**kwargs):
            candidate = Path(kwargs["output_root"]) / kwargs["output_name"]
            candidate.write_bytes(b"muxed synthetic candidate")
            candidate.chmod(0o600)
            return {
                "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                "final_mp4_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "final_mp4_bytes": candidate.stat().st_size,
            }

        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   side_effect=fake_renderer), patch(
                "kidsstudio.mac_episode_pilot.mux_episode_pilot",
                side_effect=fake_mux), patch(
                "kidsstudio.mac_episode_pilot._verify_final_audio_beats",
                side_effect=EpisodeMuxError("Final AAC beat is silent"),
                create=True):
            with self.assertRaisesRegex(EpisodeMuxError, "Final AAC"):
                run_mac_episode_pilot(**self.params(execute=True))

        self.assertFalse((self.out / "colors_ar_01.mp4").exists())

    def test_verified_candidate_is_promoted_without_overwrite(self):
        fake_native = {
            "status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "mp4_sha256": "a" * 64,
        }

        def fake_renderer(_project, render_dir):
            render_dir.mkdir(mode=0o700)
            return fake_native

        def fake_mux(**kwargs):
            candidate = Path(kwargs["output_root"]) / kwargs["output_name"]
            candidate.write_bytes(b"verified synthetic candidate")
            candidate.chmod(0o600)
            return {
                "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                "final_mp4_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "final_mp4_bytes": candidate.stat().st_size,
            }

        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   side_effect=fake_renderer), patch(
                "kidsstudio.mac_episode_pilot.mux_episode_pilot",
                side_effect=fake_mux), patch(
                "kidsstudio.mac_episode_pilot._verify_final_audio_beats",
                create=True) as verify:
            result = run_mac_episode_pilot(**self.params(execute=True))

        final = self.out / "colors_ar_01.mp4"
        candidate = self.out / "colors_ar_01-godot-render" / "verified-candidate.mp4"
        self.assertEqual(result["status"], "MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED")
        self.assertTrue(final.is_file())
        self.assertEqual(final.stat().st_mode & 0o777, 0o600)
        self.assertEqual(final.read_bytes(), candidate.read_bytes())
        self.assertEqual(result["final_mp4_sha256"], hashlib.sha256(final.read_bytes()).hexdigest())
        self.assertEqual(result["final_mp4_bytes"], final.stat().st_size)
        verify.assert_called_once()

    def test_final_aac_energy_gate_checks_each_scene_beat(self):
        def decode_with(samples_by_beat):
            def fake_ffmpeg(command, **_kwargs):
                target = Path(command[-1])
                with wave.open(str(target), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(16000)
                    for samples in samples_by_beat:
                        handle.writeframes(samples)
                return subprocess.CompletedProcess(command, 0, b"", b"")
            return fake_ffmpeg

        active = (2000).to_bytes(2, "little", signed=True) * 16000
        silent = b"\0\0" * 16000
        with patch("kidsstudio.mac_episode_pilot.subprocess.run",
                   side_effect=decode_with([active, active])):
            _verify_final_audio_beats(
                movie=self.wav, stage=self.out, beat_durations=[1, 1])

        for decoded in self.out.iterdir():
            decoded.unlink()
        with patch("kidsstudio.mac_episode_pilot.subprocess.run",
                   side_effect=decode_with([active, silent])):
            with self.assertRaisesRegex(EpisodeMuxError, "story beat"):
                _verify_final_audio_beats(
                    movie=self.wav, stage=self.out, beat_durations=[1, 1])

    def test_final_publish_race_preserves_existing_file(self):
        fake_native = {
            "status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "mp4_sha256": "a" * 64,
        }

        def fake_renderer(_project, render_dir):
            render_dir.mkdir(mode=0o700)
            return fake_native

        def fake_mux(**kwargs):
            candidate = Path(kwargs["output_root"]) / kwargs["output_name"]
            candidate.write_bytes(b"candidate")
            candidate.chmod(0o600)
            return {
                "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
                "final_mp4_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "final_mp4_bytes": candidate.stat().st_size,
            }

        final = self.out / "colors_ar_01.mp4"

        def race_create_final(**_kwargs):
            final.write_bytes(b"another completed private result")
            final.chmod(0o600)

        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   side_effect=fake_renderer), patch(
                "kidsstudio.mac_episode_pilot.mux_episode_pilot",
                side_effect=fake_mux), patch(
                "kidsstudio.mac_episode_pilot._verify_final_audio_beats",
                side_effect=race_create_final):
            with self.assertRaises(FileExistsError):
                run_mac_episode_pilot(**self.params(execute=True))

        self.assertEqual(final.read_bytes(), b"another completed private result")

    def test_silent_narration_is_rejected_before_godot_render(self):
        with wave.open(str(self.wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\0\0" * 4 * 16000)
        self.digest = hashlib.sha256(self.wav.read_bytes()).hexdigest()
        with patch("kidsstudio.mac_episode_pilot.render_godot_project") as render, \
             patch("kidsstudio.mac_episode_pilot.mux_episode_pilot") as mux:
            with self.assertRaises(EpisodeMuxError):
                run_mac_episode_pilot(**self.params(execute=True))
        render.assert_not_called()
        mux.assert_not_called()

    def test_silent_scene_beat_is_rejected_before_godot_render(self):
        (self.project / "scene_spec.json").write_text(json.dumps({
            "schema_version": 1, "fps": 24, "duration_seconds": 4,
            "beats": [
                {"start": 0, "end": 2, "motion": "wave_right"},
                {"start": 2, "end": 4, "motion": "wave_right"},
            ],
        }))
        with wave.open(str(self.wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            active = (1000).to_bytes(2, "little", signed=True) * 1600
            handle.writeframes(active + b"\0\0" * (16000 * 2 - 1600)
                               + b"\0\0" * (16000 * 2))
        self.digest = hashlib.sha256(self.wav.read_bytes()).hexdigest()
        with patch("kidsstudio.mac_episode_pilot.render_godot_project") as render:
            with self.assertRaises(EpisodeMuxError):
                run_mac_episode_pilot(**self.params(execute=True))
        render.assert_not_called()

    def test_mismatched_narration_blocks_before_render(self):
        with patch("kidsstudio.mac_episode_pilot.render_godot_project") as render:
            with self.assertRaises(EpisodeMuxError):
                run_mac_episode_pilot(**self.params(narration_sha256="0" * 64, execute=True))
        render.assert_not_called()

    def test_unapproved_export_status_blocks(self):
        (self.project / "export_report.json").write_text(json.dumps({
            "status": "UNKNOWN_EXTERNAL_PROJECT"}))
        with self.assertRaises(EpisodeMuxError):
            run_mac_episode_pilot(**self.params())

    def test_scene_audio_timing_mismatch_blocks(self):
        scene = json.loads((self.project / "scene_spec.json").read_text())
        scene["duration_seconds"] = 6
        scene["beats"][0]["end"] = 6
        (self.project / "scene_spec.json").write_text(json.dumps(scene))
        with self.assertRaises(EpisodeMuxError):
            run_mac_episode_pilot(**self.params())

    def test_existing_output_blocks_without_overwrite(self):
        file = self.out / "colors_ar_01.mp4"
        file.write_bytes(b"trusted content")
        with self.assertRaises(FileExistsError):
            run_mac_episode_pilot(**self.params(execute=True))
        self.assertEqual(file.read_bytes(), b"trusted content")

    def test_existing_render_staging_blocks(self):
        (self.out / "colors_ar_01-godot-render").mkdir()
        with self.assertRaises(FileExistsError):
            run_mac_episode_pilot(**self.params(execute=True))

    def test_public_output_root_rejected(self):
        self.out.chmod(0o755)
        with self.assertRaises(EpisodeMuxError):
            run_mac_episode_pilot(**self.params())

    def test_invalid_name_rejected(self):
        with self.assertRaises(EpisodeMuxError):
            run_mac_episode_pilot(**self.params(output_name="../other.mp4"))

    def test_render_error_does_not_call_mux(self):
        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   side_effect=RuntimeError("render failed")), \
             patch("kidsstudio.mac_episode_pilot.mux_episode_pilot") as mux:
            with self.assertRaises(RuntimeError):
                run_mac_episode_pilot(**self.params(execute=True))
        mux.assert_not_called()

    def test_cli_preview_no_output_file(self):
        args = [
            "--godot-project", str(self.project),
            "--narration-root", str(self.private),
            "--narration-name", "narration.wav",
            "--narration-sha256", self.digest,
            "--output-root", str(self.out),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "MAC_PILOT_READY_TO_RENDER")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_cli_failure_redacts_paths(self):
        output = io.StringIO()
        args = [
            "--godot-project", str(self.project),
            "--narration-root", str(self.private),
            "--narration-name", "narration.wav",
            "--narration-sha256", "0" * 64,
            "--output-root", str(self.out),
            "--execute-render",
        ]
        with contextlib.redirect_stdout(output):
            code = main(args)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "MAC_PILOT_BLOCKED_OR_UNVERIFIED")
        self.assertNotIn(str(self.private), output.getvalue())


if __name__ == "__main__":
    unittest.main()
