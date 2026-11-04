# M35 — one-step M34 signed voice-review import into current Pi

**Status:** Draft PR #28, software-only, no owner Mac/Pi/YouTube access. GitHub CI uses synthetic audio and fake reviewers; it does not establish the quality or actual capabilities of child-audio models.

M34 generates an immutable per-scene `voice_technical.json`, `observations.json`, and HMAC-signed `signed_voice_m28.json` in a private local folder. Previously, an operator had to register the M23 WAV report and M28 independent AI evidence separately on the Pi. M35 connects **only those already existing reports** to the **current** completed Pi voice job; it performs no inference itself.

## Private-only contract

- By default `studio-import-audio-review` is dry-run: no writes, no model execution and no scene approval.
- Its `--execute` mode requires a currently completed `voice_synthesize` receipt for the matching active approved script, scene, Pi job ID and WAV SHA. Paused queues, edited episode plans, wrong jobs and mismatched immutable reports fail closed.
- It verifies the signed HMAC and all M34 report-to-report hashes **before** touching the database. M23 technical SHA is registered once; M28 then performs its own validation of the original script, ASR transcript/WER, rights-source catalogue, separate roles, audio model judgments, and the current Pi job.
- Only an `AI_SCENE_READY_PRIVATE_ONLY` M28 result may be automatically made `QA_APPROVED` for that scene. `AI_SCENE_NEEDS_FIX` remains unapproved for the existing bounded M31 repair path. If execution was interrupted after M23, the *same* technical SHA may be safely resumed; a different report is always rejected.
- A byte-identical replay after internal approval is idempotent, never creates a second review or advances a different job.
- No fresh owner listening is asserted, no video or model is rendered, no public/unlisted publishing route exists, and owner review of the actual **uploaded PRIVATE video** remains mandatory.

## Command — future operator-controlled private runtime only

```sh
export KIDS_STUDIO_SCENE_QA_RUNNER_KEY='(load a real 32+-byte secret from an owner-controlled private secret manager)'
studio-import-audio-review \
  --db /PRIVATE/studio.db \
  --series colors-ar --episode 1 --scene 1 \
  --report-dir /PRIVATE/reviews/scene01_attempt001 \
  --rights /PRIVATE/scene01_rights.json
```

After checking the read-only preview, `--execute` may be added when the private Pi contains the **exact** matching M34 completed job. The key is passed in the parent environment and must be identical to M34's signer key; never store it in Git or scripts. This command does not start Whisper, the audio models, LTX or YouTube.

## CI scope and next gate

Tests use a real generated WAV plus actual FFmpeg/FFprobe and **mock** Whisper/audio-model executables. They verify: dry-run changes nothing; signed current Pi report passes M23→M28→private-only internal scene approval; exact replay is a no-op; modified signature, wrong job, wrong rights, wrong signing key and paused coordinator are blocked before state mutation.

**Next:** LTX real multimodal review execution and equivalent SHA-pinned import/repair loop; stage/assembly worker integration; then a complete original two-scene end-to-end acceptance with actual independent and qualified models, stable media and rights provenance. Only after that integrated software gate passes should the Mac/Pi pilot be attempted. The post-upload owner PRIVATE review remains a separate immutable decision.
