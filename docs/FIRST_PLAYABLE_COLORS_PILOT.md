# First playable colors pilot — zero cloud calls (Mac)

**Goal:** get a real, locally playable private MP4 quickly, without waiting for the full AI character factory. This is an **original static illustrated 24-second test**, not a finished KidsStudio animation or a YouTube-ready published episode. The existing 12-second six-beat `examples/colors_ar_01_pilot_cues.json` remains a draft. This pilot intentionally gives each of those six narration phrases **four seconds**, to better accommodate clear child-directed Arabic speech.

## Included and not included

- Included: six original Pillow illustrations for greeting, three colors, red apple, yellow sun, blue sky and recap. The pictures do not need internet or third-party art. Video output is 1280×720, 24 fps, H.264 yuv420p; audio is AAC stereo 48 kHz via the already tested `mac_episode_audio` mux tool.
- Included: local macOS voice synthesis using an Arabic system voice already installed on the Mac, or optionally a pre-existing private original 24-second 16-bit PCM narration WAV with a trusted SHA256. Mac speech is not automatically downloaded; no paid/cloud service is contacted. A system voice may sound robotic: **human listening is mandatory**.
- Excluded: true character rig animations, synced subtitles, on-screen Arabic letters, independent image/content review, AI model selection, ComfyUI/Godot execution, Pi transfer, YouTube OAuth and video uploading. This is a standalone **visual+audio smoke pilot**, not a replacement for the normal Godot rig production workflow.
- No files are changed in the Git checkout. All generated PNGs, temporary AIFFs/WAVs and videos live in a private operator-owned directory. Existing output files are never overwritten.

## Mac one-command trial

The following commands run only on your own Mac with the reviewed KidsStudio branch checked out, a private Python 3.11+ venv with Pillow installed, and `ffmpeg`, `ffprobe` and the standard macOS `say` command available.

~~~bash
cd /path/to/KidsStudio
python3 -m pip install -e .
umask 077
mkdir -p "$HOME/kidsstudio-private/ready"
chmod 700 "$HOME/kidsstudio-private/ready"
python3 -m kidsstudio.first_colors_episode \
  --output-root "$HOME/kidsstudio-private/ready"
~~~

The **default** returns `COLORS_EPISODE_PREVIEW_ONLY` and creates **no files or network activity**. It validates the selected output directory but does not require the Arabic voice to already be installed.

Now inspect installed voices (this prints only your local OS voice list):

~~~bash
say -v '?' | grep -E 'ar[_-]'
~~~

If there is no Arabic voice, install one through macOS language/accessibility voice settings **under your control**, or use the already-supported `--voice-mode supplied_wav` option below. Do not assume any particular named Arabic voice is present on all Macs.

To render **locally**, with the first installed Arabic voice:

~~~bash
python3 -m kidsstudio.first_colors_episode \
  --output-root "$HOME/kidsstudio-private/ready" \
  --output-name colors_ar_01.mp4 \
  --execute
~~~

This action creates an isolated `colors_ar_01-pilot-sources` directory (original scene PNGs, generated AIFF beat recordings and PCM WAV), then a private `colors_ar_01.mp4` only after a fully decoded audio/video technical check and SHA verification. It automatically refuses to truncate a spoken beat longer than four seconds. In that case, use a new versioned filename and a separately paced 24s WAV, or revise the storyboard/speech timings; **do not speed up or truncate educational speech without listening**.

To choose an existing specific Arabic macOS voice, add `--mac-voice ACTUAL_ARABIC_VOICE_NAME` after confirming its name from the list above. The tool refuses voices not listed under Arabic by the OS.

## Option: supply an owner-recorded or separately approved original voice

If a 24-second 16-bit PCM WAV already exists in a private 0700 directory as `colors_ar_01.wav`, set its mode to 0600, independently calculate its SHA with `shasum -a 256`, then use:

