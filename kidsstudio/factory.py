"""Run a bounded rig-first ComfyUI generation batch and collect review evidence.

Each part gets an independently generated PNG via an explicitly approved API
workflow. Requires a LOCAL ComfyUI process and an explicit CLI --execute flag.
Never silently approves visual quality or assumes diffusion returns real alpha.
"""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any
from urllib import request
from urllib.parse import urlencode, quote

from PIL import Image, UnidentifiedImageError

from .comfy import prepare_submission, validate_local_base_url
from .motion import create_motion_evidence
from .planner import make_rig_plan
from .rigqa import check_rig
from .riggeometry import measure_part_geometry, pixel_fingerprint
from .reviewer import review_rig

MAX_IMAGE_BYTES = 25_000_000

MAX_REFERENCE_BYTES = 15_000_000


def inspect_reference_image(source: str | Path) -> tuple[bytes, str, str]:
    """Validate source PNG; return bytes, deterministic name, SHA256."""
    path = Path(source).expanduser().resolve()
    payload = path.read_bytes()
    if not 1 <= len(payload) <= MAX_REFERENCE_BYTES:
        raise FactoryError("Reference PNG is empty or exceeds 15 MB.")
    try:
        with Image.open(BytesIO(payload)) as image:
            image.load()
            if image.format != "PNG" or min(image.size) < 16 or max(image.size) > 4096:
                raise FactoryError("Reference must be a valid PNG within 16..4096 pixels.")
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise FactoryError(f"Invalid reference PNG: {exc}") from exc
    digest = hashlib.sha256(payload).hexdigest()
    return payload, "KidsStudio_reference_" + digest[:16] + ".png", digest

MAX_API_BYTES = 2_000_000
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


class FactoryError(RuntimeError):
    """Batch could not safely produce rig assets."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalComfyClient:
    """Local-only ComfyUI HTTP client that ignores proxies and rejects redirects."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base = validate_local_base_url(base_url)
        self.opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def _read(self, path: str, *, json_body: dict[str, Any] | None = None,
              max_bytes: int = MAX_API_BYTES) -> bytes:
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data else "GET",
        )
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise FactoryError("ComfyUI response exceeds safety limit.")
        return raw

    def queue(self, prepared: dict[str, Any]) -> str:
        if prepared.get("status") != "READY_NOT_SUBMITTED":
            raise FactoryError("Only validated generation plans may be submitted.")
        payload = json.loads(self._read("/prompt", json_body={"prompt": prepared["prompt"]}))
        result = payload.get("prompt_id")
        if not isinstance(result, str) or not SAFE_ID.fullmatch(result):
            raise FactoryError("ComfyUI returned an invalid prompt ID.")
        if payload.get("node_errors"):
            raise FactoryError("ComfyUI reported node validation errors.")
        return result

    def await_image(self, prompt_id: str, *, save_node_id: str,
                    timeout_seconds: int = 900,
                    poll_seconds: float = 3.0) -> dict[str, str]:
        if not SAFE_ID.fullmatch(prompt_id):
            raise FactoryError("Unsafe prompt ID.")
        if not isinstance(save_node_id, str) or not SAFE_ID.fullmatch(save_node_id):
            raise FactoryError("Unsafe configured SaveImage node ID.")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            history = json.loads(self._read("/history/" + quote(prompt_id, safe="")))
            item = history.get(prompt_id)
            if isinstance(item, dict):
                status = item.get("status", {})
                if isinstance(status, dict) and status.get("status_str") == "error":
                    raise FactoryError("ComfyUI execution failed; inspect local ComfyUI logs.")
                # ComfyUI history indexes outputs by node ID. Only the
                # approved SaveImage node is authoritative for rig art:
                # previews, mask helpers or unrelated saves are not accepted.
                if isinstance(status, dict) and status.get("completed") is True:
                    outputs = item.get("outputs", {})
                    node = outputs.get(save_node_id) if isinstance(outputs, dict) else None
                    images = node.get("images") if isinstance(node, dict) else None
                    if not isinstance(images, list) or len(images) != 1:
                        raise FactoryError(
                            "Approved SaveImage must produce exactly one output image."
                        )
                    candidate = images[0]
                    if (not isinstance(candidate, dict)
                            or candidate.get("type") != "output"
                            or not isinstance(candidate.get("filename"), str)
                            or not isinstance(candidate.get("subfolder", ""), str)):
                        raise FactoryError("Approved SaveImage produced an invalid output.")
                    return {
                        "filename": candidate["filename"],
                        "subfolder": candidate.get("subfolder", ""),
                        "type": "output",
                    }
            time.sleep(poll_seconds)
        raise TimeoutError(f"ComfyUI job did not complete within {timeout_seconds}s.")

    def upload_reference(self, payload: bytes, filename: str) -> str:
        """Upload only a vetted local PNG to this loopback ComfyUI instance."""
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}\.png", filename):
            raise FactoryError("Unsafe uploaded reference filename.")
        if not 1 <= len(payload) <= MAX_REFERENCE_BYTES:
            raise FactoryError("Invalid reference payload length.")
        boundary = "KidsStudioReferenceBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + payload + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            f"true\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        req = request.Request(
            self.base + "/upload/image", data=body,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
            method="POST",
        )
        with self.opener.open(req, timeout=60) as response:
            raw = response.read(MAX_API_BYTES + 1)
        if len(raw) > MAX_API_BYTES:
            raise FactoryError("Reference upload response exceeds safety limit.")
        response = json.loads(raw)
        returned = response.get("name")
        if (returned != filename or response.get("subfolder", "") != ""
                or response.get("type", "input") != "input"):
            raise FactoryError("ComfyUI reference was not stored under approved input name.")
        return returned

    def download_png(self, image_ref: dict[str, str]) -> bytes:
        name, subfolder = image_ref.get("filename"), image_ref.get("subfolder", "")
        if (
            not isinstance(name, str) or not name.lower().endswith(".png")
            or name != Path(name).name or name.startswith(".")
            or not isinstance(subfolder, str) or "\\" in subfolder
            or subfolder.startswith("/") or ".." in subfolder.split("/")
            or image_ref.get("type") != "output"
        ):
            raise FactoryError("Unsafe ComfyUI image reference.")
        q = urlencode({"filename": name, "subfolder": subfolder, "type": "output"})
        return self._read("/view?" + q, max_bytes=MAX_IMAGE_BYTES)


