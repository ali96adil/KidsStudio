# Mac colors pilot — private technical evidence and owner review

> **Current workflow (Batch 60):** local human review is OPTIONAL before Mac→Pi staging. The user reviews the **YouTube PRIVATE draft after upload**. The commands below remain available for local pre-review, but do not have to run before technical QA-only transfer via `kidsstudio.technical_mac_pi_handoff`. No public release is automatic.

**Status:** code and Linux CI checks only; no actual Mac render, actual Arabic voice, real Pi transfer, Google OAuth or YouTube upload has been performed by these tools. This is a supervised local pilot, not an autonomous production pipeline.

## One Mac command

On a trusted macOS system with the reviewed KidsStudio branch checked out, Python 3.11+ and Pillow available, an **already installed** Arabic macOS voice, and `ffmpeg`/`ffprobe`:

```bash
cd /path/to/KidsStudio
git status --short
bash scripts/run_mac_colors_pilot.sh
```

The shell command (1) previews the local-only 24-second storyboard, (2) renders a new unique 720p H.264/AAC MP4 with a locally installed Arabic system voice, (3) verifies MP4 SHA-256, faststart, codecs and decoded video/audio samples, and (4) **re-runs the offline Mac host qualification and playback inspection** and writes private technical JSON evidence before opening the movie. All of this runs in the foreground. It **never** transfers, uploads or publishes media. The 24-second illustrations are static smoke-test artwork, not finished character animation.

If any technical step fails, the launcher stops rather than opening or handing off the video. The MP4 and any intermediate private files may remain for debugging. The evidence collect step requires a pinned, **tracked-clean** local Git checkout with a full 40-character commit and host-readiness success. On a Mac without a source checkout, it blocks rather than fabricating source provenance.

By default, the two new private locations are:
- Video: `$HOME/kidsstudio-private/ready/colors_ar_01_test_YYYYMMDD_HHMMSS.mp4`
- Sidecar: `$HOME/kidsstudio-private/qualification/colors_ar_01_test_YYYYMMDD_HHMMSS.evidence.json`

Both directories are created with owner-only permission (0700), media/sidecar files are private (0600), and evidence filenames cannot be replaced by these commands. Never put media, reports, notes, authentication credentials or OAuth tokens in the Git repo. A sidecar records only episode/version identification, hash, duration, test status, local checkout SHA and explicitly false transfer/upload/publication flags; it contains no video frames or speech recordings.

## After watching and listening to the complete 24 seconds

**The owner**, not an unattended agent, chooses one outcome and records a short note. Reading the generated `Video`, `Final MP4 SHA256` and `Private technical evidence` lines from the Mac launcher is the easiest way to supply exact values. Replace the placeholders below with those printed values:

```bash
python3 -m kidsstudio.mac_pilot_evidence review \
  --video-root "$HOME/kidsstudio-private/ready" \
  --video-name ACTUAL_GENERATED_FILENAME.mp4 \
  --expected-sha256 ACTUAL_RECORDED_64_HEX_SHA \
  --evidence-root "$HOME/kidsstudio-private/qualification" \
  --evidence-name ACTUAL_GENERATED_FILENAME.evidence.json \
  --review-outcome REVISION_REQUIRED \
  --reviewer-notes "مثلاً: نطق كلمة الأصفر يحتاج تحسين"
```

To record **local private-only acceptance** after actually checking the **entire** video and **all** spoken Arabic, change the outcome and include the two explicit attestations:

```bash
python3 -m kidsstudio.mac_pilot_evidence review \
  --video-root "$HOME/kidsstudio-private/ready" \
  --video-name ACTUAL_GENERATED_FILENAME.mp4 \
  --expected-sha256 ACTUAL_RECORDED_64_HEX_SHA \
  --evidence-root "$HOME/kidsstudio-private/qualification" \
  --evidence-name ACTUAL_GENERATED_FILENAME.evidence.json \
  --review-outcome ACCEPTED_PRIVATE \
  --reviewed-full-video \
  --reviewed-arabic-voice \
  --reviewer-notes "النسخة المحلية مقبولة كتجربة خاصة فقط"
```

