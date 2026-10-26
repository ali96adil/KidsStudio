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
import time
from typing import Any
from urllib import request
from urllib.parse import urlencode, quote

from PIL import Image, UnidentifiedImageError

from .comfy import prepare_submission, validate_local_base_url
from .motion import create_motion_evidence
from .planner import make_rig_plan
from .rigqa import check_rig

MAX_IMAGE_BYTES = 25_000_000
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

    def await_image(self, prompt_id: str, *, timeout_seconds: int = 900,
                    poll_seconds: float = 3.0) -> dict[str, str]:
        if not SAFE_ID.fullmatch(prompt_id):
            raise FactoryError("Unsafe prompt ID.")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            history = json.loads(self._read("/history/" + quote(prompt_id, safe="")))
            item = history.get(prompt_id)
            if isinstance(item, dict):
                status = item.get("status", {})
                if isinstance(status, dict) and status.get("status_str") == "error":
                    raise FactoryError("ComfyUI execution failed; inspect local ComfyUI logs.")
                outputs = item.get("outputs", {})
                if isinstance(outputs, dict):
                    images = []
                    for node in outputs.values():
                        if isinstance(node, dict) and isinstance(node.get("images"), list):
                            images.extend(node["images"])
                    candidates = [i for i in images if isinstance(i, dict)
                                  and i.get("type", "output") == "output"]
                    if candidates:
                        candidate = candidates[0]
                        return {
                            "filename": candidate.get("filename"),
                            "subfolder": candidate.get("subfolder", ""),
                            "type": "output",
                        }
                if isinstance(status, dict) and status.get("completed") is True:
                    raise FactoryError("ComfyUI job completed without output images.")
            time.sleep(poll_seconds)
        raise TimeoutError(f"ComfyUI job did not complete within {timeout_seconds}s.")

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


def build_character(
    blueprint_file: str | Path,
    workflow_file: str | Path,
    profile_file: str | Path,
    output_directory: str | Path,
    *,
    client: Any | None = None,
    timeout_seconds: int = 900,
    preview_side: int = 384,
) -> dict[str, Any]:
    """Execute a new batch; refuses to overwrite any existing output."""
    plan = make_rig_plan(blueprint_file)
    char_id = plan["character_id"]
    if not SAFE_ID.fullmatch(char_id):
        raise FactoryError("Character ID must be ASCII letters, digits, underscore or dash.")
    out = Path(output_directory).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Output directory already exists; choose a new version.")
    if any(parent.name == ".git" for parent in out.parents):
        raise FactoryError("Character production assets must not be saved inside Git.")
    # Check all target jobs *before* the first remote generation.
    prepared_jobs = [
        (job, prepare_submission(
            workflow_file, profile_file,
            prompt_text=job["prompt"],
            filename_prefix=f"KidsStudio/{char_id}/{job['part_id']}",
        ))
        for job in plan["jobs"]
    ]
    # ComfyUI workflow may be valid, but image edits and extra node types require
    # a pre-approved profile, not arbitrary additions to this implementation.
    active = client if client is not None else LocalComfyClient()

    out.mkdir(parents=True, exist_ok=False)
    (out / "assets").mkdir()
    state: dict[str, Any] = {
        "character_id": char_id,
        "status": "GENERATING",
        "blueprint_sha256": hashlib.sha256(
            Path(blueprint_file).read_bytes()).hexdigest(),
        "approved_workflow_sha256": prepared_jobs[0][1]["workflow_sha256"],
        "models": prepared_jobs[0][1]["models"],
        "jobs": [],
        "technical_pass": False,
        "visual_review_required": True,
    }
    state_file = out / "factory_report.json"
    _json_atomic(state_file, state)

    try:
        for job, prepared in prepared_jobs:
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
            image_ref = active.await_image(prompt_id, timeout_seconds=timeout_seconds)
            image_bytes = active.download_png(image_ref)
            target = out / job["target_png"]
            digest = _store_rgba_png(
                image_bytes, target,
                (plan["canvas"]["width"], plan["canvas"]["height"])
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
        _json_atomic(state_file, state)
    except Exception as exc:
        state["status"] = "FAILED"
        state["error_type"] = type(exc).__name__
        state["error"] = str(exc)
        _json_atomic(state_file, state)
        raise
    return state
