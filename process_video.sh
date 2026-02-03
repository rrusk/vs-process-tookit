#!/bin/bash
# Intelligent wrapper for the Reconstruction Engine.
# Handles Docker volume mounting, host path resolution, and parameter parsing.

IMAGE_NAME="video-reconstruction-engine"
TAG="latest"

usage() {
    echo "==============================================================================="
    echo " VIDEO RECONSTRUCTION ENGINE - HELP"
    echo "==============================================================================="
    echo "Usage: $0 <input_file> <time_or_frame> [count] [scale] [resizer] [fast] [mode] [tff]"
    echo ""
    echo "POSITIONAL PARAMETERS:"
    echo "  1. input_file      : Path to video (ISO, MKV, MP4, etc.)"
    echo "  2. time_or_frame   : Target point. Use '00:15:30.000' (time) OR '54644' (frame)."
    echo "  3. count           : Number of sequential frames to extract (Default: 1)."
    echo "  4. scale           : Integer multiplier for size (e.g., 2 for double size)."
    echo "  5. resizer         : Method: 'bicubic' (fast), 'lanczos', or 'nnedi3_resample' (best quality)."
    echo "  6. fast            : Set to 1 to skip QTGMC (fast test). Set to 0 for full quality."
    echo "  7. mode            : Output type: 'both' (comparison), 'prog' (original), 'int' (deinterlaced)."
    echo "  8. tff             : Field Order: 1 (Top Field First), 0 (Bottom), blank (Auto-detect)."
    echo ""
    echo "EXAMPLES:"
    echo "  # Extract a 2x Neural Upscaled comparison from a DVD frame:"
    echo "  $0 movie.iso 54644 1 2 nnedi3_resample 0 both"
    echo ""
    echo "  # Extract 10 original frames starting at 1 minute (no deinterlacing):"
    echo "  $0 clip.mp4 00:01:00.000 10 1 bicubic 1 prog"
    echo "==============================================================================="
    exit 1
}

if [[ "$#" -lt 2 || "$1" == "--help" || "$1" == "-h" ]]; then usage; fi

# Resolve absolute path for the input file
INPUT_FILE=$(realpath "$1")
INPUT_VAL="$2"
COUNT="${3:-1}"
SCALE="${4:-1}"
RESIZER="${5:-bicubic}"
FAST_MODE="${6:-0}"
MODE="${7:-both}"
TFF_VAL="${8:-}"

# Calculate absolute host path for the output directory
DATA_DIR=$(dirname "$INPUT_FILE")
OUT_DIR_HOST="$DATA_DIR/reconstructed"
mkdir -p "$OUT_DIR_HOST"

# Determine if input is a timestamp or frame number
EXTRA_ARGS=""
if [[ "$INPUT_VAL" == *":"* ]]; then
    EXTRA_ARGS="--time $INPUT_VAL"
else
    EXTRA_ARGS="--frame $INPUT_VAL"
fi

if [ "$FAST_MODE" -eq 1 ]; then EXTRA_ARGS="$EXTRA_ARGS --fast"; fi
if [ -n "$TFF_VAL" ]; then EXTRA_ARGS="$EXTRA_ARGS --tff $TFF_VAL"; fi

FILENAME=$(basename "$INPUT_FILE")
SCRIPT_DIR=$(pwd)




docker run --rm \
    -v "$SCRIPT_DIR:/src" \
    -v "$DATA_DIR:/data" \
    -u "$(id -u):$(id -g)" \
    -e PYTHONPATH="/usr/lib/python3/dist-packages" \
    -e VAPOURSYNTH_PLUGINS="/usr/lib/x86_64-linux-gnu/vapoursynth" \
    "$IMAGE_NAME:$TAG" \
    python3 /src/process_video.py \
        --input "/data/$FILENAME" \
        --out "/data/reconstructed" \
        --host-dir "$OUT_DIR_HOST" \
        --host-input "$INPUT_FILE" \
        --count "$COUNT" \
        --scale "$SCALE" \
        --resizer "$RESIZER" \
        --mode "$MODE" \
        $EXTRA_ARGS
