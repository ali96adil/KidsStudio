# M44 — Kill all local AI subprocess workers; pin and owner-sign 7B origin evidence

**Development branch, draft PR #28.** No owner's Mac/Pi was contacted.
No production model was installed or executed; no real provenance or
license certificate has been obtained, no media upload or publication.

## 1. Model subprocess lifecycle

M43 used `subprocess.run(timeout=...)`. This can stop the immediate
adapter but leave Python/ML child workers alive, including GPU tasks.
M44 introduces `kidsstudio/model_process_group.py` and makes M43
default to this safer execution boundary:

- POSIX/macOS only, no shell, executable must be an absolute owner-pinned
  local file. The real subprocess starts a **new session/process group**.
- The parent and **descendants in that group** receive SIGTERM followed
  by SIGKILL after a small grace period on timeout, errors, interruption,
  and **after the parent exits successfully**. The original process is
  reaped. A child that forks and deliberately creates a *different*
  session may escape; this still requires OS-level isolation if the
  model runner is untrusted.
- The process inherits no OAuth, HMAC, GitHub or OpenAI token. The
  caller passes the small allowlisted M29 subprocess environment with
  Hugging Face offline environment variables. Stdout/stderr are
  discarded, so secrets and huge logs are not buffered into memory.
- M43's maximum 900-second deadline, single model attempt, source
  SHA re-verification, immutable private outputs and UNSURE-only
  gate remain unchanged. Timeout or nonzero exit cannot produce a
  success metrics receipt. This is a resource-control boundary, not
  a GPU-memory measurement and not a claim of guaranteed complete
  cleanup of intentionally detached processes.

`tests/test_model_process_group_m44.py` launches *actual* POSIX
Python parent/child processes that would write a marker after the
deadline. It verifies the marker never appears after timeout **or
after an otherwise successful parent exit**, and that secret-bearing
or unbounded invocations are rejected. No trained model is involved.

## 2. Offline owner-attested model source and Apache-2.0 evidence

`studio-model-origin` creates/verifies a separate **private,
SHA-pinned, owner-HMAC-signed** receipt. No output path, OAuth secret
or private signing key goes into the public GitHub repository.

Unsigned draft fields are exact and immutable after signing:
```json
{
  "schema_version": 1,
  "checkpoint_package_sha256": "<actual complete M41 manifest SHA256>",
  "upstream_provider": "huggingface",
  "upstream_repository": "Qwen/Qwen2.5-Omni-7B",
  "upstream_revision": "<actual 40-character upstream commit>",
  "source_identity": "official_repository_claim",
  "model_variant": "7b",
  "license_spdx_claim": "Apache-2.0",
  "license_copy_path": "/PRIVATE/owner-license-evidence/LICENSE.txt",
  "license_copy_sha256": "<actual SHA256 of this private license copy>",
  "source_reviewed_by_owner": true,
  "license_reviewed_by_owner": true,
  "usage_scope": "local_diagnostic_only",
  "owner_review_note": "I checked this particular source and license document; pending independent validation.",
  "model_quality_qualified": false,
  "youtube_private_upload_authorized": false,
  "public_release_authorized": false
}
```

**These fields are not evidence until the owner actually reviews the
source and license and uses an authentic private secret to sign.**
The example is **not runnable** with placeholders. The attached copy
must resemble actual Apache License Version 2.0 text, be at least
200 bytes, have a separately pinned SHA, and remain private and
unchanged. 3B, research/unknown/changed licenses, altered revisions
and unsigned/forged records are denied.

One-time offline workflow:

```sh
# Store a strong private key in a local secret manager; expose it only
# to this invocation. Never use a test key or commit it to source control.
export KIDS_STUDIO_MODEL_ORIGIN_KEY="<owner-private-32+-byte-key>"

# Inspection: checks the complete model, draft and license bytes.
# It computes the signature without writing a signed record.
studio-model-origin \
  --model /PRIVATE/models/qwen2_5_omni_7b \
  --model-sha256 <actual-model-package-SHA256> \
  inspect --draft /PRIVATE/owner-license-evidence/model_draft.json \
  --draft-sha256 <actual-draft-SHA256> \
  --out /PRIVATE/owner-license-evidence/signed_model_origin.json

# An authorized --execute creates that receipt ONCE. Further changes
# need a new versioned path and an explicit new owner signature.

# Verify later:
studio-model-origin \
  --model /PRIVATE/models/qwen2_5_omni_7b \
  --model-sha256 <actual-model-package-SHA256> \
  verify \
  --receipt /PRIVATE/owner-license-evidence/signed_model_origin.json \
  --receipt-sha256 <actual-signed-receipt-SHA256>
```

On M43 model `--execute`, `--origin-receipt`,
`--origin-receipt-sha256` and the environment key are mandatory.
The owner receipt is revalidated **both before and after model
execution**. Missing/altered provenance blocks any new probe directory.
Dry-run preflight remains source-checking only and can report why
Mac resources are blocked without signing or running a model.

**Crucial trust limitation:** Local owner-HMAC proves integrity and
possession of a signing key. A malicious person can still copy a genuine
Apache license next to unrelated weights and forge claimed
`upstream_revision`. M44 cannot access the official upstream repo
from the owner's offline pilot and does **not independently verify**
the upstream commit or legal applicability. Neither
`source_independently_verified` nor `license_legally_adjudicated`
nor `third_party_licenses_verified` become TRUE. The receipt authorizes
a specifically bounded local diagnostic **only**, not commercial
release or automatic YouTube PRIVATE/PUBLIC uploads.

The default recommended candidate remains Qwen2.5-Omni **7B** under
the official Apache-2.0 listing; the **3B Research License** is
excluded from the commercial pilot. Official license pages:
https://huggingface.co/Qwen/Qwen2.5-Omni-7B/blob/main/LICENSE
https://huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/main/LICENSE

## 3. Test scope

`tests/test_model_origin_attestation_m44.py` exercises positive
HMAC evidence, read-only signing, one-time exclusive creation,
changed license/model/receipt, wrong key, false owner review,
forged 3B identity and any attempt to grant public rights.
`tests/test_model_pilot_probe_m43.py` now also refuses to execute
without this exact owner receipt or when the license copy is altered.
CI uses synthetic model files, a **fake license copy** and a fake
model command; these tests **never establish legal rights, actual
model capability, trained AI inference or real Mac memory**.

## Next external facts needed before a real Mac test

The installed 7B snapshot, complete SHA-pinned model files, official
revision and corresponding license copy, actual local dependent
Transformers/PyTorch build compatibility, measured MPS RAM demand,
and independently verified safe/offline behavior of the installed
runner. Only then consider one explicit M43 diagnostic pilot. The
separate M39 ground-truth audio/AV calibration and final owner PRIVATE
video review remain blocked. No public publishing functionality is
unlocked by this milestone.