~~~bash
python3 -m kidsstudio.first_colors_episode \
  --output-root "$HOME/kidsstudio-private/ready" \
  --voice-mode supplied_wav \
  --narration-root "$HOME/kidsstudio-private/narration" \
  --narration-name colors_ar_01.wav \
  --narration-sha256 YOUR_TRUSTED_64_DIGIT_SHA256 \
  --execute
~~~

The same audio-path privacy, format, timing and checksum checks apply. If a previous attempt left `colors_ar_01-pilot-sources`, deliberately inspect it and choose a **different** output name (e.g. `colors_ar_01_v2.mp4`) rather than replacing earlier evidence.

## Acceptance checklist (manual and mandatory)

Watch and listen to **the whole output**: do the spoken colors match the displayed objects, is the Arabic pronunciation natural, is the timing pleasant and accessible to children, are pictures simple and correct, is the voice free of clipping, and is the file actually playable on your devices? The automated test only proves that the formats are valid and source bytes match the reported digest at check time. No automatic publishing or independent pedagogical approval occurs.

If the smoke pilot succeeds, record the exact Git commit, final MP4 SHA and file duration. Then use the independent [Mac-to-Pi transfer](MAC_PI_TRANSFER_PILOT.md), recheck SHA on the Pi, and only after separate owner permission use the [YouTube PRIVATE upload pilot](PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md). Do not upload this first graphics-only smoke file as if it were a polished children's episode.

**Not tested here:** actual Apple Arabic voice availability, actual Mac rendering and audio quality, actual Pi transfer and OAuth/YouTube upload. CI tests are synthetic or mocked and cannot assert those facts.

## Batch 48 — genuine CI encoding test and simplest Mac invocation

GitHub Actions workflow `.github/workflows/real-colors-smoke.yml` performs a **real 24-second 1280×720 FFmpeg H.264/AAC** encode using the actual six original Pillow scenes and an artificially **silent 24-second test WAV**, verifies output SHA256/audio stream and decodes three actual MP4 frames to check the red apple, yellow sun and blue sky. The generated file remains in the temporary CI workspace; it is **not attached, uploaded to YouTube or approved**. This validates Linux FFmpeg behavior only, not the presence or pronunciation of a Mac Arabic voice.

On a Mac with the latest feature-branch source checkout, Python 3.11+ / Pillow, FFmpeg/FFprobe and a locally installed Arabic `say` voice, the **shortest supervised command** is:

```bash
cd /path/to/your/KidsStudio
bash scripts/run_mac_colors_pilot.sh
```

That explicit command checks the required local applications, creates a private output directory, performs a non-writing preflight, renders a new **versioned** 24-second video with an installed Arabic voice, prints SHA256, and opens the local movie for listening and review. It does **not** install or download models, transmit videos to Pi, contact YouTube, spend on AI APIs, delete earlier versions, approve publication, or launch any background service. To select a different local Python environment, set `KIDSSTUDIO_PYTHON=/absolute/path/to/python3.12`.

The GitHub CI workflow only runs `bash -n` against this launcher; **the launcher has never been executed on the user's actual Mac**. A downloadable visual-only demonstration rendered in a separate ChatGPT runtime is not equivalent to the Mac's voice-enabled, owner-reviewed output.

**Next hard gate:** supervised execution on the real Mac and inspection of the voice/visual results. Then one physical SSH Mac→Pi receipt and a separate OAuth-authorized YouTube PRIVATE test are the remaining device/network qualifications. Avoid re-entering exploratory feature development until these are done.

## Batch 50 — fail-closed playback compatibility inspection

The Mac launcher now has a **third local step** before it opens any generated episode: `kidsstudio.mp4_playback_preflight` independently verifies the final private MP4 SHA-256, parses top-level ISO BMFF boxes to check that exactly one `moov` precedes `mdat` (faststart), requires H.264 Baseline/Constrained Baseline level 3.1 or lower and AAC-LC stereo 48 kHz, and actually decodes **three video samples and two audio samples** through local FFmpeg. It checks the file SHA-256 again after probing. No samples are saved; the check reads only local media, never writes, uploads, or contacts Pi/YouTube.

