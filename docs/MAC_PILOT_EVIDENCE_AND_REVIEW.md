# Mac colors pilot — private technical evidence and owner review

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
