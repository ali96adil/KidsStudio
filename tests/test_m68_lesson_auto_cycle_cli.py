"""CLI tests: safe failure before model execution."""
import contextlib
import io
import json
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_lesson_auto_cycle_cli import main


class LessonAutoCycleCliTests(unittest.TestCase):
    def test_missing_handoff_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "--handoff", str(Path(directory) / "missing.json"),
                    "--script", str(Path(directory) / "script.txt"),
                    "--lesson-plan", str(Path(directory) / "lesson.json"),
                    "--output-dir", directory,
                    "--first-endpoint", "http://127.0.0.1:11434/api/chat",
                    "--first-model", "review-one",
                    "--second-endpoint", "http://127.0.0.1:11435/api/chat",
                    "--second-model", "review-two",
                    "--rewriter-endpoint", "http://127.0.0.1:11434/api/chat",
                    "--rewriter-model", "writer"])
            self.assertEqual(code, 2)
            self.assertIn("LESSON_AUTO_CYCLE_FAILED", output.getvalue())
            self.assertIn('"public_release_authorized": false', output.getvalue())

    def test_missing_models_block_before_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory) / "handoff.json"
            handoff.write_text(json.dumps({"source_episode_id": "e"}))
            args = [
                "--handoff", str(handoff),
                "--script", str(Path(directory) / "script.txt"),
                "--lesson-plan", str(Path(directory) / "lesson.json"),
                "--output-dir", directory,
                "--first-endpoint", "http://127.0.0.1:11434/api/chat",
                "--first-model", "review-one",
                "--second-endpoint", "http://127.0.0.1:11434/api/chat",
                "--second-model", "review-two",
                "--rewriter-endpoint", "http://127.0.0.1:11434/api/chat",
                "--rewriter-model", "writer"]
            with patch("kidsstudio.m68_lesson_auto_cycle_cli.qualify",
                       return_value={"ready_for_inference_attempt": False}), \
                 patch("kidsstudio.m68_lesson_auto_cycle_cli.run_cycle") as run:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(args)
                self.assertEqual(code, 2)
                self.assertIn("LESSON_AUTO_CYCLE_BLOCKED_MODELS_NOT_READY",
                              output.getvalue())
                run.assert_not_called()