For an existing private local MP4, use the **SHA recorded by the operator from the completed render**:

```bash
python -m kidsstudio.mp4_playback_preflight \\
  --root "$HOME/kidsstudio-private/ready" \\
  --relative-path colors_ar_01.mp4 \\
  --expected-sha256 TRUSTED_64_HEX_SHA256
```

A successful `MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED` means a conservative **technical sample** passed, **not** that the entire MP4 was decoded or successfully opened on iPhone/iPad, that Arabic pronunciation is natural, that audio is audible, or that anyone reviewed the lesson. The result always leaves publication/transfer/upload flags false. On failures, the launcher stops **before opening or handing off** the video, retains the file for private diagnosis and prints a fixed blocked status rather than a media path or FFmpeg log. Do not use this check to bypass full owner playback review. The Linux real-colors CI smoke now checks the same actual encoded H.264/AAC file and samples, without claiming Mac hardware or voice qualification.

## Batch 51 — durable private Mac evidence and explicit owner review

The foreground **scripts/run_mac_colors_pilot.sh** now has **four** stages: offline preflight, local 24-second Arabic-voice render, actual MP4 sample decoding, and creation of a **new, non-overwritten owner-private 0600 evidence JSON** under "$HOME/kidsstudio-private/qualification" outside Git. The evidence contains the exact final MP4 SHA-256, size, duration, three video/two audio decode counts, source Git commit, clean tracked checkout claim, and host readiness. Its status is always MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING; it cannot authenticate the Mac's identity, confirm a human listened, or authorize an upload.

Run the Mac launcher as previously documented. Only after it has succeeded, **watch and listen to the entire generated local video**. In the example below, replace the exact versioned name with the one printed by the launcher; do not use "latest" or a guessed hash:

~~~bash
VIDEO_NAME="colors_ar_01_test_REPLACE_WITH_ACTUAL_TIMESTAMP.mp4"
VIDEO_SHA="$(shasum -a 256 "$HOME/kidsstudio-private/ready/$VIDEO_NAME" | awk '{print $1}')"
EVIDENCE_NAME="$(basename "$VIDEO_NAME" .mp4).evidence.json"

# If the clip needs correction, save a SHA-bound note:
python -m kidsstudio.mac_pilot_evidence review \
  --video-root "$HOME/kidsstudio-private/ready" \
  --video-name "$VIDEO_NAME" --expected-sha256 "$VIDEO_SHA" \
  --evidence-root "$HOME/kidsstudio-private/qualification" \
  --evidence-name "$EVIDENCE_NAME" \
  --review-outcome REVISION_REQUIRED \
  --reviewer-notes "راجع نطق الأحمر وتزامن المشاهد"
~~~

If and only if you actually **watched the full video, listened to all Arabic narration and personally accept that specific PRIVATE test**, run the same review command with **--review-outcome ACCEPTED_PRIVATE --reviewed-full-video --reviewed-arabic-voice** instead of REVISION_REQUIRED. Both outcomes create a distinct append-only review JSON file; earlier evidence is not altered. The acceptance is a **local operator assertion without identity authentication**, and it is neither permission to upload to the owner's channel nor authorization to publish.

Review notes may be visible in your local shell history/process list when provided with --reviewer-notes, so avoid confidential notes or credentials in that argument. Both the technical report and the review files must stay on the owner's encrypted/private device, outside Git. There is no SSH transfer, Pi test, OAuth, YouTube call, queue mutation, background task or public release in this workflow.

**Actual physical Mac render, Arabic voice listening and a real human review are still NOT_RUN** in development/CI. This only provides a reliable tool to capture their evidence when the operator runs it on the Mac; never substitute a synthetic CI pass for that step.

## Batch 51 — collect private physical-Mac pilot evidence and separate owner review

