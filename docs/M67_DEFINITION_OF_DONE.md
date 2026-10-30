# M67 acceptance: definition of done

M67 is not accepted merely because source files exist or a unit test passes.

## Software gates

1. Python syntax and import checks pass on all M67 modules.
2. Full CI passes on the exact final commit, not a previous commit.
3. Offline handoff lab passes, including tampered readiness rejection.
4. Real FFmpeg decode and Godot smoke pass on representative assets.
5. M65 approved episode provenance and owner channel policy are verified.
6. An interrupted transfer is reconciled without deleting an unknown partial.
7. M65 private uploader remains the only videos.insert path.

## Hardware acceptance

1. Mac creates a playable full episode with approved visual/voice QA.
2. SHA256 of master matches after LAN transfer to Pi.
3. Pi M65 inbox accepts the original plan, readiness and media.
4. Pi performs one PRIVATE YouTube upload using its own OAuth.
5. A real video ID is stored in the journal and verified PRIVATE.
6. Owner opens the uploaded private video and records a decision.
7. Public release remains a separate owner action.

## Status command

```sh
python3 -m kidsstudio.m67_completion_gate \
  --root "$HOME/KidsStudio-Production/colors-ar-001"
```

This command is intentionally conservative. Self-reported acceptance JSON
does not constitute independent hardware verification.

## Explicit exclusions

No remote hardware tests were executed by this code change. No OAuth
credentials are stored in GitHub. No YouTube upload or publication is
performed by this document or the completion gate.
