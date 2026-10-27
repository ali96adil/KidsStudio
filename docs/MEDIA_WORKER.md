# Mac Media Worker v0.1 — bounded side-effect execution

**Status:** Software integration prototype, not deployed on the owner's Pi
or Mac. GitHub tests use fake renderer/Comfy providers; a separate CI native
Godot smoke already verifies Godot's renderer with synthetic assets.

## Runtime boundary

The Pi keeps the authoritative Studio Brain SQLite queue; a Mac requests
a media job using a *dedicated bearer identity* with an explicit media-only
capability set. The Pi sends only a `recipe_id`. The Mac never accepts file
paths, shell snippets, model IDs or unapproved executable commands from Pi
job payloads.

Two allowed job kinds:

- `character_generate`: invokes previously created bounded
  `run_character_cycle` with locally pinned blueprint, ComfyUI API workflow,
  approved profile, canonical reference image, review model, retry cap.
  It may take time and consume local GPU/resources. Only an installed,
  configured local ComfyUI + vision reviewer are allowed.
- `godot_render`: invokes the validated Godot→FFmpeg renderer on a locally
  pinned `export_report.json`; the exporter additionally checks hashes of
  GDScript and all project assets before launching Godot.

No standalone raw shell, filesystem uploads/downloads, social posting,
e-commerce, paid model endpoints or YouTube publication is authorized.

## Private Mac recipe catalogue (example — replace with local real paths/hashes)

```json
{
  "schema_version": 1,
  "recipes": {
    "bunny_scene_demo": {
      "kind": "godot_render",
      "output_root": "/Users/OWNER/KidsStudioPrivate/renders",
      "inputs": {
        "project_report": "/Users/OWNER/KidsStudioPrivate/godot_v01/export_report.json"
      },
      "sha256": {
        "project_report": "REPLACE_WITH_REAL_LOWERCASE_SHA256"
      }
    }
  }
}
```

Put recipe config and all original images outside Git. Hash each file with
`shasum -a 256 /path/to/file` and approve it locally after inspecting its
contents. Source-image hashes are verified **again before execution**. For
character generation use recipe keys `blueprint`, `workflow`, `profile`,
`reference` with hashes for each, and an explicit `review_model`. There
are no automatic model downloads or remote inference fallbacks.

## Mac-local durable receipts

Use a private local SSD SQLite journal `receipts.sqlite` (not on NFS,
SMB or Synology). It is keyed by coordinator `job_id` independent of lease
generation. Before an expensive action, commit a `STARTED` record. On
successful local result, commit a `DONE` receipt with SHA256, status,
media type and size. On restart:
- **DONE** means attempt to retransmit the receipt, never render again.
- **STARTED** means quarantine and ask for manual reconciliation; the
  underlying ComfyUI process might still be rendering.
- New job IDs cannot write into existing version directories.

The Pi completes a leased media job using metadata only and always sets
`publication_approved=false`. Lost/cancelled leases cannot publish
a completion. A 45-second heartbeat extends the 600-second Pi lease during
long work.

This provides **at-most-one-start on the SAME Mac with intact journal**,
not globally exactly-once semantics. If a Pi erroneously gives a new job ID
for the same requested render, a Mac is replaced, or local receipts are lost,
a new execution may happen. Never market this as guaranteed exactly-once.

## Example manual, once-only launch

Pi admin config (illustrative, token already provisioned):

    studio-coordinator \\
      --db /private/kidsstudio/brain.sqlite \\
      --vault /private/kidsstudio/vault \\
      --tls-cert /private/kidsstudio/pi.crt \\
      --tls-key /private/kidsstudio/pi.key \\
      --worker-id mac-media-01 \\
      --token-env KIDS_STUDIO_MEDIA_TOKEN \\
      --worker-kinds character_generate,godot_render

On Mac (requires certificate matching the coordinator hostname and a
private approved local recipe file):

    studio-media-worker \\
      --coordinator https://YOUR-PI-NAME:8765 \\
      --ca-cert /private/kidsstudio/pi.crt \\
      --recipes /private/kidsstudio/media_recipes.json \\
      --journal /private/kidsstudio/receipts.sqlite \\
      --worker-id mac-media-01 \\
      --token-env KIDS_STUDIO_MEDIA_TOKEN \\
      --once

The above is **not** a deployment command to run now; the Pi HTTPS
server must still undergo device-specific onboarding, firewall, clock/NTP,
token rotation, and LAN security testing. A coordinator process currently
configures a single worker ID; future versions will support multiple
concurrently enrolled workers with independent tokens and capabilities.

## Tests and release gate

GitHub CI verifies allowed recipe mapping, changed source hash rejection,
valid media metadata, wrong/forbidden public status, cancelled leases,
single executor call on ambiguous STARTED, remote ack-loss recovery using
new lease generations, and journal state across calls.

Even a correct MP4 is `VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW`.
Approval of actual child education value, audio, narration, safety,
YouTube upload and monetization compliance remain separate, with the
owner's private-review → public-release gate.
