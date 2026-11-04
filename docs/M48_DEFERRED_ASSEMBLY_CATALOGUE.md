# M48 — Two-phase final montage catalogue binding after scene QA

**Code-only, draft PR #28; no Mac/Pi deployment, model inference, video upload or PUBLIC permission.**

## Real integration defect corrected

M32 required the final assembly catalogue SHA256 when the orchestrator's
immutable plan was pinned, BEFORE any scene voice or LTX was produced.
However M13 scene QA and M14 freeze only create that catalogue AFTER all
approved scene jobs exist. Requiring the true final SHA before those
jobs was a circular dependency: a successful synthetic test could pin
an arbitrary dummy hash, but a legitimate first real episode cannot
know the catalogue hash until the end.

## M48 opt-in plan

New M32 orchestrator plan may use exactly:

    "assembly": {
      "recipe_id": "colors_ar_episode01_v1",
      "catalogue_sha256": "AFTER_SCENE_QA"
    }

The rest of the original immutable M32 plan (series, episode, approved
parent script, scene-plan SHA, ordered scene scripts, voice/LTX recipe
IDs, PRIVATE-only policy) remains unchanged. Previously pinned literal
64-character catalog SHA plans are supported for old test/recovery
use and cannot be rebound.

The scene loop and signed M28 QA are unaffected. Once every scene is
QA_APPROVED, M32 status reports M48_ASSEMBLY_CATALOGUE_NOT_BOUND instead
of queuing a final master with a fabricated digest.

## Final binding — one atomic, explicit owner step

Only AFTER the M13 scene outputs are approved and the real M14 Mac
catalogue exists, make an owner-controlled copy of M14 scene_evidence.json
metadata into the private authorized Pi environment. It MUST have all
the original M14 fields, including plan SHA, exact approved episode script,
ordered per-scene original script hashes, voice/LTX job IDs, actual
media hashes, and no publication permission.

An owner may then use:

    studio-orchestrator --db /PRIVATE/studio.sqlite \
      --plan /PRIVATE/orchestrator.json \
      --evidence /PRIVATE/copied_m14_scene_evidence.json \
      --catalogue-sha256 EXACT_SHA_OF_PRIVATE_MAC_M14_CATALOGUE \
      bind-assembly

An atomic Studio Brain SQLite transaction checks:
- M32 original plan SHA remains exactly pinned; no replacement.
- Parent script and active episode remain currently approved.
- Studio queue not paused; no duplicate binding.
- Every scene's M13 current voice/LTX QA state, completed Pi job
  receipts, WAV→LTX SHA and technical audio evidence are current.
- All owner-supplied M14 scene identity, source SHA, job IDs and artifact
  hashes agree with that same transaction.
- It records exact M14 metadata SHA, full current scene-set canonical
  SHA, catalogue SHA, and pinned original plan SHA.
- Does NOT enqueue a job, render media, change files or publish anything.

A second binding to another catalogue fails. The real Mac M6 worker
still re-hashes the entire frozen M14 catalogue and source files and
requires the exact Pi M16 catalogue SHA before rendering. Therefore
the Pi cannot silently switch jobs to another final media catalogue
even after it was initially accepted.

## M32 tick after binding

M32 only selects ASSEMBLE_FINAL_EPISODE when the binding matches the
original plan AND the current exact per-scene job+artifact hash set.
Changed/forged stage job/voice/video SHA, old M14 metadata or modified
plan blocks assembly, even if the scene stages are still superficially
QA_APPROVED. It then queues only ONE exact SHA-pinned render job.

## Current trust boundary

M48 validates a copied owner-controlled M14 metadata file against the
actual Pi receipts, NOT direct Mac disk access from Pi. The operator
must supply the correct SHA of the frozen Mac catalogue; the Mac
separately checks that against its actual catalogue and files. This
is NOT remote cryptographic device attestation, not proof of child-safe
artistic content or commercial license.

CI tests use synthetic Pi scene receipts and fabricated M14 metadata,
not real Mac model output. Do not claim the Mac/Pi system passed real
device tests. The next owner-authorized qualification still needs real
Chatterbox/MLX voice, LTX audio/video and independently competent
review models, FFmpeg master and private owner preview.

Existing user devices, YouTube account, main branch and PR draft
status remain unchanged by this stage.
