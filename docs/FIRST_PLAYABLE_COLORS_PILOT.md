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
