"""M35 exact current Pi voice-review import; private-only and replay-safe.

M34 executes local WAV/ASR/audio review. This bridge consumes its existing
signed evidence; it neither runs a model nor grants any publication right.
Write ordering permits a safe retry after an interrupted M23 -> M28 import.
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


class AudioImportError(ValueError):
    pass


def _document(path: Path) -> tuple[dict, str]:
    raw, sha = _private(path, 100_000, ".json")
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise AudioImportError("Malformed private M34 report.") from exc
    if not isinstance(doc, dict):
        raise AudioImportError("M34 evidence must be a JSON object.")
    return doc, sha


def import_voice_review(*, queue: StudioQueue, series_id: str,
                        episode: int, scene: int, report_dir: str | Path,
                        rights_file: str | Path, runner_key: bytes,
                        execute: bool = False) -> dict:
    """Verify current completed voice job before importing M23/M28 evidence.

    A successful import with AI_SCENE_NEEDS_FIX is NOT an approval. M31 may
    subsequently schedule a scoped repair. No model, video, upload or PUBLIC
    side effect is offered here.
    """
    if (not isinstance(series_id, str) or not series_id or
        type(episode) is not int or not 1 <= episode <= 120 or
        type(scene) is not int or not 1 <= scene <= 40 or
        type(execute) is not bool or not isinstance(runner_key, bytes) or
        len(runner_key) < 32):
        raise AudioImportError("Exact scene identity and trusted key required.")
    folder = Path(report_dir).expanduser()
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise AudioImportError("Existing absolute private M34 output folder required.")
    folder = folder.resolve()
    report_path = folder / "signed_voice_m28.json"
    technical_path = folder / "voice_technical.json"
    observation_path = folder / "observations.json"
    report, report_sha = _document(report_path)
    technical, technical_sha = _document(technical_path)
    observation, observation_sha = _document(observation_path)
    _, rights_sha = _document(Path(rights_file))
    if (report.get("series_id") != series_id or
        report.get("episode_number") != episode or
        report.get("scene") != scene or
        report.get("stage") != "voice_synthesize" or
        report.get("schema_version") != 1 or
        report.get("publication_approved") is not False or
        report.get("technical_sha256") != technical_sha or
        report.get("observations_sha256") != observation_sha or
        report.get("rights_sha256") != rights_sha or
        technical.get("status") != "VOICE_TECH_PASS_OWNER_LISTENING_PENDING" or
        technical.get("job_id") != report.get("job_id") or
        technical.get("voice_sha256") != report.get("artifact_sha256") or
        technical.get("script_sha256") != report.get("script_sha256") or
        observation.get("artifact_sha256") != report.get("artifact_sha256") or
        observation.get("script_sha256") != report.get("script_sha256") or
        not isinstance(report.get("artifact_sha256"), str) or
        not SHA.fullmatch(report["artifact_sha256"])):
        raise AudioImportError("M34 source identity or signed receipt links mismatch.")
    signature = report.get("runner_attestation")
    if not isinstance(signature, dict) or set(signature) != {
        "runner_id", "runtime_status", "hmac_sha256"
    } or signature.get("runtime_status") != "REVIEW_MODELS_EXECUTED":
        raise AudioImportError("Trusted M34 attestation missing.")
    unsigned = {key: value for key, value in report.items()
                if key != "runner_attestation"}
    signed_bytes = json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).encode("utf-8")
    expected = hmac.new(runner_key, signed_bytes, hashlib.sha256).hexdigest()
    if not isinstance(signature.get("hmac_sha256"), str) or not hmac.compare_digest(
            expected, signature["hmac_sha256"]):
        raise AudioImportError("Untrusted or altered M34 signature.")

    # Read current Pi source, not a receipt from a previous revision/job.
    with queue._connection() as db:
        pause = db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
        if pause is None or pause["paused"]:
            raise AudioImportError("Studio is paused; no review state change.")
        row = db.execute("""SELECT st.state, st.job_id, st.artifact_sha256,
                  st.scene_script_sha256, j.state AS job_state, j.kind,
                  ep.state AS episode_state, ep.source_sha256,
                  p.episode_script_sha256 AS planned_sha256
                  FROM studio_scene_stages st
                  JOIN jobs j ON j.job_id=st.job_id
                  JOIN studio_episodes ep ON ep.series_id=st.series_id
                    AND ep.ordinal=st.ordinal
                  JOIN studio_scene_plans p ON p.series_id=st.series_id
                    AND p.ordinal=st.ordinal
                  WHERE st.series_id=? AND st.ordinal=? AND st.scene=?
                    AND st.stage='voice_synthesize'""",
                 (series_id, episode, scene)).fetchone()
        if (not row or row["state"] not in ("PENDING_QA", "QA_APPROVED")
            or row["job_state"] != "COMPLETED" or
            row["kind"] != "voice_synthesize" or
            row["episode_state"] != "SCRIPT_APPROVED" or
            row["source_sha256"] != row["planned_sha256"] or
            row["job_id"] != report["job_id"] or
            row["artifact_sha256"] != report["artifact_sha256"] or
            row["scene_script_sha256"] != report["script_sha256"]):
            raise AudioImportError("M34 review is not for the current completed Pi job.")
        tech = db.execute("""SELECT report_sha256 FROM studio_scene_voice_checks
            WHERE series_id=? AND ordinal=? AND scene=? AND voice_job_id=?""",
            (series_id, episode, scene, row["job_id"])).fetchone()
        has_ai = bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_scene_ai_reviews'""").fetchone())
        ai = (db.execute("""SELECT report_sha256, state
            FROM studio_scene_ai_reviews
            WHERE series_id=? AND ordinal=? AND scene=? AND stage='voice_synthesize'
              AND job_id=?""", (series_id, episode, scene, row["job_id"])).fetchone()
              if has_ai else None)
        if (tech and tech["report_sha256"] != technical_sha) or (
                ai and ai["report_sha256"] != report_sha):
            raise AudioImportError("Different review already bound to this Pi job.")
        if row["state"] == "QA_APPROVED" and (
                not tech or not ai or ai["state"] != "AI_SCENE_READY_PRIVATE_ONLY"):
            raise AudioImportError("Approved stage does not match this review.")
        if ai and not tech:
            raise AudioImportError("AI report exists without technical evidence.")
        previous_state = row["state"]
        ai_state = ai["state"] if ai else None

    if not execute:
        return {
            "status": "M35_CURRENT_SIGNED_REPORT_PREFLIGHT_NO_WRITES",
            "scene": scene, "job_id": report["job_id"],
            "technical_sha256": technical_sha,
            "signed_report_sha256": report_sha,
            "previously_registered": bool(ai),
            "models_executed_by_this_tool": False,
            "mac_pi_hardware_test_ready": False,
            "owner_post_private_video_review_required": True,
            "public_release_authorized": False,
        }
    if previous_state == "QA_APPROVED":
        state = "M35_ALREADY_IMPORTED_PRIVATE_STAGE_APPROVED"
    else:
        ledger = SceneLedger(queue)
        gate = SceneAIGate(queue, attestation_key=runner_key)
        gate.initialize()
        # M23 is an immutable prerequisite. A crash after M23 can be retried
        # only using this exact same technical SHA. The M28 importer still
        # independently rechecks every byte, criterion and Pi job atomically.
        if not tech:
            ledger.register_voice_technical(
                series_id, episode, scene, technical_path)
        if not ai:
            verdict = gate.register(series_id, episode, scene,
                "voice_synthesize", report_file=report_path,
                observation_file=observation_path, rights_file=rights_file)
            ai_state = verdict["status"]
        if ai_state == "AI_SCENE_READY_PRIVATE_ONLY":
            gate.auto_approve(series_id, episode, scene, "voice_synthesize")
            state = "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY"
        else:
            state = "M35_AI_VOICE_NEEDS_FIX_PRIVATE_ONLY"
    return {
        "status": state, "scene": scene, "job_id": report["job_id"],
        "technical_sha256": technical_sha,
        "signed_report_sha256": report_sha,
        "models_executed_by_this_tool": False,
        "owner_post_private_video_review_required": True,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-import-audio-review",
        description="Import existing signed M34 voice evidence into current Pi M23/M28.")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--series", required=True)
    p.add_argument("--episode", type=int, required=True)
    p.add_argument("--scene", type=int, required=True)
    p.add_argument("--report-dir", type=Path, required=True)
    p.add_argument("--rights", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args(argv)
    try:
        result = import_voice_review(queue=StudioQueue(args.db),
            series_id=args.series, episode=args.episode, scene=args.scene,
            report_dir=args.report_dir, rights_file=args.rights,
            runner_key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY", "").encode(),
            execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AudioImportError, SceneError, QueueError, OSError, ValueError,
            TypeError, KeyError) as exc:
        print("M35_AUDIO_IMPORT_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
