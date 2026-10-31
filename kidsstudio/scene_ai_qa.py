"""M28: independent AI scene-stage QA with deterministic evidence checks.

This is an importer of externally generated AI judgments, NOT an AI runtime.
Real ASR and vision reviewers must be installed/qualified separately.
Fail closed when source text, actual file bytes, technical receipt, separate
reviewer identity or image observations are absent. No PUBLIC permission.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import re
import unicodedata

from .episode_assembly import _ensure_private
from .studio_queue import StudioQueue
from .studio_scenes import SceneError, STAGES, SHA

ROLE_CHECKS = {
    "voice_synthesize": {
        "pronunciation": frozenset({"pronunciation", "clarity", "script_fidelity"}),
        "child_audio_safety": frozenset({"age_appropriate", "emotional_tone", "audio_content_safety"}),
    },
    "ltx_animate": {
        "motion_sync": frozenset({"lip_sync", "voice_continuity", "character_motion"}),
        "visual_child_safety": frozenset({"age_appropriate", "visual_consistency", "no_unsafe_content"}),
    },
}
PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
WORD = re.compile(r"[\w\u0621-\u064a]+", re.UNICODE)


def _private(path: str | Path, max_bytes: int, suffix: str) -> tuple[bytes, str]:
    p=Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.suffix.lower()!=suffix:
        raise SceneError("Absolute private, non-symlink evidence file required.")
    p=p.resolve()
    _ensure_private(p.parent)
    if not p.is_file() or not 0<p.stat().st_size<=max_bytes:
        raise SceneError("Evidence unavailable or oversized.")
    raw=p.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest()


def _read_json(raw: bytes) -> dict:
    try: data=json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise SceneError("Invalid scene AI review JSON.") from exc
    if not isinstance(data,dict):
        raise SceneError("AI scene evidence must be an object.")
    return data


def _normalize(text: str) -> list[str]:
    if not isinstance(text,str) or not 1<=len(text)<=12000:
        raise SceneError("Empty or oversized transcript/script.")
    text=unicodedata.normalize("NFKC",text).casefold()
    text="".join(c for c in text if unicodedata.category(c)!="Mn")
    # Arabic orthographic variants, avoiding punctuation and elongation.
    text=text.translate(str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ٱ":"ا",
                                       "ى":"ي","ـ":""}))
    return WORD.findall(text)


def _word_error_rate(reference: str, hypothesis: str) -> float:
    a,b=_normalize(reference),_normalize(hypothesis)
    if not a or not b:
        raise SceneError("Meaningful script and ASR transcript required.")
    if len(a)>1500 or len(b)>1500:
        raise SceneError("Unbounded ASR comparison denied.")
    previous=list(range(len(b)+1))
    for i,word in enumerate(a,1):
        row=[i]
        for j,other in enumerate(b,1):
            row.append(min(row[-1]+1, previous[j]+1,
                           previous[j-1]+int(word!=other)))
        previous=row
    return previous[-1]/len(a)


class SceneAIGate:
    def __init__(self, queue: StudioQueue, *, attestation_key: bytes | None = None):
        self.queue=queue
        # A trusted local model-execution worker must own this key; no
        # recipient-chosen provider name is an authenticated proof.
        self.attestation_key=attestation_key

    def initialize(self) -> None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_ai_reviews(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL,stage TEXT NOT NULL,
                job_id TEXT NOT NULL,artifact_sha256 TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,report_sha256 TEXT NOT NULL,
                rights_sha256 TEXT NOT NULL,observation_sha256 TEXT NOT NULL,
                technical_sha256 TEXT NOT NULL,
                first_provider TEXT NOT NULL,second_provider TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN (
                  'AI_SCENE_READY_PRIVATE_ONLY','AI_SCENE_NEEDS_FIX')),
                word_error_rate REAL, created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,stage,job_id),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")

    def register(self,sid:str,ordinal:int,scene:int,stage:str, *,
                 report_file:str|Path,
                 observation_file:str|Path,
                 rights_file:str|Path)->dict:
        if stage not in ROLE_CHECKS or type(ordinal) is not int or type(scene) is not int:
            raise SceneError("Valid scene and AI stage required.")
        raw,report_sha=_private(report_file,100000,".json")
        obs_raw,obs_sha=_private(observation_file,100000,".json")
        rights_raw,rights_sha=_private(rights_file,100000,".json")
        report=_read_json(raw); obs=_read_json(obs_raw); rights=_read_json(rights_raw)
        required={"schema_version","series_id","episode_number","scene",
                  "stage","job_id","script_sha256","artifact_sha256",
                  "observations_sha256","rights_sha256","technical_sha256",
                  "reviewers","publication_approved","runner_attestation"}
        if (not isinstance(self.attestation_key,bytes) or
            len(self.attestation_key)<32):
            raise SceneError("Trusted AI model runner attestation key unavailable.")
        attestation=report.get("runner_attestation") if isinstance(report,dict) else None
        if (not isinstance(attestation,dict) or
            set(attestation)!={"runner_id","runtime_status","hmac_sha256"} or
            not isinstance(attestation["runner_id"],str) or
            not PROVIDER.fullmatch(attestation["runner_id"]) or
            attestation["runtime_status"]!="REVIEW_MODELS_EXECUTED" or
            not isinstance(attestation["hmac_sha256"],str) or
            not SHA.fullmatch(attestation["hmac_sha256"])):
            raise SceneError("Signed local AI runtime attestation required.")
        unsigned={key:value for key,value in report.items()
                  if key!="runner_attestation"}
        signed_payload=json.dumps(unsigned,sort_keys=True,
            ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
        expected_hmac=hmac.new(self.attestation_key,signed_payload,
                               hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hmac,attestation["hmac_sha256"]):
            raise SceneError("Untrusted or tampered AI model execution report.")
        if (set(report)!=required or report.get("schema_version")!=1 or
            report["series_id"]!=sid or report["episode_number"]!=ordinal or
            report["scene"]!=scene or report["stage"]!=stage or
            report["publication_approved"] is not False or
            report["observations_sha256"]!=obs_sha or
            report["rights_sha256"]!=rights_sha or
            not isinstance(report["technical_sha256"],str) or
            not SHA.fullmatch(report["technical_sha256"])):
            raise SceneError("Pinned independent scene QA report invalid.")
        reviews=report["reviewers"]
        if not isinstance(reviews,list) or len(reviews)!=2:
            raise SceneError("Exactly two scene AI providers required.")
        by_role={}
        seen=set()
        for item in reviews:
            if not isinstance(item,dict) or set(item)!={
                "role","provider_id","model_id","evidence_sha256",
                "checks","summary","publication_approved"}:
                raise SceneError("Reviewer source fields missing.")
            role,provider=item["role"],item["provider_id"]
            if (role not in ROLE_CHECKS[stage] or role in by_role or
                not isinstance(provider,str) or not PROVIDER.fullmatch(provider) or
                provider in seen or
                not isinstance(item["model_id"],str) or not 3<=len(item["model_id"])<=120 or
                item["evidence_sha256"]!=obs_sha or
                item["publication_approved"] is not False or
                not isinstance(item["summary"],str) or
                not 25<=len(item["summary"].strip())<=1500):
                raise SceneError("Independent reviewer identity/evidence incomplete.")
            checks=item["checks"]
            if not isinstance(checks,dict) or set(checks)!=ROLE_CHECKS[stage][role]:
                raise SceneError("Missing role-specific AI checks.")
            for criterion,value in checks.items():
                if (not isinstance(value,dict) or set(value)!={"decision","evidence"} or
                    value["decision"] not in ("PASS","UNSURE","NEEDS_FIX") or
                    not isinstance(value["evidence"],str) or
                    not 25<=len(value["evidence"].strip())<=800):
                    raise SceneError("AI scene judgment needs detailed evidence.")
            by_role[role]=item
            seen.add(provider)
        if set(by_role)!=set(ROLE_CHECKS[stage]):
            raise SceneError("Missing distinct scene review role.")
        if (not isinstance(rights,dict) or set(rights)!={"schema_version",
              "artifact_sha256","source_kind","source_proof_sha256",
              "source_proof_file","usage_scope","documented","rights_adjudicated",
              "publication_approved"} or rights["schema_version"]!=1 or
            rights["artifact_sha256"]!=report["artifact_sha256"] or
            rights["source_kind"] not in ("original_created","licensed",
                                         "public_domain_verified") or
            rights["usage_scope"]!="commercial_youtube_kids" or
            rights["documented"] is not True or
            rights["rights_adjudicated"] is not False or
            rights["publication_approved"] is not False or
            not isinstance(rights["source_proof_sha256"],str) or
            not SHA.fullmatch(rights["source_proof_sha256"])):
            raise SceneError("Source-specific rights catalogue missing (not legal clearance).")
        proof_bytes,source_proof_sha=_private(rights["source_proof_file"],100000,".txt")
        if source_proof_sha!=rights["source_proof_sha256"] or len(proof_bytes.strip())<30:
            raise SceneError("Actual source proof file differs from rights catalogue.")
        if (not isinstance(obs,dict) or obs.get("schema_version")!=1 or
            obs.get("stage")!=stage or
            obs.get("artifact_sha256")!=report["artifact_sha256"] or
            obs.get("script_sha256")!=report["script_sha256"] or
            obs.get("model_execution_verified") is not True or
            obs.get("publishing_approved") is not False):
            raise SceneError("Scene observation lineage unavailable.")
        wer=None
        if stage=="voice_synthesize":
            if set(obs)!={"schema_version","stage","artifact_sha256",
                           "script_sha256","script_file","asr_file",
                           "asr_model_id","asr_provider_id","asr_job_id",
                           "model_execution_verified","publishing_approved"}:
                raise SceneError("Real ASR transcript and script file required.")
            script_raw,script_sha=_private(obs["script_file"],12000,".txt")
            asr_raw,_=_private(obs["asr_file"],12000,".txt")
            if (script_sha!=report["script_sha256"] or
                not isinstance(obs["asr_model_id"],str) or
                not 3<=len(obs["asr_model_id"])<=120 or
                not isinstance(obs["asr_provider_id"],str) or
                not PROVIDER.fullmatch(obs["asr_provider_id"]) or
                obs["asr_provider_id"] in seen or
                not isinstance(obs["asr_job_id"],str) or
                not re.fullmatch(r"[a-f0-9]{32}",obs["asr_job_id"])):
                raise SceneError("Independent ASR job or exact source script missing.")
            try:
                wer=_word_error_rate(script_raw.decode("utf-8"),
                                     asr_raw.decode("utf-8"))
            except UnicodeError as exc:
                raise SceneError("ASR or script is not UTF-8.") from exc
        else:
            if (set(obs)!={"schema_version","stage","artifact_sha256",
                           "script_sha256","source_voice_sha256",
                           "frame_manifest_sha256","frame_manifest_file",
                           "frame_count","visual_review_model_id","model_execution_verified",
                           "publishing_approved"} or
                not isinstance(obs["source_voice_sha256"],str) or
                not SHA.fullmatch(obs["source_voice_sha256"]) or
                not isinstance(obs["frame_manifest_sha256"],str) or
                not SHA.fullmatch(obs["frame_manifest_sha256"]) or
                type(obs["frame_count"]) is not int or obs["frame_count"]<3 or
                not isinstance(obs["visual_review_model_id"],str) or
                len(obs["visual_review_model_id"])<3):
                raise SceneError("LTX frame observations and source voice required.")
            frames_raw,frames_sha=_private(obs["frame_manifest_file"],100000,".json")
            if frames_sha!=obs["frame_manifest_sha256"]:
                raise SceneError("Visual frame manifest changed.")
            frames_manifest=_read_json(frames_raw)
            if (set(frames_manifest)!={"schema_version","a2v_sha256","frames"} or
                frames_manifest["schema_version"]!=1 or
                frames_manifest["a2v_sha256"]!=obs["artifact_sha256"] or
                not isinstance(frames_manifest["frames"],list) or
                len(frames_manifest["frames"])!=obs["frame_count"] or
                not 3<=len(frames_manifest["frames"])<=16):
                raise SceneError("Missing bounded LTX visual observations.")
            observed_times=set()
            for frame in frames_manifest["frames"]:
                if (not isinstance(frame,dict) or
                    set(frame)!={"timestamp_seconds","file","sha256"} or
                    type(frame["timestamp_seconds"]) not in (int,float) or
                    not 0<=frame["timestamp_seconds"]<=900 or
                    frame["timestamp_seconds"] in observed_times or
                    not isinstance(frame["sha256"],str) or
                    not SHA.fullmatch(frame["sha256"])):
                    raise SceneError("Invalid or repeated frame observation.")
                observed_times.add(frame["timestamp_seconds"])
                if not isinstance(frame["file"],str) or not frame["file"].lower().endswith(".png"):
                    raise SceneError("Frame evidence must be a private PNG.")
                frame_raw,frame_sha=_private(frame["file"],10_000_000,".png")
                if frame_sha!=frame["sha256"] or not frame_raw.startswith(bytes.fromhex("89504e470d0a1a0a")):
                    raise SceneError("Actual PNG frame evidence missing or altered.")
        all_pass=all(x["decision"]=="PASS"
                     for item in reviews for x in item["checks"].values())
        # ASR source text comparison is deterministic and independent of any
        # subjective model's PASS judgment. <=10% word errors for voice.
        if wer is not None and wer>0.10:
            all_pass=False

        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT st.state,st.job_id,st.artifact_sha256,
                st.scene_script_sha256,st.source_voice_sha256,
                j.kind,j.state AS job_state,j.result_json,
                sc.script_sha256, e.source_sha256 AS episode_script,
                e.state AS episode_state,p.episode_script_sha256 AS plan_script
                FROM studio_scene_stages st
                JOIN jobs j ON j.job_id=st.job_id
                JOIN studio_scenes sc ON sc.series_id=st.series_id
                    AND sc.ordinal=st.ordinal AND sc.scene=st.scene
                JOIN studio_scene_plans p ON p.series_id=st.series_id
                    AND p.ordinal=st.ordinal
                JOIN studio_episodes e ON e.series_id=st.series_id
                    AND e.ordinal=st.ordinal
                WHERE st.series_id=? AND st.ordinal=? AND st.scene=?
                AND st.stage=?""",(sid,ordinal,scene,stage)).fetchone()
            if (not row or row["state"]!="PENDING_QA" or
                row["job_state"]!="COMPLETED" or row["kind"]!=stage or
                row["episode_state"]!="SCRIPT_APPROVED" or
                row["episode_script"]!=row["plan_script"] or
                row["scene_script_sha256"]!=row["script_sha256"] or
                row["job_id"]!=report["job_id"] or
                row["artifact_sha256"]!=report["artifact_sha256"] or
                row["script_sha256"]!=report["script_sha256"]):
                raise SceneError("Current Pi scene source/master or job receipt changed.")
            try: receipt=json.loads(row["result_json"] or "{}")
            except (TypeError,ValueError) as exc:
                raise SceneError("Invalid completed worker receipt.") from exc
            if (receipt.get("status")!=STAGES[stage][0] or
                receipt.get("artifact_sha256")!=report["artifact_sha256"] or
                receipt.get("artifact_type")!=STAGES[stage][1] or
                receipt.get("publication_approved") is not False):
                raise SceneError("Scene Pi media receipt not valid.")
            if stage=="voice_synthesize":
                tech=db.execute("""SELECT report_sha256,status,voice_sha256
                    FROM studio_scene_voice_checks WHERE series_id=?
                    AND ordinal=? AND scene=? AND voice_job_id=?""",
                    (sid,ordinal,scene,row["job_id"])).fetchone()
                if (not tech or tech["status"]!="TECH_PASS_OWNER_LISTENING_PENDING" or
                    tech["voice_sha256"]!=row["artifact_sha256"] or
                    tech["report_sha256"]!=report["technical_sha256"]):
                    raise SceneError("Real M23 WAV technical QA required, not owner listening.")
            else:
                tech=db.execute("""SELECT report_sha256,status,voice_sha256,a2v_sha256
                    FROM studio_scene_audio_checks WHERE series_id=?
                    AND ordinal=? AND scene=? AND ltx_job_id=?""",
                    (sid,ordinal,scene,row["job_id"])).fetchone()
                if (not tech or tech["status"]!="TECH_COMPATIBLE_HUMAN_QA_REQUIRED" or
                    tech["voice_sha256"]!=row["source_voice_sha256"] or
                    tech["a2v_sha256"]!=row["artifact_sha256"] or
                    tech["report_sha256"]!=report["technical_sha256"] or
                    obs["source_voice_sha256"]!=row["source_voice_sha256"]):
                    raise SceneError("Actual M10 audio continuity required for AI LTX QA.")
            if db.execute("""SELECT 1 FROM studio_scene_ai_reviews
                WHERE series_id=? AND ordinal=? AND scene=? AND stage=?
                AND job_id=?""",(sid,ordinal,scene,stage,row["job_id"])).fetchone():
                raise SceneError("AI scene review already registered; cannot overwrite.")
            state="AI_SCENE_READY_PRIVATE_ONLY" if all_pass else "AI_SCENE_NEEDS_FIX"
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_scene_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid,ordinal,scene,stage,row["job_id"],
                 row["artifact_sha256"],row["scene_script_sha256"],
                 report_sha,rights_sha,obs_sha,report["technical_sha256"],
                 reviews[0]["provider_id"],reviews[1]["provider_id"],
                 state,wer,now))
            if not all_pass:
                db.execute("""INSERT INTO studio_series_notes(
                    series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                    (sid,ordinal,"M28 AI SCENE NEEDS FIX: scene "+
                     str(scene)+" "+stage+
                     (" ASR word_error_rate="+str(round(wer,3))
                      if wer is not None else "") ,now))
        return {"status":state,"scene":scene,"stage":stage,
                "word_error_rate":wer,
                "owner_stage_review_required":False,
                "owner_post_private_video_review_required":True,
                "public_release_authorized":False}

    def auto_approve(self,sid:str,ordinal:int,scene:int,stage:str)->dict:
        if stage not in ROLE_CHECKS or type(scene) is not int or type(ordinal) is not int:
            raise SceneError("Valid scene-stage required.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT state,job_id,artifact_sha256,
                scene_script_sha256,source_voice_sha256
                FROM studio_scene_stages WHERE series_id=? AND ordinal=?
                AND scene=? AND stage=?""",(sid,ordinal,scene,stage)).fetchone()
            if not row or row["state"]!="PENDING_QA":
                raise SceneError("AI stage gate can only approve current pending QA.")
            qa=db.execute("""SELECT * FROM studio_scene_ai_reviews
                WHERE series_id=? AND ordinal=? AND scene=? AND stage=? AND
                job_id=?""",(sid,ordinal,scene,stage,row["job_id"])).fetchone()
            if (not qa or qa["state"]!="AI_SCENE_READY_PRIVATE_ONLY" or
                qa["artifact_sha256"]!=row["artifact_sha256"] or
                qa["script_sha256"]!=row["scene_script_sha256"] or
                qa["first_provider"]==qa["second_provider"]):
                raise SceneError("Two independent current AI stage proofs required.")
            tech_name=("studio_scene_voice_checks" if stage=="voice_synthesize"
                       else "studio_scene_audio_checks")
            check=db.execute("""SELECT report_sha256 FROM """+tech_name+"""
                WHERE series_id=? AND ordinal=? AND scene=? AND """+
                ("voice_job_id" if stage=="voice_synthesize" else "ltx_job_id")+
                "=?",(sid,ordinal,scene,row["job_id"])).fetchone()
            if not check or check["report_sha256"]!=qa["technical_sha256"]:
                raise SceneError("Current source continuity/technical evidence missing.")
            db.execute("""UPDATE studio_scene_stages
                SET state='QA_APPROVED',
                owner_note='AI_INTERNAL_PRIVATE_ONLY_OWNER_REVIEW_AFTER_UPLOAD',
                updated_at=? WHERE series_id=? AND ordinal=? AND
                scene=? AND stage=? AND job_id=? AND state='PENDING_QA'""",
                (self.queue.clock(),sid,ordinal,scene,stage,row["job_id"]))
        return {"status":"AI_STAGE_APPROVED_INTERNAL_ONLY",
                "scene":scene,"stage":stage,
                "owner_post_private_video_review_required":True,
                "public_release_authorized":False}
