"""Explicit local Whisper CLI adapter for narration quality checks.

No model download, no network API and no automatic publication approval.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .transcript_qa import compare_transcript


class WhisperAdapterError(RuntimeError):
    pass


def review_wav(
    wav: str | Path,
    approved_script: str,
    *,
    executable: str = "whisper",
    language: str = "ar",
    model: str = "base",
    timeout: int = 600,
) -> dict:
    audio = Path(wav).expanduser().resolve()
    if not audio.is_file() or audio.suffix.lower() != ".wav":
        raise WhisperAdapterError("A local WAV file is required")
    if language not in ("ar", "en"):
        raise WhisperAdapterError("Only Arabic and English are approved")
    if not model or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./" for c in model):
        raise WhisperAdapterError("Invalid local model selector")
    if timeout < 1 or timeout > 3600:
        raise WhisperAdapterError("Invalid timeout")
    with tempfile.TemporaryDirectory(prefix="kidsstudio-whisper-") as output:
        command = [
            executable, str(audio), "--language", language, "--model", model,
            "--task", "transcribe", "--output_format", "json",
            "--output_dir", output, "--verbose", "False",
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True,
                           timeout=timeout)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise WhisperAdapterError("Local transcription failed") from exc
        transcript_file = Path(output) / (audio.stem + ".json")
        if not transcript_file.is_file():
            raise WhisperAdapterError("Whisper transcript was not created")
        if transcript_file.stat().st_size > 5_000_000:
            raise WhisperAdapterError("Whisper transcript is too large")
        try:
            transcript = json.loads(transcript_file.read_text(encoding="utf-8"))["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WhisperAdapterError("Invalid Whisper JSON output") from exc
        if not isinstance(transcript, str):
            raise WhisperAdapterError("Whisper text must be a string")
    report = compare_transcript(approved_script, transcript)
    return {
        "status": report.status,
        "word_error_rate": report.word_error_rate,
        "reference_words": report.reference_words,
        "recognized_words": report.recognized_words,
        "transcript": transcript,
        "publication_approved": False,
    }
