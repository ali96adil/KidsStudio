"""M8 offline, fail-closed checkpoint qualification for owner-installed MLX engines.

This proves local checkpoint bytes and machine prerequisites only. It does NOT
verify that the Chatterbox or LTX wrapper actually works or model licenses.
No model download, model execution, network or API calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any

from .episode_assembly import digest, _ensure_private

SHA = re.compile(r"^[a-f0-9]{64}$")
KINDS = {"voice_synthesize":"chatterbox_multilingual_mlx",
         "ltx_animate":"ltx_2_3_mlx"}
MAX_MODEL_BYTES = 35_000_000_000


class EngineQualificationError(ValueError):
    """Locally installed engine does not satisfy the owner-pinned contract."""


def _physical_ram() -> int:
    try:
        result = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=5)
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise EngineQualificationError("Cannot verify Mac physical memory.") from exc


def qualify_engine(manifest_path: str | Path, *, expected_kind: str,
                   private_root: str | Path,
                   system: str | None = None, arch: str | None = None,
                   memory_bytes: int | None = None) -> dict[str, Any]:
    if expected_kind not in KINDS:
        raise EngineQualificationError("Unsupported private engine family.")
    root = _ensure_private(Path(private_root))
    path = Path(manifest_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise EngineQualificationError("Manifest must be an absolute non-symlink file.")
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 100_000:
        raise EngineQualificationError("Manifest must be a small file in the private root.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EngineQualificationError("Invalid engine manifest JSON.") from exc
    required = {"schema_version","kind","engine","platform","arch",
                "minimum_memory_gib","network_required","checkpoints"}
    if not isinstance(data,dict) or set(data) != required:
        raise EngineQualificationError("Engine manifest keys not approved.")
    if (data["schema_version"] != 1 or data["kind"] != expected_kind or
        data["engine"] != KINDS[expected_kind] or
        data["platform"] != "Darwin" or data["arch"] not in ("arm64","aarch64") or
        data["network_required"] is not False or
        type(data["minimum_memory_gib"]) is not int or
        not 8 <= data["minimum_memory_gib"] <= 128):
        raise EngineQualificationError("Engine/version or offline platform contract rejected.")
    machine_arch = arch if arch is not None else platform.machine()
    machine_system = system if system is not None else platform.system()
    if machine_system != "Darwin" or machine_arch not in ("arm64","aarch64"):
        raise EngineQualificationError("Approved MLX engine needs Apple Silicon macOS.")
    ram = memory_bytes if memory_bytes is not None else _physical_ram()
    if type(ram) is not int or ram < data["minimum_memory_gib"] * (1024**3):
        raise EngineQualificationError("Not enough qualified physical memory.")
    models = data["checkpoints"]
    if not isinstance(models,list) or not 1 <= len(models) <= 16:
        raise EngineQualificationError("At least one pinned local checkpoint required.")
    seen = set()
    checked = []
    for model in models:
        if not isinstance(model,dict) or set(model) != {"role","path","sha256"}:
            raise EngineQualificationError("Checkpoint must specify role, path and SHA256.")
        role, fname, expected = model["role"], model["path"], model["sha256"]
        if not isinstance(role,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,48}",role):
            raise EngineQualificationError("Invalid checkpoint role.")
        if not isinstance(fname,str) or not fname.startswith("/") or not isinstance(expected,str) or not SHA.fullmatch(expected):
            raise EngineQualificationError("Checkpoint requires absolute path and exact SHA256.")
        source=Path(fname).expanduser()
        if source.is_symlink():
            raise EngineQualificationError("Checkpoint symlink not accepted.")
        source=source.resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise EngineQualificationError("Checkpoint missing or outside private media root.")
        if (role in seen or not 0 < source.stat().st_size <= MAX_MODEL_BYTES or
                digest(source) != expected):
            raise EngineQualificationError("Duplicate, oversized or mutated model checkpoint.")
        seen.add(role)
        checked.append({"role":role,"bytes":source.stat().st_size,"sha256":expected})
    return {"schema_version":1,"status":"CHECKPOINT_BYTES_VERIFIED_ENGINE_NOT_RUN",
            "engine":data["engine"],"kind":expected_kind,
            "manifest_sha256":digest(path),"checkpoints":checked,
            "physical_memory_gib":round(ram/1024**3,2),
            "model_execution_tested":False,"voice_rights_verified":False,
            "network_used":False,"publication_approved":False}


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-engine-qualify")
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--private-root",type=Path,required=True)
    p.add_argument("--kind",choices=tuple(KINDS),required=True)
    args=p.parse_args(argv)
    try:
        result=qualify_engine(args.manifest,expected_kind=args.kind,
                              private_root=args.private_root)
    except (EngineQualificationError,OSError,ValueError) as exc:
        print("ENGINE_QUALIFICATION_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