Review always rehashes the *current* video against the sidecar and its original SHA. It creates a **new separate private** `*.review.<random>.json` file; it never edits the earlier evidence or previous reviews. If the source file changed, evidence is absent/unsafe or the exact hash differs, review fails. To make corrections, render a **new version**, keep the old file/evidence and record the revision request instead of overwriting history.

The `ACCEPTED_PRIVATE` status is an **unauthenticated local operator assertion**, not independently proven owner identity, Google API permission, media upload authorization or approval to release anything publicly. The local evidence is non-overwriting by the tool **but not tamper-proof** against its filesystem owner. There is no claim of an inspected iOS device, a full-file automated decode or verified Arabic pronunciation. Manually open, listen and inspect the clip on the intended devices.

## Next physical acceptance gates

A recorded local review does **not** invoke `mac_to_pi_transfer` or `pi_youtube_private_upload`. After a satisfactory real-Mac visual/audio review, separately qualify the physical Pi, compare source revisions, perform one **explicit** host-key-verified SSH transfer and independently compare MP4 SHA on the Pi. Then, under separate owner supervision and with private credentials not shared in chat/GitHub, test the **PRIVATE-only** YouTube upload. The owner must watch the resulting YouTube PRIVATE draft and make a separate later publication decision. See [MAC_PI_TRANSFER_PILOT.md](MAC_PI_TRANSFER_PILOT.md), [PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md](PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md), and [MVP_FINISH_LINE.md](MVP_FINISH_LINE.md).

## Batch 53 — diagnose voice before spending time on render

The foreground launcher now runs a read-only `mac_colors_preflight` **before** beginning rendering. It refuses missing/invalid installed Arabic `say` voices, a dirty/unavailable Git checkout, missing local FFmpeg/ffprobe and an unsafe output root. The detailed command can be run separately: `python3 -m kidsstudio.mac_colors_preflight --artifact-root "$HOME/kidsstudio-private/ready"`. The output has only fixed blocker codes; it deliberately does not print the voice name or private file paths.

For the native macOS voice route, the completed original 24-second PCM speech track additionally needs measurable audio energy in **all six four-second beats**, rather than merely a valid WAV header. This catches empty and nearly silent native voice outputs but **does not** verify spoken language or correctness; an owner must still listen. The evidence sidecar is technical metadata only, never publication permission. The optional `supplied_wav` route is not automatically classified as spoken Arabic by this gate and still needs owner listening.

## Batch 54 — validate Arabic voice before video encode; choose an installed voice

The first colors render now synthesizes and checks all six Arabic voice beats **before** encoding the illustrated 24-second MP4. If a system voice is missing, silent, too long for a beat or otherwise fails, the video encode and final mux are **not started**. Failed attempts may leave private intermediate speech files for local diagnosis but never upload them.

The Mac launcher also accepts an optional, specifically selected *already installed* Arabic system voice without modifying the project:

```bash
# Run locally on the Mac to see available voices and languages:
say -v '?'

# Example: only if an Arabic voice named Maged is actually listed:
KIDSSTUDIO_MAC_VOICE=Maged bash scripts/run_mac_colors_pilot.sh
```

A supplied name is checked against the installed Arabic voice list both during preflight and rendering. The launcher uses branches rather than empty Bash arrays to support the system Bash included with macOS, and each output filename has both timestamp and a random retry suffix to avoid collisions when two attempts happen within one second. Do **not** share your speech files or generated clip publicly while reviewing them.

This change improves local operational reliability; it does not prove correct Arabic pronunciation or replace the full owner listening/playback check. Actual owner Mac, Pi transfer, YouTube PRIVATE upload and later publication decisions remain separate human-supervised steps.

## Batch 56 — SHA-free local review shortcut (no automatic approval)

