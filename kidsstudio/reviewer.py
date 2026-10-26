"""Independent, local vision-model review of character motion evidence.

Requires an explicitly selected multimodal Ollama model. No model downloads or
remote API fallbacks. Technical QA is a prerequisite, not a substitute for art QA.
Review reports are auditable and tied to hashes of source layers and evidence.
"""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
from urllib import request

from PIL import Image

from .rigqa import check_rig

MODEL_RE = re.compile(r"^[a-zA-Z0-9_.:/-]{1,90}$")
MAX_RESPONSE_BYTES = 300_000
RUBRIC = """You are an INDEPENDENT senior 2D character-rig quality reviewer for an original
children's educational animation studio. The image is a CONTACT SHEET of motions,
with labeled panels (neutral, wave_right, wave_left, head_tilt, jump, walk).
Compare with optional canonical reference if provided. Do NOT approve just because
the render succeeded. Carefully inspect:
- Disconnected limbs, broken shoulder/neck/hip joins and holes or old-arm ghosts;
- Deformed or incomplete arms, paws, legs, ears or cheeks during motion;
- Abnormal layering/occlusions, texture/color shifts, halo edges, cropped parts;
- Facial identity inconsistency or misaligned eyes/mouth;
- Visible frame-to-frame continuity, believable child-friendly posing.
Rate each issue with motion panel, concise evidence and severity. Do not invent
issues that cannot be seen. Prefer REVISE if uncertain.
Return strict JSON ONLY:
{"verdict":"PASS|REVISE|FAIL","confidence":0.0,
 "issues":[{"motion":"wave_right","severity":"low|medium|high",
 "description":"specific visible artifact"}],"reason":"brief explanation"}
Use PASS only if no material visible defects and you are at least 0.8 confident.
A model PASS is not equivalent to human release/publishing permission.
"""


