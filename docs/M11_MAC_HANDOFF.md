# M11 — Final static Mac handoff and non-destructive Bunny asset intake

**Status:** GitHub draft PR development only. No user Mac/Pi installation, live
Chatterbox or LTX inference, model download, paid API, external service,
YouTube upload, private preview or public publication occurred.

## Why this was needed

M10 permits original Bunny reference artwork in a distinct approved
ComfyUI-Shared root, but M6 StagePlan only allows runtime inputs within its
primary KidsStudio private_root. A correct-looking static inventory could
therefore pass while the later real media job refuses to run. M11 resolves
this without moving, overwriting or modifying the artist's original image.

M11 also closes a second gap: a valid M10 inventory and a valid M6 stage
recipe do NOT necessarily reference the same approved script, wrapper,
Python environment, FFprobe executable or model manifest. Merely testing
the two independently does not establish a consistent production handoff.

## 1. Exact source image import

The optional studio-import-bunny tool:
- requires owner-supplied absolute original PNG and approved source root;
- checks the exact original SHA256, PNG signature, allowed size and no symlink;
- PREVIEW mode does not write any file;
- only --execute creates a new, private, uniquely named immutable copy under
  KidsStudio/assets/imports/ASSET_ID/bunny_reference.png;
- hashes both the original and the new copy after writing;
- saves a local receipt with both SHA256 values and no original source path;
- rejects reusing an existing asset ID, replacing an old copy or broken receipt;
- does not alter ComfyUI-Shared, models, existing video, prompts or Git files.

Future owner commands (NOT to run now):

    studio-import-bunny \
      --source /PRIVATE/ComfyUI-Shared/input/Bunny_reference.png \
      --approved-source-root /PRIVATE/ComfyUI-Shared \
      --private-root /PRIVATE/KidsStudio \
      --asset-id bunny_front_v01 --sha256 OWNER_ORIGINAL_SHA256

    studio-import-bunny \
      --source /PRIVATE/ComfyUI-Shared/input/Bunny_reference.png \
      --approved-source-root /PRIVATE/ComfyUI-Shared \
      --private-root /PRIVATE/KidsStudio \
      --asset-id bunny_front_v01 --sha256 OWNER_ORIGINAL_SHA256 --execute

    studio-import-bunny \
      --private-root /PRIVATE/KidsStudio \
      --asset-id bunny_front_v01 --sha256 OWNER_ORIGINAL_SHA256 --verify

A partial failed import stays in its reserved directory for explicit owner
reconciliation; no silent retry, cleanup or overwrite.

## 2. Static exact two-stage handoff, no engine execution

The new studio-handoff-review compares an already verified M10 Mac contract
and explicit M6 voice recipe, with an OPTIONAL LTX recipe. It validates:
- Mac contract checkpoint hashes, runtime and storage prerequisites;
- StagePlan's own preflight with hash-pinned private file inputs;
- same primary KidsStudio root and approved script SHA and path;
- same pinned Python interpreter SHA for each stage, same wrapper source
  path/SHA, FFprobe binary SHA and same approved model manifest;
- LTX references exactly the approved original Bunny image bytes, and when
  the original remains outside the primary KidsStudio root, a *verified M11
  imported copy* is used instead of an ad-hoc copy;
- script SHA equality between voice stage and LTX stage when both exist.

If only the voice stage is available, the status is
VOICE_READY_LTX_RECIPE_PENDING_APPROVED_WAV. This is the honest stage BEFORE
generating and owner-approving a WAV: the final LTX recipe cannot yet pin its
future source audio hash. If both stage manifests match, the status is
STAGE_MANIFESTS_MATCH_NOT_RUN, never "rendered" or "approved."

Future read-only command, AFTER an owner-authorized Mac installation:

    studio-handoff-review \
      --mac-contract /PRIVATE/KidsStudio/mac_contract.json \
      --voice-recipe /PRIVATE/KidsStudio/recipes/voice_stage.json

Later, after actual WAV generation and owner approval:

    studio-handoff-review \
      --mac-contract /PRIVATE/KidsStudio/mac_contract.json \
      --voice-recipe /PRIVATE/KidsStudio/recipes/voice_stage.json \
      --ltx-recipe /PRIVATE/KidsStudio/recipes/ltx_stage.json

Neither tool invokes an engine entrypoint, compiles a model, contacts an API,
updates Studio Brain SQLite or queues a remote job. Both can be used on
approved local files in a later final integration session. Reports omit
absolute source paths and private media contents.

## 3. Known remaining limits / future single Mac-Pi acceptance

- Real Chatterbox Multilingual MLX and LTX-2.3 MLX Python/CLI adapters have
  NOT been verified against installed versions. Hash-pinned wrapper source
  is a trust anchor, not an executed API qualification.
- A static handoff cannot prove the future generated WAV or A2V is good.
- The voice SHA receipt and M10 audio-continuity + human lip-sync QA must
  be checked AFTER real render. Do not pre-fill an ungenerated audio SHA.
- Checkpoint SHA proves file bytes only, not licensing, authenticity or model
  performance. Owner must independently check commercial voice/music/art
  permissions and educational quality.
- Global GPU coordination is cooperative only for integrated KidsStudio jobs.
- Previous standalone Control Center v1-v3 DB migration, independent backup
  restore, whole real episode rendering, private YouTube review remain pending.
- Keep draft PR unmerged and no user-device changes until the agreed
  owner-authorized full end-to-end acceptance test.

All CI tests are synthetic: they prove static agreement, non-destructive PNG
copy and rejection of mismatched sources, NOT successful real MLX inference.
