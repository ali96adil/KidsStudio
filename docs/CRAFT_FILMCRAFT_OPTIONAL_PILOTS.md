# Craft Anything + FilmCraft — optional KidsStudio pilots

**Status:** read-only qualification tools have been added. Neither Craft Anything nor FilmCraft has been installed, run, or tested on the user's Mac. Existing Godot/FFmpeg and Mac→Pi/YouTube paths remain untouched.

Upstream reviewed on 2026-11-07:
- [Craft Anything](https://github.com/storytold/craft-anything) — MIT OR Apache-2.0, early alpha. Clean room is the default and works with visible UI observations rather than target source. It is **not an OS sandbox**. The upstream CLI/MCP/agents are not activated by this integration.
- [FilmCraft](https://github.com/storytold/filmcraft) — MIT OR Apache-2.0, alpha. Upstream advertises H.264/AAC MP4, Arabic-capable text shaping, timelines, CLI and MCP, but real-production readiness is limited. All relevant properties must be verified with the user's own synthetic samples on the actual Mac.

**Permissions:** only inspect KidsStudio-owned UI and synthetic media. Do not reproduce proprietary artwork, program code, brand marks, music, fonts, assets or footage without rights. Keep automation disabled until the tool's source/release, CLI scope, credentials and workspace permissions have been reviewed. Pin an upstream release before live tests.

## Pilot 38 — three-width dashboard screenshot evidence

Use kidsstudio/craft_ui_evidence.py. It performs **no Craft Anything calls**. The operator manually supplies three PNG screenshots of a KidsStudio dashboard test UI captured at CSS widths 375, 768 and 1280. Store the PNG files in an existing private root outside Git, mode 0700, and chmod each PNG and the JSON manifest to 0600. Use shasum -a 256 for each actual PNG. Example private craft.json:

~~~json
{
  "schema_version": 1,
  "tool": "craft-anything",
  "target": "kidsstudio-owned-dashboard",
  "screenshots": [
    {"viewport_css_width": 375, "relative_path": "mobile.png", "sha256": "REPLACE_WITH_REAL_64_HEX_SHA"},
    {"viewport_css_width": 768, "relative_path": "tablet.png", "sha256": "REPLACE_WITH_REAL_64_HEX_SHA"},
    {"viewport_css_width": 1280, "relative_path": "desktop.png", "sha256": "REPLACE_WITH_REAL_64_HEX_SHA"}
  ]
}
~~~

Example command:

~~~bash
python -m kidsstudio.craft_ui_evidence \
  --evidence-root "$HOME/kidsstudio-private/creative-tool-evidence/craft" \
  --manifest craft.json
~~~

The tool SHA-checks each PNG against the supplied hash, checks limited IHDR header dimensions, and rejects symlinks, unsafe paths, public file permissions, duplicate content, and incomplete width coverage. A Retina screenshot can have a physical pixel width 1–4× its claimed CSS viewport width.

**A passing result means the *provided files* matched their own expected SHA at the time of the check.** It does not prove images came from Craft Anything, that the recorded viewport was true, that the entire PNG is valid, that the UI is visually equivalent, or that buttons function. Manually review Arabic RTL, responsive layout, touch targets, failed/loading states and accessibility. Keep captured content synthetic and private.

## Pilot 39 — optional FilmCraft exported-media check

Use kidsstudio/filmcraft_export_check.py. Keep the original Godot/FFmpeg output as the baseline. On a separate private, non-production project, manually edit and export an original synthetic video from a reviewed FilmCraft release. Include narration/audio when testing the *final delivery* profile; silent early Godot previews are not final deliverables.

The technical output profile used for comparison: MP4 with one H.264 1280×720 yuv420p video stream at 24, 25, 29.97 or 30 fps; one AAC stereo 48 kHz audio stream; duration 0.1–600 seconds. Verify all actual quality and Arabic caption concerns separately (voice sync, loudness, frame integrity, RTL glyph shaping, caption legibility and rights). Configure these settings in FilmCraft manually before running the check.

Place the exported test episode-pilot.mp4 in a private directory outside Git, 0700, chmod the video 0600, and obtain its SHA with shasum -a 256. Ensure an independently reviewed ffprobe installation is available locally.

~~~bash
python -m kidsstudio.filmcraft_export_check \
  --evidence-root "$HOME/kidsstudio-private/creative-tool-evidence/filmcraft" \
  --relative-path episode-pilot.mp4 \
  --expected-sha256 REPLACE_WITH_REAL_64_HEX_SHA
~~~

This operator-initiated checker hashes the actual file **before and after** running local ffprobe with fixed arguments and a bounded timeout. It does not launch FilmCraft, change the media, use MCP, transfer the file, or upload it anywhere. **A technical PASS does not authenticate that FilmCraft produced the file**, nor does it verify audio perception, frame appearance, typography, educational accuracy, content rights, or upload approval. Real-world quality and subtitles require human/independent checks.

## Security and rollback

- Both tools are add-on evidence inspectors, not substitutions for the current Godot/FFmpeg workflow.
- Input evidence must be regular owner-only files (0600), with no symlink components, inside an existing owner-only private root (0700) outside Git. No data should be committed.
- No queue updates, new remote endpoints, model downloads, paid inference, FilmCraft control-channel actions, or child-content publication.
- The local filesystem checks are not an OS sandbox; a malicious concurrent process with write access could still race file replacement.
- Disable these evaluation tools simply by not invoking their CLI modules. Keep existing approved media immutable; archive or delete experimental copies only after deliberate review.
- Craft Anything actual UI runs, FilmCraft actual export on the Mac, Mac→Pi network transfer, and YouTube tests are still **NOT_RUN**.