class VisionReviewError(RuntimeError):
    """The local vision reviewer is unavailable or returned invalid evidence."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalVisionClient:
    """Local-only multimodal Ollama /api/chat adapter."""

    def __init__(self, url: str = "http://127.0.0.1:11434"):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port is None
            or not (1 <= parsed.port <= 65535)
            or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment
            or parsed.username is not None
        ):
            raise VisionReviewError("Reviewer endpoint must be a local HTTP port.")
        self.base = f"http://127.0.0.1:{parsed.port}"
        self.opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def review(self, model: str, images_b64: list[str]) -> dict[str, Any]:
        if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
            raise VisionReviewError("Invalid local vision model name.")
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 1400},
            "messages": [
                {"role": "system", "content": RUBRIC},
                {"role": "user",
                 "content": "Review this motion contact sheet for animation defects. "
                            "If a second image is provided it is the approved identity "
                            "reference. Answer JSON only.",
                 "images": images_b64},
            ],
        }
        req = request.Request(
            self.base + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(req, timeout=600) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise VisionReviewError("Visual reviewer response too large.")
        response_data = json.loads(raw)
        text = response_data.get("message", {}).get("content")
        if not isinstance(text, str):
            raise VisionReviewError("Visual model returned no text response.")
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise VisionReviewError("Visual review must be a JSON object.")
        return obj


def _hash(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _image_as_b64(file: Path) -> str:
    if not file.is_file():
        raise VisionReviewError(f"Review image not found: {file.name}")
    with Image.open(file) as image:
        image.load()
        if image.width > 8000 or image.height > 8000:
            raise VisionReviewError("Image exceeds visual review dimensions.")
        img = image.convert("RGB")
        if max(img.size) > 3072:
            ratio = 3072 / max(img.size)
            img = img.resize(
                (round(img.width * ratio), round(img.height * ratio)),
                Image.Resampling.LANCZOS,
            )
        data = BytesIO()
        img.save(data, "JPEG", quality=84)
    return base64.b64encode(data.getvalue()).decode("ascii")


def _verdict(obj: dict[str, Any]) -> dict[str, Any]:
    decision = obj.get("verdict")
    confidence = obj.get("confidence")
    reason = obj.get("reason")
    issues = obj.get("issues")
    if decision not in ("PASS", "REVISE", "FAIL"):
        raise VisionReviewError("Vision model returned unknown verdict.")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise VisionReviewError("Vision model returned invalid confidence.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1500:
        raise VisionReviewError("Vision model must provide a reason.")
    if not isinstance(issues, list) or len(issues) > 30:
        raise VisionReviewError("Vision model returned invalid issues list.")
    cleaned = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise VisionReviewError("Invalid issue entry.")
        motion, severity, detail = (
            issue.get("motion"), issue.get("severity"), issue.get("description")
        )
        if not isinstance(motion, str) or len(motion) > 64:
            raise VisionReviewError("Invalid motion in review.")
        if severity not in ("low", "medium", "high"):
            raise VisionReviewError("Invalid issue severity.")
        if not isinstance(detail, str) or not detail.strip() or len(detail) > 500:
            raise VisionReviewError("Invalid issue description.")
        cleaned.append({
            "motion": motion, "severity": severity, "description": detail
        })
    # Fail closed if the model contradicts itself.
    if decision == "PASS" and (confidence < 0.80 or
                               any(i["severity"] in ("medium", "high") for i in cleaned)):
        decision = "REVISE"
        reason = "Model approval did not meet confidence/defect gate. " + reason
    return {
        "verdict": decision, "confidence": confidence,
        "issues": cleaned, "reason": reason,
    }


def review_rig(
    manifest_file: str | Path,
    motion_evidence_file: str | Path,
    output_file: str | Path,
    *,
    model: str,
    reference_file: str | Path | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Evaluate motion evidence tied to current source files, never mutate rig assets."""
    manifest = Path(manifest_file).expanduser().resolve()
    evidence = Path(motion_evidence_file).expanduser().resolve()
    target = Path(output_file).expanduser().resolve()
    if target.exists():
        raise FileExistsError("Review report already exists; use a new version.")
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise VisionReviewError("An explicit local vision model name is required.")
    technical = check_rig(manifest)
    if not technical["passed"]:
        raise VisionReviewError("Technical rig QA failed; visual PASS is forbidden.")

    info = json.loads(evidence.read_text(encoding="utf-8"))
    expected = info.get("source_hashes")
    if not isinstance(expected, dict):
        raise VisionReviewError("Motion evidence has no source hashes; regenerate previews.")
    actual = {"rig.json": _hash(manifest)}
    rigdata = json.loads(manifest.read_text(encoding="utf-8"))
    for part in rigdata["parts"]:
        actual[part["file"]] = _hash(manifest.parent / part["file"])
    if expected != actual:
        raise VisionReviewError("Review evidence is stale: rig source files changed.")

    sheet = evidence.parent / "motion_contact_sheet.png"
    if info.get("contact_sheet_sha256") != _hash(sheet):
        raise VisionReviewError("Contact sheet changed after evidence creation.")

    images = [_image_as_b64(sheet)]
    reference_digest = None
    if reference_file is not None:
        reference = Path(reference_file).expanduser().resolve()
        reference_digest = _hash(reference)
        images.append(_image_as_b64(reference))
    vision = client if client is not None else LocalVisionClient()
    raw = vision.review(model, images)
    decision = _verdict(raw)
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": {
            "PASS": "APPROVED_BY_LOCAL_AI_QA",
            "REVISE": "REVISE_REQUIRED",
            "FAIL": "REJECTED_BY_LOCAL_AI_QA",
        }[decision["verdict"]],
        "character_id": rigdata["character_id"],
        "model": model,
        "evidence_sha256": _hash(evidence),
        "reference_sha256": reference_digest,
        "reviewer": "independent_local_multimodal_model",
        "owner_release_approval_required": True,
        **decision,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return result
