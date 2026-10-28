"""M18: actual final M7 verification of a real, synthetic TWO-scene master.

Uses real subprocess FFmpeg and FFprobe on disposable Linux CI. Every frame
and PCM sample is generated locally from test patterns. No model, voice,
private artwork, AI inference, network access, or publication is used.
"""
from __future__ import annotations

from array import array
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from kidsstudio.episode_assembly import EpisodeAssembler, EpisodeAssemblyError
from kidsstudio.episode_quality import CHECKS, inspect_video


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class RealFinalQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kidsstudio-m18-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.assertIsNotNone(self.ffmpeg, "M18 requires actual ffmpeg in CI.")
        self.assertIsNotNone(self.ffprobe, "M18 requires actual ffprobe in CI.")
        self.script = self.root / "approved_original_script.txt"
        self.script.write_text("Synthetic test only: the ball changes colors.\n",
                               encoding="utf-8")
        self.face_v06 = self.root / "v06.py"
        self.face_v07 = self.root / "v07.py"
        self.face_v06.write_text("# Not invoked: no face cleanup.\n")
        self.face_v07.write_text("# Not invoked: no face cleanup.\n")

    def _make_scene(self, name: str, color: str, pitch: int) -> Path:
        path = self.root / (name + ".mp4")
        subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
            "-f", "lavfi", "-i", "color=c=" + color + ":s=384x384:r=24:d=1.5",
            "-f", "lavfi", "-i",
            "sine=frequency=" + str(pitch) + ":sample_rate=48000:duration=1.5",
            "-map", "0:v:0", "-map", "1:a:0", "-t", "1.5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
            str(path),
        ], check=True, capture_output=True, timeout=60)
        return path

    def _assemble(self) -> tuple[Path, str, tuple[str, str]]:
        red = self._make_scene("scene_01_red", "red", 440)
        blue = self._make_scene("scene_02_blue", "blue", 880)
        before = (file_sha(red), file_sha(blue))
        recipe = {
            "schema_version": 1,
            "series_id": "colors-ar",
            "episode_number": 1,
            "private_root": str(self.root),
            "output_root": str(self.root / "outputs"),
            "script": {"path": str(self.script), "sha256": file_sha(self.script)},
            "voice_rights": "INTERNAL_TEST_ONLY",
            "tools": {
                "ffmpeg": self.ffmpeg, "ffprobe": self.ffprobe,
                "face_python": sys.executable,
                "face_v06": str(self.face_v06),
                "face_v06_sha256": file_sha(self.face_v06),
                "face_v07": str(self.face_v07),
                "face_v07_sha256": file_sha(self.face_v07),
            },
            "clips": [
                {"video": str(red), "sha256": before[0], "face_cleanup": "none"},
                {"video": str(blue), "sha256": before[1], "face_cleanup": "none"},
            ],
        }
        recipe_path = self.root / "episode_recipe.json"
        recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
        assembler = EpisodeAssembler(recipe_path)
        self.assertEqual(assembler.preflight()["status"], "READY_FOR_LOCAL_ASSEMBLY")
        output = assembler.execute(run_id="m18-full-gate")
        self.assertEqual(output["status"], "RENDERED_PENDING_HUMAN_AV_QA")
        self.assertEqual(output["clips_built"], 2)
        self.assertIs(output["publication_approved"], False)
        self.assertEqual((file_sha(red), file_sha(blue)), before,
                         "Assembler must not mutate original scenes.")
        master = Path(output["final_media_path"])
        return master, output["final_media_sha256"], before

    def _pitch_hz(self, video: Path, start: float) -> float:
        # Decode a known section of the assembled audio to real signed PCM.
        # Counting rising zero crossings verifies content at two positions,
        # rather than merely checking that an AAC stream exists.
        duration = 0.40
        raw = subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", str(start), "-i", str(video), "-t", str(duration),
            "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "s16le", "-",
        ], check=True, capture_output=True, timeout=60).stdout
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        self.assertGreater(len(values), 14000, "Audio excerpt missing.")
        self.assertGreater(max(values) - min(values), 400,
                           "Audio should not be silent.")
        crossings = sum(a <= 0 < b for a, b in zip(values, values[1:]))
        return crossings * 48000 / len(values)

    def test_real_final_m7_full_decode_and_two_distinct_audio_scenes(self):
        master, current_sha, _ = self._assemble()
        result = inspect_video(master, current_sha, ffprobe=self.ffprobe,
                               ffmpeg=self.ffmpeg)
        self.assertEqual(result["status"], "TECH_PASS_OWNER_REVIEW_PENDING")
        self.assertEqual(set(result["checks"]), set(CHECKS))
        self.assertTrue(all(result["checks"].values()),
                        "M7 must decode the complete final MP4, not a fake stub.")
        self.assertIs(result["subjective_checks_performed"], False)
        self.assertIs(result["rights_verified"], False)
        self.assertIs(result["publishing_approved"], False)
        self.assertAlmostEqual(result["duration_seconds"], 3.0, delta=0.6)
        self.assertAlmostEqual(self._pitch_hz(master, 0.30), 440, delta=20)
        self.assertAlmostEqual(self._pitch_hz(master, 1.85), 880, delta=25)
        # A different queue receipt must fail even for a valid MP4.
        wrong = inspect_video(master, "f" * 64 if current_sha != "f" * 64
                              else "e" * 64, ffprobe=self.ffprobe,
                              ffmpeg=self.ffmpeg)
        self.assertEqual(wrong["status"], "TECH_FAILED")
        self.assertFalse(wrong["checks"]["media_sha256_matches"])
        self.assertFalse(wrong["checks"]["full_decode_success"],
                         "M7 must not decode a file with a mismatched receipt.")

    def test_modified_scene_blocked_before_output_creation(self):
        clip = self._make_scene("scene_01_red", "red", 440)
        second = self._make_scene("scene_02_blue", "blue", 880)
        recipe = {
            "schema_version": 1, "series_id": "colors-ar", "episode_number": 1,
            "private_root": str(self.root), "output_root": str(self.root / "outputs"),
            "script": {"path": str(self.script), "sha256": file_sha(self.script)},
            "voice_rights": "INTERNAL_TEST_ONLY",
            "tools": {"ffmpeg": self.ffmpeg, "ffprobe": self.ffprobe,
                      "face_python": sys.executable,
                      "face_v06": str(self.face_v06),
                      "face_v06_sha256": file_sha(self.face_v06),
                      "face_v07": str(self.face_v07),
                      "face_v07_sha256": file_sha(self.face_v07)},
            "clips": [{"video": str(p), "sha256": file_sha(p),
                       "face_cleanup": "none"} for p in (clip, second)],
        }
        file = self.root / "episode_recipe.json"
        file.write_text(json.dumps(recipe), encoding="utf-8")
        engine = EpisodeAssembler(file)
        second.write_bytes(second.read_bytes() + b"modified-after-approval")
        with self.assertRaises(EpisodeAssemblyError):
            engine.preflight()
        self.assertFalse((self.root / "outputs").exists())


if __name__ == "__main__":
    unittest.main()
