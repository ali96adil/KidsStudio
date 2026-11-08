#!/usr/bin/env bash
# One explicit foreground local Mac invocation: original colors demo only.
# No install, no network/SSH, no YouTube upload or publication.
set -euo pipefail
umask 077

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "MAC_COLORS_BLOCKED: This launcher requires the actual Mac."
  exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO"

PYTHON="${KIDSSTUDIO_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "MAC_COLORS_BLOCKED: Python was not found. Select your venv Python."
  exit 2
fi
if ! "$PYTHON" -c 'import sys; import PIL; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "MAC_COLORS_BLOCKED: Python 3.11+ with Pillow is required."
  exit 2
fi
# A supplied original WAV is an explicit alternative if macOS has no
# installed Arabic say voice. Never silently fall back or use stale inputs.
NARRATION_ENABLED=0
if [[ -n "${KIDSSTUDIO_NARRATION_ROOT+x}" || -n "${KIDSSTUDIO_NARRATION_NAME+x}" || -n "${KIDSSTUDIO_NARRATION_SHA256+x}" ]]; then
  if [[ -z "${KIDSSTUDIO_NARRATION_ROOT:-}" || -z "${KIDSSTUDIO_NARRATION_NAME:-}" || -z "${KIDSSTUDIO_NARRATION_SHA256:-}" ]]; then
    echo "MAC_COLORS_BLOCKED: WAV mode needs narration root, name and SHA256 together."
    exit 2
  fi
  if [[ -n "${KIDSSTUDIO_MAC_VOICE:-}" ]]; then
    echo "MAC_COLORS_BLOCKED: Choose one voice mode; cannot mix native voice and WAV."
    exit 2
  fi
  NARRATION_ENABLED=1
fi

for program in ffmpeg ffprobe shasum git; do
  if ! command -v "$program" >/dev/null 2>&1; then
    echo "MAC_COLORS_BLOCKED: Missing local executable: $program"
    exit 2
  fi
done
if [[ "$NARRATION_ENABLED" -eq 0 ]] && ! command -v say >/dev/null 2>&1; then
  echo "MAC_COLORS_BLOCKED: Native mode requires locally installed macOS say."
  exit 2
fi

OUTPUT_DIR="$HOME/kidsstudio-private/ready"
EVIDENCE_DIR="$HOME/kidsstudio-private/qualification"
"$PYTHON" -m kidsstudio.mac_pilot_evidence prepare-launcher-dirs --home "$HOME"

# Separate calls rather than arrays keep this compatible with Bash 3.2.
# Neither preflight nor preview launches TTS or renders any media.
echo "Gate 0/4: verify clean Git, private output, tools and selected original voice source"
if [[ "$NARRATION_ENABLED" -eq 1 ]]; then
  "$PYTHON" -m kidsstudio.mac_colors_preflight \
    --artifact-root "$OUTPUT_DIR" --voice-mode supplied_wav \
    --narration-root "$KIDSSTUDIO_NARRATION_ROOT" \
    --narration-name "$KIDSSTUDIO_NARRATION_NAME" \
    --narration-sha256 "$KIDSSTUDIO_NARRATION_SHA256"
elif [[ -n "${KIDSSTUDIO_MAC_VOICE:-}" ]]; then
  "$PYTHON" -m kidsstudio.mac_colors_preflight \
    --artifact-root "$OUTPUT_DIR" --voice-mode macos --mac-voice "$KIDSSTUDIO_MAC_VOICE"
else
  "$PYTHON" -m kidsstudio.mac_colors_preflight \
    --artifact-root "$OUTPUT_DIR" --voice-mode macos
fi

# Include random per-invocation suffix so even same-second retries cannot
# silently reuse a failed staging directory. All output remains non-overwriting.
BASENAME="colors_ar_01_test_$(date '+%Y%m%d_%H%M%S')_${RANDOM}${RANDOM}.mp4"
TARGET="$OUTPUT_DIR/$BASENAME"

echo "Source checkout: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Step 1/4: local preflight (no render, no network)"
set +e
if [[ "$NARRATION_ENABLED" -eq 1 ]]; then
  PREVIEW="$("$PYTHON" -m kidsstudio.first_colors_episode \
    --output-root "$OUTPUT_DIR" --output-name "$BASENAME" \
    --voice-mode supplied_wav \
    --narration-root "$KIDSSTUDIO_NARRATION_ROOT" \
    --narration-name "$KIDSSTUDIO_NARRATION_NAME" \
    --narration-sha256 "$KIDSSTUDIO_NARRATION_SHA256" 2>&1)"
