# M49 — Verify the actual frozen Mac catalogue on the Pi

**Status:** GitHub draft PR #28 only. No installation, owner Mac/Pi access,
real TTS/LTX inference, paid API, YouTube upload or public publication.

## Why M49 is necessary

M48 defers binding the episode montage until every scene is independently
QA approved, but previously accepted an owner-supplied catalogue SHA256
without checking its actual file bytes. A mistaken or forged SHA could
enter the job queue even though the Mac never had a matching catalogue.

M49 now requires the owner-authorized operator host to access TWO actual
copies of M14 metadata files: the scene evidence JSON and frozen catalogue
JSON. The Pi-side one-time binding validates:
- Exact SHA256 of the actual M14 catalogue file matches the supplied pin.
- Absolute, private non-symlink JSON; bounded 60 KB; outside Git.
- Exactly one expected episode_assemble recipe under the approved M32 ID.
- Exactly two required original Mac media file references: episode_recipe
  and scene_evidence, with SHA pins and absolute path metadata.
- Catalogue's scene_evidence SHA equals the actual Pi-side evidence copy.
- Catalogue's episode_recipe SHA equals the original recipe SHA inside
  M14 evidence.
- Every scene/job/voice/visual SHA in M14 evidence matches current
  approved and completed Studio Brain Pi records.
- Paused or mutated jobs and attempts to rebind remain blocked.
- Binding never starts rendering or publishes media.

## Later authorized two-device pilot: correct sequence

1. Owner pins a 2-scene M32 plan using the marker AFTER_SCENE_QA as the
   final assembly catalogue_sha256. The recipe_id is chosen in advance.
2. Mac/Pi produces every scene WAV and LTX output, reviews its exact
   SHA and technical voice continuity, and records independent QA.
3. On owner Mac, M13 builds the local montage recipe, and M14 freezes
   the corresponding scene evidence and catalogue. This happens only
   AFTER the last scene passed QA.
4. Owner deliberately transfers BYTE-IDENTICAL COPIES of both M14 JSON
   files to a private Pi/operator folder, preserving embedded original
   absolute MAC paths and JSON bytes. The Pi does not read those Mac
   media paths; they are metadata for the Mac-side worker.
5. Operator compares the local copy SHA to the Mac's actual catalogue
   SHA, then runs:

       python -m kidsstudio.studio_orchestrator \
         --db /PRIVATE/studio.sqlite \
         --plan /PRIVATE/orchestrator.json \
         --evidence /PRIVATE/pi_copies/scene_evidence.json \
         --catalogue /PRIVATE/pi_copies/frozen_catalogue.json \
         --catalogue-sha256 EXACT_MAC_CATALOGUE_SHA256 \
         bind-assembly

6. Successful binding records the exact immutable SHA and current
   scene-set hash but queues NO job. A separate operator tick starts
   the job; Pi sends the SHA and approved recipe ID.
7. Mac M16 re-hashes its ORIGINAL catalogue and independently verifies
   all local media, receipts and exact M14 evidence before FFmpeg.

A Pi file SHA proves only the transferred metadata. It is not a remote
digital signature or proof the Mac media exists. Actual Mac media
authenticity remains the authenticated worker's responsibility.

## Synthetic tests

M32/M48 integration suite now covers exact private catalogue matching,
wrong hash, mismatched M14 evidence or montage SHA, wrong recipe ID,
symlink rejection, duplicate bindings and incomplete staged QA.
These are simulation tests, not a production hardware qualification.

**Keep PR #28 draft, unmerged and private.** No owner-device deployment,
model inference, OAuth or YouTube upload has occurred.
