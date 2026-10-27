"""Bounded autonomous character production, independent review and targeted repair.

Each attempt is immutable. Approved results remain internal assets only, never
a public-release authorization. Repairs require part-specific visual evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .comfy import prepare_submission
from .factory import (
    FactoryError, LocalComfyClient, build_character, inspect_reference_image
)
from .planner import make_rig_plan
from .reviewer import LocalVisionClient, MODEL_RE

PART_RE = re.compile(r"^[a-zA-Z0-9_]{1,80}$")


class CycleError(ValueError):
    """Invalid production cycle inputs or prohibited repair request."""


def choose_repair_parts(
    decision: dict[str, Any],
    *,
    valid_parts: set[str],
    max_parts: int = 3,
) -> tuple[frozenset[str], dict[str, str], str | None]:
    """Select only explicitly attributed defects; ambiguity escalates, not guesses."""
    if decision.get("verdict") != "REVISE":
        return frozenset(), {}, "Reviewer did not request revision."
    issues = decision.get("issues")
    if not isinstance(issues, list) or not issues:
        return frozenset(), {}, "Review requested revision without actionable issues."
    by_part: dict[str, list[str]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            return frozenset(), {}, "Malformed reviewer issue."
        ident = issue.get("part_id")
        detail = issue.get("description")
        if (
            not isinstance(ident, str) or ident not in valid_parts
            or not PART_RE.fullmatch(ident)
            or not isinstance(detail, str) or not (1 <= len(detail) <= 500)
        ):
            return frozenset(), {}, "An issue lacks an unambiguous valid part_id."
        by_part.setdefault(ident, []).append(detail.strip())
    if len(by_part) > max_parts:
        return frozenset(), {}, "Too many defective parts for a bounded repair."
    feedback: dict[str, str] = {}
    for ident, messages in by_part.items():
        combined = " | ".join(dict.fromkeys(messages))
        if len(combined) > 700:
            return frozenset(), {}, "Repair instructions exceed the safe size limit."
        feedback[ident] = combined
    return frozenset(by_part), feedback, None


def _write_cycle(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def run_character_cycle(
    blueprint_file: str | Path,
    workflow_file: str | Path,
    profile_file: str | Path,
    reference_image: str | Path,
    output_directory: str | Path,
    *,
    vision_model: str,
    max_attempts: int = 2,
    max_repair_parts: int = 3,
    comfy_client: Any | None = None,
    vision_client: Any | None = None,
    timeout_seconds: int = 900,
    preview_side: int = 384,
) -> dict[str, Any]:
    """Run once and at most max_attempts-1 bounded targeted revisions."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise CycleError("max_attempts must be an integer between 1 and 3.")
    if type(max_repair_parts) is not int or not 1 <= max_repair_parts <= 4:
        raise CycleError("max_repair_parts must be between 1 and 4.")
    if not isinstance(vision_model, str) or not MODEL_RE.fullmatch(vision_model):
        raise CycleError("An installed local multimodal vision model is required.")
    out = Path(output_directory).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Cycle output directory already exists.")
    if any((p / ".git").exists() for p in (out, *out.parents)):
        raise CycleError("Character media may not be written inside a Git repository.")

    plan = make_rig_plan(blueprint_file)
    _, reference_name, reference_digest = inspect_reference_image(reference_image)
    first = plan["jobs"][0]
    # Preflight approval and reference path before writing any output directory.
    prepare_submission(
        workflow_file, profile_file, prompt_text=first["prompt"],
        filename_prefix=f"KidsStudio/{plan['character_id']}/{first['part_id']}",
        reference_image_name=reference_name,
    )
    valid_parts = {job["part_id"] for job in plan["jobs"]}
    active_comfy = comfy_client if comfy_client is not None else LocalComfyClient()
    active_vision = vision_client if vision_client is not None else LocalVisionClient()

    out.mkdir(parents=True, exist_ok=False)
    ledger: dict[str, Any] = {
        "schema_version": 1,
        "character_id": plan["character_id"],
        "status": "IN_PROGRESS",
        "max_attempts": max_attempts,
        "max_repair_parts": max_repair_parts,
        "reference_sha256": reference_digest,
        "owner_publication_approval_required": True,
        "attempts": [],
    }
    ledger_file = out / "production_cycle.json"
    _write_cycle(ledger_file, ledger)
    previous: Path | None = None
    parts: frozenset[str] | None = None
    feedback: dict[str, str] | None = None

    try:
        for number in range(1, max_attempts + 1):
            attempt = out / f"attempt_{number:02d}"
            state = build_character(
                blueprint_file, workflow_file, profile_file, attempt,
                client=active_comfy, timeout_seconds=timeout_seconds,
                preview_side=preview_side, review_model=vision_model,
                vision_client=active_vision, reference_image=reference_image,
                reuse_from=previous, regenerate_parts=parts,
                repair_feedback=feedback,
            )
            decision = state.get("visual_review")
            entry: dict[str, Any] = {
                "attempt": number,
                "directory": str(attempt),
                "status": state["status"],
                "regenerated_parts": (
                    sorted(parts) if parts is not None else sorted(valid_parts)
                ),
                "generated_comfy_jobs": sum(
                    job["status"] == "COLLECTED" for job in state["jobs"]
                ),
                "reused_parts": sum(
                    job["status"] == "REUSED" for job in state["jobs"]
                ),
                "report_sha256": hashlib.sha256(
                    (attempt / "factory_report.json").read_bytes()
                ).hexdigest(),
            }
            ledger["attempts"].append(entry)
            if state["status"] == "APPROVED_BY_LOCAL_AI_QA":
                ledger["status"] = "INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION"
                ledger["accepted_attempt"] = str(attempt)
                break
            if state["status"] == "REJECTED_BY_LOCAL_AI_QA":
                ledger["status"] = "REJECTED_FINAL"
                ledger["explanation"] = "Independent visual reviewer rejected the rig."
                break
            if state["status"] != "REVISE_REQUIRED" or not isinstance(decision, dict):
                ledger["status"] = "BLOCKED_MANUAL_REVIEW"
                ledger["explanation"] = "Missing actionable independent visual review."
                break
            if number >= max_attempts:
                ledger["status"] = "REPAIR_BUDGET_EXHAUSTED"
                ledger["explanation"] = "The revision limit was reached."
                break
            parts, feedback, reason = choose_repair_parts(
                decision, valid_parts=valid_parts, max_parts=max_repair_parts,
            )
            if reason is not None:
                ledger["status"] = "BLOCKED_MANUAL_TRIAGE"
                ledger["explanation"] = reason
                break
            previous = attempt
            _write_cycle(ledger_file, ledger)
    except Exception as exc:
        ledger["status"] = "PRODUCTION_FAILED"
        ledger["error_type"] = type(exc).__name__
        ledger["error"] = str(exc)[:1200]
        _write_cycle(ledger_file, ledger)
        raise
    _write_cycle(ledger_file, ledger)
    return ledger
