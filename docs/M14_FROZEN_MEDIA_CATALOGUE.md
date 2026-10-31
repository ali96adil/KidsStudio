# M14 — Frozen scene-to-Mac worker catalogue

STATUS: Development code on draft GitHub PR #28. No owner Mac/Pi installation, engine inference, paid API, rendering, or YouTube upload occurred.

## The concrete missing link

M13 authenticates each scene's Pi job receipts and actual Mac files, then produces a pinned M4 FFmpeg assembly recipe. Previously the M6 Mac worker accepted any approved-looking M4 recipe by SHA; that alone did not prove the chosen clips had passed M13's per-scene review.

M14 introduces a deliberate owner-controlled freeze between M13 approval and M6 worker execution.

## Manual freeze (future device test only)

The one-shot studio-scene-catalogue command reads the current Studio Brain approved scene plan, previously generated M4 recipe, and each current local narration WAV, A2V MP4, Mac stage receipt, and exact Pi completed typed job result. It checks source SHA, scene order, owner stage QA and matching M10 technical audio evidence.

It creates two NEW private, non-overwritable files under the approved Mac root:
- Scene evidence JSON with original approved episode script hash, full scene-plan SHA, montage recipe SHA, ordered scenes, current job IDs, scene script SHA, voice WAV SHA, LTX MP4 SHA, and roots.
- Frozen Mac MediaRecipes catalogue JSON, with episode_recipe and scene_evidence inputs both SHA-pinned.

No job is started, no media modified, no model called, no upload performed.

Example owner command for LATER, not to run today:

    studio-scene-catalogue --db /PRIVATE/studio.sqlite \
      --template /PRIVATE/KidsStudio/template.json \
      --assembly-recipe /PRIVATE/KidsStudio/recipes/ep01.json \
      --series colors-ar --episode 1 \
      --voice-output-root /PRIVATE/KidsStudio/voice_outputs \
      --ltx-output-root /PRIVATE/KidsStudio/ltx_outputs \
      --evidence /PRIVATE/KidsStudio/catalogue/evidence_v1.json \
      --catalogue /PRIVATE/KidsStudio/catalogue/catalogue_v1.json \
      --recipe-id colors_ar_ep01_v1

## Local Mac worker now fails closed

For any episode_assemble recipe containing more than ONE clip, MediaRecipes.resolve requires the additional scene_evidence input. It verifies the exact saved episode recipe SHA, seal SHA, scene numbers, hashes, current local WAV/MP4 bytes, and matching local Mac stage receipt files. A separately valid MP4 cannot be swapped into the montage. A changed receipt, substituted audio, missing seal or repeated freeze is rejected before rendering. Existing one-scene legacy recipes can still be reviewed independently.

The worker's remote payload still supplies only the allowlisted recipe_id and script SHA — never an arbitrary path, model, shell command or publication permission.

### Deliberate trust boundaries

This is a SHA-pinned owner-controlled local attestation, NOT a PKI signature or remote proof that the Pi approved the catalogue hash. A future coordinator-side catalogue SHA pin remains a possible further improvement. The seal also does not prove originality, copyright, voice rights, genuine lip-sync or pedagogic benefit. Owner must review the completed video under M7 and explicitly approve its final media hash.

Media is on the Mac, Studio Brain may be on Pi, so the one-time source evidence transfer still requires a trusted owner-authorized environment. No automatic transfer or live model compatibility is introduced.

## Offline CI coverage

Synthetic two-scene tests exercise successful frozen catalogue verification, refusal of unsealed multi-clip catalogues, changed second-clip media, mutated Mac stage receipts and no-overwrite semantics. No real Chatterbox or LTX inference or real media rendering occurs. All changes remain in DRAFT PR #28, unmerged into main.
