"""Conservative production-readiness audit for reference-conditioned rig art.

A connected LoadImage node alone is NOT enough: reference must pass through a
pinned image-conditioning node into the sampler, and generation through an
explicit alpha/matting node to the actual SaveImage output. This is a graph
wiring proof, not proof that models produce professional rig art.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .comfy import ComfySafetyError, prepare_submission
from .planner import make_rig_plan
from .factory import inspect_reference_image

REQUIRED_STAGES = (
    "conditioning_node_id", "sampler_node_id", "matting_node_id",
)


def _parents(workflow: dict[str, Any], node_id: str) -> set[str]:
    parents: set[str] = set()
    def scan(obj: Any) -> None:
        if isinstance(obj, list):
            if (
                len(obj) == 2 and isinstance(obj[0], str)
                and type(obj[1]) is int and obj[0] in workflow
            ):
                parents.add(obj[0])
            else:
                for item in obj:
                    scan(item)
        elif isinstance(obj, dict):
            for item in obj.values():
                scan(item)
    scan(workflow[node_id]["inputs"])
    return parents


def audit_character_workflow(
    blueprint_file: str | Path,
    workflow_file: str | Path,
    profile_file: str | Path,
    reference_file: str | Path,
) -> dict[str, Any]:
    """Offline, no GPU/network, block weak or misleading ComfyUI art workflows."""
    plan = make_rig_plan(blueprint_file)
    _, reference_name, ref_hash = inspect_reference_image(reference_file)
    first = plan["jobs"][0]
    prepared = prepare_submission(
        workflow_file, profile_file, prompt_text=first["prompt"],
        filename_prefix=f"KidsStudio/{plan['character_id']}/{first['part_id']}",
        reference_image_name=reference_name,
    )
    # Only the approved pinned workflow is audited, not mutable generated prompts.
    workflow = json.loads(Path(workflow_file).read_text(encoding="utf-8"))
    profile = json.loads(Path(profile_file).read_text(encoding="utf-8"))
    stages = profile.get("production_contract")
    if not isinstance(stages, dict) or set(stages) != set(REQUIRED_STAGES):
        raise ComfySafetyError(
            "Production requires conditioning_node_id, sampler_node_id and "
            "matting_node_id in the approved local profile."
        )
    prompt_id = profile["prompt_node_id"]
    reference_id = profile.get("reference_node_id")
    save_id = profile["filename_node_id"]
    selected = [prompt_id, reference_id, save_id, *[stages[k] for k in REQUIRED_STAGES]]
    if (any(not isinstance(v, str) or v not in workflow for v in selected)
            or len(set(selected)) != len(selected)):
        raise ComfySafetyError("Production stage nodes must exist and be distinct.")
    if workflow[save_id]["class_type"] != "SaveImage":
        raise ComfySafetyError("Production output must be standard SaveImage.")

    # Explicitly audit a DAG rather than merely seeing a reference somewhere
    # upstream from final output (which permits bypass/background compositing).
    cache: dict[str, set[str]] = {}
    visiting: set[str] = set()
    def ancestors(node_id: str) -> set[str]:
        if node_id in cache:
            return cache[node_id]
        if node_id in visiting:
            raise ComfySafetyError("Cyclic data dependencies in production workflow.")
        visiting.add(node_id)
        parents: set[str] = set()
        for parent in _parents(workflow, node_id):
            parents.add(parent)
            parents.update(ancestors(parent))
        visiting.remove(node_id)
        cache[node_id] = parents
        return parents

    conditioning = stages["conditioning_node_id"]
    sampler = stages["sampler_node_id"]
    matte = stages["matting_node_id"]
    if reference_id not in ancestors(conditioning):
        raise ComfySafetyError(
            "Canonical identity reference does not enter pinned conditioning node."
        )
    if conditioning not in ancestors(sampler):
        raise ComfySafetyError(
            "Image conditioning is not connected to the pinned sampler."
        )
    if prompt_id not in ancestors(sampler):
        raise ComfySafetyError(
            "The part-specific text prompt does not affect the pinned sampler."
        )
    if sampler not in ancestors(matte):
        raise ComfySafetyError(
            "Generated image does not reach the pinned alpha/matting stage."
        )
    if matte not in ancestors(save_id):
        raise ComfySafetyError(
            "The pinned alpha/matting output does not reach SaveImage."
        )
    # Check the complete saved graph for cycles, not just contract ancestry.
    ancestors(save_id)
    return {
        "status": "GRAPH_READY_NOT_GENERATED",
        "character_id": plan["character_id"],
        "blueprint_sha256": hashlib.sha256(
            Path(blueprint_file).read_bytes()
        ).hexdigest(),
        "reference_sha256": ref_hash,
        "workflow_sha256": prepared["workflow_sha256"],
        "output_node_id": save_id,
        "contract_node_classes": {
            stage: workflow[stages[stage]]["class_type"]
            for stage in REQUIRED_STAGES
        },
        "node_count": prepared["node_count"],
        "visual_and_alpha_output_still_unverified": True,
    }
