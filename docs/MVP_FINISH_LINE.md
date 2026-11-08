# KidsStudio MVP finish line — stop adding optional integrations

> **Workflow correction (Batch 60):** the user's intended human approval is **AFTER** a PRIVATE YouTube draft exists, not a prerequisite to Mac→Pi staging. Technical QA and SHA verification qualify staging; public publication always requires a separate explicit human decision. The historical Batch 58 reviewed-only path is optional, not the current default.

**MVP objective:** One original Arabic educational episode (colors series pilot) rendered locally on the Mac, delivered without corruption to Raspberry Pi 4, uploaded **PRIVATE** to the user's YouTube account after explicit authorization, then inspected by the owner with notes and a separate decision before any public release. Keep the first English episode and further tools as follow-ups; avoid blocking the Arabic pilot on FilmCraft, Craft Anything, OmniRoute or unrelated plugins.

## Verified in the GitHub branch

- Python CI and a synthetic real-Godot smoke pipeline have passed in previous commits. **These are CI/environment tests, not a supervised run of the user's Mac.**
- Local text-agent and independent reviewer mock integration; local ComfyUI / Godot/FFmpeg adapters; queue leases and fail-closed review/QA checks.
- Read-only host readiness, checked local review receipts, basic host report pairing and SHA256 evidence checks. Matching Git revision support lives in batch 43; still requires two fresh real-host reports.
- Private upload **preflight/dry run only**. A new explicit opt-in resumable uploader exists in the pilot branch, but **no Google OAuth login or real Pi upload has been tested**. Do not claim end-to-end PRIVATE upload works until an owner-supervised pilot confirms it.

## Remaining blocking acceptance gates (no artificial milestones)

### A. Local Mac production test — NOT_RUN

On the actual Mac, check out the pinned feature branch commit, create an owner-private artifact root, and run:

```bash
python -m unittest discover -s tests
python -m kidsstudio.host_qualification --role mac-render \
  --artifact-root "$HOME/kidsstudio-private/ready" --min-free-gib 2
```

A new one-command opt-in Mac pilot now links the actual Godot render to an existing rights-cleared 16-bit PCM WAV using local FFmpeg; see `MAC_ARABIC_EPISODE_PILOT.md` and `examples/colors_ar_01_pilot_cues.json`. This remains an **untested physical-Mac workflow** and does not itself create final color props or an Arabic recording. Then manually qualify the already-supported render pipeline using original rights-cleared character images and a short Arabic colors script. Verify a playable H.264 MP4, **actual Arabic narration/audio** and basic sound/picture synchronization, no copyrighted music or commercial appeals, and valid SHA256. Real media creation is **not** started by the offline host command. Save report and media privately, no uploads and no unattended agent execution at this stage.

### B. Raspberry Pi transfer and PRIVATE upload — NOT_RUN

On the physical Pi 4, after checking out the same revision and preparing a mode-0700 inbox:

```bash
python -m kidsstudio.host_qualification --role pi-private-handoff \
  --artifact-root "$HOME/kidsstudio-private/inbox" --min-free-gib 2
```

Collect both reports privately and run the read-only comparator as documented in `G4_MAC_PI_QUALIFICATION.md`. A dedicated, opt-in SSH transfer implementation now exists (`mac_to_pi_transfer.py` + `pi_transfer_receive.py`) and has mock tests, but a **real Mac→Pi LAN transfer** remains NOT_RUN. Follow `MAC_PI_TRANSFER_PILOT.md` to run it only after verified host-key setup, then independently compare sender/receiver SHA256 and verify Pi disk space, restart recovery, network/permissions and retry behavior. **An explicit foreground PRIVATE resumable upload implementation exists, but its Google API network path is mock-tested only.** See `PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md`. Initial OAuth enrollment, live Pi upload and YouTube Studio confirmation are still untested; no unattended upload service is allowed. The new local command enforces PRIVATE, made-for-kids confirmation, durable journal and status check, but still needs a security review and supervised test credentials before live use. A manual authenticated PRIVATE upload is a temporary pilot option, not proof the Pi uploader is complete.

### C. End-to-end owner acceptance and freeze — NOT_RUN

