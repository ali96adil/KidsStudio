# M46 — Mac runtime compatibility, no Qwen weights loaded

**Status:** Development only, draft PR #28. No owner Mac, Raspberry Pi,
model checkpoint, YouTube account or authenticated production device
was contacted while authoring M46. CI uses synthetic Torch/MPS modules.

M42–M45 can prove a local checkpoint package and installed Python
*module filenames* exist; that is NOT enough to prove the installed
PyTorch version can actually perform work on Apple MPS or that the
installed Transformers build provides the Qwen2.5 Omni **Thinker** API.

M46 adds `studio-omni-runtime-compat`, deliberately **not** a second
model-quality approval. It is an explicit, small and bounded
local dependency probe:

* Default (without `--execute`): re-hash all files in the private
  M41 model directory, validate the exact config's 7B architecture,
  and run the M42 **screen** for RAM, disk and dependency *presence*.
  It imports no Torch, loads no weights, writes nothing, uses no network.
* Explicit `--execute` **only on an owner-authorized Apple Silicon
  Mac**: starts a fresh Python `-I` isolated worker process under
  M44's bounded process-group shutdown. Its max timeout is 180 seconds.
  The worker imports installed Torch and Transformers with Hugging Face
  offline environment variables and no inherited API keys.
* It checks both
  `Qwen2_5OmniThinkerForConditionalGeneration` and
  `Qwen2_5OmniProcessor` have a callable `from_pretrained`.
  **It never calls from_pretrained.** It then verifies the actual
  `torch.backends.mps.is_built()`/`is_available()` and performs
  exactly one scalar tensor operation on `device="mps"`,
  checking the numeric result and that the result's device is MPS
  rather than a CPU fallback.
* A worker error or timeout produces no successful compatibility
  receipt; the new process group is terminated, including non-detached
  children. A successful observation creates only one private
  `mps_runtime.json` in a new output directory, with short, validated
  version strings and **all model-competence/publication flags false**.
* The parent re-hashes the entire original M41 model directory and the
  Python interpreter executable after the check and refuses any
  changed model/runner. This is a proof of runtime API and a scalar MPS
  operation in that process, **not** proof that a 7B model loads,
  that 10-second audiovisual inference fits in unified RAM,
  that audio/Arabic/lip-sync works, or that a checkpoint is licensed.
* The probe does not make a network syscall itself, but imported
  third-party dependencies are executable code; Hugging Face offline
  settings are **not a complete OS network sandbox**.
  A later Mac pilot must arrange process/user/network isolation.
  Model-legal provenance remains a separate M44 owner claim.

The worker runs from the installed `kidsstudio` package under
`python -I -m kidsstudio.omni_runtime_compat`. It must therefore be
installed in the same isolated Python environment as Torch and
Transformers. An executable venv Python may be a symlink; the tool
pins the resolved executable bytes and retains the original venv path
to preserve package resolution. The compatibility command does not
install or download any dependencies.

## Future Mac-only usage (illustrative, not executed)

```sh
# Default: no Torch import and no model inference.
studio-omni-runtime-compat \
 --model /PRIVATE/models/qwen_omni_7b \
 --model-sha256 <actual-complete-M41-package-SHA256>

# A later explicitly authorized small Apple-MPS scalar test only.
# NEVER an automatic model run or YouTube publication.
studio-omni-runtime-compat \
 --model /PRIVATE/models/qwen_omni_7b \
 --model-sha256 <actual-complete-M41-package-SHA256> \
 --out /PRIVATE/runtime-checks/omni-mps-scalar-001 \
 --execute --timeout-seconds 60
```

Successful result:
`M46_RUNTIME_OBSERVATION_NOT_MODEL_QUALIFICATION`. It reports
`mps_scalar_probe_reported=true`, but
`model_weights_loaded=false`, `model_quality_qualified=false`,
`mac_pi_hardware_qualified=false`,
`private_upload_permitted=false` and
`public_release_authorized=false`.

No output or action of M46 can override M39 independent canary truth,
M44 legal source checks, M45 NOT READY inventory, current Mac/Pi TLS,
actual production assets or explicit owner video approval.

## Sources / truthful scope

Hugging Face's documented
`Qwen2_5OmniThinkerForConditionalGeneration` + processor API supports
mixed audio/video and text-only observation without loading the
separate audio-generation model:
https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/qwen2_5_omni.md

The official 7B configuration shows the 3584-hidden/28-layer Thinker
text architecture used for the existing M42 7B screening rule:
https://huggingface.co/Qwen/Qwen2.5-Omni-7B/blob/main/config.json

`tests/test_omni_runtime_compat_m46.py` uses fake Torch/Transformers
modules, mock MPS arithmetic and a fake worker result. This verifies
the **software rejection contracts**, not genuine Apple MPS hardware.
The earlier actual-FFmpeg/synthetic-model tests remain separate.
