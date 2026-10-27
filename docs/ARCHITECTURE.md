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

## Standalone rig animation project exporter

The `export-godot` command creates a local Godot 4 project from a validated
`rig.json` with **separate transparent PNG layers** and a validated
`scene_spec.json` action timeline. Each part has its own `Node2D`
joint positioned at its declared pivot and `Sprite2D` image anchored to
the common canvas coordinates. Ears, eyes and mouth are parented to head
without flattening the artwork. Playback uses frame `delta` so Godot
`--write-movie --fixed-fps` exports are deterministic.

Actions initially supported: neutral, wave_right, wave_left, head_tilt,
jump, walk. These are proof-of-rig motions, NOT final acting animation.
Real deformation, mesh blending, mouth shapes, believable walk cycles
and facial performance require additional layers/animation.

The default export is `PREVIEW_ONLY_UNAPPROVED`. With
`--require-reviewed` an independent local AI PASS, fresh motion evidence,
and hashes of the exact current part files are required before **internal**
asset export. The owner still approves publication.

## Pi HTTPS coordinator (prototype)

The Pi keeps the authoritative SQLite control-plane and a private
`0600` editorial artifact vault. The Mac initiates HTTPS requests, using
a standard CA-verified certificate (or operator-installed trusted self-signed
certificate) and a per-worker environment-backed bearer token. The Pi
authenticates the worker **before reading the JSON body**, enforces a
capability allowlist and bounded message sizes, and uses the existing
SQLite generation-fenced leases. Exactly one linked editorial review
inherits its original provider ID and SHA-256 of the immutable Pi text.

This is intentionally restricted to script_draft/editorial_review — no
remote shell, model download, arbitrary filesystem action, YouTube
publication, image generation or video rendering. A Mac provider may be
a free or local OpenAI-compatible chat endpoint, but the remote worker
never opts into a paid route. TLS and bearer token only; production
hardening (mTLS/token rotation, firewalls, rate limiting, device enrollment,
clock health, execution side-effect dedupe) remains before unattended
LAN/Internet deployment.
