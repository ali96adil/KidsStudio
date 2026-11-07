# KidsStudio MVP finish line — stop adding optional integrations

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
