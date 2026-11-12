# G4 Mac → Pi private video transfer — supervised pilot

> **Current default — PRIVATE-first workflow (Batch 60):** For the colors pilot, use `kidsstudio.technical_mac_pi_handoff`. It verifies the local Mac technical evidence and exact SHA before staging a PRIVATE draft on the Pi; human review is **after** YouTube PRIVATE upload. The older `reviewed_mac_pi_handoff` below remains an optional stricter manual-before-transfer route, **not a mandatory prerequisite for PRIVATE staging**. Neither command authorizes public publication.

**Status:** implemented as two opt-in Python commands using authenticated SSH. The code is covered by isolated mock tests; no SSH connection to the user's Pi has been performed.

The Mac renders the MP4 locally. Only the completed MP4 is sent to Pi using an already configured SSH key. The Pi receiver is fixed to its local home directory `~/kidsstudio-private/inbox` and atomically installs the file *only after* SHA-256 and byte count match. No SQLite queue, API key, Pi upload service, ComfyUI, YouTube or public publication action is triggered.

## 1. Pi preparation (supervised)

On the Pi itself, install the exact reviewed KidsStudio source revision in a Python 3.11+ environment (use a private venv, not root); ensure both devices have the same reviewed Git commit. The SSH user must be the same unprivileged user running the Pi receiver. Create the private fixed inbox:

~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/inbox"
chmod 700 "$HOME/kidsstudio-private/inbox"
python3 -m kidsstudio.pi_transfer_receive --help
~~~

The last command only checks the receiver module is available and does **not** read stdin or create files. If the package is installed in a venv, use its absolute Python binary path later with `--remote-python`. Do not enable a new listening service; the receiver is called over SSH by the already-running OpenSSH server.

SSH key authentication and host-key pinning must be configured **independently**. Validate the Pi's SSH host fingerprint from the actual Pi console, and register the trusted host key in Mac's known_hosts. The sender uses `StrictHostKeyChecking=yes` and `BatchMode=yes`; it will not silently accept unknown host keys or ask for a password. Only use the LAN address/name of the Pi you verified.

## 2. Mac preparation

From the matching trusted KidsStudio checkout/venv on the Mac, copy the **already completed, rights-cleared original test** video into an owner-only directory outside Git. File mode must be 0600 and parent directory 0700:

~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/ready"
chmod 700 "$HOME/kidsstudio-private/ready"
chmod 600 "$HOME/kidsstudio-private/ready/colors_ar_001.mp4"
shasum -a 256 "$HOME/kidsstudio-private/ready/colors_ar_001.mp4"
~~~

Use the 64-character SHA from that file. Preview the transfer with **no SSH call** by omitting `--execute-transfer`:

~~~bash
python3 -m kidsstudio.mac_to_pi_transfer \
  --video-root "$HOME/kidsstudio-private/ready" \
  --relative-path colors_ar_001.mp4 \
  --expected-sha256 VERIFIED_SHA256 \
  --destination-name colors_ar_001.mp4 \
  --pi-host YOUR_VERIFIED_PI_LAN_NAME_OR_IPV4 --pi-user YOUR_PI_SSH_USER
~~~

It must report `MAC_PI_TRANSFER_PREVIEW_ONLY` and `ssh_connection_performed: false`. Then, only under supervision, run the **same** command with `--execute-transfer`. That second invocation will connect over SSH, stream the complete video, and ask the Pi to validate its SHA and atomically create a mode-0600 file. When the receiver replies with an exact matching private receipt and Mac source checksum still matches, the Mac reports `MAC_PI_PRIVATE_TRANSFER_VERIFIED`. All stdout is metadata, not media bytes.

If using a Pi venv, specify e.g. `--remote-python /home/YOUR_PI_SSH_USER/KidsStudio/.venv/bin/python3`. Only a reviewed absolute executable path or `python3` is accepted; remote script arguments are shell-quoted and values are strongly validated.

## 3. Independently recheck on Pi, then hold for private upload

On Pi after the Mac reports success:

~~~bash
python3 -m kidsstudio.transfer_verify \
  --root "$HOME/kidsstudio-private/inbox" \
  --relative-path colors_ar_001.mp4 \
  --expected-sha256 VERIFIED_SHA256
~~~

Require `VERIFIED`. Then separately run the private-only YouTube upload preflight from the Pi pilot runbook. **The transfer command does not upload**. The upload itself remains an opt-in foreground action, requiring owner-confirmed audience designation and a manually established OAuth credential.

## Fail-closed behavior and limitations

