# First physical KidsStudio colors pilot — offline Mac/Pi doctor

**Status: code and CI qualification only. Neither the operator's Mac nor their Raspberry Pi has been examined by these tests.** This runbook supports the approved **PRIVATE-first** order: generate and run technical QA on Mac → copy by explicitly approved SSH to Pi → separately authorize a PRIVATE YouTube draft → owner reviews it and decides revisions or later public release.

## The first thing to run (read-only, no media creation)

From the **trusted KidsStudio checkout** on the actual Mac, with the same Python 3.11+ environment used for the pilot:

~~~bash
python3 -m kidsstudio.first_pilot_device_doctor --role mac
~~~

Run separately from the **trusted matching source checkout** on the actual Raspberry Pi 4:

~~~bash
python3 -m kidsstudio.first_pilot_device_doctor --role pi
~~~

The doctor does **not** create directories, install/download models or voices, execute audio, render video, read credentials, open SSH, authenticate Google, upload anything, or change files. It checks local filesystem/ownership/free space, Python version, source revision and clean Git status, role OS/CPU (and actual Raspberry Pi hardware for the Pi), local offline synthetic review gate and, for Mac only, required media executables, installed Arabic macOS voice and available SSH client. It prints fixed-safe check codes and brief suggested fixes without leaking your file paths or voice list. It will **not** show passwords or OAuth state.

Both machines must have source available in a local **clean Git checkout** and a Python environment that can import KidsStudio; Python **3.11 or newer** is needed. A doctor cannot fix missing installation of the software used to invoke it. To set up a venv yourself, use an already installed Python 3.11+ and follow the repo's approved installation procedure; no command above performs an install. Pi does **not** require Pillow or Apple \`say\`: it is the receiver/uploader, not the renderer.

### Private directories (user-controlled preparation, not performed by doctor)

The probes require these **existing** owner-private directories outside Git:

Mac:
~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/ready" "$HOME/kidsstudio-private/qualification"
chmod 700 "$HOME/kidsstudio-private/ready" "$HOME/kidsstudio-private/qualification"
~~~

Pi:
~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/inbox"
chmod 700 "$HOME/kidsstudio-private/inbox"
~~~

The directories should be owned by the user who runs the corresponding process. If an existing directory or ancestor is a symlink, move to a trusted non-symlink private path instead of following it. The default report requires at least 2 GiB free but actual video staging and uploads may require more. The Pi's credential and upload-journal directories remain separate, and are **not inspected** by this command.

### Report meanings and safe next steps

- \`FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY\`, exit **0**: the local *offline* gates passed for this role. **Does not mean the actual media rendered, the voice is correct, Mac and Pi source SHA match, SSH works, or PRIVATE YouTube upload is qualified**.
- \`FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_BLOCKED\`, exit **1**: read the safe \`blockers[].code\` and \`suggested_fix\`. Common failures are \`artifact_root_exists\`, \`artifact_root_private\`, \`free_space_threshold\`, \`installed_arabic_voice_missing_or_invalid\`, \`source_commit_sha40\`, and \`source_checkout_clean\`.
- \`FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_ERROR\`, exit **2**: local inspection failed; no raw filesystem exception or credential path is printed.

**Source revision trap fixed in Batch 61:** the older \`host_qualification\` displayed \`source_commit\` and \`source_checkout_clean\` but could still say \`SUPERVISED_TESTS_READY\` even with a modified/unavailable Git checkout. Both fields now **gate** readiness. On each device compare the actual \`source_commit\` in the two reports manually; even two \`READY\` results are not proof they match. If Mac and Pi revisions differ, stop before SSH and bring both to the same reviewed commit. Do not force a \`git reset --hard\` or delete your local edits to make a test green.

If an Arabic \`say\` voice is missing, install or select it in macOS Settings **yourself**, then run the doctor again. No voice download is initiated by the doctor. To inspect available Arabic voices privately on your Mac you may run \`say -v '?'\` in its Terminal; never paste the whole voice list if it contains identifying local details. A plain installed voice is not evidence of good child-friendly Arabic pronunciation.

## Once both reports are ready

1. On the Mac, run \`bash scripts/run_mac_colors_pilot.sh\` *under your supervision*. It generates the original six-scene 24s video locally, validates voice energy, H.264/AAC decode, SHA and a private technical sidecar; it never uploads. It has **not yet been executed on the owner's physical Mac**.
2. With the Pi SSH key/host fingerprint verified **from the actual Pi console**, preview \`python3 -m kidsstudio.technical_mac_pi_handoff --evidence-name ACTUAL.evidence.json --pi-host VERIFIED_PI --pi-user PI_USER\`. No SSH call occurs until you explicitly repeat with \`--execute-transfer\`.
3. Independently verify the SHA on Pi, then follow \`PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md\` for a **separate owner-authorized Google OAuth PRIVATE-only upload**. The uploader and OAuth path are not yet live tested.
4. **After the video is PRIVATE in YouTube Studio**, watch/listen to the whole episode, record notes or request a new version. Keep public release disabled until a later, separate affirmative decision.

**Still NOT_RUN:** a real Mac Arabic TTS render/review, real Pi SSH/throughput/receipt, initial channel OAuth enrollment, real PRIVATE YouTube upload and owner review. GitHub CI never substitutes for those.

## Batch 62 — offline original WAV route when Apple Arabic say is absent

The one-command Mac launcher now has **two explicit, mutually exclusive original-audio sources**. Its default remains an already-installed Arabic macOS `say` voice. If the Mac has no suitable local voice, prepare your **own original** spoken-Arabic WAV, 24.00 seconds long, uncompressed PCM **16-bit mono**, 16–96 kHz, with six 4-second speech beats matching the pictured colors. The source must be in an existing private mode-0700 directory outside Git, with the WAV file mode 0600. Do not upload the WAV or private paths to GitHub.

From the Mac's trusted KidsStudio checkout, for a WAV actually named `colors_ar_01.wav`:

```bash
umask 077
# Prepare your original narration separately. This does NOT synthesize speech.
export KIDSSTUDIO_NARRATION_ROOT="$HOME/kidsstudio-private/narration"
export KIDSSTUDIO_NARRATION_NAME="colors_ar_01.wav"
export KIDSSTUDIO_NARRATION_SHA256="$(shasum -a 256 "$KIDSSTUDIO_NARRATION_ROOT/$KIDSSTUDIO_NARRATION_NAME" | awk '{print $1}')"
python3 -m kidsstudio.first_pilot_device_doctor --role mac \
  --voice-mode supplied_wav \
  --narration-root "$KIDSSTUDIO_NARRATION_ROOT" \
  --narration-name "$KIDSSTUDIO_NARRATION_NAME" \
  --narration-sha256 "$KIDSSTUDIO_NARRATION_SHA256"
