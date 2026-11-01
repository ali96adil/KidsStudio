import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.whisper_adapter import WhisperAdapterError, review_wav


class WhisperAdapterTests(unittest.TestCase):
    def test_rejects_missing_audio_without_process(self):
        with patch("kidsstudio.whisper_adapter.subprocess.run") as run:
            with self.assertRaises(WhisperAdapterError):
                review_wav("/does/not/exist.wav", "hello")
            run.assert_not_called()

    def test_rejects_unsupported_language(self):
        with tempfile.TemporaryDirectory() as d:
            audio = Path(d) / "voice.wav"
            audio.write_bytes(b"RIFF")
            with self.assertRaises(WhisperAdapterError):
                review_wav(audio, "hello", language="fr")

    def test_transcript_is_compared_but_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            audio = Path(d) / "voice.wav"
            audio.write_bytes(b"RIFF")
            def fake_run(command, **kwargs):
                output = Path(command[command.index("--output_dir") + 1])
                (output / "voice.json").write_text(json.dumps({"text": "هذا لون احمر"}), encoding="utf-8")
            with patch("kidsstudio.whisper_adapter.subprocess.run", side_effect=fake_run):
                result = review_wav(audio, "هذا لون أحمر")
            self.assertEqual(result["status"], "TEXT_MATCH_CANDIDATE")
            self.assertFalse(result["publication_approved"])

    def test_silent_transcript_requires_review(self):
        with tempfile.TemporaryDirectory() as d:
            audio = Path(d) / "voice.wav"
            audio.write_bytes(b"RIFF")
            def fake_run(command, **kwargs):
                output = Path(command[command.index("--output_dir") + 1])
                (output / "voice.json").write_text(json.dumps({"text": ""}), encoding="utf-8")
            with patch("kidsstudio.whisper_adapter.subprocess.run", side_effect=fake_run):
                result = review_wav(audio, "مرحبا")
            self.assertEqual(result["status"], "REVIEW_REQUIRED_EMPTY_TRANSCRIPT")