The user watches the full private YouTube draft, checks Arabic pedagogical accuracy, age suitability, visual/audio quality and rights, and records APPROVE PRIVATE / REVISION REQUIRED with notes attached to that exact video SHA. No acceptance event becomes permission to publish publicly. Record the final tested Git commit, actual Mac/Pi hardware/software versions, private upload evidence and rollback steps. Only then label this **MVP PILOT VERIFIED**. Public release is a separate deliberate owner action and must never happen automatically.

## Faster execution policy

- **Freeze scope now:** no more optional engines, reverse engineering integrations, theme work or new dashboard features until A–C are tested.
- One complete episode through the pipeline is the priority, not dozens of mechanical feature batches.
- Work on code can be completed in GitHub, but **physical Mac/Pi tests, local model availability, OAuth authorization and watching the resulting video cannot be truthfully marked done by CI**.
- When a device test fails, fix that concrete blocker and rerun; do not start unrelated features. All private content and credentials stay out of GitHub.
- Preserve `main` and PR #33 unmerged until physical evidence and explicit acceptance. Maintain the previous known-good production setup.

**Current decision:** SOURCE-CODE PILOT / DEVICE QUALIFICATION PENDING. This is not a full production launch or an authorized upload.

## Batch 44 — foreground private uploader added, NOT live-qualified

`kidsstudio/pi_youtube_private_upload.py` adds a deliberate operator-only YouTube resumable upload client and state journal, with a Google OAuth refresh-token client, SHA checks, private-only metadata, resumable session offset probes, and remote PRIVATE status verification. **No OAuth client or real video was uploaded**; CI uses fake Google responses. Owner authorization remains a CLI assertion, not an authenticated identity. The program does not initiate OAuth login or enable background queue consumption. See [`PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md`](PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md).

## Batch 45 — Mac-to-Pi transfer source added (not device tested)

`kidsstudio/mac_to_pi_transfer.py` provides a preview-only default and an explicit `--execute-transfer` foreground SSH stream; `kidsstudio/pi_transfer_receive.py` is bound to the Pi's owner-private `~/kidsstudio-private/inbox`, hashes the stream, and atomically creates a non-overwritable MP4. Duplicate identical media is verified rather than replaced, and a broken/mismatched transfer cannot be promoted. The sender accepts only a validated hostname/SSH user/port and refuses unknown SSH host keys. All integration tests use a fake SSH runner; **no connection to the user's devices has been made**.

Supervised transfer procedure: [MAC_PI_TRANSFER_PILOT.md](MAC_PI_TRANSFER_PILOT.md). After a verified Pi receipt, the Pi can independently run the explicit PRIVATE upload pilot; this is not yet an autonomous production service. A complete Mac render with Arabic narration, actual Pi SSH transfer, real OAuth test upload, and owner review are still the three remaining physical acceptance steps.

## Batch 46 — Mac render plus narration integrated (not yet used on Mac)

`kidsstudio/mac_episode_audio.py` validates a SHA-pinned silent 720p Godot MP4 and an original uncompressed WAV, checks pacing, then **only with explicit execute** muxes stereo 48 kHz AAC audio into a new non-overwritten PRIVATE MP4. `kidsstudio/mac_episode_pilot.py` chains verified Godot rendering and narration muxing into one supervised command with a read-only preview default. The colors draft includes six timed speech/visual cues; **the actual color illustrations and approved Arabic voice must still be provided or created**. Inputs and output are checked against SHA256 and owner-private paths. See [MAC_ARABIC_EPISODE_PILOT.md](MAC_ARABIC_EPISODE_PILOT.md) for Mac steps. Neither code module invokes Pi, OAuth or YouTube; physical device tests remain NOT_RUN.

## Batch 47 — First self-contained colors visual/audio smoke (not yet on Mac)

`kidsstudio.first_colors_episode` now draws six **original** static 1280x720 illustrated color scenes locally with Pillow, encodes a 24-second H.264 preview with FFmpeg, and (only with explicit `--execute`) adds either an **already installed** Arabic macOS `say` voice or a privately supplied SHA-pinned 24-second original WAV. It validates durations, blocks truncation of long spoken beats, and delegates final AAC stereo mux/sha/no-overwrite gates to `mac_episode_audio`. It needs **no ComfyUI model, third-party graphics, new TTS API or cloud connection**.

