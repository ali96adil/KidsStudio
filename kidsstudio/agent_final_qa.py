"""M27 opt-in two-independent-agent internal QA before PRIVATE review.

This module checks evidence/lineage, not whether model judgments are true.
A model verdict cannot establish copyright ownership, rights, actual
observation, or YouTube policy compliance. Review adapters must supply
independently generated audiovisual evidence and a separately verified
asset-rights catalogue; missing evidence blocks the private upload.
No API/model is run here and NOTHING authorizes PUBLIC release.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from .episode_assembly import _ensure_private
from .studio_queue import StudioQueue
from .studio_quality_ledger import QualityGateError, CRITERIA

SHA = re.compile(r"^[a-f0-9]{64}$")
PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
ROLE_CRITERIA = {
    "pedagogy_language": frozenset({
        "learning_objective", "age_appropriate_pedagogy",
        "language_pronunciation", "accessibility_and_subtitles",
        "originality_and_attribution",
    }),
    "visual_child_safety": frozenset({
        "character_consistency", "lip_sync_and_motion", "audio_mix",
        "child_safety", "full_episode_watch",
    }),
}
UNASSESSED_RIGHTS = "music_voice_visual_rights"


def _file(file: str | Path, *, suffix: str, max_bytes: int) -> tuple[Path,bytes,str]:
    p=Path(file).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.suffix.lower()!=suffix:
        raise QualityGateError("Absolute non-symlink private evidence required.")
    p=p.resolve()
    _ensure_private(p.parent)
    if not p.is_file() or not 0<p.stat().st_size<=max_bytes:
        raise QualityGateError("Missing/oversized internal QA evidence.")
    data=p.read_bytes()
    return p,data,hashlib.sha256(data).hexdigest()


def _obj(raw:bytes)->dict:
    try: item=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise QualityGateError("Invalid internal QA JSON.") from exc
    if not isinstance(item,dict):
        raise QualityGateError("Internal QA must be a JSON object.")
    return item


class AgentFinalQA:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_ai_final_reviews (
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                render_job_id TEXT NOT NULL,media_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,review_bundle_sha256 TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,rights_sha256 TEXT NOT NULL,
                pedagogy_provider TEXT NOT NULL,visual_provider TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,render_job_id),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")

    def register(self, series_id: str, ordinal: int, *,
                 review_bundle: str | Path,
                 observed_media_evidence: str | Path,
                 rights_catalogue: str | Path) -> dict:
        _,raw,bundle_sha=_file(review_bundle,suffix=".json",max_bytes=100000)
        _,evidence_bytes,evidence_sha=_file(
            observed_media_evidence,suffix=".json",max_bytes=500000)
        _,rights_bytes,rights_sha=_file(
            rights_catalogue,suffix=".json",max_bytes=100000)
        review=_obj(raw); evidence=_obj(evidence_bytes); rights=_obj(rights_bytes)

        if (set(review)!={"schema_version","series_id","episode_number",
                           "render_job_id","media_sha256","script_sha256",
                           "observed_evidence_sha256","rights_catalogue_sha256",
                           "reviewers","publishing_approved"} or
            type(review["schema_version"]) is not int or review["schema_version"]!=1 or
            review["publishing_approved"] is not False or
            type(review["episode_number"]) is not int or
            review["series_id"]!=series_id or review["episode_number"]!=ordinal or
            review["observed_evidence_sha256"]!=evidence_sha or
            review["rights_catalogue_sha256"]!=rights_sha or
            not isinstance(review["reviewers"],list) or len(review["reviewers"])!=2):
            raise QualityGateError("Two independent reviewers must share pinned evidence.")
        reviewers={}
        providers=set()
        for item in review["reviewers"]:
            if not isinstance(item,dict) or set(item)!={
                "role","provider_id","model_id","evidence_sha256",
                "criteria","summary","release_approved"}:
                raise QualityGateError("Reviewer identity/evidence fields invalid.")
            role=item["role"]
            provider=item["provider_id"]
            if (role not in ROLE_CRITERIA or role in reviewers or
                not isinstance(provider,str) or not PROVIDER.fullmatch(provider) or
                provider in providers or
                not isinstance(item["model_id"],str) or
                not 3<=len(item["model_id"])<=120 or
                item["evidence_sha256"]!=evidence_sha or
                item["release_approved"] is not False or
                not isinstance(item["summary"],str) or
                not 25<=len(item["summary"].strip())<=1500):
                raise QualityGateError("Independent review identity or provenance invalid.")
            criteria=item["criteria"]
            if not isinstance(criteria,dict) or set(criteria)!=ROLE_CRITERIA[role]:
                raise QualityGateError("Missing or unexpected AI review criteria.")
            for name,row in criteria.items():
                if (not isinstance(row,dict) or set(row)!={"decision","evidence"} or
                    row["decision"] not in ("PASS","NEEDS_FIX","UNSURE") or
                    not isinstance(row["evidence"],str) or
                    not 25<=len(row["evidence"].strip())<=800):
                    raise QualityGateError("Every criterion requires written observed evidence.")
            reviewers[role]=item
            providers.add(provider)
        if set(reviewers)!=set(ROLE_CRITERIA):
            raise QualityGateError("Both pedagogical and audiovisual reviewer required.")

        # The evidence manifest contains hashes of separately extracted
        # transcript, sampled frames and decoded audio checks. SHA checks
        # bind artifacts; they do not prove the agent actually inspected them.
        if (not isinstance(evidence,dict) or set(evidence)!={
            "schema_version","media_sha256","script_sha256",
            "transcript_sha256","frames_manifest_sha256",
            "audio_analysis_sha256","sampling_complete",
            "subjective_quality_verified","publishing_approved"} or
            evidence["schema_version"]!=1 or
            any(not isinstance(evidence[k],str) or not SHA.fullmatch(evidence[k])
                for k in ("media_sha256","script_sha256","transcript_sha256",
                          "frames_manifest_sha256","audio_analysis_sha256")) or
            evidence["sampling_complete"] is not True or
            evidence["subjective_quality_verified"] is not False or
            evidence["publishing_approved"] is not False):
            raise QualityGateError("Audio/transcript/visual source evidence missing.")

        # Asset rights must be supplied by a SEPARATE provenance catalogue.
        # AI-written claims or free-text "commercial rights verified" aren't
        # accepted as substitutes for each specific source proof hash.
        if (not isinstance(rights,dict) or set(rights)!={
            "schema_version","media_sha256","assets",
            "all_assets_accounted_for","publishing_approved"} or
            rights["schema_version"]!=1 or rights["media_sha256"]!=review["media_sha256"] or
            rights["all_assets_accounted_for"] is not True or
            rights["publishing_approved"] is not False or
            not isinstance(rights["assets"],list) or
            not 1<=len(rights["assets"])<=100):
            raise QualityGateError("Immutable rights source catalogue required.")
        fingerprints=set()
        for asset in rights["assets"]:
            if (not isinstance(asset,dict) or set(asset)!={
                "asset_sha256","provenance_kind","proof_sha256",
                "use_scope","rights_status"} or
                any(not isinstance(asset[k],str) or not SHA.fullmatch(asset[k])
                    for k in ("asset_sha256","proof_sha256")) or
                asset["asset_sha256"] in fingerprints or
                asset["provenance_kind"] not in (
                    "original_created","licensed","public_domain_verified") or
                asset["use_scope"]!="commercial_youtube_kids" or
                asset["rights_status"]!="DOCUMENTED_NOT_LEGALLY_ADJUDICATED"):
                raise QualityGateError("Undocumented, duplicated or unlicensed input.")
            fingerprints.add(asset["asset_sha256"])

        if (evidence["media_sha256"]!=review["media_sha256"] or
            evidence["script_sha256"]!=review["script_sha256"]):
            raise QualityGateError("Cross-source media/script digest mismatch.")
        all_pass=all(
            x["decision"]=="PASS"
            for item in reviewers.values() for x in item["criteria"].values())
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT state,render_job_id,source_sha256 FROM
                studio_episodes WHERE series_id=? AND ordinal=?""",
                (series_id,ordinal)).fetchone()
            if (not ep or ep["state"]!="RENDERED_QA_PENDING"
                or ep["source_sha256"]!=review["script_sha256"]
                or ep["render_job_id"]!=review["render_job_id"]):
                raise QualityGateError("Episode or source script no longer current.")
            qa=db.execute("""SELECT * FROM studio_quality_reviews WHERE
                series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,ep["render_job_id"])).fetchone()
            if (not qa or qa["state"]!="TECH_PASSED_WAITING_HUMAN" or
                qa["media_sha256"]!=review["media_sha256"] or
                not qa["tech_report_sha256"]):
                raise QualityGateError("Current completed M7 technical QA required.")
            prior=db.execute("""SELECT 1 FROM studio_ai_final_reviews WHERE
                series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,ep["render_job_id"])).fetchone()
            if prior:
                raise QualityGateError("Agent review already registered; no overwrite.")
            state=("AI_INTERNAL_READY_PRIVATE_ONLY" if all_pass
                   else "AI_INTERNAL_CHANGES_REQUIRED")
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_ai_final_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (series_id,ordinal,ep["render_job_id"],qa["media_sha256"],
                 ep["source_sha256"],bundle_sha,evidence_sha,rights_sha,
                 reviewers["pedagogy_language"]["provider_id"],
                 reviewers["visual_child_safety"]["provider_id"],state,now))
            db.execute("""UPDATE studio_quality_reviews SET
                state=?,review_report_sha256=?,checks_passed=?,updated_at=?
                WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                (state,bundle_sha,11 if all_pass else 0,
                 now,series_id,ordinal,ep["render_job_id"]))
            if not all_pass:
                failures=[name for item in reviewers.values()
                          for name,x in item["criteria"].items()
                          if x["decision"]!="PASS"]
                db.execute("""INSERT INTO studio_series_notes
                    (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                    (series_id,ordinal,
                     "M27 AI TRIAGE: "+", ".join(sorted(failures)),now))
            db.execute("""INSERT INTO studio_quality_audit
                (series_id,ordinal,render_job_id,event,created_at)
                VALUES (?,?,?,?,?)""",
                (series_id,ordinal,ep["render_job_id"],
                 "M27_TWO_INDEPENDENT_AI_REPORTS_READY" if all_pass
                 else "M27_AI_REVIEW_NEEDS_FIX",now))
        return {
            "status":state,"series_id":series_id,
            "episode_number":ordinal,
            "media_sha256":review["media_sha256"],
            "agent_qa_bundle_sha256":bundle_sha,
            "distinct_provider_count":2,
            "rights_legal_certainty_proven":False,
            "owner_video_review_required_after_private_upload":True,
            "publishing_approved":False,
        }
