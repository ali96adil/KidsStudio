"""M36 conservative M29 visual/M10 -> current Pi scene evidence import.

Sampled PNG frames do not contain audio. This adapter can register exact M10
technical continuity but NEVER silently interpret a frame-only vision report
as lip-sync or audio continuity proof. Existing incomplete visual evidence
remains private; no repair, render or publication is authorized by UNSURE.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

from .scene_ai_qa import SceneAIGate, SceneError, _private
from .studio_queue import StudioQueue, QueueError
from .studio_scenes import SceneLedger, SHA


class VisionImportError(ValueError):
    pass


def _json_file(path: str | Path, limit: int = 100000) -> tuple[dict, str]:
    raw, sha = _private(path, limit, ".json")
    try:
        data = json.loads(raw)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise VisionImportError("Invalid private audiovisual evidence.") from exc
    if not isinstance(data, dict):
        raise VisionImportError("Expected JSON object evidence.")
    return data, sha


def import_visual_review(*, queue: StudioQueue, series_id: str,
                         episode: int, scene: int, report_dir: str | Path,
                         m10_report: str | Path, rights_file: str | Path,
                         runner_key: bytes, execute: bool = False) -> dict:
    if (not isinstance(series_id, str) or not series_id or
        type(episode) is not int or not 1 <= episode <= 120 or
        type(scene) is not int or not 1 <= scene <= 40 or
        type(execute) is not bool or not isinstance(runner_key, bytes) or
        len(runner_key) < 32):
        raise VisionImportError("Valid current episode, scene and trusted key required.")
    folder = Path(report_dir).expanduser()
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise VisionImportError("Private M29 report directory required.")
    folder = folder.resolve()
    pending, pending_sha = _json_file(folder / "model_report_pending_m10.json")
    signed, signed_sha = _json_file(folder / "signed_m28.json")
    observation, obs_sha = _json_file(folder / "observations.json")
    m10, tech_sha = _json_file(m10_report, 40000)
    _, rights_sha = _json_file(rights_file)
    assert_no_release = (
        signed.get("publication_approved") is False and
        pending.get("public_release_authorized") is False and
        pending.get("m28_stage_approved") is False
    )
    if (not assert_no_release or
        pending.get("schema_version") != 1 or
        pending.get("status") != "REAL_LOCAL_VISUAL_MODEL_REPORTS_PENDING_M10_BIND" or
        pending.get("runner_models_executed") is not True or
        pending.get("stage") != "ltx_animate" or
        signed.get("schema_version") != 1 or
        signed.get("series_id") != series_id or
        signed.get("episode_number") != episode or
        signed.get("scene") != scene or
        signed.get("stage") != "ltx_animate" or
        signed.get("observations_sha256") != obs_sha or
        signed.get("rights_sha256") != rights_sha or
        signed.get("technical_sha256") != tech_sha or
        any(signed.get(key) != pending.get(key) for key in (
            "series_id", "episode_number", "scene", "stage", "job_id",
            "script_sha256", "artifact_sha256", "reviewers"
        )) or
        observation.get("stage") != "ltx_animate" or
        observation.get("artifact_sha256") != signed.get("artifact_sha256") or
        observation.get("script_sha256") != signed.get("script_sha256") or
        observation.get("source_voice_sha256") != m10.get("voice_sha256") or
        m10.get("a2v_sha256") != signed.get("artifact_sha256") or
        m10.get("status") != "AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" or
        not isinstance(signed.get("artifact_sha256"), str) or
        not SHA.fullmatch(signed["artifact_sha256"])):
        raise VisionImportError("M29 bundle, original voice and exact M10/rights disagree.")
    attestation = signed.get("runner_attestation")
    if (not isinstance(attestation, dict) or
        set(attestation) != {"runner_id", "runtime_status", "hmac_sha256"} or
        attestation["runner_id"] != "m29_local_multimodal_worker" or
        attestation["runtime_status"] != "REVIEW_MODELS_EXECUTED" or
        not isinstance(attestation["hmac_sha256"], str)):
        raise VisionImportError("Missing trusted local M29 runner attestation.")
    unsigned = {key: value for key, value in signed.items()
                if key != "runner_attestation"}
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not hmac.compare_digest(
            hmac.new(runner_key, payload, hashlib.sha256).hexdigest(),
            attestation["hmac_sha256"]):
        raise VisionImportError("Invalid M29 model-runner signature.")
    reviews = signed.get("reviewers")
    if (not isinstance(reviews, list) or len(reviews) != 2 or
        not isinstance(reviews[0], dict) or not isinstance(reviews[1], dict) or
        reviews[0].get("role") != "motion_sync" or
        reviews[1].get("role") != "visual_child_safety"):
        raise VisionImportError("Expected original independent M29 reviewer roles.")
    checks = reviews[0].get("checks", {})
    if not isinstance(checks, dict):
        raise VisionImportError("Missing motion observations.")
    # M29 samples PNGs only, so image models may NOT certify audible
    # word continuity or accurate lip timing, even if they assert PASS.
    for key in ("lip_sync", "voice_continuity"):
        if not isinstance(checks.get(key), dict) or (
                checks[key].get("decision") not in ("UNSURE", "NEEDS_FIX")):
            raise VisionImportError("Silent video frames are not lip-sync/audio proof.")
    decision_rows = [x for item in reviews
                     for x in (item.get("checks", {}) or {}).values()]
    if not decision_rows or any(
            not isinstance(x, dict) or
            x.get("decision") not in ("PASS", "UNSURE", "NEEDS_FIX")
            for x in decision_rows):
        raise VisionImportError("Unverified local reviewer decision.")
    # An UNSURE is a need for new AV evidence, NOT a damaged clip warranting
    # two M31 GPU repairs. M28's importer currently treats it as NEEDS_FIX,
    # so do not send M29 frame-only observations there.
    av_incomplete = any(x["decision"] == "UNSURE" for x in decision_rows)
    if not av_incomplete:
        raise VisionImportError("M29 silent-frame review must be incomplete.")

    with queue._connection() as db:
        paused = db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
        if not paused or paused["paused"]:
            raise VisionImportError("Paused studio cannot import scene review.")
        row = db.execute("""SELECT st.state, st.job_id, st.artifact_sha256,
                st.scene_script_sha256, st.source_voice_sha256,
                j.kind, j.state AS job_state, e.state AS episode_state,
                e.source_sha256, p.episode_script_sha256 AS plan_script,
                v.state AS voice_state, v.artifact_sha256 AS voice_sha
                FROM studio_scene_stages st
                JOIN jobs j ON j.job_id=st.job_id
                JOIN studio_episodes e ON e.series_id=st.series_id
                    AND e.ordinal=st.ordinal
                JOIN studio_scene_plans p ON p.series_id=st.series_id
                    AND p.ordinal=st.ordinal
                JOIN studio_scene_stages v ON v.series_id=st.series_id
                    AND v.ordinal=st.ordinal AND v.scene=st.scene
                    AND v.stage='voice_synthesize'
                WHERE st.series_id=? AND st.ordinal=? AND st.scene=?
                    AND st.stage='ltx_animate'""",
                 (series_id, episode, scene)).fetchone()
        if (not row or row["state"] != "PENDING_QA" or
            row["job_state"] != "COMPLETED" or row["kind"] != "ltx_animate" or
            row["episode_state"] != "SCRIPT_APPROVED" or
            row["source_sha256"] != row["plan_script"] or
            row["voice_state"] != "QA_APPROVED" or
            row["voice_sha"] != row["source_voice_sha256"] or
            row["voice_sha"] != observation["source_voice_sha256"] or
            row["job_id"] != signed["job_id"] or
            row["artifact_sha256"] != signed["artifact_sha256"] or
            row["scene_script_sha256"] != signed["script_sha256"]):
            raise VisionImportError("Stale, unapproved voice or wrong completed Pi LTX job.")
        tech = db.execute("""SELECT report_sha256
            FROM studio_scene_audio_checks
            WHERE series_id=? AND ordinal=? AND scene=? AND ltx_job_id=?""",
            (series_id, episode, scene, row["job_id"])).fetchone()
        if tech and tech["report_sha256"] != tech_sha:
            raise VisionImportError("Different M10 receipt already registered.")
        exists = bool(db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='studio_scene_ai_reviews'""").fetchone())
        ai = (db.execute("""SELECT report_sha256
            FROM studio_scene_ai_reviews
            WHERE series_id=? AND ordinal=? AND scene=? AND
              stage='ltx_animate' AND job_id=?""",
            (series_id, episode, scene, row["job_id"])).fetchone()
            if exists else None)
        if ai:
            raise VisionImportError("Another signed M28 verdict already registered.")

    if execute and not tech:
        # Atomic current-Pi/source/voice revalidation inside M13 registration.
        SceneLedger(queue).register_audio(series_id, episode, scene, m10_report)
    return {
        "status": ("M36_VISUAL_REVIEW_AV_EVIDENCE_REQUIRED" if execute
                   else "M36_SIGNED_CURRENT_VISUAL_PREFLIGHT_NO_WRITES"),
        "scene": scene, "job_id": signed["job_id"],
        "m10_sha256": tech_sha,
        "signed_m29_sha256": signed_sha,
        "technical_receipt_registered": bool(execute or tech),
        "visual_issue_reported": any(x["decision"] == "NEEDS_FIX"
                                      for x in decision_rows),
        "missing_review": ["lip_sync_with_audio", "voice_continuity_with_audio"],
        "scene_ai_approved": False,
        "m31_repair_queued": False,
        "models_executed_by_this_tool": False,
        "owner_post_private_video_review_required": True,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-import-visual-review",
        description="Conservative M29 vision + M10 technical Pi bridge; no fake AV PASS.")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--series", required=True)
    p.add_argument("--episode", type=int, required=True)
    p.add_argument("--scene", type=int, required=True)
    p.add_argument("--report-dir", type=Path, required=True)
    p.add_argument("--m10-report", type=Path, required=True)
    p.add_argument("--rights", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    opts = p.parse_args(argv)
    try:
        result = import_visual_review(queue=StudioQueue(opts.db),
            series_id=opts.series, episode=opts.episode, scene=opts.scene,
            report_dir=opts.report_dir, m10_report=opts.m10_report,
            rights_file=opts.rights,
            runner_key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY", "").encode(),
            execute=opts.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VisionImportError, SceneError, QueueError, OSError, ValueError,
            TypeError, KeyError) as exc:
        print("M36_VISUAL_IMPORT_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
