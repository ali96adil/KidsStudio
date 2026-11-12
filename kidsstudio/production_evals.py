"""Deterministic, read-only evaluation of synthetic editorial candidates.

No network, paid inference, queue mutation or media publication.
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class EvalResult:
    passed: bool
    score: float
    checks: dict[str, bool]
    sha256: str

    def as_dict(self) -> dict:
        return {"passed": self.passed, "score": self.score,
                "checks": self.checks, "sha256": self.sha256}


def evaluate_script(text: str, *, language: str, required_terms: tuple[str, ...] = (),
                    min_chars: int = 40, max_chars: int = 6000) -> EvalResult:
    """Mechanical checks only; does NOT certify language, education or child safety.

    ``language_script`` is a conservative Unicode script-dominance heuristic,
    not language identification: it catches a candidate dominated by the
    opposite Arabic/Latin script but cannot validate grammar or meaning.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if language not in ("ar", "en"):
        raise ValueError("language must be ar or en")
    if not (0 < min_chars <= max_chars):
        raise ValueError("invalid length bounds")
    if not isinstance(required_terms, tuple) or not all(
        isinstance(term, str) and term.strip() for term in required_terms
    ):
        raise ValueError("required_terms must contain nonempty strings")
    normalized = text.strip()
    def fold(value: str) -> str:
        return unicodedata.normalize('NFKC', value).casefold()
    script_letters = [
        unicodedata.name(char, "")
        for char in unicodedata.normalize("NFKC", normalized)
        if char.isalpha()
    ]
    target_prefix = "ARABIC LETTER" if language == "ar" else "LATIN "
    target_letters = sum(name.startswith(target_prefix) for name in script_letters)
    other_letters = len(script_letters) - target_letters
    checks = {
        "length": min_chars <= len(normalized) <= max_chars,
        "language_script": target_letters > other_letters,
        "required_terms": all(fold(term) in fold(normalized) for term in required_terms),
        "nonempty_lines": bool(normalized) and all(line.strip() for line in normalized.splitlines()),
    }
    score = sum(checks.values()) / len(checks)
    return EvalResult(all(checks.values()), score, checks,
                      hashlib.sha256(text.encode("utf-8")).hexdigest())


def aggregate_runs(results: list[EvalResult]) -> dict:
    """Summarize repeatability; caller chooses sample size and independent review."""
    if not results:
        raise ValueError("at least one result required")
    passes = sum(result.passed for result in results)
    return {"runs": len(results), "passes": passes,
            "pass_rate": passes / len(results),
            "mean_score": sum(result.score for result in results) / len(results)}


def evaluate_fixture(payload: Mapping) -> dict:
    """Evaluate one caller-provided fixture; never reads production artifacts."""
    result = evaluate_script(
        payload["text"], language=payload["language"],
        required_terms=tuple(payload.get("required_terms", ())),
        min_chars=payload.get("min_chars", 40),
        max_chars=payload.get("max_chars", 6000),
    )
    return result.as_dict()