# ONLY AFTER the offline doctor reports READY:
bash scripts/run_mac_colors_pilot.sh
```

The launcher itself now routes the *same* three environment values to the non-render preflight, the no-write preview and the real render, and blocks incomplete inputs or `KIDSSTUDIO_MAC_VOICE` mixed with WAV mode. The preflight checks the private file mode/owner, file name, SHA256, exact six-beat 24s mono PCM format and at least 60ms of audible signal per beat. It **does not require Apple say** when the supplied-WAV mode is explicitly selected, and never silently falls back between sources. The production code independently rechecks file SHA/format before muxing; wrong/changed bytes abort.

The energy check only detects missing/near-silent beats, not spoken Arabic, natural pronunciation, intelligibility, age-appropriate teaching, or music rights. Human review still happens after the PRIVATE YouTube draft. The script does not contact Pi or YouTube. A hosted macOS CI test runs the actual shell with an **FFmpeg synthetic sine tone WAV**, not a real Arabic recording, and `KIDSSTUDIO_SKIP_OPEN=1` disables GUI launch only in that controlled test; it never claims real owner review.

## Batch 63 — after PRIVATE YouTube upload, capture review for the exact version

After the Pi uploader actually returns `PRIVATE_UPLOAD_CONFIRMED`, the owner checks the current video in YouTube Studio and reads its **exact video ID**, then follows [PI_PRIVATE_DRAFT_OWNER_REVIEW.md](PI_PRIVATE_DRAFT_OWNER_REVIEW.md) for the no-network Pi verification/notes CLI. The journal must include the corresponding original MP4 filename, source SHA256 and episode ID; current privacy is **not** independently rechecked by this offline tool. Notes are saved in separate owner-private 0600 files, never made public, never treated as permission to publish. If a draft needs revision, produce a new file and new PRIVATE upload/review, not overwrite a prior version. Actual operator execution is still NOT_RUN.

## Batch 64 — inspect the local PRIVATE draft review queue on Pi

Once upload journals and review directories exist, run `python3 -m kidsstudio.pi_private_draft_inbox` on the Pi for a text overview of confirmed PRIVATE drafts awaiting owner review, versions needing revision, versions accepted PRIVATE-only, ambiguous incomplete uploads and invalid local evidence. This is **read-only** and does not require OAuth or Internet. For JSON use `--format json`; use `--show-video-ids` only when you explicitly need the private ID in the local report. It does not read your notes into the summary or guarantee current remote privacy. See [PI_PRIVATE_DRAFT_OWNER_REVIEW.md](PI_PRIVATE_DRAFT_OWNER_REVIEW.md).

## Batch 65 — optional authenticated phone UI for post-PRIVATE notes

When the Pi directories and source checkout have passed the earlier checks, run `python3 -m kidsstudio.pi_private_draft_web` on the Pi, read its **session-only** terminal password, and access `http://127.0.0.1:8844/` on the Pi. For a Mac/phone browser, use a **verified SSH client with local port forwarding** to Pi localhost rather than exposing an HTTP service on the LAN. The Arabic mobile-friendly page lists confirmed PRIVATE drafts and permits writing a SHA-bound `REVISION_REQUIRED` or `ACCEPTED_PRIVATE` note; the latter requires independent full-video and Arabic listening assertions. It does not stream uploaded videos, verify Google's present visibility, edit remote videos, or authorize publication. Full operator device testing remains NOT_RUN. See [PI_PRIVATE_DRAFT_OWNER_REVIEW.md](PI_PRIVATE_DRAFT_OWNER_REVIEW.md).