- No overwrite: a destination with the same name and different digest is rejected. Retrying the *identical* media still re-sends and SHA-checks the bytes, then returns `PI_INBOX_ALREADY_VERIFIED` without replacing the existing file.
- SSH failure, interruption, mismatched SHA, extra bytes, premature EOF, unsafe paths, permissive file/directory modes or unexpected receiver output block success. Temporary Pi files are cleaned on ordinary exceptions; after sudden power loss a hidden `.incoming-*` file may remain and should be reviewed manually before cleanup.
- A valid SSH host key proves you connected to the previously trusted SSH endpoint, not that the media was visually approved or that the host was immune to compromise. These filesystem checks are not an OS sandbox against simultaneous attacks by a process with write access to the same private directory.
- No remote directories are implicitly created. The server needs no incoming TCP port beyond its existing SSH port. No retries happen in the background; reruns are explicit and do not silently alter a completed destination.
- This is a **foreground MVP pilot**: the Mac must stay running while video is streamed, but can be shut down once Pi receipt + independent checksum are verified. The Pi can later upload independently.
- Current test status is MOCK/CI ONLY. A real Mac→Pi LAN test, power interruption test, transfer timing measurement and OAuth upload remain **NOT_RUN** until the operator actually executes them.

## Batch 58 — reviewed colors pilot handoff (recommended path)

For the **first original Arabic colors pilot**, use `kidsstudio.reviewed_mac_pi_handoff` instead of directly calling the generic low-level transfer utility. The original video must have (1) a validated private technical evidence file saved by the real Mac render, (2) at least one `ACCEPTED_PRIVATE` review note for the **exact same SHA-256, source commit and file bytes**, including explicit owner assertions that the *whole video and Arabic speech* were reviewed, and (3) **no** `REVISION_REQUIRED` note for that version. A previous acceptance never cancels a revision request: fix the issue and produce/review a **new** episode file. If evidence is missing, edited, mismatched, symlinked, publicly readable or contradictory, the handoff is blocked **before SSH**.

After the real owner Mac render and explicit local guided review, the owner selects the exact evidence filename from `python3 -m kidsstudio.mac_pilot_review_shortcut list`. To preview the handoff with **NO SSH connection**, run on the Mac:

```bash
python3 -m kidsstudio.reviewed_mac_pi_handoff \
  --evidence-name ACTUAL_GENERATED_NAME.evidence.json \
  --pi-host YOUR_VERIFIED_PI_LAN_NAME_OR_IPV4 \
  --pi-user YOUR_PI_SSH_USER
```

A successful preview returns `MAC_PI_REVIEWED_TRANSFER_PREVIEW_ONLY`, the source SHA/byte count, and `ssh_connection_performed: false`. This only validates an **operator-asserted** local acceptance and prepares the existing sender: it does **not** authenticate the operator's identity, contact the Pi or upload anything. Only **after** independently confirming Pi host key, SSH identity, same trusted KidsStudio commit, storage/inbox and the exact selected video, the owner may explicitly repeat the same invocation with `--execute-transfer`. That deliberately calls the existing host-key-pinned, foreground SSH sender and verifies Pi receiver receipt. It is **not** executed by the Mac render launcher, guided review, CI or any background agent. The successful *real* result would be `MAC_PI_REVIEWED_PRIVATE_TRANSFER_VERIFIED`; local CI mock receipt tests do **not** establish that physical result.

After real SSH, independently run the Pi-side `kidsstudio.transfer_verify` SHA command before considering a separately authorized **PRIVATE** YouTube upload. No review record, transfer plan or Pi inbox receipt gives permission to upload or publish, and a local acceptance can be asserted by an unauthenticated filesystem user: this workflow is procedural gating, **not cryptographic owner identity verification**. The generic `mac_to_pi_transfer` remains a lower-level utility, but bypasses the review-note gate, so do not use it for the supervised colors pilot.

## Batch 60 — correct PRIVATE-first technical staging (current recommended route)

Owner's intended order is **Mac render → automated technical QA → Pi staging → separately authorized YouTube PRIVATE upload → owner watches PRIVATE draft → owner notes/revises/decides on a later public release**. Do not force manual Mac approval before the PRIVATE draft is available.

The Mac launcher records an exact 0600 technical sidecar after a real local FFmpeg/ffprobe playback gate and clean source qualification. The new `kidsstudio.technical_mac_pi_handoff` verifies the selected private sidecar's source revision, host role/OS, 3 video and 2 audio decoded samples, faststart, owner-review-pending flags, exact SHA256 and file size. **No `ACCEPTED_PRIVATE` human review note is required**, because no public release is happening. It does not call YouTube or schedule a release.

On the real Mac, with the verified Pi SSH host key and user correctly configured, preview the handoff **without any SSH**:

```bash
python3 -m kidsstudio.technical_mac_pi_handoff \
  --evidence-name ACTUAL_GENERATED_NAME.evidence.json \
  --pi-host YOUR_VERIFIED_PI_LAN_NAME_OR_IPV4 \
  --pi-user YOUR_PI_SSH_USER
```

Only when the user explicitly decides to transfer the technically checked PRIVATE source, add `--execute-transfer` to that same command; it uses existing authenticated SSH/strict host key/SHA-checked atomic Pi receiver. **Sending to Pi is not an upload to YouTube.** On Pi, independently verify exact SHA and, after separate OAuth authorization/consent, use `pi_youtube_private_upload` to upload **PRIVATE only**. The owner then reviews the PRIVATE YouTube draft, records notes and may request revision. A separate explicit publication decision is always required.

No actual Pi or Google credentials are exercised by the CI test. The earlier `reviewed_mac_pi_handoff` remains supported for users who personally choose to inspect the local clip *before* transferring; it must not be represented as the only path.