The foreground Mac launcher now includes a **fourth step**: after the verified H.264/AAC encode, it runs `kidsstudio.mac_pilot_evidence collect`, repeats offline role/checkout qualification and the MP4 decoder preflight, and writes a **unique owner-private technical evidence JSON** in `$HOME/kidsstudio-private/qualification` before opening the video. Evidence is SHA-256-bound to the specific MP4, includes the checked-out Git commit and explicit pending/false review/upload/publication flags, and never changes the media or any existing evidence file. Running the launcher from a source checkout with local tracked changes blocks the evidence step instead of recording misleading provenance.

Once the owner has actually watched and listened to the whole Arabic video, the separate `kidsstudio.mac_pilot_evidence review` command records either `REVISION_REQUIRED` with notes or `ACCEPTED_PRIVATE` **only when the operator explicitly confirms both full-video and Arabic-voice review**. Each review is a separate 0600 JSON file. The reviewer identity is not cryptographically authenticated; private acceptance does not approve Pi transfer, an upload, or a public release. Full commands and file locations: [MAC_PILOT_EVIDENCE_AND_REVIEW.md](MAC_PILOT_EVIDENCE_AND_REVIEW.md).

The new sidecars are **non-replacing through the tool, not tamper-proof** against their filesystem owner. GitHub CI uses synthetic data and mocked platform checks; the real Mac/voice, physical Pi and YouTube steps are still `NOT_RUN`.

## Batch 52 — real macOS runner encoding validation

The additional GitHub Actions workflow `.github/workflows/macos-colors-smoke.yml` runs on a **GitHub-hosted macOS 15 runner**, not the user's Mac. It installs the project and a pinned FFmpeg binary, uses the **same real 24-second illustrated MP4 generation pipeline with a synthetic silent WAV** previously exercised on Linux, then verifies SHA-256, H.264/AAC faststart, decoded image/audio samples and the three color cues. The MP4 is deleted with its CI temporary directory and is **never uploaded as a GitHub artifact**.

A separate CI step checks for an **already installed** native Arabic macOS `say` voice. When available, it attempts to synthesize the six original speech beats into a temporary 24-second private WAV, checks basic duration, and deletes it. When no Arabic voice is installed on the hosted runner, it prints `MACOS_CI_ARABIC_VOICE_NOT_INSTALLED_NOT_TESTED` instead of claiming that speech synthesis passed. This is a **capability check, not listening or Arabic pronunciation verification**. The CI does not download voices, install a speech model, access project secrets, generate public videos, contact a Pi, or invoke a YouTube API.

The physical owner-Mac test is **still required**: CI may use different voices, audio hardware, FFmpeg paths, macOS versions and local Python environments. The supervised four-step command remains `bash scripts/run_mac_colors_pilot.sh`. An actual owner review must follow with its exact SHA-bound notes; see [MAC_PILOT_EVIDENCE_AND_REVIEW.md](MAC_PILOT_EVIDENCE_AND_REVIEW.md).

## Batch 53 — pre-render native Arabic voice readiness and per-beat PCM signal presence

Before the supervised one-command Mac launcher starts the expensive MP4 encode, it runs:
```bash
python3 -m kidsstudio.mac_colors_preflight \
  --artifact-root "$HOME/kidsstudio-private/ready"
```
This command is **read-only** and checks the real Mac role, Python/private artifact root/free disk, a clean full-source Git checkout, `ffmpeg`, `ffprobe`, `say`, `git` and `shasum`, plus detection of an **already-installed** native Arabic `say` voice. It never downloads a voice or renders speech/video; on failure it prints fixed, non-sensitive blocker codes and exits nonzero **before** MP4 encoding. If `installed_arabic_voice_missing_or_invalid` is listed, choose an actual installed Arabic system voice or configure one locally under operator control; the code never silently switches to English. Use a private original SHA-pinned WAV via the supported separate `--voice-mode supplied_wav` command if no system voice is available.

