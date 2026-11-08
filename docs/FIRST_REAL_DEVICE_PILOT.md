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