Runbook: [FIRST_PLAYABLE_COLORS_PILOT.md](FIRST_PLAYABLE_COLORS_PILOT.md). The original 12-second storyboard remains an editorial draft; this static illustration pilot gives six beats four seconds apiece. Real macOS voice availability, listening quality, full visual review and physical device transfer/upload remain **NOT_RUN**. CI tests and a separate synthetic FFmpeg syntax smoke do not imply actual Mac qualification. Do not label this production animated content or approve it for public YouTube release.

## Batch 50 — playback sample gate, not yet physical Mac approval

The one-command Mac colors launcher now runs an actual SHA-pinned local MP4 container+codec preflight after rendering and before playback: faststart `moov` precedes `mdat`, conservative H.264 Baseline/AAC-LC metadata, three decoded video samples and two audio samples. The Linux real-colors CI encodes the full synthetic-silent 24-second episode and runs the same check. This targets the observed player-compatibility problem but **does not prove device-specific playback**, full-file decoding, Arabic voice quality, educational correctness, Pi SSH delivery or any upload. If a check fails, it stops instead of opening the file; the privately stored output can be diagnosed. The blocking acceptance gates A–C above remain NOT_RUN on the owner's devices. See [FIRST_PLAYABLE_COLORS_PILOT.md](FIRST_PLAYABLE_COLORS_PILOT.md).

## Batch 51 — record actual Mac evidence and private owner decision, without bypassing gates

The Mac one-command colors launcher now stores a non-overwriting 0600 JSON evidence report outside Git after independently checking real MP4 compatibility, a Mac host readiness run, and matching the checkout's clean source commit. The filename tracks the versioned MP4, so there is no "latest" ambiguity. A separate **python -m kidsstudio.mac_pilot_evidence review** command can append SHA-matched revision notes or an operator-asserted ACCEPTED_PRIVATE record only after confirming both the full video and Arabic narration were reviewed. These records **do not authenticate owner identity, authorize YouTube uploads or mark videos public**. See [FIRST_PLAYABLE_COLORS_PILOT.md](FIRST_PLAYABLE_COLORS_PILOT.md).

Nothing in CI can execute a command on the user's actual Mac or Pi or hear the real synthesized Arabic voice. The three acceptance gates A–C remain pending until a supervised operator actually produces and inspects the first file, confirms the SSH handoff and separately authorizes a PRIVATE-only YouTube pilot.

## Batch 51 — local Mac proof and owner review are two separate gates

`scripts/run_mac_colors_pilot.sh` now ends its foreground local render by saving a SHA-pinned technical report outside Git after host/checkout and MP4 sample verification. The owner can separately record `REVISION_REQUIRED` notes or a private-only review claim with explicit whole-video and Arabic voice listening flags, tied to the **same MP4 SHA**. These records have owner-only permissions and are not overwritten by the tool, but they are not authenticated attestation, cannot prove the listener's identity and cannot grant network upload or publication authorization.

Practical Mac steps: [MAC_PILOT_EVIDENCE_AND_REVIEW.md](MAC_PILOT_EVIDENCE_AND_REVIEW.md). The project remains **SOURCE-CODE PILOT / DEVICE QUALIFICATION PENDING**: the actual Mac Arabic voice, physical SSH handoff, Pi PRIVATE YouTube upload and review of a real YouTube draft have not been executed in this session. No feature branch commit is an authorization to publish.

## Batch 52 — additional macOS-specific CI assurance, not device qualification

In addition to the Linux original 24-second synthetic-silent render smoke, `.github/workflows/macos-colors-smoke.yml` exercises the same real H.264/AAC pipeline on an **ephemeral GitHub macOS 15 runner**, plus an optional local-system Arabic `say` speech-synthesis capability check. An Arabic voice not present on the runner is explicitly reported as `NOT_TESTED`; a CI success never substitutes for listening to the user's actual Mac render. No generated media/artifact is uploaded, no live Pi transfer is performed and no private/public YouTube upload is authorized. Scope is still frozen on the one Arabic colors pilot; operator attendance at the Mac/Pi remains the blocking physical gate.

## Batch 53 — stop failed Mac renders early

