"""M45 offline, read-only model pilot evidence readiness summary.

The owner should not infer Mac GPU/Arabic AV quality from a CI PASS, an
HMAC signature, a single model result, or synthetic benchmark labels.
Reverify current private source bytes, pinned M41 checkpoint, M44 owner
claim, M43 exact local probe sources and M39 canary inputs. Report separate
technical-evidence and real-world blockers; NEVER authorize uploads.

Default changes nothing. Optional --execute only writes an immutable
owner-private JSON snapshot, still marked NOT READY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable

from .episode_assembly import _ensure_private,digest
from .model_package import verify_checkpoint,ModelPackageError
from .model_origin_attestation import verify_origin,ModelOriginError
from .model_pilot_probe import _verify_result,PilotProbeError,ALL_ROLES
from .qwen_omni_local import inspect_local,OmniAdapterError
from .real_media_evidence import private_file,_binary,EvidenceCaptureError
from .av_model_calibration import _manifest,CalibrationError

SHA=re.compile(r"^[0-9a-f]{64}$")
MAX_REPORT=200_000


class EvidenceReadinessError(ValueError):
    pass


def _read_pinned(path:str|Path,sha:str,*,max_bytes:int=MAX_REPORT)->tuple[dict,Path]:
    if not isinstance(sha,str) or not SHA.fullmatch(sha):
        raise EvidenceReadinessError("Exact lowercase SHA256 for evidence required.")
    raw=Path(path).expanduser()
    if (not raw.is_absolute() or raw.is_symlink() or
        raw.suffix.lower()!=".json"):
        raise EvidenceReadinessError("Private absolute non-symlink JSON expected.")
    p=raw.resolve()
    _ensure_private(p.parent)
    if (not p.is_file() or not 100<=p.stat().st_size<=max_bytes or
        (p.parent.stat().st_mode & 0o022) or
        (p.stat().st_mode & 0o022) or digest(p)!=sha):
        raise EvidenceReadinessError("Local evidence missing, unsafe or changed.")
    try:record=json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise EvidenceReadinessError("Malformed SHA-pinned evidence.") from exc
    if not isinstance(record,dict):
        raise EvidenceReadinessError("Evidence must be an object.")
    return record,p


def _source(file:str|Path,sha:str,ext:str)->Path:
    if not isinstance(sha,str) or not SHA.fullmatch(sha):
        raise EvidenceReadinessError("Pinned original source SHA256 missing.")
    p=private_file(file,ext,max_bytes=400_000_000)
    if digest(p)!=sha:
        raise EvidenceReadinessError("Original media/script changed.")
    return p


def _gate(items:list,code:str,state:str,description:str):
    items.append({"id":code,"state":state,"detail":description})


def assess_model_evidence(*,model:str|Path,model_sha256:str,
    variant:str="7b",origin_receipt:str|Path|None=None,
    origin_sha256:str|None=None,owner_key:bytes|None=None,
    adapter:str|Path|None=None,pilot_metrics:str|Path|None=None,
    pilot_metrics_sha256:str|None=None,
    model_diagnostic:str|Path|None=None,
    model_diagnostic_sha256:str|None=None,
    script:str|Path|None=None,wav:str|Path|None=None,
    transcript:str|Path|None=None,mp4:str|Path|None=None,
    frames_manifest:str|Path|None=None,
    ffprobe:str|Path|None=None,
    av_canary_report:str|Path|None=None,
    av_canary_sha256:str|None=None,
    av_canary_manifest:str|Path|None=None,
    resource_screen:Callable=inspect_local,
    out:str|Path|None=None,execute:bool=False)->dict:
    """No inference, model upload, Pi/network access or public permission."""
    if type(execute) is not bool or variant!="7b":
        raise EvidenceReadinessError("Only explicit commercial-eligible 7B pilot audit.")
    directory=verify_checkpoint(model,model_sha256,allow_directory=True)
    if not directory.is_dir():
        raise EvidenceReadinessError("Require complete M41 sharded model directory.")
    gates=[]
    _gate(gates,"M41_CHECKPOINT_INTEGRITY","PASS_OFFLINE",
          "Whole private checkpoint directory SHA and member inventory rechecked.")
    origin_ok=False
    if origin_receipt is None and origin_sha256 is None and owner_key is None:
        _gate(gates,"M44_OWNER_ORIGIN_ATTESTATION","NOT_SUPPLIED",
              "No owner-signed source/license claim.")
    else:
        if (origin_receipt is None or origin_sha256 is None or
            not isinstance(owner_key,bytes) or len(owner_key)<32):
            raise EvidenceReadinessError("Incomplete private owner source attestation.")
        evidence=verify_origin(model=directory,model_sha256=model_sha256,
            receipt=origin_receipt,receipt_sha256=origin_sha256,
            owner_key=owner_key,variant=variant)
        origin_ok=evidence["owner_attestation_verified"]
        _gate(gates,"M44_OWNER_ORIGIN_ATTESTATION","PASS_OWNER_CLAIM"
              if origin_ok else "BLOCKED",
              "Authenticated private source claim; upstream snapshot/rights still unverified.")
    current=resource_screen(model=directory,expected_model_sha=model_sha256,
                            variant=variant)
    if (not isinstance(current,dict) or
        current.get("model_package_sha256")!=model_sha256 or
        current.get("model_inference_tested") is not False or
        current.get("model_quality_qualified") is not False or
        current.get("public_release_authorized") is not False or
        current.get("status") not in (
        "M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN",
        "M42_RESOURCE_SCREEN_BLOCKED")):
        raise EvidenceReadinessError("Unexpected current Mac resource screen.")
    resource_ok=current["status"]=="M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN"
    _gate(gates,"M42_CURRENT_MAC_RESOURCE_SCREEN",
          "PASS_OFFLINE_SCREEN_ONLY" if resource_ok else "BLOCKED",
          "Resource screen is not Mac MPS inference or measured GPU memory.")
    metrics_present=any(x is not None for x in (
        adapter,pilot_metrics,pilot_metrics_sha256,model_diagnostic,
        model_diagnostic_sha256,script,wav,transcript,mp4,
        frames_manifest,ffprobe))
    metric_ok=False
    pilot_role=None
    if not metrics_present:
        _gate(gates,"M43_PINNED_PILOT_OBSERVATION","NOT_SUPPLIED",
              "Missing actual bounded diagnostic and original pinned scene sources.")
    else:
        if any(x is None for x in (
            adapter,pilot_metrics,pilot_metrics_sha256,model_diagnostic,
            model_diagnostic_sha256,script,wav)):
            raise EvidenceReadinessError("Incomplete model pilot source binding.")
        record,_=_read_pinned(pilot_metrics,pilot_metrics_sha256)
        diag,diag_file=_read_pinned(model_diagnostic,model_diagnostic_sha256,
                                    max_bytes=20_000)
        pilot_role=record.get("role")
        if (pilot_role not in ALL_ROLES or
            record.get("schema_version")!=1 or
            record.get("status")!="M43_OBSERVATION_ONLY_NOT_AI_QUALIFIED" or
            record.get("model_package_sha256")!=model_sha256 or
            record.get("model_origin_receipt_sha256")!=origin_sha256 or
            record.get("owner_origin_attestation_checked") is not True or
            record.get("upstream_source_independently_verified") is not False or
            record.get("license_legally_adjudicated") is not False or
            record.get("diagnostic_sha256")!=model_diagnostic_sha256 or
            record.get("model_calls")!=1 or
            type(record.get("elapsed_seconds")) not in (int,float) or
            not 0<=record["elapsed_seconds"]<=900 or
            record.get("model_inference_proven") is not False or
            record.get("model_quality_qualified") is not False or
            record.get("child_safety_certified") is not False or
            record.get("private_upload_permitted") is not False or
            record.get("public_release_authorized") is not False or
            not origin_ok):
            raise EvidenceReadinessError("Model pilot receipt is not an owner-attested M43 diagnostic.")
        binary=_binary(str(adapter))
        if digest(Path(binary))!=record.get("adapter_sha256"):
            raise EvidenceReadinessError("Installed local model adapter differs from pilot.")
        sources=record.get("source_sha256")
        if not isinstance(sources,dict):
            raise EvidenceReadinessError("Pilot report requires source SHA mapping.")
        expected={"model_sha256":model_sha256,
                  "script_sha256":digest(_source(script,
                      sources.get("script_sha256"),".txt"))}
        if pilot_role in ("pronunciation","child_audio_safety"):
            if transcript is None or mp4 is not None or frames_manifest is not None:
                raise EvidenceReadinessError("Voice pilot requires ASR and no AV inputs.")
            expected["audio_sha256"]=digest(_source(wav,
                sources.get("audio_sha256"),".wav"))
            expected["transcript_sha256"]=digest(_source(transcript,
                sources.get("transcript_sha256"),".txt"))
        else:
            if (mp4 is None or frames_manifest is None or
                ffprobe is None or transcript is not None):
                raise EvidenceReadinessError("AV pilot needs MP4/frames and FFprobe.")
            expected["wav_sha256"]=digest(_source(wav,
                sources.get("wav_sha256"),".wav"))
            expected["mp4_sha256"]=digest(_source(mp4,
                sources.get("mp4_sha256"),".mp4"))
            expected["frames_manifest_sha256"]=digest(_source(
                frames_manifest,sources.get("frames_manifest_sha256"),".json"))
            if _binary(str(ffprobe))!=str(Path(ffprobe).expanduser().resolve()):
                raise EvidenceReadinessError("FFprobe executable path changed.")
        if sources!=expected:
            raise EvidenceReadinessError("Pilot report source mapping not exact.")
        if _verify_result(diag_file,role=pilot_role,
                          source=expected)!=model_diagnostic_sha256:
            raise EvidenceReadinessError("Unqualified AV diagnostic SHA mismatch.")
        metric_ok=True
        _gate(gates,"M43_PINNED_PILOT_OBSERVATION","PASS_BYTES_ONLY",
              "Bound to original media, signed owner claim, and UNSURE-only output; no model competence proven.")
    canary_present=any(x is not None for x in (
        av_canary_report,av_canary_sha256,av_canary_manifest))
    canary_checked=False
    if not canary_present:
        _gate(gates,"M39_CANARY_CONTRAST_EVIDENCE","NOT_SUPPLIED",
              "No independent four-case adversarial AV contrast evidence.")
    else:
        if any(x is None for x in (
            av_canary_report,av_canary_sha256,av_canary_manifest)):
            raise EvidenceReadinessError("All canary evidence and source manifest required.")
        canary,canary_path=_read_pinned(av_canary_report,av_canary_sha256)
        canaries,manifest_pin=_manifest(av_canary_manifest)
        if (canary.get("schema_version")!=1 or
            canary.get("manifest_sha256")!=manifest_pin or
            canary.get("canary_count")!=4 or
            canary.get("model_calls")!=8 or
            canary.get("owner_ground_truth_independently_verified") is not False or
            canary.get("model_quality_qualified") is not False or
            canary.get("public_release_authorized") is not False or
            not isinstance(canary.get("findings"),list) or
            len(canary["findings"])!=4 or
            any(not isinstance(x,dict) for x in canary["findings"]) or
            {x.get("case_id") for x in canary["findings"]}!=
            {x["id"] for x in canaries}):
            raise EvidenceReadinessError("Canary score cannot be passed off as owner-qualified ground truth.")
        expected_shas={x["id"]:x["mp4_sha"] for x in canaries}
        mismatch_count=0
        for finding in canary["findings"]:
            if (not isinstance(finding,dict) or
                set(finding)!={"case_id","mp4_sha256",
                               "wrong_verdicts","passes_expected_labels"} or
                finding["mp4_sha256"]!=expected_shas.get(finding["case_id"]) or
                not isinstance(finding["wrong_verdicts"],list) or
                type(finding["passes_expected_labels"]) is not bool or
                finding["passes_expected_labels"]!=
                (len(finding["wrong_verdicts"])==0)):
                raise EvidenceReadinessError("Canary outcome source/score mismatch.")
            for item in finding["wrong_verdicts"]:
                if (not isinstance(item,dict) or
                    set(item)!={"role","criterion","expected","observed"} or
                    item["expected"] not in ("PASS","NEEDS_FIX") or
                    item["observed"] not in ("PASS","NEEDS_FIX","UNSURE")):
                    raise EvidenceReadinessError("Invalid canary mismatch item.")
            mismatch_count+=len(finding["wrong_verdicts"])
        if (type(canary.get("mismatched_criteria")) is not int or
            canary["mismatched_criteria"]!=mismatch_count or
            type(canary.get("all_canaries_match")) is not bool or
            canary["all_canaries_match"]!=(mismatch_count==0) or
            canary.get("status")!=(
                "M39_CANARY_SIGNAL_MATCHED_UNVERIFIED_GROUND_TRUTH"
                if mismatch_count==0 else
                "M39_UNSAFE_OR_UNQUALIFIED_AV_MODEL_VERDICTS")):
            raise EvidenceReadinessError("AV canary summary contradicts original findings.")
        canary_checked=True
        _gate(gates,"M39_CANARY_CONTRAST_EVIDENCE","PASS_SOURCE_BYTES_ONLY",
              "Canary clips and results pinned; source labels not independently established.")
    for name,description in (
        ("INDEPENDENT_UPSTREAM_WEIGHT_PROVENANCE",
         "Owner HMAC and Apache copy do not independently prove original checkpoint revision."),
        ("COMMERCIAL_RIGHTS_ADJUDICATION",
         "Real commercial model/dependency/content use rights require independent verification."),
        ("REAL_APPLE_MPS_LOAD_AND_GPU_MEMORY",
         "Mac MPS load, actual unified memory and thermal stability not established by code/receipts."),
        ("REAL_ARABIC_VOICE_AND_VISUAL_COMPETENCE",
         "Model-observation-only UNSURE does not establish listening, Arabic or lip-sync skill."),
        ("INDEPENDENT_CANARY_GROUND_TRUTH",
         "Owner/qualified reviewers must confirm real benchmark labels independently."),
        ("AUTHENTICATED_MAC_PI_END_TO_END",
         "Pi live TLS, clock, queues, media ACK and two-scene render not yet verified."),
        ("CHILD_CONTENT_AND_EDUCATIONAL_POLICY",
         "Child-safe, pedagogical and rights checks require actual original final media."),
        ("AUTHORIZED_PRIVATE_YOUTUBE_REVIEW",
         "Private upload requires separate verified production evidence and owner action."),
        ("EXPLICIT_OWNER_PUBLIC_RELEASE",
         "PUBLIC always requires separate explicit owner approval.")
    ):
        _gate(gates,name,"NOT_YET_QUALIFIED",description)
    blockers=[x["id"] for x in gates
              if x["state"] not in (
                "PASS_OFFLINE","PASS_OWNER_CLAIM","PASS_OFFLINE_SCREEN_ONLY",
                "PASS_BYTES_ONLY","PASS_SOURCE_BYTES_ONLY")]
    report={"schema_version":1,
        "status":"M45_EVIDENCE_INVENTORY_NOT_PRODUCTION_READY",
        "checkpoint_package_sha256":model_sha256,
        "pilot_role":pilot_role,
        "owner_origin_attestation_checked":origin_ok,
        "resource_screen_passed_without_inference":resource_ok,
        "exact_pilot_observation_bytes_checked":metric_ok,
        "four_canary_source_bytes_checked":canary_checked,
        "gates":gates,"blockers":blockers,
        "qualified_gate_count":0,
        "model_inference_performed_by_this_command":False,
        "source_provenance_independently_verified":False,
        "model_quality_qualified":False,
        "independent_canary_truth_qualified":False,
        "mac_pi_hardware_qualified":False,
        "network_used":False,
        "private_upload_permitted":False,
        "owner_review_required":True,
        "public_release_authorized":False,
        "writes_performed":False}
    if execute:
        if out is None:
            raise EvidenceReadinessError("Explicit fresh private evidence snapshot path required.")
        target=Path(out).expanduser()
        if (not target.is_absolute() or target.is_symlink() or
            target.exists() or not target.parent.is_dir() or
            target.parent.is_symlink() or target.suffix.lower()!=".json" or
            (target.parent.stat().st_mode & 0o022)):
            raise EvidenceReadinessError("New owner-private snapshot JSON required.")
        _ensure_private(target.parent)
        persisted={**report,"writes_performed":True}
        raw=(json.dumps(persisted,sort_keys=True,ensure_ascii=False,
                       indent=2,allow_nan=False)+"\n").encode("utf-8")
        fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        report={**persisted,"report_sha256":hashlib.sha256(raw).hexdigest()}
    return report


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-model-readiness")
    p.add_argument("--model",required=True)
    p.add_argument("--model-sha256",required=True)
    p.add_argument("--origin-receipt")
    p.add_argument("--origin-sha256")
    p.add_argument("--adapter")
    p.add_argument("--pilot-metrics")
    p.add_argument("--pilot-metrics-sha256")
    p.add_argument("--model-diagnostic")
    p.add_argument("--model-diagnostic-sha256")
    p.add_argument("--script");p.add_argument("--wav")
    p.add_argument("--transcript");p.add_argument("--mp4")
    p.add_argument("--frames-manifest");p.add_argument("--ffprobe")
    p.add_argument("--av-canary-report")
    p.add_argument("--av-canary-sha256")
    p.add_argument("--av-canary-manifest")
    p.add_argument("--out")
    p.add_argument("--execute",action="store_true",
                   help="Save one private NOT READY report; never run model.")
    x=p.parse_args(argv)
    try:
        report=assess_model_evidence(model=x.model,
            model_sha256=x.model_sha256,origin_receipt=x.origin_receipt,
            origin_sha256=x.origin_sha256,
            owner_key=(os.environ.get("KIDS_STUDIO_MODEL_ORIGIN_KEY","").encode()
                       if x.origin_receipt is not None else None),
            adapter=x.adapter,pilot_metrics=x.pilot_metrics,
            pilot_metrics_sha256=x.pilot_metrics_sha256,
            model_diagnostic=x.model_diagnostic,
            model_diagnostic_sha256=x.model_diagnostic_sha256,
            script=x.script,wav=x.wav,transcript=x.transcript,
            mp4=x.mp4,frames_manifest=x.frames_manifest,ffprobe=x.ffprobe,
            av_canary_report=x.av_canary_report,
            av_canary_sha256=x.av_canary_sha256,
            av_canary_manifest=x.av_canary_manifest,
            out=x.out,execute=x.execute)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (EvidenceReadinessError,ModelPackageError,ModelOriginError,
            PilotProbeError,OmniAdapterError,EvidenceCaptureError,
            CalibrationError,OSError,ValueError,TypeError,KeyError) as exc:
        print("M45_EVIDENCE_READINESS_BLOCKED: "+type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
