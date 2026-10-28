# M41 — Pinned multi-file HF / MLX model packages (private, offline)

**Status:** Source code in the KidsStudio development branch, draft PR #28.
No owner Mac or Raspberry Pi was contacted. No trained model was
installed, downloaded, loaded or evaluated; no video was uploaded.

## Why M41 matters

M40 could pin only a single `.bin`, `.gguf` or `.safetensors` file per
reviewer. Most Hugging Face / MLX checkpoints are **directories** containing
multiple safetensors shards, `config.json`, tokenizer data and metadata.
Pretending one shard's SHA represents the entire trained model leaves other
source bytes unverified. M41 provides an audited package format and extends
the **actual** M34 WAV and M37 synchronized audiovisual adapter interfaces
to accept these verified directories with `--model /PRIVATE/model-directory`.

The installed `whisper.cpp` ASR role deliberately **still requires a
single .bin checkpoint**. Sharded model packages are supported only for
the four independent audio and AV reviewers; actual local adapters must
be written for the chosen model runtime and understand a directory
`--model` argument. No automatic Transformers/MLX engine is installed
or auto-detected by this milestone.

## Model package contract

Each checkpoint directory has a file named `model_files.json`:

```json
{
  "schema_version": 1,
  "format": "kidsstudio_sharded_model_v1",
  "files": [
    {"path": "config.json", "sha256": "<actual SHA256>", "bytes": 412},
    {"path": "model-00001-of-00002.safetensors",
     "sha256": "<actual SHA256>", "bytes": 100000000},
    {"path": "model-00002-of-00002.safetensors",
     "sha256": "<actual SHA256>", "bytes": 100000000}
  ],
  "inference_qualified": false,
  "public_release_authorized": false
}
```

The sizes and SHAs above are illustrative only. The directory's
`model_sha256` inside the existing M40 bundle is **the SHA256 of the
exact `model_files.json` file**. Critically, that digest alone is not
sufficient: `verify_checkpoint` and `checkpoint_digest` re-open the
package, verify *every* member size and SHA, and enumerate every current
file in the directory to reject unlisted, missing or substituted files.
They also reject symlinks, traversal, paths escaping the root, hidden
directories, hidden files, executables/scripts, and changed manifests.
File scans are repeated after each M34/M37 reviewer execution, so a
model replaced during invocation cannot produce accepted evidence.

Bounded scope: maximum 128 package files, 7 GB per individual member
and 35 GB total. Accepted data suffixes include safetensors, GGUF, BIN,
JSON, tokenizer TXT, vocab, model and tiktoken metadata. No `.py`
files are accepted; never use `trust_remote_code=True` or execute a
model repository's scripts. A model that requires executable extensions
cannot silently bypass this approval boundary.

## Safer setup, when explicitly ready for a real owner-Mac inspection

First place the already installed complete sharded model into a
dedicated owner-private local folder. Only after selecting its checkpoint
and verifying usage rights, run:

```sh
# Read-only by default: compute member SHA and package SHA in stdout.
studio-model-package --directory /PRIVATE/models/reviewer-a

# Explicit write once: creates model_files.json exclusively.
studio-model-package --directory /PRIVATE/models/reviewer-a --execute

# Pin that computed package_sha256 as reviewer.model_sha256 in the M40
# private model_bundle.json and set reviewer.model to the full directory.
# Rehash that whole M40 bundle and use studio-model-bundle inspect.
```

If any file changes, the package fails closed. The freeze tool never
overwrites an existing manifest, never downloads a checkpoint, and never
publishes. If the package is wrong, create a **new versioned directory**
and a newly pinned bundle instead of quietly editing an approved package.

## Scope proven by CI

`tests/test_model_packages_m41.py` covers real file SHA digests,
a complete synthetic multi-file model directory, M40 load, rejection of
extra/deleted/mutated members, symlinks and escaping paths, a one-time
freeze CLI, rejection of hidden/script files, and an actual FFmpeg
sound-bearing MP4 passed to the M37 review bridge through a fake
directory-aware AV executable that correctly returns **UNSURE**.
All other existing M34/M37 tests continue to exercise single-file
compatibility.

**None of those synthetic tests qualify the model's ability to hear
Arabic, synchronize lips, review children's content or adjudicate rights.**
The new package is only source-byte provenance. Before an actual Mac/Pi
pilot, independent real model execution, memory measurements, real AV
canary calibration (M39), proper source rights, and authenticated Pi
transfers remain mandatory. No default PRIVATE upload and no PUBLIC
publishing permission arise from M41.