Once the Mac renders six voice segments, `kidsstudio.audio_pcm_energy.check_six_beat_pcm_energy` verifies that the locally generated **24-second mono 16-bit PCM WAV has measurable signal in each of the six four-second scenes** before muxing the final MP4. A silent or almost silent beat fails closed and leaves the intermediate files private for supervised diagnosis. This signal-presence check cannot recognize Arabic words or prove that the narration is intelligible, pleasant, correctly paced or properly pronounced; the owner's complete listening review still controls acceptance.

The Linux and hosted-macOS CI **synthetic silent-WAV** encoder smokes intentionally use `--voice-mode supplied_wav` and are **not** treated as actual Arabic speech. The energy requirement is enforced on the native `say` speech track; it does not pretend that imported WAV content is voice-verified. Actual operator Mac audio and device playback remain NOT_RUN.

## Batch 54 — voice-first pilot and optional installed Arabic voice selection

For `voice_mode=macos`, the first colors episode now **synthesizes and checks all six narration beats first**, before performing the 1280×720 H.264 video encode. Invalid, silent or overlong native voice segments stop the render **without starting the video encoder or final mux**. SHA-pinned, operator-supplied WAV inputs remain independently validated in the existing alternative route.

On the actual Mac, the one-command launcher optionally reads `KIDSSTUDIO_MAC_VOICE` to select one *already installed* Arabic macOS `say` voice (e.g., `KIDSSTUDIO_MAC_VOICE=Maged bash scripts/run_mac_colors_pilot.sh` if Maged appears in `say -v '?'`). It passes exactly the same choice to preflight and to synthesis, rejecting invalid/non-Arabic/uninstalled choices; default remains the first detected installed Arabic voice. It uses macOS Bash 3.2-compatible conditional commands and private filenames with per-run random suffixes to avoid same-second retries colliding. No new voice/model download or network operation is involved. **Audio signal presence is not proof of Arabic intelligibility or educational quality.**

## Batch 55 — complete native-mode synthetic audio/video integration on hosted macOS

The macOS GitHub Actions workflow now performs a **second full 24-second MP4 encode** through the production `voice_mode=macos` path, not the imported silent WAV path. To keep CI independent of a machine-installed Arabic speech voice, a **test-only Python interception** replaces macOS `say` responses with six locally generated **sine-wave AIFF tones**. The real code still performs all six AIFF probes, resampling/padding/concatenation into 24-second PCM, the six-beat energy gate, the real illustrated H.264 render, private SHA-pinned AAC mux, MP4 faststart/profile/sample decoder verification, and finally **decodes AAC separately from each of the six four-second video segments** to verify none of the audio beats vanished during mux. The rendered media stays in temporary private CI storage and is deleted; no audio or video GitHub artifact is published.

A green `MACOS_CI_NATIVE_MODE_WITH_SYNTHETIC_TONES_PASSED` proves **synthetic audio-path wiring and final file integrity only**. Test tones are not speech and cannot validate native Apple `say` Arabic voices, pronunciations, pedagogical quality, the user's hardware, or iPhone playback. The separate optional installed-voice check continues to return `MACOS_CI_ARABIC_VOICE_NOT_INSTALLED_NOT_TESTED` on a hosted Mac without an Arabic TTS voice; this status must never be rewritten as a passed human-voice test. All actual operator Mac/Pi/YouTube gates remain NOT_RUN.

## Batch 61 — device doctor before first real local run

Before running the Mac rendering launcher for the first time, run `python3 -m kidsstudio.first_pilot_device_doctor --role mac` from your exact pinned KidsStudio checkout/venv. It performs local read-only source/permissions/disk/media/installed-Arabic-voice checks, gives fixed-safe suggestions for blockers, and does not generate any output or install voices. A green doctor is **not** a test of the actual spoken Arabic or the final MP4. After Mac technical QA, the normal workflow is Pi PRIVATE staging through `kidsstudio.technical_mac_pi_handoff`, a separately authorized YouTube PRIVATE upload, then **owner review of the PRIVATE draft**; do not require manual pre-transfer acceptance. See [FIRST_REAL_DEVICE_PILOT.md](FIRST_REAL_DEVICE_PILOT.md).
