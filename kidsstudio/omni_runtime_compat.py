"""M46 offline Apple Silicon Torch/MPS + Transformers runtime compatibility probe.

M42's importlib.find_spec checks only presence. They cannot show whether
Torch imports, the MPS backend is actually usable, or installed Transformers
exports both Qwen2.5-Omni text-only runtime classes. M46 separates these
probes from checkpoint loading: optional subprocess checks a ONE-SCALAR
Apple-MPS operation, never calls from_pretrained or inference.

Default read-only: inspect current M41 model + M42 resource screen only.
--execute: one bounded POSIX child, no OAuth keys, no network by policy,
no installed model opened by the worker, no YouTube upload.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Callable

from .episode_assembly import _ensure_private,digest
from .model_package import verify_checkpoint,checkpoint_digest,ModelPackageError
from .model_process_group import bounded_model_process,ModelProcessError
from .qwen_omni_local import inspect_local,OmniAdapterError
from .real_media_evidence import private_dir,media_subprocess_env,EvidenceCaptureError

VERSION=re.compile(r"^[0-9a-zA-Z._+\-]{1,64}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
TIMEOUT_MAX=180


class RuntimeCompatError(ValueError):
    pass


def _version(v:object)->str:
    if not isinstance(v,str) or not VERSION.fullmatch(v):
        raise RuntimeCompatError("Unsafe or missing installed Python library version.")
    return v


def inspect_apple_mps(*,system:str|None=None,arch:str|None=None,
                      loader:Callable=importlib.import_module)->dict:
    """Small real device scalar; no model load or inference.

    loader injection supports CI mocks WITHOUT torch/Transformers installs.
    """
    system=system if system is not None else platform.system()
    arch=arch if arch is not None else platform.machine()
    if system!="Darwin" or arch not in ("arm64","aarch64"):
        raise RuntimeCompatError("Apple Silicon macOS only; no Linux mock device fallback.")
    # Environment must be disabled for Hub lookups BEFORE third-party imports.
    for name in ("HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE","HF_DATASETS_OFFLINE"):
        os.environ[name]="1"
    try:
        torch=loader("torch")
        transformers=loader("transformers")
        cls=getattr(transformers,"Qwen2_5OmniThinkerForConditionalGeneration")
        processor=getattr(transformers,"Qwen2_5OmniProcessor")
        if not (callable(getattr(cls,"from_pretrained",None)) and
                callable(getattr(processor,"from_pretrained",None))):
            raise RuntimeCompatError("Installed Transformers has incompatible Qwen Omni classes.")
        if not (torch.backends.mps.is_built() and
                torch.backends.mps.is_available()):
            raise RuntimeCompatError("Mac Torch MPS is not built or available.")
        scalar=torch.ones(1,device="mps")
        if getattr(scalar.device,"type",None)!="mps":
            raise RuntimeCompatError("The tiny Torch op ran on CPU, not Apple MPS.")
        observed=scalar.add(1).cpu().tolist()
        if observed!=[2.0]:
            raise RuntimeCompatError("One-scalar Apple MPS arithmetic did not match.")
        torch_version=_version(torch.__version__)
        transformers_version=_version(transformers.__version__)
    except RuntimeCompatError:
        raise
    except (ImportError,OSError,AttributeError,RuntimeError,TypeError,
            ValueError) as exc:
        raise RuntimeCompatError("Actual local Torch/MPS or Omni class check failed.") from exc
    return {
        "schema_version":1,
        "status":"M46_MPS_SCALAR_IMPORTS_WORK_MODEL_NOT_LOADED",
        "system":"Darwin","architecture":arch,
        "torch_version":torch_version,
        "transformers_version":transformers_version,
        "mps_built":True,"mps_available":True,
        "mps_scalar_arithmetic_passed":True,
        "qwen_thinker_class_imported":True,
        "qwen_processor_class_imported":True,
        "model_weights_loaded":False,
        "model_inference_performed":False,
        "model_quality_qualified":False,
        "audio_video_perception_qualified":False,
        "commercial_license_legally_adjudicated":False,
        "mac_pi_hardware_qualified":False,
        "child_safety_certified":False,
        "network_isolation_verified":False,
        "private_upload_permitted":False,
        "public_release_authorized":False,
    }


def _write_exclusive(out:Path,result:dict)->str:
    raw=(json.dumps(result,sort_keys=True,ensure_ascii=False,
                    indent=2,allow_nan=False)+"\n").encode("utf-8")
    if len(raw)>7000:
        raise RuntimeCompatError("Unbounded runtime compatibility report.")
    fd=os.open(str(out),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    return hashlib.sha256(raw).hexdigest()


def _verify_worker(path:Path)->tuple[dict,str]:
    if (not path.is_file() or path.is_symlink() or
        not 250<=path.stat().st_size<=7000 or
        (path.stat().st_mode & 0o022)):
        raise RuntimeCompatError("No private, bounded MPS result from worker.")
    try:result=json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise RuntimeCompatError("Invalid MPS JSON worker response.") from exc
    expected={"schema_version","status","system","architecture",
        "torch_version","transformers_version","mps_built",
        "mps_available","mps_scalar_arithmetic_passed",
        "qwen_thinker_class_imported","qwen_processor_class_imported",
        "model_weights_loaded","model_inference_performed",
        "model_quality_qualified","audio_video_perception_qualified",
        "commercial_license_legally_adjudicated",
        "mac_pi_hardware_qualified","child_safety_certified",
        "network_isolation_verified","private_upload_permitted",
        "public_release_authorized"}
    if (not isinstance(result,dict) or set(result)!=expected or
        result["schema_version"]!=1 or
        result["status"]!="M46_MPS_SCALAR_IMPORTS_WORK_MODEL_NOT_LOADED" or
        result["system"]!="Darwin" or
        result["architecture"] not in ("arm64","aarch64") or
        any(result[key] is not True for key in (
            "mps_built","mps_available","mps_scalar_arithmetic_passed",
            "qwen_thinker_class_imported","qwen_processor_class_imported")) or
        any(result[key] is not False for key in (
            "model_weights_loaded","model_inference_performed",
            "model_quality_qualified","audio_video_perception_qualified",
            "commercial_license_legally_adjudicated",
            "mac_pi_hardware_qualified","child_safety_certified",
            "network_isolation_verified","private_upload_permitted",
            "public_release_authorized"))):
        raise RuntimeCompatError("Worker reported unsupported model qualification.")
    _version(result["torch_version"])
    _version(result["transformers_version"])
    return result,digest(path)


def probe_runtime(*,model:str|Path,model_sha256:str,variant:str="7b",
                  python_binary:str|Path|None=None,
                  out_dir:str|Path|None=None,
                  timeout_seconds:int=60,execute:bool=False,
                  resource_screen:Callable=inspect_local,
                  launcher:Callable=bounded_model_process)->dict:
    if (type(execute) is not bool or variant!="7b" or
        type(timeout_seconds) is not int or
        not 1<=timeout_seconds<=TIMEOUT_MAX):
        raise RuntimeCompatError("Only bounded, explicit 7B compatibility preflight.")
    directory=verify_checkpoint(model,model_sha256,allow_directory=True)
    if not directory.is_dir():
        raise RuntimeCompatError("Require M41 multi-file Qwen 7B package.")
    screen=resource_screen(model=directory,expected_model_sha=model_sha256,
                           variant=variant)
    if (not isinstance(screen,dict) or screen.get("model_package_sha256")
        !=model_sha256 or screen.get("model_inference_tested") is not False or
        screen.get("model_quality_qualified") is not False or
        screen.get("public_release_authorized") is not False or
        screen.get("status") not in (
        "M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN",
        "M42_RESOURCE_SCREEN_BLOCKED")):
        raise RuntimeCompatError("Untrusted source/model resource screen.")
    if not execute:
        return {"schema_version":1,"status":"M46_READ_ONLY_RUNTIME_NOT_IMPORTED",
            "model_package_sha256":model_sha256,
            "resource_screen":screen,
            "mps_scalar_probe_performed":False,
            "model_weights_loaded":False,"model_inference_performed":False,
            "model_quality_qualified":False,"network_isolation_verified":False,
            "private_upload_permitted":False,
            "public_release_authorized":False,"files_written":False}
    if screen["status"]!="M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN":
        raise RuntimeCompatError("M42 current owner Mac screen blocks runtime import.")
    candidate=Path(python_binary or sys.executable).expanduser()
    if not candidate.is_absolute() or not candidate.is_file() or not os.access(
            candidate,os.X_OK):
        raise RuntimeCompatError("Explicit local Python runtime required.")
    # A symlinked venv/python may have a legitimate role in Python's
    # sys.prefix discovery. Bind both original path and target bytes:
    # a real owner pilot still needs an OS-isolated local environment.
    resolved=candidate.resolve(strict=True)
    if not resolved.is_file():
        raise RuntimeCompatError("Local Python target missing.")
    python_sha=digest(resolved)
    if out_dir is None:
        raise RuntimeCompatError("Fresh private output directory required.")
    target=Path(out_dir).expanduser()
    if (not target.is_absolute() or target.is_symlink() or target.exists()
        or not target.parent.is_dir() or target.parent.is_symlink() or
        (target.parent.stat().st_mode & 0o022)):
        raise RuntimeCompatError("New owner-private output folder required.")
    _ensure_private(target.parent)
    folder=private_dir(target)
    result_file=folder/"mps_runtime.json"
    # -I disables user site and PYTHONPATH. Installed/eeditable package
    # must still be available in that isolated site environment.
    args=[str(candidate),"-I","-m","kidsstudio.omni_runtime_compat",
          "--worker","--out",str(result_file)]
    env=media_subprocess_env()
    env.update({"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1",
                "HF_DATASETS_OFFLINE":"1","PYTHONNOUSERSITE":"1",
                "PYTORCH_ENABLE_MPS_FALLBACK":"0"})
    begin=time.perf_counter()
    try:
        proc=launcher(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,timeout=timeout_seconds,
                      env=env,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeCompatError("MPS import/scalar probe expired or failed.") from exc
    if proc.returncode!=0:
        raise RuntimeCompatError("Local MPS import/scalar worker failed.")
    runtime,sha=_verify_worker(result_file)
    if (checkpoint_digest(directory)!=model_sha256 or
        digest(resolved)!=python_sha):
        raise RuntimeCompatError("Local model or Python executable changed during MPS check.")
    receipt={
        "schema_version":1,
        "status":"M46_RUNTIME_OBSERVATION_NOT_MODEL_QUALIFICATION",
        "model_package_sha256":model_sha256,
        "python_binary_sha256":python_sha,
        "runtime_report_sha256":sha,
        "torch_version":runtime["torch_version"],
        "transformers_version":runtime["transformers_version"],
        "mps_scalar_probe_reported":True,
        "elapsed_seconds":round(time.perf_counter()-begin,3),
        "model_weights_loaded":False,
        "model_inference_performed":False,
        "model_quality_qualified":False,
        "mac_pi_hardware_qualified":False,
        "source_provenance_verified":False,
        "network_isolation_verified":False,
        "private_upload_permitted":False,
        "public_release_authorized":False,
        "files_written":True,
    }
    receipt_sha=_write_exclusive(folder/"runtime_receipt.json",receipt)
    return {**receipt,"runtime_receipt_sha256":receipt_sha}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-omni-runtime-compat")
    p.add_argument("--worker",action="store_true")
    p.add_argument("--out",type=Path)
    p.add_argument("--model",type=Path)
    p.add_argument("--model-sha256")
    p.add_argument("--python",type=Path)
    p.add_argument("--variant",choices=("7b",),default="7b")
    p.add_argument("--timeout-seconds",type=int,default=60)
    p.add_argument("--execute",action="store_true")
    x=p.parse_args(argv)
    try:
        if x.worker:
            if (not x.out or x.model or x.model_sha256 or x.execute or
                x.python or x.timeout_seconds!=60):
                raise RuntimeCompatError("Worker is only for isolated dependency check.")
            if (not x.out.is_absolute() or x.out.exists() or x.out.is_symlink()
                or not x.out.parent.is_dir() or
                (x.out.parent.stat().st_mode & 0o022)):
                raise RuntimeCompatError("Worker must write exactly one private result.")
            _ensure_private(x.out.parent)
            _write_exclusive(x.out,inspect_apple_mps())
            return 0
        if x.model is None or x.model_sha256 is None:
            raise RuntimeCompatError("Model directory + complete checkpoint SHA required.")
        result=probe_runtime(model=x.model,
            model_sha256=x.model_sha256,variant=x.variant,
            python_binary=x.python,out_dir=x.out,
            timeout_seconds=x.timeout_seconds,execute=x.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (RuntimeCompatError,ModelProcessError,ModelPackageError,
            OmniAdapterError,EvidenceCaptureError,ValueError,TypeError,
            OSError,KeyError) as exc:
        print("M46_RUNTIME_COMPAT_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
