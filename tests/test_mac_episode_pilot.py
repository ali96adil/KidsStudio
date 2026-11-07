from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from kidsstudio.mac_episode_pilot import run_mac_episode_pilot, main
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
            handle.writeframes(b"\0\0" * 4 * 16000)
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
        fake_final = {
            "status": "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED",
            "final_mp4_sha256": "b" * 64,
            "final_mp4_bytes": 1050,
        }
        with patch("kidsstudio.mac_episode_pilot.render_godot_project",
                   return_value=fake_native) as renderer, \
             patch("kidsstudio.mac_episode_pilot.mux_episode_pilot",
                   return_value=fake_final) as mux:
            result = run_mac_episode_pilot(**self.params(execute=True))
        self.assertEqual(result["status"], "MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED")
        self.assertEqual(result["final_mp4_sha256"], "b" * 64)
        self.assertTrue(result["narration_mixed"])
        self.assertFalse(result["publication_approved"])
        renderer.assert_called_once()
        mux.assert_called_once()
        self.assertTrue(mux.call_args.kwargs["execute"])
        self.assertEqual(mux.call_args.kwargs["video_sha256"], "a" * 64)
        self.assertEqual(mux.call_args.kwargs["narration_sha256"], self.digest)

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
