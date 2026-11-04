"""Opt-in, read-only editorial artifact evaluation.

Reads an immutable local worker answer, verifies SHA256 and returns a report.
Never updates the queue, rewrites artifacts, invokes models or publishes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .production_evals import evaluate_script


class EditorialEvalError(ValueError):
    """Invalid artifact provenance or unsafe evaluation request."""


def evaluate_local_artifact(
    *, artifact_root: str | Path, manifest_path: str | Path,
    expected_sha256: str, language: str, required_terms: tuple[str, ...] = (),
    min_chars: int = 40, max_chars: int = 6000,
) -> dict:
    root = Path(artifact_root).expanduser().resolve(strict=True)
    manifest = Path(manifest_path).expanduser().resolve(strict=True)
    if not root.is_dir() or not manifest.is_relative_to(root):
        raise EditorialEvalError("Artifact must be within the private root")
    if manifest.name != "result.json":
        raise EditorialEvalError("Expected a local worker result.json")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise EditorialEvalError("Invalid expected SHA256")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise EditorialEvalError("Invalid expected SHA256") from exc
    if manifest.stat().st_size > 50_000:
        raise EditorialEvalError("Manifest exceeds limit")
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EditorialEvalError("Invalid manifest encoding or JSON") from exc
    if not isinstance(metadata, dict):
        raise EditorialEvalError("Manifest must be a JSON object")
    if metadata.get("answer_sha256") != expected_sha256:
        raise EditorialEvalError("Manifest hash mismatch")
    answer = (manifest.parent / "answer.txt").resolve(strict=True)
    if not answer.is_relative_to(root) or not answer.is_file():
        raise EditorialEvalError("Answer outside artifact root")
    if answer.stat().st_size > 50_000:
        raise EditorialEvalError("Answer exceeds limit")
    raw = answer.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise EditorialEvalError("Artifact bytes differ from expected SHA256")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EditorialEvalError("Answer is not UTF-8") from exc
    result = evaluate_script(text, language=language,
                             required_terms=required_terms,
                             min_chars=min_chars, max_chars=max_chars)
    return {
        "schema_version": 1,
        "status": "MECHANICAL_PASS_REVIEW_REQUIRED" if result.passed
                  else "REVISE_REQUIRED",
        "source_sha256": digest,
        "language": language,
        "checks": result.checks,
        "score": result.score,
        "publication_approved": False,
    }
