"""M10 owner-Mac readiness inventory. Read-only, offline, no engine launch.

The device report confirms *local bytes and environment only*. It does NOT
qualify model APIs, sample output, licensing, lip sync or production readiness.
CI injects synthetic Darwin metadata; only a real owner-Mac run can supply
trustworthy machine facts. Never commits private paths, models or media.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from typing import Any

from .engine_qualification import qualify_engine, EngineQualificationError
from .episode_assembly import digest, _ensure_private

SHA=re.compile(r"^[a-f0-9]{64}$")
ROLE=re.compile(r"^[a-z][a-z0-9_]{2,39}$")
REQUIRED_ASSETS=frozenset({
    "approved_script", "bunny_reference", "voice_wrapper", "ltx_wrapper",
    "face_v06", "face_v07"
})
REQUIRED_TOOLS=frozenset({
    "voice_python", "ltx_python", "ffmpeg", "ffprobe"
})
KINDS=frozenset({"voice_synthesize","ltx_animate"})


class MacIntakeError(ValueError):
    """Owner Mac intake configuration or local asset provenance is invalid."""


def _safe_source(path: Any, allowed_roots: list[Path], *, tool: bool=False) -> Path:
    if not isinstance(path,str) or not path.startswith("/"):
        raise MacIntakeError("All locations must be explicit absolute paths.")
    item=Path(path).expanduser()
    if item.is_symlink():
        raise MacIntakeError("Symlinks cannot be pinned as canonical sources.")
    resolved=item.resolve()
    if not resolved.is_file() or not 0 < resolved.stat().st_size <= 35_000_000_000:
        raise MacIntakeError("Pinned file missing, empty or oversized.")
    if not tool and not any(resolved.is_relative_to(root) for root in allowed_roots):
        raise MacIntakeError("Private asset lives outside the owner-approved local roots.")
    if tool and not os.access(resolved,os.X_OK):
        raise MacIntakeError("Approved local tool is not executable.")
    return resolved


def _exact_pin(item: Any, roots: list[Path], *, tool: bool=False) -> tuple[Path, str]:
    if not isinstance(item,dict) or set(item)!={"role","path","sha256"}:
        raise MacIntakeError("Expected exactly role, path and sha256.")
    if not isinstance(item["sha256"],str) or not SHA.fullmatch(item["sha256"]):
        raise MacIntakeError("An exact lower-case SHA256 is required.")
    path=_safe_source(item["path"],roots,tool=tool)
    if digest(path)!=item["sha256"]:
        raise MacIntakeError("Pinned file changed after owner approval.")
    return path,item["sha256"]


def check_mac_contract(
    manifest: str | Path,
    *, system: str | None=None,
    arch: str | None=None,
    memory_bytes: int | None=None,
    free_bytes: int | None=None,
) -> dict[str,Any]:
    file=Path(manifest).expanduser()
    if not file.is_absolute() or file.is_symlink():
        raise MacIntakeError("Mac contract must be a private absolute non-symlink file.")
    file=file.resolve()
    _ensure_private(file.parent)
    if not file.is_file() or not 0 < file.stat().st_size <= 150_000:
        raise MacIntakeError("Missing/oversized private Mac contract.")
    try:
        obj=json.loads(file.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise MacIntakeError("Invalid Mac contract JSON.") from exc
    expected={"schema_version","private_roots","assets","tools",
              "engine_manifests","minimum_free_gib"}
    if not isinstance(obj,dict) or set(obj)!=expected or obj["schema_version"]!=1:
        raise MacIntakeError("Mac contract schema mismatch.")
    raw_roots=obj["private_roots"]
    if not isinstance(raw_roots,list) or not 1 <= len(raw_roots) <= 4:
        raise MacIntakeError("Configure 1..4 explicitly approved private asset roots.")
    roots=[]
    for raw in raw_roots:
        if not isinstance(raw,str) or not raw.startswith("/") or Path(raw).is_symlink():
            raise MacIntakeError("Private roots require non-symlink absolute paths.")
        root=_ensure_private(Path(raw))
        if not root.is_dir() or root in roots:
            raise MacIntakeError("Private root missing/duplicate or inside Git.")
        roots.append(root)
    if not file.is_relative_to(roots[0]):
        raise MacIntakeError("Mac manifest must be stored under the primary private root.")
    minimum=obj["minimum_free_gib"]
    if type(minimum) is not int or not 5 <= minimum <= 500:
        raise MacIntakeError("Reserve 5..500 GiB of free local storage.")
    free=free_bytes if free_bytes is not None else shutil.disk_usage(roots[0]).free
    if type(free) is not int or free < minimum*(1024**3):
        raise MacIntakeError("Insufficient approved Mac storage for the pipeline.")
    assets=obj["assets"]
    tools=obj["tools"]
    if not isinstance(assets,list) or not isinstance(tools,list):
        raise MacIntakeError("Assets and tools must be explicit lists.")
    if not 6 <= len(assets) <= 24 or not 4 <= len(tools) <= 12:
        raise MacIntakeError("Asset or tool inventory has unexpected item count.")
    asset_map={}
    tool_map={}
    tool_paths={}
    for entry in assets:
        if not isinstance(entry,dict) or not isinstance(entry.get("role"),str):
            raise MacIntakeError("Asset role must be a string.")
        role=entry["role"]
        if not ROLE.fullmatch(role) or role in asset_map:
            raise MacIntakeError("Invalid or duplicate asset role.")
        path,sha=_exact_pin(entry,roots)
        asset_map[role]={"bytes":path.stat().st_size,"sha256":sha}
    for entry in tools:
        if not isinstance(entry,dict) or not isinstance(entry.get("role"),str):
            raise MacIntakeError("Tool role must be a string.")
        role=entry["role"]
        if not ROLE.fullmatch(role) or role in tool_map:
            raise MacIntakeError("Invalid or duplicate tool role.")
        path,sha=_exact_pin(entry,roots,tool=True)
        tool_map[role]={"bytes":path.stat().st_size,"sha256":sha}
        tool_paths[role]=path
    if not REQUIRED_ASSETS.issubset(asset_map):
        raise MacIntakeError("Missing approved script, Bunny reference or actual wrapper scripts.")
    if not REQUIRED_TOOLS.issubset(tool_map):
        raise MacIntakeError("Missing voice/LTX Python and ffmpeg/ffprobe runtime pins.")
    # Exact hash alone proves identity, not a correct executable ROLE.
    # The historical synthetic test even accepted a Python interpreter as
    # both ffmpeg and ffprobe, producing false Mac toolchain readiness.
    ffmpeg=tool_paths["ffmpeg"]
    ffprobe=tool_paths["ffprobe"]
    if (ffmpeg==ffprobe or ffmpeg in
        (tool_paths["voice_python"],tool_paths["ltx_python"]) or
        ffprobe in (tool_paths["voice_python"],tool_paths["ltx_python"])
        or ffmpeg.name.lower()!="ffmpeg" or ffprobe.name.lower()!="ffprobe"):
        raise MacIntakeError(
            "FFmpeg, FFprobe and Python roles must resolve to correct distinct binaries.")
    versions=obj["engine_manifests"]
    if not isinstance(versions,list) or len(versions)!=2:
        raise MacIntakeError("Both owner-reviewed Chatterbox and LTX manifests required.")
    kinds=set()
    engines=[]
    for entry in versions:
        if not isinstance(entry,dict) or set(entry)!={"kind","path","sha256"}:
            raise MacIntakeError("Engine reference must specify kind/path/sha256.")
        kind=entry["kind"]
        if kind not in KINDS or kind in kinds:
            raise MacIntakeError("Only one unique manifest per engine is accepted.")
        model=_safe_source(entry["path"],roots)
        if not isinstance(entry["sha256"],str) or not SHA.fullmatch(entry["sha256"]):
            raise MacIntakeError("Engine manifest SHA256 required.")
        if digest(model)!=entry["sha256"]:
            raise MacIntakeError("Engine manifest changed.")
        parent=next((root for root in roots if model.is_relative_to(root)),None)
        if parent is None:
            raise MacIntakeError("Engine file must be private.")
        qualified=qualify_engine(
            model,expected_kind=kind,private_root=parent,
            system=system,arch=arch,memory_bytes=memory_bytes)
        engines.append({
            "kind":kind,
            "status":qualified["status"],
            "manifest_sha256":qualified["manifest_sha256"],
            "checkpoint_count":len(qualified["checkpoints"]),
            "model_execution_tested":False,
        })
        kinds.add(kind)
    if kinds!=KINDS:
        raise MacIntakeError("Both voice and LTX engines must be pinned.")
    return {
        "schema_version":1,
        "status":"PINNED_LOCAL_MAC_ASSETS_VERIFIED_ENGINES_NOT_RUN",
        "contract_sha256":digest(file),
        "verified_assets":asset_map,
        "verified_local_tools":tool_map,
        "engine_qualification":sorted(engines,key=lambda r:r["kind"]),
        "available_gib":round(free/1024**3,2),
        "minimum_free_gib":minimum,
        "real_tts_or_video_run_performed":False,
        "voice_and_model_license_validated":False,
        "device_owner_qa_approved":False,
        "youtube_upload_performed":False,
        "publication_authorized":False,
        "disclosure":"Paths and secrets excluded from report; no inference executed."
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-mac-contract")
    p.add_argument("--manifest",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        data=check_mac_contract(args.manifest)
    except (MacIntakeError,EngineQualificationError,OSError,ValueError) as exc:
        print("STUDIO_MAC_CONTRACT_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(data,indent=2,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
