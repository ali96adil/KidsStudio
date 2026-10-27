# KidsStudio

AI-powered bilingual educational animation studio for children.

**Status:** Early R&D. The Godot/ComfyUI experiments described below were run on a Mac outside this repository; production automation is not yet deployed.

## Production principle

**Rig first, animate second.** Generate original, independently layered character assets with explicit pivots and hidden-body overlap. Assemble and animate them in Godot using structured scene instructions. Run technical checks, visual reviews and independent educational/safety checks before any public release.

## Architecture

- **Pi 4:** future studio coordinator, durable queue, agents and audit log.
- **Mac M3 Max:** local AI art, character rigging, audio, render and quality-control worker.
- **Synology:** archival storage; maintain a separate independent backup.
- **GitHub:** code, safe schemas, reference documents and CI, **not** original artwork, model weights, credentials or rendered media.
- **YouTube:** one multilingual-first channel where account features allow; Arabic and English editorial review are independent.
- **Telegram:** private owner command bot, parent resource channel, eventual moderated forum.

## Implemented in this repository

1. A typed, versioned rig specification with a **local asset generation plan**.
2. A deterministic **technical rig QA** tool checking input safety, transparent PNGs, required parts and **strict anatomical envelopes** for production blueprints. It rejects whole-body impostor layers, duplicate images, empty/tiny shapes and misplaced limbs.
3. Tests and a GitHub Actions workflow.
4. A checksum-approved **local-only ComfyUI API bridge** for explicit opt-in job submission.
5. **Character Factory v0.1:** sequential ComfyUI jobs for each isolated part, validated alpha, versioned rig and provenance, six animated motion previews/contact sheet, and a fail-closed technical review report. An optional independent local multimodal reviewer can return PASS / REVISE / FAIL with an auditable report; it requires a separately installed vision model and has **not** been tested against actual art yet.
6. **Godot 4 rig project exporter and local MP4 renderer:** real Sprite2D layers and pivot Node2D joints, hierarchical head/ears/face, deterministic JSON action beats, project source integrity, and one-command fixed-fps Godot/FFmpeg video render. A native Godot 4.7.2 CI smoke test uses synthetic assets to validate actual GDScript playback/encoding. Preview exports and videos are explicitly unapproved.

This initial QA does **not** judge artistic quality, seams, motion, IP originality or child safety. Technical approval is **not** final asset approval.

## Quickstart (Python 3.11+)

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    python -m unittest discover -s tests -v

Create generation instructions from the example character blueprint:

    kidsstudio plan-rig examples/bunny_blueprint.json --output /tmp/bunny_plan.json

After creating the independently layered PNGs and rig.json manifest, run:

    kidsstudio qa-rig path/to/rig.json --report /tmp/rig_report.json

The QA tool returns exit code 0 when **technical** checks pass and a nonzero exit code when they fail. Artistic and visual review remain mandatory.

## Status from local experiments (not yet imported)

- Godot 4.7.2: successful 12-second, 1280x720, 30-fps H.264 prototype from JSON action beats.
- ComfyUI / FLUX.2 Klein 4B: character illustration and image editing proven on Apple Silicon.
- Cutting arms out of a flat PNG produced visible seams; **rejected as the long-term production method**.
- Next: generate head/body/arms/legs/ears/face as separate rig-first source layers and automate an animated contact-sheet QA.

See docs/ARCHITECTURE.md, docs/STUDIO_CONSTITUTION.md, docs/COMFYUI_ADAPTER.md, docs/CHARACTER_FACTORY.md, docs/GODOT_RIG_PLAYER.md, docs/STUDIO_QUEUE.md and docs/ROADMAP.md.

## Privacy / licensing

No license has been granted for redistribution of studio-specific work. Respect the individual licenses of software, AI checkpoints, voices, music and artwork. Do not include photos or identifying information of children in public development data.

**Identity preservation:** an approved ComfyUI LoadImage reference node may be required for each part; the factory hashes and uploads the canonical original only to local ComfyUI and uses it again for independent visual QA. ComfyUI must have an appropriately wired, manually approved reference-conditioned workflow.

## Character Factory v0.2: bounded repair cycle

Run a single **local-only**, reference-conditioned production cycle with an
independent installed vision model, limited to two attempts by default:

    kidsstudio produce-character examples/bunny_blueprint.json \
      --workflow /local/approved/workflow_api.json \
      --profile /local/approved/comfy_profile.json \
      --reference /local/characters/bunny/bunny_neutral_v01.png \
      --review-model YOUR_INSTALLED_LOCAL_VISION_MODEL \
      --out /local/characters/bunny/production_cycle_001 --execute

If visual QA requests revision and attributes a defect to an exact part,
the cycle makes a new immutable attempt, reusing validated parts and
regenerating only the rejected ones. An ambiguous defect, explicit FAIL,
missing reviewer, broken alpha, invalid provenance or exhausted retry
limit stops rather than approving/submitting unreviewed art.
Full details: [bounded production cycle](docs/PRODUCTION_CYCLE.md).

## Studio Brain v0.1 — durable queue

A dedicated **local SQLite** control plane can now persist approved job types,
allocate work to a Mac/Pi worker via time-limited leases and fencing tokens,
retain an audit log, pause new dispatch or revoke a claim. It has no network
server and cannot execute a job or call a paid model by itself. Each
worker-side activity will require a separate explicitly approved adapter.

    studioctl --db /private/local/studio.sqlite init
    studioctl --db /private/local/studio.sqlite status

See [Studio Queue operations](docs/STUDIO_QUEUE.md). All state and full logs
remain outside public Git and outside the NAS transactional data share.
