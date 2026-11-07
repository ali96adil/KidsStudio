# KidsStudio MVP finish line — stop adding optional integrations

**MVP objective:** One original Arabic educational episode (colors series pilot) rendered locally on the Mac, delivered without corruption to Raspberry Pi 4, uploaded **PRIVATE** to the user's YouTube account after explicit authorization, then inspected by the owner with notes and a separate decision before any public release. Keep the first English episode and further tools as follow-ups; avoid blocking the Arabic pilot on FilmCraft, Craft Anything, OmniRoute or unrelated plugins.

## Verified in the GitHub branch

- Python CI and a synthetic real-Godot smoke pipeline have passed in previous commits. **These are CI/environment tests, not a supervised run of the user's Mac.**
- Local text-agent and independent reviewer mock integration; local ComfyUI / Godot/FFmpeg adapters; queue leases and fail-closed review/QA checks.
- Read-only host readiness, checked local review receipts, basic host report pairing and SHA256 evidence checks. Matching Git revision support lives in batch 43; still requires two fresh real-host reports.
- Private upload **preflight/dry run only**. The repository **does not yet establish a working live YouTube OAuth upload from the Pi**, so do not claim end-to-end PRIVATE upload works.

## Remaining blocking acceptance gates (no artificial milestones)

### A. Local Mac production test — NOT_RUN

On the actual Mac, check out the pinned feature branch commit, create an owner-private artifact root, and run:

```bash
python -m unittest discover -s tests
python -m kidsstudio.host_qualification --role mac-render \
  --artifact-root "$HOME/kidsstudio-private/ready" --min-free-gib 2
```

Then manually qualify the already-supported render pipeline using original rights-cleared character images and a short Arabic colors script. Verify a playable H.264 MP4, **actual Arabic narration/audio** and basic sound/picture synchronization, no copyrighted music or commercial appeals, and valid SHA256. Real media creation is **not** started by the offline host command. Save report and media privately, no uploads and no unattended agent execution at this stage.

### B. Raspberry Pi transfer and PRIVATE upload — NOT_RUN

On the physical Pi 4, after checking out the same revision and preparing a mode-0700 inbox:

```bash
python -m kidsstudio.host_qualification --role pi-private-handoff \
  --artifact-root "$HOME/kidsstudio-private/inbox" --min-free-gib 2
```

Collect both reports privately and run the read-only comparator as documented in `G4_MAC_PI_QUALIFICATION.md`. Do a separately authorized **real transfer of one test MP4**, compare sender and receiver SHA256, and verify Pi disk space, restart recovery, network/permissions and retry behavior. **No working automated PRIVATE YouTube upload has been demonstrated yet.** Before unattended upload is enabled, implement and independently test OAuth token storage, YouTube visibility forced to PRIVATE, made-for-kids declaration, idempotent retry/resume, owner authorization and Pi reboot handling, using official test credentials only with the owner's consent. A manual authenticated PRIVATE upload is a temporary pilot option, not proof the Pi uploader is complete.

### C. End-to-end owner acceptance and freeze — NOT_RUN

The user watches the full private YouTube draft, checks Arabic pedagogical accuracy, age suitability, visual/audio quality and rights, and records APPROVE PRIVATE / REVISION REQUIRED with notes attached to that exact video SHA. No acceptance event becomes permission to publish publicly. Record the final tested Git commit, actual Mac/Pi hardware/software versions, private upload evidence and rollback steps. Only then label this **MVP PILOT VERIFIED**. Public release is a separate deliberate owner action and must never happen automatically.

## Faster execution policy

- **Freeze scope now:** no more optional engines, reverse engineering integrations, theme work or new dashboard features until A–C are tested.
- One complete episode through the pipeline is the priority, not dozens of mechanical feature batches.
- Work on code can be completed in GitHub, but **physical Mac/Pi tests, local model availability, OAuth authorization and watching the resulting video cannot be truthfully marked done by CI**.
- When a device test fails, fix that concrete blocker and rerun; do not start unrelated features. All private content and credentials stay out of GitHub.
- Preserve `main` and PR #33 unmerged until physical evidence and explicit acceptance. Maintain the previous known-good production setup.

**Current decision:** SOURCE-CODE PILOT / DEVICE QUALIFICATION PENDING. This is not a full production launch or an authorized upload.
