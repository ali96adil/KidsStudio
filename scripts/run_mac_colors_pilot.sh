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

# Unique filename: no deletion/overwriting of earlier accepted previews.
BASENAME="colors_ar_01_test_$(date '+%Y%m%d_%H%M%S').mp4"
TARGET="$OUTPUT_DIR/$BASENAME"

echo "Source checkout: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Step 1/2: local preflight (no render, no network)"
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

echo "Step 2/2: owner-invoked local render and macOS Arabic voice"
"$PYTHON" -m kidsstudio.first_colors_episode \
  --output-root "$OUTPUT_DIR" \
  --output-name "$BASENAME" \
  --voice-mode macos --execute

if [[ ! -s "$TARGET" ]]; then
  echo "MAC_COLORS_BLOCKED: finished video missing."
  exit 2
fi
chmod 600 "$TARGET"
echo "Video (private, NOT uploaded): $TARGET"
shasum -a 256 "$TARGET"
echo "Listen and watch the ENTIRE clip before any Pi transfer or upload."
# Open only the local result for the owner's immediate visual/audio review.
open "$TARGET"
