"""Offline text comparison for independently transcribed narration.

This module does not run Whisper or approve publication. A transcription
adapter must supply the recognized text; uncertain results remain flagged.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> list[str]:
    if not isinstance(text, str):
        raise TypeError("Expected transcript text")
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}))
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


def edit_distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class TranscriptReport:
    status: str
    word_error_rate: float
    reference_words: int
    recognized_words: int


def compare_transcript(script: str, recognized: str, *, max_wer: float = 0.08) -> TranscriptReport:
    if not 0 <= max_wer <= 1:
        raise ValueError("max_wer must be between 0 and 1")
    reference, hypothesis = normalize(script), normalize(recognized)
    if not reference:
        return TranscriptReport("REVIEW_REQUIRED_EMPTY_SCRIPT", 1.0, 0, len(hypothesis))
    if not hypothesis:
        return TranscriptReport("REVIEW_REQUIRED_EMPTY_TRANSCRIPT", 1.0, len(reference), 0)
    wer = edit_distance(reference, hypothesis) / len(reference)
    return TranscriptReport("TEXT_MATCH_CANDIDATE" if wer <= max_wer else "REVIEW_REQUIRED_MISMATCH",
                            round(wer, 6), len(reference), len(hypothesis))
