#!/bin/bash
# ==============================================================================
# VIDEO RECONSTRUCTION ENGINE - PRODUCTION WRAPPER
# ==============================================================================
# Dependency: docker, realpath
# ==============================================================================

set -e # Exit on error

# --- Default Configuration ---
IMAGE_NAME="video-reconstruction-engine"
COUNT=1
SCALE=1
RESIZER="nnedi3_resample"
FAST=0
MODE="composite"
DENOISE="medium"
STABILIZE=0
TFF="" 

# Dependency Check
for cmd in docker realpath; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: Required dependency '$cmd' not found in PATH."
        exit 1
    fi
done

usage() {
    cat << EOF
Usage: $0 -i <input_path> -f <frame_or_timestamp> [options]

Required:
  -i  Input file path
  -f  Frame number or timestamp (00:00:00.000)

Options:
  -m  Mode: composite (default), single, original, deint
  -s  Scale: Integer multiplier (default: 1)
  -x  Stabilize: 1 (on), 0 (off)
  -t  TFF: 1 (Top), 0 (Bottom), Omit for Auto-detect
  -z  Fast Mode: Set 1 to use Fast preset
EOF
    exit 1
}

# --- Argument Parsing ---
while getopts "i:f:c:s:r:m:d:x:t:z:h" opt; do
    case $opt in
        i) INPUT_FILE=$(realpath "$OPTARG") ;;
        f) INPUT_VAL="$OPTARG" ;;
        c) COUNT="$OPTARG" ;;
        s) SCALE="$OPTARG" ;;
        r) RESIZER="$OPTARG" ;;
        m) MODE="$OPTARG" ;;
        d) DENOISE="$OPTARG" ;;
        x) STABILIZE="$OPTARG" ;;
        t) TFF="$OPTARG" ;;
        z) FAST="$OPTARG" ;;
        h|*) usage ;;
    esac
done

if [[ -z "$INPUT_FILE" || -z "$INPUT_VAL" ]]; then usage; fi

# Path resolution
DATA_DIR=$(dirname "$INPUT_FILE")
OUT_DIR_HOST="$DATA_DIR/reconstructed"
mkdir -p "$OUT_DIR_HOST"
FILENAME=$(basename "$INPUT_FILE")

# Assemble Python Command Array for safe execution
PY_CMD=(
    python3 /src/process_video.py
    --input "/data/$FILENAME"
    --out "/data/reconstructed"
    --host-dir "$OUT_DIR_HOST"
    --host-input "$INPUT_FILE"
    --count "$COUNT"
    --scale "$SCALE"
    --resizer "$RESIZER"
    --mode "$MODE"
    --denoise "$DENOISE"
    --stabilize "$STABILIZE"
)

[[ "$INPUT_VAL" == *":"* ]] && PY_CMD+=(--time "$INPUT_VAL") || PY_CMD+=(--frame "$INPUT_VAL")
[[ "$FAST" == "1" ]] && PY_CMD+=(--fast)
[[ -n "$TFF" ]] && PY_CMD+=(--tff "$TFF")

# --- Execute Container ---
# Use exec to pass signals (Ctrl+C) directly to the containerized process
exec docker run --rm \
    -v "$(pwd):/src" \
    -v "$DATA_DIR:/data" \
    -u "$(id -u):$(id -g)" \
    "$IMAGE_NAME:latest" "${PY_CMD[@]}"
