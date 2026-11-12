"""Offline, read-only OmniRoute candidate comparison.

Uses operator-supplied text, counters, timing and rate assumptions. No requests
to OmniRoute; no claim of verified model identity, actual billing or child safety.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from .omniroute_profile import _model_info
from .production_evals import evaluate_script

MAX_FIXTURE_BYTES = 128_000
MAX_CANDIDATES = 12


class OmniRouteBenchmarkError(ValueError):
    """Invalid offline comparison fixture or unsafe evidence path."""


def _counter(candidate: dict, key: str) -> int | None:
    value = candidate.get(key)
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 2_000_000:
        raise OmniRouteBenchmarkError("Counters must be bounded nonnegative integers.")
    return value


def _latency(candidate: dict) -> float | None:
    value = candidate.get("latency_ms")
    if value is None:
        return None
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 3_600_000:
        raise OmniRouteBenchmarkError("Latency must be a bounded number.")
    return float(value)


def _rate(candidate: dict, key: str) -> Decimal | None:
    value = candidate.get(key)
    if value is None:
        return None
    if type(value) not in (int, float, str):
        raise OmniRouteBenchmarkError("Pricing must be an explicit finite number.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise OmniRouteBenchmarkError("Invalid operator pricing.") from exc
    if not result.is_finite() or not 0 <= result <= 10_000:
        raise OmniRouteBenchmarkError("Pricing must be nonnegative and bounded.")
    return result


def compare_text_candidates(candidates: list[dict]) -> dict:
    """Evaluate synthetic fixtures without forwarding or returning candidate text."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise OmniRouteBenchmarkError("Expected 1..12 candidate evaluations.")
    outputs = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise OmniRouteBenchmarkError("Candidate must be a dictionary.")
        model = candidate.get("model")
        _model_info(model)
        language = candidate.get("language")
        text = candidate.get("text")
        required = candidate.get("required_terms", [])
        if (not isinstance(text, str) or len(text) > 12000
                or not isinstance(required, list) or len(required) > 12
                or not all(isinstance(t, str) and 0 < len(t) <= 100 for t in required)):
            raise OmniRouteBenchmarkError("Invalid text or required terms.")
        prompt_tokens = _counter(candidate, "prompt_tokens")
        completion_tokens = _counter(candidate, "completion_tokens")
        ms = _latency(candidate)
        input_rate = _rate(candidate, "usd_per_m_input_tokens")
        output_rate = _rate(candidate, "usd_per_m_output_tokens")
        if (input_rate is None) != (output_rate is None):
            raise OmniRouteBenchmarkError("Both rates are required for an estimate.")
        cost = None
        if input_rate is not None:
            if prompt_tokens is None or completion_tokens is None:
                raise OmniRouteBenchmarkError("Token counts are required for cost estimates.")
            cost = float((Decimal(prompt_tokens) * input_rate
                          + Decimal(completion_tokens) * output_rate)
                         / Decimal(1_000_000))
        result = evaluate_script(text, language=language,
                                 required_terms=tuple(required))
        outputs.append({
            "model": model,
            "language": language,
            "text_sha256": result.sha256,
            "mechanical_passed": result.passed,
            "mechanical_score": result.score,
            "mechanical_checks": result.checks,
            "prompt_tokens_reported": prompt_tokens,
            "completion_tokens_reported": completion_tokens,
            "latency_ms_reported": ms,
            "estimated_api_cost_usd": cost,
            "pricing_operator_supplied_not_verified": True,
            "model_identity_not_verified": True,
            "children_content_approved": False,
        })
    return {
        "schema_version": 1,
        "status": "OFFLINE_COMPARISON_UNVERIFIED",
        "candidates": outputs,
        "total_estimated_api_cost_usd": (
            round(sum(item["estimated_api_cost_usd"] for item in outputs), 8)
            if all(item["estimated_api_cost_usd"] is not None for item in outputs)
            else None
        ),
        "inference_requests_performed": 0,
        "no_automatic_model_selection": True,
        "owner_publication_approved": False,
        "real_billing_verified": False,
        "child_safety_verified": False,
    }


def _read_private_fixture(filename: str) -> list[dict]:
    path = Path(os.path.abspath(os.path.expanduser(filename)))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise OmniRouteBenchmarkError("Symlinked fixture path is forbidden.")
    if any((part / ".git").exists() for part in (path.parent, *path.parents)):
        raise OmniRouteBenchmarkError("Fixtures must remain outside Git.")
    parent = path.parent
    if (not parent.is_dir() or parent.stat().st_mode & 0o077
            or (os.name == "posix" and parent.stat().st_uid != os.getuid())):
        raise OmniRouteBenchmarkError("Private 0700 fixture directory required.")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or (os.name == "posix" and info.st_uid != os.getuid())
                or info.st_size > MAX_FIXTURE_BYTES):
            raise OmniRouteBenchmarkError("Unsafe fixture file.")
        data = source.read(MAX_FIXTURE_BYTES + 1)
    if len(data) > MAX_FIXTURE_BYTES:
        raise OmniRouteBenchmarkError("Fixture too large.")
    obj = json.loads(data)
    if not isinstance(obj, dict) or set(obj) != {"candidates"}:
        raise OmniRouteBenchmarkError("Expected a candidates object.")
    return obj["candidates"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline OmniRoute provider comparison")
    parser.add_argument("--private-fixture", required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_text_candidates(_read_private_fixture(args.private_fixture))
    except (ValueError, OSError, UnicodeError, TypeError):
        result = {"status": "OFFLINE_COMPARISON_REJECTED",
                  "inference_requests_performed": 0,
                  "owner_publication_approved": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
