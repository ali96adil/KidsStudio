# M6 — Voice and LTX production stage contracts

**Status: code in a draft GitHub PR only. No owner Mac/Pi deployment.**
Tests use synthetic local executors and synthetic media. No actual
Chatterbox or LTX inference, weight download, API call or YouTube publishing.

## Studio production sequence

1. The writer generates an independent script which is manually approved
   with its immutable SHA256 by the owner.
2. voice_synthesize queues one approved Mac-local Chatterbox recipe. Its
   WAV result is registered as VOICE_RENDERED_PENDING_QA.
3. Owner hears and verifies the exact WAV, pronunciation, quality and rights,
   and explicitly records QA_APPROVED against the WAV digest.
4. ltx_animate can be queued only after voice owner approval. The Pi job binds
   the exact owner-approved voice artifact SHA and script SHA.
5. The Mac pinned LTX recipe MUST name a matching voice WAV and original
   reference image. Video receipts are A2V_RENDERED_PENDING_QA.
6. Owner reviews A2V framing, motion, lipsync and safety, then explicitly
   approves the exact MP4 digest.
7. When either M6 stage was opened, episode_assemble is blocked until BOTH
   voice and LTX are QA_APPROVED. Legacy use of pre-rendered pinned assets
   remains available for episodes that have not opened M6 stages.
8. Final episode QA and YouTube publishing remain independent human gates.

Stage states: QUEUED, PENDING_QA, QA_APPROVED, BLOCKED, RESET_FOR_RETRY.
Failures require an explicit owner retry reason; no blind auto-rerender.

## Source of truth and dashboard

All Pi stage metadata lives in the existing Studio Brain SQLite file, not
a separate Control Center database. The local read-only dashboard displays
actual stage QA state, NOT_TRACKED if no stage receipt exists. Face cleanup
does not yet have an independent recorded stage (remains NOT_TRACKED).

Only job kind + recipe ID + approved script digest (+ approved voice digest
for LTX) leave Pi in the media request. No source paths or arbitrary commands
are accepted from Pi. Private artwork, source media and voice stay on Mac.

## Local Mac recipe contracts

A private MediaRecipes catalog contains entries of kind voice_synthesize
or ltx_animate, with input stage_recipe pinned to SHA256 and an approved
output_root. The separate private stage recipe has exact keys:

    schema_version, kind, private_root, output_root, script, inputs,
    runner, engine_manifest, voice_rights, limits, ffprobe

For voice_synthesize, inputs contains ONLY a pinned approved script source.
For ltx_animate, inputs contains EXACTLY pinned voice_wav and reference_image.
The script digest is pinned independently in both.

Runner includes:
    python, python_sha256, entrypoint, entrypoint_sha256, args

Entrypoint MUST be an owner-approved wrapper implementing the pinned CLI
contract. No Python -c, shell expansion or command sent from Pi is accepted.
Owner-configured args contain fixed tokens and required placeholders:
    {script}, {engine_manifest}, {output}
and for LTX additionally {voice_wav}, {reference_image}.

One stage attempt writes an immutable local run folder. On success:
    voice_synthesize -> narration.wav
    ltx_animate -> a2v.mp4

Stage worker checks non-symlink, byte cap, ffprobe stream presence/duration,
pins script/input/runtime/wrapper/engine manifest, and sends only metadata to
Pi. Existing Mac durable MediaJournal prevents blind retry after loss of ACK.

A local flock prevents TWO of these M6 workers running on the same configured
output root; it does not coordinate independent ComfyUI/Godot processes.
KIDS_STUDIO_OFFLINE=1 is only advisory, NOT a network sandbox. Python entry
scripts must be trusted. Engine manifests are pinned files; actual checkpoint
weights have not been audited individually, so this is not final model-proof.

## Operator commands — future run only, do NOT deploy now

First initialize the additional schema after existing Studio Brain + Series
Manager have been set up:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-stages

Then an owner-approved script in active series may queue voice:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      queue-stage colors-ar 1 --stage voice_synthesize --recipe bunny_voice_01

After the separately enrolled Mac worker and review, synchronize receipts:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite sync-stages

Owner explicitly approves exact source media hash with a substantive note:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      approve-stage colors-ar 1 --stage voice_synthesize \
      --sha256 EXACT_WAV_SHA --note "Owner listened and verified the exact WAV"

Then queue LTX, synchronize and similarly approve its exact MP4 hash:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      queue-stage colors-ar 1 --stage ltx_animate --recipe bunny_ltx_01

Use the ordinary episode_assemble path after both stages are approved.

## Remaining real production blockers

- Actual installed Chatterbox multilingual MLX runner contract, voice
  preset B, license and commercial voice-reference rights unverified here.
- Actual installed LTX 2.3 MLX A2V runner contract/weights not verified here.
- End-to-end script-to-audio-to-a2v generation on Mac not attempted.
- A universal GPU scheduler for unrelated ComfyUI/Godot jobs is not done.
- Real visual lip sync, educational QA, final rights and backup gates pending.
- No automatic public YouTube publishing. Owner must approve each release.

CI tests are synthetic and prove orchestration/QA-state correctness, not
real engine performance or aesthetic quality.
