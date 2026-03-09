#!/bin/bash
# extract_keyframes.sh — Extract keyframes + audio from video via ffmpeg.
# Usage: ./extract_keyframes.sh <video_path> <output_dir>
# Output: keyframe_001.jpg ... keyframe_005.jpg + audio.wav in output_dir
#         Prints JSON with extracted file paths to stdout.

set -euo pipefail

if [ $# -lt 2 ]; then
    echo '{"error": "Usage: extract_keyframes.sh <video_path> <output_dir>"}' >&2
    exit 1
fi

VIDEO="$1"
OUTDIR="$2"
FFMPEG="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"

if [ ! -f "$VIDEO" ]; then
    echo "{\"error\": \"Video file not found: $VIDEO\"}" >&2
    exit 1
fi

if ! command -v "$FFMPEG" &>/dev/null; then
    echo '{"error": "ffmpeg not found"}' >&2
    exit 1
fi

mkdir -p "$OUTDIR"

# Extract up to 5 keyframes at even intervals
# Try I-frame selection first, fall back to scene-change or uniform sampling
"$FFMPEG" -y -i "$VIDEO" \
    -vf "select=eq(pict_type\\,I)" -vsync vfill \
    -frames:v 5 -q:v 2 \
    "$OUTDIR/keyframe_%03d.jpg" 2>/dev/null || true

# If no keyframes extracted (e.g. HEVC without I-frame markers), sample uniformly
if ! ls "$OUTDIR"/keyframe_*.jpg &>/dev/null; then
    "$FFMPEG" -y -i "$VIDEO" \
        -vf "fps=1/3" -frames:v 5 -q:v 2 \
        "$OUTDIR/keyframe_%03d.jpg" 2>/dev/null || true
fi

# Extract audio as WAV (16kHz mono for transcription)
AUDIO_OUT="$OUTDIR/audio.wav"
"$FFMPEG" -y -i "$VIDEO" \
    -vn -acodec pcm_s16le -ar 16000 -ac 1 \
    "$AUDIO_OUT" 2>/dev/null || true

# Get video duration (macOS grep doesn't have -P, use sed instead)
DURATION=$(("$FFMPEG" -i "$VIDEO" 2>&1 || true) | sed -n 's/.*Duration: \([0-9:.]*\).*/\1/p' | head -1 | tr -d '\n')
DURATION="${DURATION:-unknown}"

# Build JSON output with file listing
FRAMES="["
first=true
for f in "$OUTDIR"/keyframe_*.jpg; do
    [ -f "$f" ] || continue
    if [ "$first" = true ]; then
        first=false
    else
        FRAMES+=","
    fi
    FRAMES+="\"$f\""
done
FRAMES+="]"

HAS_AUDIO="false"
if [ -f "$AUDIO_OUT" ] && [ -s "$AUDIO_OUT" ]; then
    HAS_AUDIO="true"
fi

AUDIO_JSON=$([ "$HAS_AUDIO" = "true" ] && echo "\"$AUDIO_OUT\"" || echo "null")
printf '{"keyframes": %s, "audio": %s, "duration": "%s"}\n' "$FRAMES" "$AUDIO_JSON" "$DURATION"