def _json_atomic(file: Path, data: dict[str, Any]) -> None:
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(file)


def _store_rgba_png(image_bytes: bytes, file: Path, canvas: tuple[int, int]) -> str:
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise FactoryError("Generated PNG too large.")
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.format != "PNG" or img.size != canvas:
                raise FactoryError("Output must be a PNG at the configured canvas resolution.")
            if "A" not in img.getbands() and "transparency" not in img.info:
                raise FactoryError(
                    "NO_ALPHA: ComfyUI returned an opaque image. "
                    "Configure a real transparency/matting node; no fake transparency allowed."
                )
            rgba = img.convert("RGBA")
            lo, hi = rgba.getchannel("A").getextrema()
            if lo != 0 or hi != 255:
                raise FactoryError(
                    "ALPHA_INVALID: part needs transparent background and opaque artwork."
                )
            if rgba.getchannel("A").getbbox() is None:
                raise FactoryError("PART_EMPTY: generated part has no visible pixels.")
            rgba.save(file, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FactoryError(f"Cannot decode generated PNG: {exc}") from exc
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _early_part_geometry_gate(
    png_path: Path,
    job: dict[str, Any],
    policy: dict[str, Any],
    previous_fingerprints: dict[str, str],
) -> dict[str, Any] | None:
    """Reject a misplaced or duplicated new part BEFORE spending on later parts."""
    if not policy.get("strict_parts", False):
        return None
    rect = job.get("expected_region")
    if rect is None:
        raise FactoryError(f"{job['part_id']}: missing expected region in strict mode.")
    with Image.open(png_path) as img:
        img.load()
        measures = measure_part_geometry(
            img, rect, alpha_threshold=policy["alpha_threshold"]
        )
        if policy["reject_identical_layers"]:
            fingerprint = pixel_fingerprint(img)
            other = previous_fingerprints.get(fingerprint)
            if other is not None:
                raise FactoryError(
                    f"GEOMETRY_DUPLICATE: {job['part_id']} duplicates {other}."
                )
            previous_fingerprints[fingerprint] = job["part_id"]
    if (
        measures["visible_pixels"] == 0
        or measures["outside_fraction"] > policy["max_outside_fraction"] + 1e-6
        or measures["inside_fill_fraction"] + 1e-6 <
            policy["min_inside_fill_fraction"]
    ):
        raise FactoryError(
            f"GEOMETRY_FAIL: {job['part_id']} has "
            f"{measures['outside_fraction']:.1%} paint outside its permitted "
            f"region and {measures['inside_fill_fraction']:.2%} inside fill."
        )
    return measures


def build_character(
    blueprint_file: str | Path,
    workflow_file: str | Path,
    profile_file: str | Path,
    output_directory: str | Path,
    *,
    client: Any | None = None,
    timeout_seconds: int = 900,
    preview_side: int = 384,
    review_model: str | None = None,
    vision_client: Any | None = None,
    reference_image: str | Path | None = None,
    reuse_from: str | Path | None = None,
    regenerate_parts: frozenset[str] | None = None,
    repair_feedback: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a new batch; refuses to overwrite any existing output."""
    plan = make_rig_plan(blueprint_file)
    char_id = plan["character_id"]
    if not SAFE_ID.fullmatch(char_id):
        raise FactoryError("Character ID must be ASCII letters, digits, underscore or dash.")
    out = Path(output_directory).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Output directory already exists; choose a new version.")
    # Refuse any directory inside an actual Git working tree.
    if any((parent / ".git").exists() for parent in (out, *out.parents)):
        raise FactoryError("Character production assets must not be saved inside Git.")
    reference_bytes: bytes | None = None
    reference_name: str | None = None
    reference_digest: str | None = None
    if reference_image is not None:
        reference_bytes, reference_name, reference_digest = inspect_reference_image(
            reference_image
        )
    # A repair always creates an immutable new attempt; never mutate approved
    # or rejected artwork in-place. All old assets must match the same blueprint,
    # workflow, reference and their recorded hashes before any generation.
    previous: Path | None = None
    previous_report: dict[str, Any] | None = None
    if reuse_from is not None:
        previous = Path(reuse_from).expanduser().resolve()
        if not previous.is_dir() or previous == out:
            raise FactoryError("Repair source must be an existing separate attempt.")
        if not isinstance(regenerate_parts, frozenset) or not regenerate_parts:
            raise FactoryError("Repair must name at least one part to regenerate.")
        valid_parts = {job["part_id"] for job in plan["jobs"]}
        if not regenerate_parts.issubset(valid_parts):
            raise FactoryError("Repair requested unknown part ids.")
        prev_rig = previous / "rig.json"
        prev_qa = check_rig(prev_rig)
        if not prev_qa["passed"]:
            raise FactoryError("Cannot reuse an invalid previous rig.")
        previous_report = json.loads(
            (previous / "factory_report.json").read_text(encoding="utf-8")
        )
        if previous_report.get("status") != "REVISE_REQUIRED":
            raise FactoryError("Only a visually REVISE_REQUIRED attempt can be repaired.")
        previous_manifest = json.loads(prev_rig.read_text(encoding="utf-8"))
        if (
            previous_manifest != plan["rig_manifest_template"]
            or previous_report.get("blueprint_sha256") !=
                hashlib.sha256(Path(blueprint_file).read_bytes()).hexdigest()
            or previous_report.get("canonical_reference_sha256") != reference_digest
        ):
            raise FactoryError("Source attempt differs from current blueprint/reference.")
        jobs = previous_report.get("jobs", [])
        if not isinstance(jobs, list):
            raise FactoryError("Previous provenance entries are missing.")
        for job in plan["jobs"]:
            ident = job["part_id"]
            entry = next((j for j in jobs if isinstance(j, dict) and
                          j.get("part_id") == ident), None)
            if entry is None or entry.get("status") not in ("COLLECTED", "REUSED"):
                raise FactoryError(f"Unverified source part: {ident}")
            image_file = previous / job["target_png"]
            if not image_file.is_file() or (
                hashlib.sha256(image_file.read_bytes()).hexdigest()
                != entry.get("sha256")
            ):
                raise FactoryError(f"Original part changed after review: {ident}")
    elif regenerate_parts is not None or repair_feedback is not None:
        raise FactoryError("Repair options require a previous attempt.")
    if repair_feedback is not None:
        if (
            not isinstance(repair_feedback, dict)
            or not regenerate_parts
            or set(repair_feedback) != set(regenerate_parts)
            or any(not isinstance(v, str) or
                   not (1 <= len(v) <= 700) for v in repair_feedback.values())
        ):
            raise FactoryError("Repair feedback must cover each selected part.")

    # Check all target jobs *before* the first remote generation.
    prepared_jobs = [
        (job, prepare_submission(
            workflow_file, profile_file,
            prompt_text=(
                job["prompt"] + (
                    " Address these rig QA defects while preserving the canonical "
                    "character identity and all other parts: " +
                    repair_feedback[job["part_id"]]
                    if repair_feedback is not None and
                    job["part_id"] in repair_feedback else ""
                )
            ),
            filename_prefix=f"KidsStudio/{char_id}/{job['part_id']}",
            reference_image_name=reference_name,
        ))
        for job in plan["jobs"]
    ]
    if previous_report is not None and (
        previous_report.get("approved_workflow_sha256")
        != prepared_jobs[0][1]["workflow_sha256"]
    ):
        raise FactoryError("Previous attempt used a different approved workflow.")
    # ComfyUI workflow may be valid, but image edits and extra node types require
    # a pre-approved profile, not arbitrary additions to this implementation.
    active = client if client is not None else LocalComfyClient()

    out.mkdir(parents=True, exist_ok=False)
    (out / "assets").mkdir()
    policy = plan["rig_manifest_template"].get("qa_policy", {})
    previous_fingerprints: dict[str, str] = {}
    state: dict[str, Any] = {
        "character_id": char_id,
        "status": "GENERATING",
        "blueprint_sha256": hashlib.sha256(
            Path(blueprint_file).read_bytes()).hexdigest(),
        "approved_workflow_sha256": prepared_jobs[0][1]["workflow_sha256"],
        "models": prepared_jobs[0][1]["models"],
        "canonical_reference_sha256": reference_digest,
        "reference_conditioned": reference_name is not None,
        "jobs": [],
        "reused_from": str(previous) if previous is not None else None,
        "reused_report_sha256": (
            hashlib.sha256((previous / "factory_report.json").read_bytes()).hexdigest()
            if previous is not None else None
        ),
        "regenerated_parts": sorted(regenerate_parts) if regenerate_parts else [],
        "technical_pass": False,
        "visual_review_required": True,
    }
    state_file = out / "factory_report.json"
    _json_atomic(state_file, state)

    try:
        if reference_bytes is not None and reference_name is not None:
            actual_name = active.upload_reference(reference_bytes, reference_name)
            if actual_name != reference_name:
                raise FactoryError("Reference upload did not preserve the approved name.")
        for job, prepared in prepared_jobs:
            if previous is not None and job["part_id"] not in regenerate_parts:
                src = previous / job["target_png"]
                dst = out / job["target_png"]
                shutil.copyfile(src, dst)
                _early_part_geometry_gate(
                    dst, job, policy, previous_fingerprints
                )
                digest = hashlib.sha256(dst.read_bytes()).hexdigest()
                state["jobs"].append({
                    "part_id": job["part_id"],
                    "status": "REUSED",
                    "sha256": digest,
                    "file": job["target_png"],
                    "source_attempt": str(previous),
                    "prompt_sha256": hashlib.sha256(
                        job["prompt"].encode("utf-8")).hexdigest(),
                })
                _json_atomic(state_file, state)
                continue
            entry: dict[str, Any] = {
                "part_id": job["part_id"],
                "status": "QUEUED",
                "prompt_sha256": hashlib.sha256(
                    job["prompt"].encode("utf-8")).hexdigest(),
            }
            state["jobs"].append(entry)
            _json_atomic(state_file, state)
            prompt_id = active.queue(prepared)
            entry["prompt_id"] = prompt_id
            entry["status"] = "RUNNING"
            _json_atomic(state_file, state)
            image_ref = active.await_image(
                prompt_id,
                save_node_id=prepared["save_node_id"],
                timeout_seconds=timeout_seconds,
            )
            image_bytes = active.download_png(image_ref)
            target = out / job["target_png"]
            digest = _store_rgba_png(
                image_bytes, target,
                (plan["canvas"]["width"], plan["canvas"]["height"])
            )
            entry["geometry"] = _early_part_geometry_gate(
                target, job, policy, previous_fingerprints
            )
            entry.update({
                "status": "COLLECTED",
                "sha256": digest,
                "file": job["target_png"],
                "source_filename": image_ref["filename"],
            })
            _json_atomic(state_file, state)

        manifest = out / "rig.json"
        _json_atomic(manifest, plan["rig_manifest_template"])
        technical = check_rig(manifest)
        state["technical_pass"] = technical["passed"]
        state["technical_qa"] = technical
        if not technical["passed"]:
            state["status"] = "TECHNICAL_FAIL"
        else:
            evidence = create_motion_evidence(
                manifest, out / "review", side=preview_side)
            state["evidence"] = {
                "contact_sheet": "review/motion_contact_sheet.png",
                "animation": "review/motion_preview.gif",
                "motions": evidence["motions"],
            }
            state["status"] = "NEEDS_INDEPENDENT_VISUAL_REVIEW"
            if review_model is not None:
                decision = review_rig(
                    manifest, out / "review" / "motion_evidence.json",
                    out / "visual_review.json", model=review_model,
                    client=vision_client,
                    reference_file=reference_image,
                )
                state["visual_review"] = decision
                state["status"] = decision["status"]
        _json_atomic(state_file, state)
    except Exception as exc:
        state["status"] = "FAILED"
        state["error_type"] = type(exc).__name__
        state["error"] = str(exc)
        _json_atomic(state_file, state)
        raise
    return state
