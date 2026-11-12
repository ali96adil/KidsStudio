# Mac MVP pilot: one command for original Godot visuals + Arabic narration

**Status:** local-only opt-in composition, CI-tested. NOT executed on the user's Mac, and not yet an approved episode.

This pilot closes a practical gap between the existing **silent Godot 1280×720 H.264 renderer** and the Pi's **final-delivery profile requiring AAC 48 kHz stereo sound**. No cloud TTS, model inference, network call, Mac→Pi transfer or YouTube upload is executed by either command.

### First episode content

`examples/colors_ar_01_pilot_cues.json` provides an original **24-second** Arabic colors concept with six four-second speech/visual beats, matching the current `first_colors_episode` pilot timing and narration. It is **a draft storyboard**, not an actual audio recording or an owner-qualified episode. Never assume the fixed beat length suits a real narrator: retime storyboard, scene and narration together. Never claim educational correctness from the voice alone.

### Required private sources (on the real Mac)

1. A locally exported, original, reviewed **KidsStudio Godot project** with `export_report.json` and `scene_spec.json` and matching source-hash report. The existing `godot_render.py` checks project integrity and rejects tampering at execution. Its underlying scene FPS must be supported and duration 4–600 seconds.
2. A separately recorded or locally generated **original narration WAV**, uncompressed 16-bit PCM, mono or stereo, 16–96 kHz, in a user-owned private directory. The narration must fit the scene duration within **750ms**. A Mac microphone recording or a local TTS voice may be used after review; no TTS voice is downloaded or invoked by this code.
3. A pre-existing local **0700** output directory outside Git, and source audio file mode **0600**. All media and original art remain outside the repository. Run from the intended local Python environment, with local `godot`, `ffmpeg` and `ffprobe` available.

If you have an original rights-cleared local `narration.aiff`, convert it separately with FFmpeg and check quality and duration before continuing:

~~~bash
ffmpeg -nostdin -i narration.aiff -c:a pcm_s16le -ar 48000 -ac 1 narration.wav
chmod 600 narration.wav
~~~

This does not guarantee suitable pacing or pronunciation: listen to it and adjust the scene to match. Avoid automatic truncation and do not use copyrighted audio or unlicensed voices.

### Dry preview (no rendering, no output file)

On the Mac, for an export project in a private directory:

~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/ready"
chmod 700 "$HOME/kidsstudio-private/ready"
# Verify the narration WAV is in a private 0700 directory and chmod 600 it.
shasum -a 256 "$HOME/kidsstudio-private/narration/colors_ar_01.wav"

python -m kidsstudio.mac_episode_pilot \
  --godot-project "$HOME/kidsstudio-private/exports/colors_ar_01" \
  --narration-root "$HOME/kidsstudio-private/narration" \
  --narration-name colors_ar_01.wav \
  --narration-sha256 TRUSTED_NARRATION_SHA256 \
  --output-root "$HOME/kidsstudio-private/ready" \
  --output-name colors_ar_01.mp4
~~~

Read-only result: `MAC_PILOT_READY_TO_RENDER`. It validates private narration, SHA, WAV format and duration, output name and scene metadata. It does **not** run Godot, ffmpeg, paid inference, SSH or YouTube.

### Explicit local render / mux (with supervised permission)

Repeat the exact same command **plus `--execute-render`**. This then:

- Uses the established `render_godot_project` integrity checks and Godot/FFmpeg encoder to render a **new** nonoverwritten `colors_ar_01-godot-render/character_preview.mp4` under the output root.
- SHA-verifies the silent MP4 and user-supplied audio, enforces H.264 yuv420p 1280×720 and supported FPS, and runs local FFmpeg with `-c:v copy`, `-c:a aac`, `-ar 48000`, `-ac 2` and a 192 kbit/s audio target to write a nonoverwritten temporary MP4.
- Reprobes the complete output for H.264/AAC, expected duration and stereo 48 kHz audio, rehashes the inputs, then atomically publishes a new owner-only output file `colors_ar_01.mp4` with mode 0600. It never overwrites an existing master.
- Returns `MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED` and the new MP4 SHA256 and bytes. This is **not** artistic/educational approval and not permission to upload.

On failure, existing input files are left unchanged and the output is not silently replaced. A partial render directory may remain for inspection; use a different versioned output name for a deliberate retry.

### Next operator-supervised steps

1. Open and watch the entire Mac output. Verify the **spoken color matches the visible color**, natural Arabic pronunciation and accent, voice level, no clipping, timing, captions where applicable, character identity, licensed assets, and that the actual resulting video is appropriate for children. The checks above cannot evaluate these.
2. From the Mac and Pi source checkouts of the **same reviewed commit**, run host qualification and secure transfer only after local SSH host-key pairing: [MAC_PI_TRANSFER_PILOT.md](MAC_PI_TRANSFER_PILOT.md). Independently compare SHA on Pi after receiving.
3. With a separately owner-authorized and tested YouTube OAuth client, upload as **PRIVATE** using [PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md](PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md). Watch and review the private draft; **never auto-publish**.

**Reality check:** CI may execute a synthetic FFmpeg roundtrip and mock the one-command Godot call. It is not proof of a real original Arabic narration, generated color visuals, or that the user's physical Mac/Pi passed.
