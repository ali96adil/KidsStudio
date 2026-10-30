"""M62 dedicated PRIVATE recovered-master QA and non-executable YouTube handoff.

Reuses M7's technical checks and M27's independent pedagogy/visual review
contract without forging an ordinary episode_assemble completion. Every
write rechecks the same M61 reservation/source scene lineage. A SHA pins a
transferred file; it does NOT prove that an AI observed media or legally owns
assets. No upload, network call, OAuth, PUBLIC change, or ordinary job insert.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .agent_final_qa import ROLE_CRITERIA, PROVIDER, _file, _obj
from .episode_quality import CHECKS
from .recovery_lease import RecoveryLeaseGate, DONE, RecoveryLeaseError
from .studio_queue import StudioQueue
from .youtube_private_upload import CHANNEL

SHA=re.compile(r"^[a-f0-9]{64}$")
PID=re.compile(r"^[a-f0-9]{32}$")
READY="M62_AI_INTERNAL_READY_PRIVATE_ONLY_NOT_UPLOADED"
FIX="M62_AI_INTERNAL_CHANGES_REQUIRED"
TECH="M62_TECH_PASSED_AWAITING_INDEPENDENT_AI"
STAGED="M62_PRIVATE_UPLOAD_HANDOFF_STAGED_NOT_QUEUED"


class RecoveryQualityError(ValueError):
    """Recovered master lacks current Pi receipts or independent AI QA."""


def _source(db:sqlite3.Connection,proposal_id:str)->tuple[sqlite3.Row,dict]:
    if not isinstance(proposal_id,str) or not PID.fullmatch(proposal_id):
        raise RecoveryQualityError("Exact M56 proposal ID required.")
    row=db.execute("""SELECT * FROM studio_recovery_leases
        WHERE proposal_id=?""",(proposal_id,)).fetchone()
    if not row or row["state"]!=DONE or not row["result_sha256"]:
        raise RecoveryQualityError("Only M61 completed private technical master is eligible.")
    try:
        pins=RecoveryLeaseGate._guard(RecoveryLeaseGate.__new__(
            RecoveryLeaseGate),db,row)
    except Exception as exc:
        # _guard references no other mutable state, except the proposal
        # and current Pi ledger; use a separately configured guard below.
        raise RecoveryQualityError("M61 provenance check refused.") from exc
    if pins["job_id"]!=row["reserved_job_id"]:
        raise RecoveryQualityError("M61 reserved job identity changed.")
    return row,pins


def _load_json(file:str|Path,*,max_bytes:int)->tuple[dict,str]:
    _,raw,sha=_file(file,suffix=".json",max_bytes=max_bytes)
    return _obj(raw),sha


def _validate_observation(
    review:dict,observed:dict,rights:dict,*,
    evidence_sha:str,rights_sha:str,
    master_sha:str,script_sha:str,
    series_id:str,ordinal:int,job_id:str,
)->tuple[bool,str,str]:
    expected_review={"schema_version","series_id","episode_number",
        "render_job_id","media_sha256","script_sha256",
        "observed_evidence_sha256","rights_catalogue_sha256",
        "reviewers","publishing_approved"}
    if (set(review)!=expected_review or
        review["schema_version"]!=1 or
        review["series_id"]!=series_id or
        type(review["episode_number"]) is not int or
        review["episode_number"]!=ordinal or
        review["render_job_id"]!=job_id or
        review["media_sha256"]!=master_sha or
        review["script_sha256"]!=script_sha or
        review["observed_evidence_sha256"]!=evidence_sha or
        review["rights_catalogue_sha256"]!=rights_sha or
        review["publishing_approved"] is not False or
        not isinstance(review["reviewers"],list) or
        len(review["reviewers"])!=2):
        raise RecoveryQualityError("M62 exact M27 review bundle lineage required.")
    if (not isinstance(observed,dict) or set(observed)!={
            "schema_version","media_sha256","script_sha256",
            "transcript_sha256","frames_manifest_sha256",
            "audio_analysis_sha256","sampling_complete",
            "subjective_quality_verified","publishing_approved"} or
        observed["schema_version"]!=1 or
        observed["media_sha256"]!=master_sha or
        observed["script_sha256"]!=script_sha or
        any(not isinstance(observed[x],str) or not SHA.fullmatch(observed[x])
            for x in ("transcript_sha256","frames_manifest_sha256",
                      "audio_analysis_sha256")) or
        observed["sampling_complete"] is not True or
        observed["subjective_quality_verified"] is not False or
        observed["publishing_approved"] is not False):
        raise RecoveryQualityError("M62 frame/audio/transcript observation evidence required.")
    if (not isinstance(rights,dict) or set(rights)!={
            "schema_version","media_sha256","assets",
            "all_assets_accounted_for","publishing_approved"} or
        rights["schema_version"]!=1 or rights["media_sha256"]!=master_sha or
        rights["all_assets_accounted_for"] is not True or
        rights["publishing_approved"] is not False or
        not isinstance(rights["assets"],list) or
        not 1<=len(rights["assets"])<=100):
        raise RecoveryQualityError("M62 external asset-rights evidence incomplete.")
    asset_shas=set()
    for asset in rights["assets"]:
        if (not isinstance(asset,dict) or set(asset)!={
                "asset_sha256","provenance_kind","proof_sha256",
                "use_scope","rights_status"} or
            any(not isinstance(asset[k],str) or not SHA.fullmatch(asset[k])
                for k in ("asset_sha256","proof_sha256")) or
            asset["asset_sha256"] in asset_shas or
            asset["provenance_kind"] not in (
                "original_created","licensed","public_domain_verified") or
            asset["use_scope"]!="commercial_youtube_kids" or
            asset["rights_status"]!="DOCUMENTED_NOT_LEGALLY_ADJUDICATED"):
            raise RecoveryQualityError("M62 media rights not independently documented.")
        asset_shas.add(asset["asset_sha256"])
    roles={}
    providers=set()
    passes=[]
    for reviewer in review["reviewers"]:
        if not isinstance(reviewer,dict) or set(reviewer)!={
                "role","provider_id","model_id","evidence_sha256",
                "criteria","summary","release_approved"}:
            raise RecoveryQualityError("M62 reviewer role fields invalid.")
        role=reviewer["role"]
        provider=reviewer["provider_id"]
        if (role not in ROLE_CRITERIA or role in roles or
            not isinstance(provider,str) or not PROVIDER.fullmatch(provider) or
            provider in providers or
            not isinstance(reviewer["model_id"],str) or
            not 3<=len(reviewer["model_id"])<=120 or
            reviewer["evidence_sha256"]!=evidence_sha or
            reviewer["release_approved"] is not False or
            not isinstance(reviewer["summary"],str) or
            not 25<=len(reviewer["summary"].strip())<=1500 or
            not isinstance(reviewer["criteria"],dict) or
            set(reviewer["criteria"])!=ROLE_CRITERIA[role]):
            raise RecoveryQualityError("M62 independent AI reviewer evidence malformed.")
        for criterion in reviewer["criteria"].values():
            if (not isinstance(criterion,dict) or
                set(criterion)!={"decision","evidence"} or
                criterion["decision"] not in ("PASS","NEEDS_FIX","UNSURE") or
                not isinstance(criterion["evidence"],str) or
                not 25<=len(criterion["evidence"].strip())<=800):
                raise RecoveryQualityError("M62 each review criterion needs observed evidence.")
            passes.append(criterion["decision"]=="PASS")
        providers.add(provider)
        roles[role]=reviewer
    if set(roles)!=set(ROLE_CRITERIA):
        raise RecoveryQualityError("M62 two distinct pedagogy/visual roles required.")
    return (all(passes),roles["pedagogy_language"]["provider_id"],
            roles["visual_child_safety"]["provider_id"])


class RecoveryFinalQA:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                    type='table' AND name='studio_recovery_leases'""").fetchone():
                raise RecoveryQualityError("M61 recovery lease schema required.")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_final_qa(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_leases(proposal_id),
                recovery_job_id TEXT NOT NULL UNIQUE,
                master_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,
                tech_report_sha256 TEXT NOT NULL,
                review_bundle_sha256 TEXT,
                observed_evidence_sha256 TEXT,
                rights_catalogue_sha256 TEXT,
                pedagogy_provider TEXT,
                visual_provider TEXT,
                state TEXT NOT NULL CHECK(state IN (
                    'M62_TECH_PASSED_AWAITING_INDEPENDENT_AI',
                    'M62_AI_INTERNAL_READY_PRIVATE_ONLY_NOT_UPLOADED',
                    'M62_AI_INTERNAL_CHANGES_REQUIRED')),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_private_handoffs(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_final_qa(proposal_id),
                recovery_job_id TEXT NOT NULL UNIQUE,
                master_sha256 TEXT NOT NULL,
                review_bundle_sha256 TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                policy_revision INTEGER NOT NULL,
                made_for_kids INTEGER NOT NULL,
                contains_synthetic_media INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(
                    state='M62_PRIVATE_UPLOAD_HANDOFF_STAGED_NOT_QUEUED'),
                created_at REAL NOT NULL
            )""")

    def _source(self,db:sqlite3.Connection,proposal_id:str)->tuple[sqlite3.Row,dict]:
        if not isinstance(proposal_id,str) or not PID.fullmatch(proposal_id):
            raise RecoveryQualityError("M62 exact proposal ID required.")
        row=db.execute("""SELECT * FROM studio_recovery_leases
            WHERE proposal_id=?""",(proposal_id,)).fetchone()
        if not row or row["state"]!=DONE or not row["result_sha256"]:
            raise RecoveryQualityError("M62 requires a completed M61 private master.")
        try:pins=RecoveryLeaseGate(self.queue)._guard(db,row)
        except (RecoveryLeaseError,sqlite3.Error,OSError,ValueError) as exc:
            raise RecoveryQualityError("M62 original Pi source/scene lineage revoked.") from exc
        return row,pins

    def register_technical(self,proposal_id:str,report_file:str|Path)->dict:
        report,report_sha=_load_json(report_file,max_bytes=150_000)
        if (set(report)!={"schema_version","status",
                "media_sha256","expected_media_sha256",
                "file_bytes","duration_seconds","checks",
                "subjective_checks_performed","rights_verified",
                "publishing_approved"} or report["schema_version"]!=1 or
            report["status"]!="TECH_PASS_OWNER_REVIEW_PENDING" or
            not isinstance(report["checks"],dict) or
            set(report["checks"])!=set(CHECKS) or
            any(report["checks"][check] is not True for check in CHECKS) or
            report["subjective_checks_performed"] is not False or
            report["rights_verified"] is not False or
            report["publishing_approved"] is not False or
            type(report["file_bytes"]) is not int or
            not 0<report["file_bytes"]<=2_000_000_000 or
            type(report["duration_seconds"]) not in (int,float) or
            not 2<=report["duration_seconds"]<=900):
            raise RecoveryQualityError("M62 requires full M7 independent technical report.")
        with self.queue._connection(write=True) as db:
            row,pins=self._source(db,proposal_id)
            if (report["media_sha256"]!=row["result_sha256"] or
                report["expected_media_sha256"]!=row["result_sha256"]):
                raise RecoveryQualityError("M62 M7 report is not this recovered master.")
            if db.execute("""SELECT 1 FROM studio_recovery_final_qa
                WHERE proposal_id=?""",(proposal_id,)).fetchone():
                raise RecoveryQualityError("M62 existing technical QA cannot be overwritten.")
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_recovery_final_qa(
                proposal_id,recovery_job_id,master_sha256,script_sha256,
                tech_report_sha256,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",(
                proposal_id,row["reserved_job_id"],row["result_sha256"],
                pins["script_sha256"],report_sha,TECH,now,now))
            self.queue._event(db,pins["original_job_id"],
                "M62_RECOVERY_M7_TECHNICAL_REPORT_PINNED",
                {"proposal_id":proposal_id})
        return {"status":TECH,"proposal_id":proposal_id,
                "media_sha256":report["media_sha256"],
                "pi_verified_mac_video_bytes":False,
                "public_release_authorized":False}

    def register_ai(self,proposal_id:str,*,review_bundle:str|Path,
                    observed_media_evidence:str|Path,
                    rights_catalogue:str|Path)->dict:
        review,bundle_sha=_load_json(review_bundle,max_bytes=100_000)
        evidence,evidence_sha=_load_json(observed_media_evidence,max_bytes=500_000)
        rights,rights_sha=_load_json(rights_catalogue,max_bytes=100_000)
        with self.queue._connection(write=True) as db:
            lease,pins=self._source(db,proposal_id)
            row=db.execute("""SELECT * FROM studio_recovery_final_qa
                WHERE proposal_id=?""",(proposal_id,)).fetchone()
            if (not row or row["state"]!=TECH or
                row["recovery_job_id"]!=lease["reserved_job_id"] or
                row["master_sha256"]!=lease["result_sha256"] or
                row["script_sha256"]!=pins["script_sha256"]):
                raise RecoveryQualityError("M62 fresh technical report/identities required.")
            original=db.execute("""SELECT series_id,ordinal FROM
                studio_recovery_intents WHERE proposal_id=?""",
                (proposal_id,)).fetchone()
            if not original:
                raise RecoveryQualityError("M62 original episode metadata unavailable.")
            all_pass,pedagogy,visual=_validate_observation(
                review,evidence,rights,
                evidence_sha=evidence_sha,rights_sha=rights_sha,
                master_sha=row["master_sha256"],script_sha=row["script_sha256"],
                series_id=original["series_id"],ordinal=original["ordinal"],
                job_id=row["recovery_job_id"])
            state=READY if all_pass else FIX
            now=self.queue.clock()
            db.execute("""UPDATE studio_recovery_final_qa SET
                state=?,review_bundle_sha256=?,observed_evidence_sha256=?,
                rights_catalogue_sha256=?,pedagogy_provider=?,
                visual_provider=?,updated_at=? WHERE proposal_id=?""",
                (state,bundle_sha,evidence_sha,rights_sha,
                 pedagogy,visual,now,proposal_id))
            if not all_pass:
                db.execute("""INSERT INTO studio_series_notes(
                    series_id,ordinal,note,created_at) VALUES(?,?,?,?)""",
                    (original["series_id"],original["ordinal"],
                     "M62 RECOVERY AI QA NEEDS FIX — independent internal review",
                     now))
            self.queue._event(db,pins["original_job_id"],
                "M62_RECOVERY_AI_PRIVATE_READY" if all_pass
                else "M62_RECOVERY_AI_FIX_REQUIRED",
                {"proposal_id":proposal_id})
        return {"status":state,"proposal_id":proposal_id,
                "independent_provider_count":2,
                "rights_legal_certainty_proven":False,
                "owner_post_private_upload_review_required":True,
                "public_release_authorized":False}

    def stage_private_handoff(self,proposal_id:str,*,channel_id:str,
                              made_for_kids:bool,
                              contains_synthetic_media:bool)->dict:
        if (not isinstance(channel_id,str) or not CHANNEL.fullmatch(channel_id)
            or type(made_for_kids) is not bool or
            type(contains_synthetic_media) is not bool):
            raise RecoveryQualityError("M62 explicit exact upload audience/channel required.")
        with self.queue._connection(write=True) as db:
            lease,pins=self._source(db,proposal_id)
            qa=db.execute("""SELECT * FROM studio_recovery_final_qa
                WHERE proposal_id=?""",(proposal_id,)).fetchone()
            episode=db.execute("""SELECT i.series_id,i.ordinal,e.state AS
                episode_state,s.state AS series_state
                FROM studio_recovery_intents i
                JOIN studio_episodes e
                ON e.series_id=i.series_id AND e.ordinal=i.ordinal
                JOIN studio_series s ON s.series_id=i.series_id
                WHERE i.proposal_id=?""",(proposal_id,)).fetchone()
            if (not qa or qa["state"]!=READY or not episode or
                episode["episode_state"]!="BLOCKED" or
                episode["series_state"]!="ACTIVE" or
                qa["master_sha256"]!=lease["result_sha256"] or
                qa["recovery_job_id"]!=lease["reserved_job_id"] or
                qa["script_sha256"]!=pins["script_sha256"] or
                not qa["tech_report_sha256"] or not qa["review_bundle_sha256"] or
                not qa["observed_evidence_sha256"] or
                not qa["rights_catalogue_sha256"]):
                raise RecoveryQualityError("M62 complete independent private QA required.")
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_youtube_private_policies'""").fetchone():
                raise RecoveryQualityError("M62 owner M26 standing private policy missing.")
            policy=db.execute("""SELECT * FROM studio_youtube_private_policies
                WHERE series_id=?""",(episode["series_id"],)).fetchone()
            if (not policy or policy["state"]!="ENABLED" or
                policy["channel_id"]!=channel_id or
                bool(policy["allowed_made_for_kids"])!=made_for_kids or
                bool(policy["allowed_synthetic_media"])!=contains_synthetic_media):
                raise RecoveryQualityError("M62 policy does not authorize this private channel.")
            if db.execute("""SELECT 1 FROM studio_recovery_private_handoffs
                WHERE proposal_id=?""",(proposal_id,)).fetchone():
                raise RecoveryQualityError("M62 private handoff already staged.")
            # M26 still rejects recovered jobs. DO NOT insert an upload job
            # into its ordinary queue or forge an EPISODE_APPROVED state.
            db.execute("""INSERT INTO studio_recovery_private_handoffs
                VALUES(?,?,?,?,?,?,?,?,?,?)""",(
                proposal_id,lease["reserved_job_id"],qa["master_sha256"],
                qa["review_bundle_sha256"],channel_id,policy["revision"],
                int(made_for_kids),int(contains_synthetic_media),
                STAGED,self.queue.clock()))
            self.queue._event(db,pins["original_job_id"],
                "M62_RECOVERY_PRIVATE_HANDOFF_STAGED_NOT_QUEUED",
                {"proposal_id":proposal_id,"policy_revision":policy["revision"]})
        return {"status":STAGED,"proposal_id":proposal_id,
                "recovery_job_id":lease["reserved_job_id"],
                "master_sha256":qa["master_sha256"],
                "channel_id":channel_id,"visibility":"PRIVATE_ONLY",
                "youtube_upload_job_created":False,
                "network_used":False,"oauth_used":False,
                "owner_post_private_upload_review_required":True,
                "public_release_authorized":False}