The Mac pilot launcher now performs a no-render prerequisite check for an already-installed Arabic macOS voice and pinned clean checkout **before** encoding. Native `say` WAV output must contain non-negligible signal energy in each of the six original four-second scenes; otherwise the local render is blocked before final mux. This reduces wasted rendering and silent-first-draft failures but **does not** validate Arabic pronunciation, substitute for human listening, or perform the actual supervised operator Mac test. No automatic voice/model downloads, cloud inference, Pi SSH transfer or YouTube upload are enabled.

## Batch 54 — avoid expensive failed Mac video renders

The native macOS colors pilot builds and validates its six Arabic speech beats **before** encoding the picture track, so a broken or silent native voice never spends time creating the full silent MP4. An optional `KIDSSTUDIO_MAC_VOICE` chooses an already-installed Arabic voice consistently during preflight and rendering; the launcher remains Bash 3.2-compatible and produces retry-unique private file names. Passing automated checks still does not constitute reviewed Arabic speech or a run on the owner's physical Mac.

## Batch 55 — CI exercises native voice-mode piping, not spoken Arabic

Added a full hosted-macOS `voice_mode=macos` CI integration using **six synthetic FFmpeg AIFF tones**, never fake spoken words or user media. It verifies the real production AIFF-to-PCM timing/energy, real illustrated 24-second render, AAC mux, H.264/AAC preflight and separately decodes all six beats from the **finished MP4**. It catches sound loss during final mux while making no claim that an actual installed Arabic `say` voice speaks correctly. Do not treat synthetic CI passing as a substitute for the supervised owner Mac render, voice listening and private video review.

## Batch 56 — simpler supervised review without relaxing owner approval

Added `kidsstudio.mac_pilot_review_shortcut`, whose read-only `list` subcommand displays only private, original, validated SHA-matched Mac colors evidence. Its `record` subcommand takes **one exact evidence filename** and an explicit review outcome, derives video filename and SHA-256 from that validated proof and reuses the immutable-by-tool private review-note writer. Accepting a draft still requires separate assertions that the owner watched the complete video and listened to the Arabic voice. The helper performs no transfer, OAuth, upload, publication or implicit newest-video acceptance; it does not count as real owner device validation.

## Batch 57 — guided real-operator review gate

Added `python3 -m kidsstudio.mac_pilot_review_shortcut guided` as a foreground, **TTY-only** Mac pilot review assistant. It requires exact numbered video selection, a separate explicit revise/private-accept outcome, and final `SAVE`; private acceptance additionally requires separate `YES` attestations for watching the entire video and listening to Arabic voice. It rechecks media SHA and sidecar immediately before writing an append-only-by-tool private review note. Invalid choices, no terminal, missing evidence, or EOF never create an approval. This removes error-prone manual SHA/filename copying without replacing actual owner review or authorizing Pi/YouTube/publication.

## Batch 58 — explicit owner-reviewed proof required before the first Mac→Pi pilot

`kidsstudio.reviewed_mac_pi_handoff` wraps the existing opt-in SSH sender. For the first colors pilot, **render success is insufficient**: require the SHA-pinned private Mac technical sidecar plus an exact matching operator-asserted `ACCEPTED_PRIVATE` note, both full-video + Arabic voice review confirmations, and **zero** `REVISION_REQUIRED` notes for that same video version. Invalid or tampered notes and source bytes fail closed. Default invocation is a read-only **NO-SSH preview**; actual sending requires a separate owner-supervised `--execute-transfer` on the real Mac and a preconfigured, host-key-verified Pi. Nothing calls OAuth/YouTube or grants public publication permission. The actual Mac/Pi/YouTube steps are still NOT_RUN by CI. Follow [MAC_PI_TRANSFER_PILOT.md](MAC_PI_TRANSFER_PILOT.md).

## Batch 59 — one synthetic full private chain in CI, no live Google/Pi

The existing `scripts/ci_colors_episode_smoke.py` now reuses its **real original FFmpeg-encoded 24-second MP4** to test the entire local first-episode integration, not only isolated components. The ephemeral CI fixture (1) collects the actual MP4's SHA-verified technical sidecar while **simulating** the Mac host identity/clean Git checkout; (2) proves that unreviewed video is refused before any transfer; (3) writes a **SIMULATED** local `ACCEPTED_PRIVATE` note with the existing review writer—**no human watched or heard the sample**; (4) previews a reviewed SSH transfer without connecting; (5) exercises the *actual Pi atomic stdin receiver* via a fake in-process SSH adapter and checks its stored video SHA; and (6) runs the **existing resumable private uploader** with only a fake Google service and fake token, checking private/made-for-kids metadata, complete byte count, remote-private status model, and final private journal. This does not create or upload real Google videos or connect to a Pi. Synthetic CI notes and clips are temporary and are never pushed as Actions artifacts.