After an **actual successful Mac run**, the launcher prints the exact recorded evidence filename and the command to list available local proofs. You do not need to retype the 64-character video SHA or video filename. This convenience layer re-reads the owner's private technical evidence, validates its original source SHA/clean state, its expected video name/bytes and exact current MP4 SHA-256, and only then delegates to the existing review record writer.

Run this in the checked-out KidsStudio directory on the same Mac:

```bash
# Read-only: show the latest 10 actual, hash-verified local pilot entries.
python3 -m kidsstudio.mac_pilot_review_shortcut list

# After full viewing, record a revision note tied to ONE EXACT evidence file.
python3 -m kidsstudio.mac_pilot_review_shortcut record \
  --evidence-name ACTUAL_GENERATED_NAME.evidence.json \
  --review-outcome REVISION_REQUIRED \
  --reviewer-notes "مثلاً: الصوت يحتاج تعديل"
```

If and only if you have watched the **entire** MP4 and listened to **every** Arabic line yourself, the same exact evidence name can be marked locally accepted for private review with all of:

```bash
python3 -m kidsstudio.mac_pilot_review_shortcut record \
  --evidence-name ACTUAL_GENERATED_NAME.evidence.json \
  --review-outcome ACCEPTED_PRIVATE \
  --reviewed-full-video \
  --reviewed-arabic-voice \
  --reviewer-notes "مقبول كتجربة محلية خاصة فقط"
```

The shortcut **never chooses a review candidate implicitly by timestamp**. It does not open the video, assert you watched it, upload files or publish anything. Listing is strictly read-only and omits invalid/mismatched sidecars. Any request to record review must supply an exact technical sidecar filename, an outcome and, for acceptance, the two explicit reviewed flags. It still writes a distinct 0600 note, refuses tampered/untrusted input and rechecks the current media hash. *Acceptance here is not transfer permission, upload permission or publication approval.* The full manual SHA-based command earlier in this runbook remains supported.

## Batch 57 — guided local review in one command (Terminal only)

After the pilot opens your new local MP4, **watch all 24 seconds and listen to every Arabic sentence yourself**. From the same trusted, checked-out KidsStudio repository on the Mac, run:

```bash
python3 -m kidsstudio.mac_pilot_review_shortcut guided
```

The guided command is deliberately interactive and **requires an actual input/output terminal**; piped stdin, scheduled CI, or unattended invocations cannot record a decision. It lists up to 10 existing, SHA-matched private pilot evidence files and requires you to type the number of the exact video. There is **no default/latest selection**. After showing that video's name, you must separately choose `R` (needs revision) or `A` (accept as a *local private pilot*). A revision requires a nonempty written note. Acceptance requires you to explicitly type `YES` for having watched the **entire** video, then type `YES` for personally checking **all Arabic speech**. Both choices require a final exact `SAVE` before the software writes one separate private review JSON.

Typing `0`, `C`, an invalid selection, an incomplete/EOF prompt or anything other than the exact required confirmation **cancels without creating any review**. Right before saving, the shortcut **checks the original technical sidecar and hashes the selected MP4 again**; tampering between the list display and the final `SAVE` fails closed. The old `list` and `record` CLI remain supported for advanced use. The Mac launcher now prints the guided command after it generates a valid local video; it does **not** run guided mode or accept a video by itself. These are operator assertions, not independently authenticated reviewer identities, and never grant permission to transfer, upload or publish.

## Batch 60 — when to use local guided review

The human-first review described earlier is **optional** on the Mac. For the normal KidsStudio PRIVATE-first path, no review confirmation is needed before Pi staging. The Mac launcher prints the exact technical evidence file; follow the *technical* handoff procedure in [MAC_PI_TRANSFER_PILOT.md](MAC_PI_TRANSFER_PILOT.md), then separately authorize YouTube PRIVATE upload on the Pi. Watch the resulting PRIVATE draft on YouTube, enter notes/feedback and make a distinct decision about any later public publication. Neither the `guided` local review command nor `ACCEPTED_PRIVATE` grants permission to make a video public.
