# M19 — Two-scene Mac voice preflight, with genuine distinct scene scripts

**Scope:** GitHub draft PR #28 only. No installed owner Mac/Pi services, no
Chatterbox or LTX inference, model downloads, ComfyUI/FLUX image production,
personal media, account access, paid API, publishing or backup operations.

## Integration gap

M11's static handoff used a *single parent* `approved_script` asset.
M13 deliberately stores different SHA256-pinned scripts for every approved
scene of an episode. Reusing M11 without adjustment would reject two
legitimate distinct scene scripts, or (worse) encourage an operator to
reuse the same full episode text for both voice jobs.

M19 adds a conservative **two-scene, voice-only, no-execution** CLI. It
keeps M11's exact parent-script rule unchanged for legacy full-episode
handoff. Only M19's separately validated M13-style scene-plan caller
may bind different scene scripts into the same M11 Mac wrapper/tool/engine
verification logic.

## Preconditions for a future explicitly authorized owner Mac test

Have actual owner-reviewed private files under the approved Mac primary
private root (these paths below are placeholders, not real discovered paths):

- M10 `mac_contract.json`, referencing the approved **parent** episode
  script, original Bunny asset and exact Chatterbox/LTX checkpoint bytes;
- M13-style `scene_plan.json` with exactly two ordered, distinct scene
  script SHA256 values and the parent episode-script SHA256, **plus its exact
  owner-recorded plan SHA256** from M13 registration;
- two original independent, already-owner-reviewed scene text files;
- two M6 `voice_synthesize` recipes, each pinning the appropriate scene
  script as *both* its `script` and `inputs.script`;
- the same owner-approved voice wrapper source, Python runtime, FFprobe
  and engine manifest as the M10 contract.

The M10 Mac contract's `approved_script` still identifies the **parent**
episode script. The M19 script overrides are strictly checked against
the **M13-style scene plan**, never treated as the same parent text.

The exact local command, only once files exist and the user authorizes
a workstation inspection, is:

```bash
studio-two-scene-preflight \
  --mac-contract /PRIVATE/KidsStudio/mac_contract.json \
  --scene-plan /PRIVATE/KidsStudio/scene_plan.json \
  --scene-plan-sha256 EXACT_OWNER_RECORDED_M13_PLAN_SHA256 \
  --scene-1-script /PRIVATE/KidsStudio/scripts/scene01.txt \
  --scene-1-voice-recipe /PRIVATE/KidsStudio/recipes/scene01_voice.json \
  --scene-2-script /PRIVATE/KidsStudio/scripts/scene02.txt \
  --scene-2-voice-recipe /PRIVATE/KidsStudio/recipes/scene02_voice.json
```

No `--execute` option exists. The CLI is read-only, performs no model
execution and no transmission. It returns a redacted JSON result:
`TWO_SCENE_VOICE_CONFIG_PINNED_NOT_RUN`, or exits with a private-path-free
blocked code. It never writes a report, alters a source, changes a queue,
claims real engine readiness, creates a worker lease or approves publication.

## Evidence and boundaries

The new synthetic tests verify:

1. Two different source scene scripts can match the *same* M10 Mac contract
   while preserving each individual exact recipe/source pin.
2. Source/recipe swap or altered script bytes fails.
3. Parent episode SHA mismatch, **changed approved scene-plan bytes**, or duplicate scene hashes fails.
4. Replacing the approved Chatterbox wrapper with the LTX wrapper fails.
5. The existing M11 parent-script handoff remains strict, so no legacy
   behavior is widened.
6. All tests remain read-only with no output directory, private path
   disclosure, model inference or uploads.

**Important:** An M13-shaped local JSON file is an *owner-supplied claim*,
not cryptographic evidence that the real Pi Studio Brain registered or
approved it. This first-stage tool reports
`canonical_pi_scene_approval_verified: false`; the device test must
cross-check M13's real immutable scene plan and owner approval first.

Passing M19 does **not** establish Chatterbox wrapper API compatibility,
working audio, a legal voice license, child-safe dialogue, Bunny animation,
WAV approval, M10 audio continuity, M7 final quality, independent backups,
or any YouTube eligibility. The LTX recipe **must not** be pre-filled with
an imaginary audio SHA: it is created only after the actual voice WAV
exists and the owner has listened to and approved that exact hash.

## Next stage (not started)

A later explicit owner-authorized Mac/Pi pilot will:

1. Verify this M19 scene plan against canonical M13 Pi episode/scenes.
2. On the Mac, qualify the real Chatterbox Multilingual MLX wrapper API,
   verify checkpoint terms and approved voice reference; run only the first
   scene, listen, and approve its WAV.
3. Do the same for the second scene; pin real WAV inputs in LTX stage plans.
4. Verify LTX-2.3 MLX real wrapper, stage media and M10 continuity; inspect
   output visually and acoustically before owner approval.
5. Freeze M14/M16 exact scene catalogue, assemble with M18-tested real
   final-master FFmpeg, run M7's *actual* media QA and all 11 substantive
   independent human/rights criteria, and test separate media backups.
6. Keep YouTube **PRIVATE** upload behind a fresh owner instruction;
   public publishing is a later, separate action.

Failure in any asset checksum, model rights, worker version, device clock,
audio/video QA or backup blocks the trial. No automatic retries or release.