else
  PREVIEW="$("$PYTHON" -m kidsstudio.first_colors_episode \
    --output-root "$OUTPUT_DIR" --output-name "$BASENAME" \
    --voice-mode macos 2>&1)"
fi
PREVIEW_EXIT=$?
set -e
printf '%s\n' "$PREVIEW"
if [[ "$PREVIEW_EXIT" -ne 1 ]] || [[ "$PREVIEW" != *COLORS_EPISODE_PREVIEW_ONLY* ]]; then
  echo "MAC_COLORS_BLOCKED: preflight did not pass."
  exit 2
fi

echo "Step 2/4: owner-invoked local render with explicitly selected original narration"
if [[ "$NARRATION_ENABLED" -eq 1 ]]; then
  "$PYTHON" -m kidsstudio.first_colors_episode \
    --output-root "$OUTPUT_DIR" \
    --output-name "$BASENAME" \
    --voice-mode supplied_wav \
    --narration-root "$KIDSSTUDIO_NARRATION_ROOT" \
    --narration-name "$KIDSSTUDIO_NARRATION_NAME" \
    --narration-sha256 "$KIDSSTUDIO_NARRATION_SHA256" --execute
elif [[ -n "${KIDSSTUDIO_MAC_VOICE:-}" ]]; then
  "$PYTHON" -m kidsstudio.first_colors_episode \
    --output-root "$OUTPUT_DIR" \
    --output-name "$BASENAME" \
    --voice-mode macos --mac-voice "$KIDSSTUDIO_MAC_VOICE" --execute
else
  "$PYTHON" -m kidsstudio.first_colors_episode \
    --output-root "$OUTPUT_DIR" \
    --output-name "$BASENAME" \
    --voice-mode macos --execute
fi

if [[ ! -s "$TARGET" ]]; then
  echo "MAC_COLORS_BLOCKED: finished video missing."
  exit 2
fi
MOVIE_SHA="$(shasum -a 256 "$TARGET" | awk '{print $1}')"
echo "Step 3/4: inspect actual MP4 faststart, H264/AAC and decoded samples"
"$PYTHON" -m kidsstudio.mp4_playback_preflight \
  --root "$OUTPUT_DIR" \
  --relative-path "$BASENAME" \
  --expected-sha256 "$MOVIE_SHA"
echo "Local technical compatibility preflight passed (not an owner review)."
echo "Step 4/4: persist immutable private evidence (owner review pending)"
EVIDENCE_NAME="${BASENAME%.mp4}.evidence.json"
"$PYTHON" -m kidsstudio.mac_pilot_evidence collect \
  --episode-id colors_ar_01 \
  --video-root "$OUTPUT_DIR" \
  --video-name "$BASENAME" \
  --expected-sha256 "$MOVIE_SHA" \
  --evidence-root "$EVIDENCE_DIR" \
  --evidence-name "$EVIDENCE_NAME"
echo "Video (private, NOT uploaded): $TARGET"
echo "Final MP4 SHA256: $MOVIE_SHA"
echo "Private technical evidence (review pending): $EVIDENCE_DIR/$EVIDENCE_NAME"
echo "KidsStudio PRIVATE-first flow: technical QA -> private Pi staging -> separately authorized PRIVATE YouTube draft -> YOUR review."
printf 'QA-only Pi transfer PREVIEW (no SSH): %s -m kidsstudio.technical_mac_pi_handoff --evidence-name %q --pi-host YOUR_VERIFIED_PI_HOST --pi-user YOUR_PI_SSH_USER\n' "$PYTHON" "$EVIDENCE_NAME"
echo "The real SSH transfer is a separate explicit --execute-transfer action after Pi host-key setup."
echo "The Pi upload is a separate explicit PRIVATE-only OAuth action; no upload or publication is started here."
echo "AFTER the PRIVATE YouTube draft, personally review the video and leave notes."
echo "Optional local review tool: $PYTHON -m kidsstudio.mac_pilot_review_shortcut guided"
echo "Neither a local preview nor a private upload is permission for PUBLIC release."
# Normally open the local file for optional viewing. Hosted CI may choose
# KIDSSTUDIO_SKIP_OPEN=1, never evidence that a real person viewed it.
if [[ "${KIDSSTUDIO_SKIP_OPEN:-}" == "1" ]]; then
  echo "Local open skipped explicitly (CI/no GUI; human content review NOT completed)."
else
  open "$TARGET"
fi
