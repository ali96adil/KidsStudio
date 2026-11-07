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
for program in ffmpeg ffprobe say shasum; do
  if ! command -v "$program" >/dev/null 2>&1; then
    echo "MAC_COLORS_BLOCKED: Missing local executable: $program"
    exit 2
  fi
done

OUTPUT_DIR="$HOME/kidsstudio-private/ready"
mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"

# Optional explicit choice among ALREADY INSTALLED Arabic macOS voices.
# Arrays keep the name literal; invalid/uninstalled names fail closed.
VOICE_ARGS=()
if [[ -n "${KIDSSTUDIO_MAC_VOICE:-}" ]]; then
  VOICE_ARGS=(--mac-voice "$KIDSSTUDIO_MAC_VOICE")
fi

# Check native Arabic voice, full Git checkout and private host BEFORE encoding.
# Does not synthesize audio, write a video or use the network.
echo "Gate 0/4: check installed Arabic voice, Git source and private Mac readiness"
"$PYTHON" -m kidsstudio.mac_colors_preflight \
  --artifact-root "$OUTPUT_DIR" "${VOICE_ARGS[@]}"

# Include random per-invocation suffix so even same-second retries cannot
# silently reuse a failed staging directory. All output remains non-overwriting.
BASENAME="colors_ar_01_test_$(date '+%Y%m%d_%H%M%S')_${RANDOM}${RANDOM}.mp4"
TARGET="$OUTPUT_DIR/$BASENAME"

echo "Source checkout: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Step 1/4: local preflight (no render, no network)"
set +e
PREVIEW="$("$PYTHON" -m kidsstudio.first_colors_episode \
  --output-root "$OUTPUT_DIR" --output-name "$BASENAME" 2>&1)"
PREVIEW_EXIT=$?
set -e
printf '%s\n' "$PREVIEW"
if [[ "$PREVIEW_EXIT" -ne 1 ]] || [[ "$PREVIEW" != *COLORS_EPISODE_PREVIEW_ONLY* ]]; then
  echo "MAC_COLORS_BLOCKED: preflight did not pass."
  exit 2
fi

echo "Step 2/4: owner-invoked local render and macOS Arabic voice"
"$PYTHON" -m kidsstudio.first_colors_episode \
  --output-root "$OUTPUT_DIR" \
  --output-name "$BASENAME" \
  --voice-mode macos "${VOICE_ARGS[@]}" --execute

if [[ ! -s "$TARGET" ]]; then
  echo "MAC_COLORS_BLOCKED: finished video missing."
  exit 2
fi
chmod 600 "$TARGET"
MOVIE_SHA="$(shasum -a 256 "$TARGET" | awk '{print $1}')"
echo "Step 3/4: inspect actual MP4 faststart, H264/AAC and decoded samples"
"$PYTHON" -m kidsstudio.mp4_playback_preflight \
  --root "$OUTPUT_DIR" \
  --relative-path "$BASENAME" \
  --expected-sha256 "$MOVIE_SHA"
echo "Local technical compatibility preflight passed (not an owner review)."
echo "Step 4/4: persist immutable private evidence (owner review pending)"
EVIDENCE_DIR="$HOME/kidsstudio-private/qualification"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"
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
echo "Listen and watch the ENTIRE clip before any Pi transfer or upload."
# Open only the local result for the owner's immediate visual/audio review.
open "$TARGET"
