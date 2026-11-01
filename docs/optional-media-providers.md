# Optional media providers — Kids Studio

Status: integration specification (not enabled in production).

## Decision
- Keep Godot + ComfyUI as the primary local visual pipeline.
- Add Cloudflare Workers AI as an **optional** image-generation provider, not Cloudflare's hosting product. Requires account credentials, model availability checks, quota/cost controls, and commercial-use/license verification.
- Add Remotion as an **optional** template-based compositor for repeatable educational cards, subtitles, transitions and exports. Keep Godot for character animation.
- Keep Whisper local for speech-to-text QA, checking script vs generated narration.
- ElevenLabs is optional only when local TTS fails quality tests; never assume free commercial usage.
- Colab is experimental/manual, not a reliable unattended production backend.
- Claude Code is a development assistant, not an unattended production requirement.

## Image provider contract
Inputs: scene_id, prompt, negative_prompt (if supported), aspect_ratio, seed (if supported), style_reference, language, provider_preference.
Outputs: asset file, provider/model/version, generated_at, prompt hash, license/cost metadata, QA status.
Fallback: Cloudflare failure, quota or cost threshold -> local ComfyUI. No silent changes to approved character designs.

## Pipeline
script -> character/style consistency -> local ComfyUI or optional Cloudflare -> visual QA -> Godot/optional Remotion -> voice -> local Whisper transcript QA -> private YouTube upload via Pi -> human review -> publication.

## Safety and operations
- Default off for all paid/cloud providers; secrets in environment variables, never Git.
- Enforce per-job/per-day budgets, retries with backoff, and provenance logs.
- Never upload children's personal data or unreleased sensitive assets without explicit approval.
- All generated assets require visual consistency and copyright/policy review.
- Mac renders locally and transfers to Pi; Pi owns upload and retry.
- No changes to current production workflow until integration tests pass.

## Acceptance tests
1. Cloud disabled: existing pipeline unchanged.
2. Cloud enabled: generate a test image, record model/quota/cost and license.
3. Quota/error: fallback to local generation without losing scene state.
4. Remotion: generate a 10-second color-learning card with deterministic export.
5. Whisper: compare spoken transcript to approved script and flag mismatches.
6. Pi: interrupted upload resumes/retries without re-rendering.