A green `OFFLINE_REAL_MP4_TO_FAKE_PI_TO_FAKE_YOUTUBE_PRIVATE_PASSED` means **component wiring and SHA/receipt consistency passed under simulated operator/SSH/YouTube conditions only**. Actual supervised Mac Arabic speech production, local viewing/listening, Pi real SSH transfer and genuine authenticated PRIVATE upload remain NOT_RUN. This full-chain smoke specifically guards against 'all parts separately passed, but handoff wiring failed' without misleadingly claiming end-to-end deployment.

## Batch 60 — corrected owner review order; no compulsory pre-upload human approval

Earlier Batch 58 imposed a local owner review before transfer; that was inconsistent with the intended workflow. **Current default:** actual Mac renders the original colors MP4 and performs automated technical/energy/compatibility checks, writes immutable-by-tool private SHA-pinned technical evidence, then `kidsstudio.technical_mac_pi_handoff` permits **explicit PRIVATE Pi staging WITHOUT requiring prior human review**, provided exact original evidence, private paths, source commit, codec/audio sample checks and current SHA/bytes all match. This is not arbitrary/unqualified video transfer. The Pi independently verifies the media and separately, with initial owner OAuth consent and explicit PRIVATE-only authorization, submits the draft. **Only after the resulting YouTube video is PRIVATE does the owner review/listen, record notes or revisions and later separately decide whether to publish.** There is no CLI or automation that makes the file public.

The older review-before-transfer path remains optional for cautious local previews. CI now follows the correct order: real 24s encoded MP4 → validated technical sidecar → no owner approval yet → in-process mock Pi SSH receiver → fake Google PRIVATE resumable upload → only then a simulated revision note (**not a real human**). Both physical Mac Arabic TTS qualification and live Pi/Google upload remain NOT_RUN; do not confuse mock green tests with owner approval or a real device pilot.

## Batch 61 — fix false READY source qualification and offer one-command offline device diagnosis

The existing Mac/Pi host qualification **used to report** `source_commit` and `source_checkout_clean` without gating the `SUPERVISED_TESTS_READY` status on either field. That was unsafe for the actual cross-device pilot: different or dirty source could be marked ready before staging. Both a valid pinned 40-hex commit and a clean local checkout now explicitly gate readiness, with Boolean check fields exposed and regression tests covering Mac and Pi.

Before the physical pilot, run `python3 -m kidsstudio.first_pilot_device_doctor --role mac` on the real Mac, and `python3 -m kidsstudio.first_pilot_device_doctor --role pi` on the real Pi. This read-only, no-network, no-write command combines existing host checks with Mac voice/FFmpeg/FFprobe/SSH prerequisites and gives fixed-safe actionable blocker codes; it neither installs missing prerequisites nor authenticates cross-host revision equality. See [FIRST_REAL_DEVICE_PILOT.md](FIRST_REAL_DEVICE_PILOT.md). **Device and OAuth tests remain NOT_RUN.**

## Batch 62 — remove Apple Arabic voice as a blocker for a prepared original WAV

An existing lower-level original-WAV render path was unusable through the normal one-command Mac pilot launcher because `mac_colors_preflight` and the launcher always required a local Arabic `say` voice. The operator can now explicitly supply a **SHA-pinned 24-second original mono PCM WAV** with a non-silent signal in each four-second beat through three `KIDSSTUDIO_NARRATION_*` variables. The Mac doctor/preflight and actual Bash launcher agree on the selected mode; incomplete or conflicting source options and bad/modified/private-permission WAVs block before encoding. No fallback quietly substitutes another voice, and no speech is produced by the WAV route. Hosted macOS CI now executes the actual launch shell with a **synthetic test-only WAV** as a complete technical test, never claiming actual spoken Arabic. Human content review remains after the authorized YouTube PRIVATE upload. See [FIRST_REAL_DEVICE_PILOT.md](FIRST_REAL_DEVICE_PILOT.md).
