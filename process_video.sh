#!/bin/bash
# Description: Intelligent wrapper for the Reconstruction Engine.
# Supports automatic detection of timestamps vs. direct frame numbers.

IMAGE_NAME="video-reconstruction-engine"
TAG="latest"

usage() {
    echo "Usage: $0 <input_file> <time_or_frame> [count] [scale] [resizer] [fast] [mode]"
    echo "Example (MTS Discovery): $0 clip.mts 00:01:15.500 10 1 bicubic 1"
    echo "Example (ISO Production): $0 movie.iso 54644 1 2 nnedi3_resample 0 int"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

# Path resolution for Docker volumes
INPUT_FILE=$(realpath "$1")
INPUT_VAL="$2"
COUNT="${3:-1}"
SCALE="${4:-1}"
RESIZER="${5:-bicubic}"
FAST_MODE="${6:-0}"
MODE="${7:-both}"

# Determine if input is HH:MM:SS or an integer frame number
EXTRA_ARGS=""
if [[ "$INPUT_VAL" == *":"* ]]; then
    EXTRA_ARGS="--time $INPUT_VAL"
else
    EXTRA_ARGS="--frame $INPUT_VAL"
fi

if [ "$FAST_MODE" -eq 1 ]; then EXTRA_ARGS="$EXTRA_ARGS --fast"; fi

DATA_DIR=$(dirname "$INPUT_FILE")
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
        --count "$COUNT" \
        --scale "$SCALE" \
        --resizer "$RESIZER" \
        --mode "$MODE" \
        $EXTRA_ARGS
