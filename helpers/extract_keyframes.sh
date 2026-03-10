#!/bin/bash
# extract_keyframes.sh — Extract keyframes + audio from video via ffmpeg.
# Usage: ./extract_keyframes.sh <video_path> <output_dir>
# Output: frame_001.jpg ... + audio.wav in output_dir
#         Prints JSON manifest with frame paths, timestamps, and audio info.
#
# Strategy (auto-selected by duration):
#   Short videos (≤30s): 1 fps — comprehensive coverage
#   Long videos (>30s):  1 frame per 2 seconds — manageable count
# Capped at MAX_VIDEO_FRAMES (default 30).

set -euo pipefail

if [ $# -lt 2 ]; then
    echo '{"error": "Usage: extract_keyframes.sh <video_path> <output_dir>"}' >&2
    exit 1
fi

VIDEO="$1"
OUTDIR="$2"
FFMPEG="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"
MAX_FRAMES="${MAX_VIDEO_FRAMES:-30}"

if [ ! -f "$VIDEO" ]; then
    echo "{\"error\": \"Video file not found: $VIDEO\"}" >&2
    exit 1
fi

if ! command -v "$FFMPEG" &>/dev/null; then
    echo '{"error": "ffmpeg not found"}' >&2
    exit 1
fi

mkdir -p "$OUTDIR"

# Get video duration in seconds
DURATION_RAW=$(("$FFMPEG" -i "$VIDEO" 2>&1 || true) | sed -n 's/.*Duration: \([0-9]*\):\([0-9]*\):\([0-9.]*\).*/\1 \2 \3/p' | head -1)
if [ -n "$DURATION_RAW" ]; then
    DURATION_SECS=$(echo "$DURATION_RAW" | awk '{printf "%.0f", $1*3600 + $2*60 + $3}')
    DURATION_HMS=$(echo "$DURATION_RAW" | awk '{printf "%02d:%02d:%05.2f", $1, $2, $3}')
else
    DURATION_SECS=0
    DURATION_HMS="unknown"
fi

# Choose extraction strategy based on duration
if [ "$DURATION_SECS" -le 30 ] 2>/dev/null; then
    FPS_RATE="1"
    FPS_NUM=1  # frames per second (for timestamp calc)
else
    FPS_RATE="1/2"
    FPS_NUM=0  # flag: 1 frame per 2 seconds
fi

# Extract frames
"$FFMPEG" -y -i "$VIDEO" \
    -vf "fps=$FPS_RATE" -q:v 2 \
    "$OUTDIR/frame_%03d.jpg" 2>/dev/null || true

# If no frames extracted (e.g. HEVC issue), try I-frame fallback
if ! ls "$OUTDIR"/frame_*.jpg &>/dev/null; then
    "$FFMPEG" -y -i "$VIDEO" \
        -vf "select=eq(pict_type\\,I)" -vsync vfill \
        -frames:v "$MAX_FRAMES" -q:v 2 \
        "$OUTDIR/frame_%03d.jpg" 2>/dev/null || true
fi

# Cap at MAX_FRAMES — remove excess files
count=0
for f in "$OUTDIR"/frame_*.jpg; do
    [ -f "$f" ] || continue
    count=$((count + 1))
    if [ "$count" -gt "$MAX_FRAMES" ]; then
        rm "$f"
    fi
done

# Extract audio as WAV (16kHz mono for transcription)
AUDIO_OUT="$OUTDIR/audio.wav"
"$FFMPEG" -y -i "$VIDEO" \
    -vn -acodec pcm_s16le -ar 16000 -ac 1 \
    "$AUDIO_OUT" 2>/dev/null || true

# Compute inter-frame motion scores via SSIM
# Low SSIM = high motion/blur between frames. Stored as 1-SSIM (0=static, 1=total change).
MOTION_SCORES=()
PREV_FRAME=""
for f in "$OUTDIR"/frame_*.jpg; do
    [ -f "$f" ] || continue
    if [ -n "$PREV_FRAME" ]; then
        ssim_raw=$("$FFMPEG" -i "$PREV_FRAME" -i "$f" -lavfi ssim -f null - 2>&1 \
            | grep 'All:' | sed 's/.*All:\([0-9.]*\).*/\1/' || echo "1.0")
        # motion = 1 - ssim (higher = more different from previous)
        motion=$(awk "BEGIN {printf \"%.4f\", 1 - $ssim_raw}")
        MOTION_SCORES+=("$motion")
    else
        MOTION_SCORES+=("0.0000")  # first frame has no predecessor
    fi
    PREV_FRAME="$f"
done

# Build JSON manifest with frame paths, timestamps, and motion scores
FRAMES="["
first=true
idx=0
for f in "$OUTDIR"/frame_*.jpg; do
    [ -f "$f" ] || continue
    if [ "$first" = true ]; then
        first=false
    else
        FRAMES+=","
    fi
    # Compute timestamp based on fps rate
    if [ "$FPS_NUM" -eq 1 ] 2>/dev/null; then
        TIME_SEC="$idx.0"
    else
        TIME_SEC="$((idx * 2)).0"
    fi
    MSCORE="${MOTION_SCORES[$idx]:-0.0000}"
    FRAMES+="{\"path\": \"$f\", \"time\": $TIME_SEC, \"motion\": $MSCORE}"
    idx=$((idx + 1))
done
FRAMES+="]"

HAS_AUDIO="false"
if [ -f "$AUDIO_OUT" ] && [ -s "$AUDIO_OUT" ]; then
    HAS_AUDIO="true"
fi

AUDIO_JSON=$([ "$HAS_AUDIO" = "true" ] && echo "\"$AUDIO_OUT\"" || echo "null")
printf '{"frames": %s, "audio": %s, "duration": "%s", "frame_count": %d}\n' \
    "$FRAMES" "$AUDIO_JSON" "$DURATION_HMS" "$idx"
