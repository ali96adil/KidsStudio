# KidsStudio Architecture (target, not fully implemented)

## Control plane
Python service with typed agent tools, persistent job state, decision/event log, quotas, independent reviews and explicit publishing approvals. Pi 4 is the intended always-on controller; *do not* run graphics diffusion or rendering there. The Mac is a registered, intermittent worker and must be allowed to go offline safely.

## Art / animation plane
ComfyUI on Mac (local API) -> individual PNG part generation -> technical QA -> joint and motion render tests in Godot -> independent visual QA -> accepted versioned character assets. A flat image is a useful identity reference, **not** a valid rig source by itself.

### Rig-first contract v1
Character blueprint (identity, canvas, parts, pivots, instructions) is compiled into part-generation jobs and a rig manifest template. Each part must be a separate, full-canvas **RGBA PNG** aligned to the same shared coordinates. Separate files: body, head, left/right arms and legs; ears, eyes, mouth when needed. Hidden attachment regions must be drawn; pivot coordinates and z-order must be explicit.

The current CLI checks these mechanically. It **does not** test whether the model followed the part prompt, visual alignment, overlap smoothness, frame flicker or facial continuity. We must render sample actions and run an independently tasked visual reviewer before accepting a rig.

### Future agent stages
1. Design brief with identity locked.
2. Rig Asset Generator receives blueprint and reference art; uses ComfyUI API and stores exact workflow/seed/model metadata.
3. Rig QA runs automated checks and samples 0/25/50/75/100% of each action, generates animated tests.
4. Independent vision reviewer returns PASS/REVISE/FAIL with evidence; no automatic visual PASS if the AI provider is absent.
5. Stage approved rigs in asset registry, never overwrite approved masters.
6. Godot uses scene_spec.json actions to generate repeatable renders.
7. Language-specific audio/lipsync and educational QA.
8. YouTube PRIVATE staging; owner final public release approval.

## Media and storage
Source AI images, WAV, model weights, voice references, internal secrets and MP4 masters remain **outside Git**, in local production directories. Synology archive uses hash checks; maintain another physically independent backup. Active transactional DB lives on Pi-attached storage, not an NAS share.

## Security
- Private owner Telegram bot allowlist, narrow credentials per service.
- Never store AI API keys, YouTube refresh tokens, Telegram tokens or children's data in repository.
- The repository was first observed as **public**. Restrict visibility before adding proprietary designs or deployment secrets.
- CI runs only deterministic tests on sample-generated temporary data; no external paid models or service credentials.

## Runtime acknowledgements
Local evidence before this repo: Godot JSON movie proof; FLUX.2 Klein illustration and image edit proof. No AI manager daemon, ComfyUI adapter, autonomous evaluator or night render scheduling has been deployed yet.
