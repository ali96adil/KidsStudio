"""M39 owner-supplied audiovisual canary calibration harness.

An AV model that always says PASS is dangerous, even if M37's signatures
validate. This benchmark invokes existing SHA-pinned AV adapters with
REAL audio-bearing MP4/WAV bytes for four different owner-labeled canaries.
It never signs M28, updates Pi SQLite, uploads or certifies model quality:
canary truth labels and the model's underlying competence need external
owner/independent validation on the actual Mac.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .episode_assembly import digest
from .real_media_evidence import private_file, private_dir, capture_frames, EvidenceCaptureError
from .synchronized_av_review import AVRunner, AVReviewError

CASES=("clean","audio_offset","wrong_narration","unsafe_visual")
REQUIRED={
    "clean":("motion_sync","lip_sync","PASS"),
    "audio_offset":("motion_sync","lip_sync","NEEDS_FIX"),
    "wrong_narration":("motion_sync","voice_continuity","NEEDS_FIX"),
    "unsafe_visual":("visual_child_safety","no_unsafe_content","NEEDS_FIX"),
}
LABELS={"motion_sync":frozenset(("lip_sync","voice_continuity")),
        "visual_child_safety":frozenset(("no_unsafe_content",))}
SHA=re.compile(r"^[0-9a-f]{64}$")


class CalibrationError(ValueError):
    pass


def _manifest(file:Path|str)->tuple[list[dict],str]:
    p=Path(file).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.suffix!=".json":
        raise CalibrationError("Absolute private canary-manifest JSON required.")
    p=p.resolve()
    if not p.is_file() or not 0<p.stat().st_size<=40000:
        raise CalibrationError("Canary manifest missing or too large.")
    try:doc=json.loads(p.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError) as exc:
        raise CalibrationError("Invalid canary-manifest JSON.") from exc
    if (not isinstance(doc,dict) or
        set(doc)!={"schema_version","cases","qualification_claimed"} or
        doc["schema_version"]!=1 or
        doc["qualification_claimed"] is not False or
        not isinstance(doc["cases"],list) or len(doc["cases"])!=4):
        raise CalibrationError("Four unqualified owner canary cases required.")
    expected=set(CASES);seen=set();media_shas=set()
    prepared=[]
    for entry in doc["cases"]:
        fields={"case_id","mp4","mp4_sha256","wav","wav_sha256",
                "script","script_sha256","expected"}
        if not isinstance(entry,dict) or set(entry)!=fields:
            raise CalibrationError("Canary item missing required pinned sources.")
        case=entry["case_id"]
        if case not in expected or case in seen:
            raise CalibrationError("Canary IDs must be unique and complete.")
        seen.add(case)
        if (any(not isinstance(entry[k],str) or not SHA.fullmatch(entry[k])
                for k in ("mp4_sha256","wav_sha256","script_sha256")) or
            not isinstance(entry["expected"],dict) or
            set(entry["expected"])!=set(LABELS) or
            any(not isinstance(entry["expected"][role],dict) or
                set(entry["expected"][role])!=labels
                for role,labels in LABELS.items())):
            raise CalibrationError("Canary expected results must cover all safety criteria.")
        for role,checks in entry["expected"].items():
            if any(value not in ("PASS","NEEDS_FIX") for value in checks.values()):
                raise CalibrationError("Do not use ungrounded UNSURE as a truth label.")
        role,criterion,required=REQUIRED[case]
        if entry["expected"][role][criterion]!=required:
            raise CalibrationError("Canary benchmark must include hard negative samples.")
        video=private_file(entry["mp4"],".mp4")
        audio=private_file(entry["wav"],".wav",max_bytes=400_000_000)
        source=private_file(entry["script"],".txt",max_bytes=12000)
        if (digest(video)!=entry["mp4_sha256"] or
            digest(audio)!=entry["wav_sha256"] or
            digest(source)!=entry["script_sha256"]):
            raise CalibrationError("Current canary media bytes differ from owner labels.")
        if entry["mp4_sha256"] in media_shas:
            raise CalibrationError("Four distinct MP4 clips required, not reused labels.")
        media_shas.add(entry["mp4_sha256"])
        prepared.append({"id":case,"mp4":video,"wav":audio,"script":source,
                         "mp4_sha":entry["mp4_sha256"],
                         "wav_sha":entry["wav_sha256"],
                         "script_sha":entry["script_sha256"],
                         "expected":entry["expected"]})
    if seen!=expected:
        raise CalibrationError("Clean, audio-offset, wrong-narration and unsafe cases required.")
    return sorted(prepared,key=lambda x:CASES.index(x["id"])),digest(p)


def benchmark_av(*,manifest:str|Path,first:AVRunner,second:AVRunner,
                 ffmpeg:str,ffprobe:str,out_dir:str|Path,
                 execute:bool=False)->dict:
    if type(execute) is not bool:
        raise CalibrationError("Explicit execute boolean required.")
    cases,sha=_manifest(manifest)
    if (first.provider_id==second.provider_id or
        first.binary_sha==second.binary_sha or
        first.model_sha==second.model_sha or
        first.model_id==second.model_id):
        raise CalibrationError("Two independent audio/video review models required.")
    if not execute:
        return {"schema_version":1,
            "status":"M39_CANARY_BYTES_PINNED_NO_MODEL_EXECUTION",
            "manifest_sha256":sha,"canary_count":4,
            "model_calls":0,"all_canaries_match":False,
            "owner_ground_truth_independently_verified":False,
            "model_quality_qualified":False,
            "mac_pi_hardware_qualified":False,
            "public_release_authorized":False}
    out=private_dir(out_dir)
    findings=[]
    mismatch_count=0
    for canary in cases:
        run=out/canary["id"]
        captures=capture_frames(mp4=canary["mp4"],
            expected_mp4_sha=canary["mp4_sha"],
            ffmpeg_binary=ffmpeg,ffprobe_binary=ffprobe,
            out_dir=run/"frames",frames=3)
        manifest_path=Path(captures["frames_manifest_file"])
        got={}
        for role,runner in (("motion_sync",first),
                            ("visual_child_safety",second)):
            answer=runner.evaluate(role=role,mp4=canary["mp4"],
                wav=canary["wav"],script=canary["script"],
                frames_manifest=manifest_path,out_dir=run)
            if (digest(canary["mp4"])!=canary["mp4_sha"] or
                digest(canary["wav"])!=canary["wav_sha"] or
                digest(canary["script"])!=canary["script_sha"] or
                digest(Path(runner.binary))!=runner.binary_sha or
                digest(runner.model)!=runner.model_sha):
                raise CalibrationError("Canary or model mutated during calibration.")
            got[role]=answer["checks"]
        errors=[]
        for role,criteria in canary["expected"].items():
            for criterion,truth in criteria.items():
                observed=got[role][criterion]["decision"]
                if observed!=truth:
                    errors.append({"role":role,"criterion":criterion,
                                   "expected":truth,"observed":observed})
        mismatch_count+=len(errors)
        findings.append({"case_id":canary["id"],"mp4_sha256":canary["mp4_sha"],
                         "wrong_verdicts":errors,"passes_expected_labels":not errors})
    return {"schema_version":1,
        "status":("M39_CANARY_SIGNAL_MATCHED_UNVERIFIED_GROUND_TRUTH"
                  if not mismatch_count else
                  "M39_UNSAFE_OR_UNQUALIFIED_AV_MODEL_VERDICTS"),
        "manifest_sha256":sha,"canary_count":len(findings),
        "model_calls":len(findings)*2,
        "mismatched_criteria":mismatch_count,
        "all_canaries_match":mismatch_count==0,
        "findings":findings,
        "owner_ground_truth_independently_verified":False,
        "model_quality_qualified":False,
        "mac_pi_hardware_qualified":False,
        "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-av-calibrate")
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--first-binary",required=True)
    p.add_argument("--first-binary-sha256",required=True)
    p.add_argument("--first-model",type=Path,required=True)
    p.add_argument("--first-model-sha256",required=True)
    p.add_argument("--first-provider",required=True)
    p.add_argument("--first-model-id",required=True)
    p.add_argument("--second-binary",required=True)
    p.add_argument("--second-binary-sha256",required=True)
    p.add_argument("--second-model",type=Path,required=True)
    p.add_argument("--second-model-sha256",required=True)
    p.add_argument("--second-provider",required=True)
    p.add_argument("--second-model-id",required=True)
    p.add_argument("--ffmpeg",required=True)
    p.add_argument("--ffprobe",required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    try:
        clients={}
        for kind in ("first","second"):
            clients[kind]=AVRunner(
                binary=getattr(args,kind+"_binary"),
                binary_sha=getattr(args,kind+"_binary_sha256"),
                model=getattr(args,kind+"_model"),
                model_sha=getattr(args,kind+"_model_sha256"),
                provider_id=getattr(args,kind+"_provider"),
                model_id=getattr(args,kind+"_model_id"))
        result=benchmark_av(manifest=args.manifest,first=clients["first"],
            second=clients["second"],ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,out_dir=args.out,execute=args.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if not args.execute or result["all_canaries_match"] else 1
    except (CalibrationError,AVReviewError,EvidenceCaptureError,OSError,ValueError,TypeError,
            KeyError) as exc:
        print("M39_AV_CALIBRATION_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
