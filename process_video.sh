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
STEP=1
SCALE=1
RESIZER="nnedi3_resample"
FAST=0
MODE="composite"
DENOISE="medium"
DENOISE_STAGE="pre"
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
==============================================================================
VIDEO RECONSTRUCTION ENGINE - USAGE
==============================================================================

Usage: $0 -i <input_path> -f <frame_or_timestamp> [options]

REQUIRED PARAMETERS:
  -i  Input file path (ISO, MKV, MP4, etc.)
  -f  Target point: Frame number (e.g., 54644) OR Timestamp (HH:MM:SS.mmm)

OUTPUT OPTIONS:
  -m  Mode (Default: $MODE)
      • composite  : 2x2 grid showing Original/Deint/Denoise/Stabilize
      • single     : Full pipeline (deint + denoise + stabilize)
      • deint      : Deinterlacing only
      • original   : No processing (raw frame)
      
  -s  Scale factor (Default: $SCALE)
      Integer multiplier for resolution (1=original, 2=double, etc.)
      
  -r  Resizer algorithm (Default: $RESIZER)
      • nnedi3_resample : Neural network (best quality, slower)
      • lanczos         : Sharp edges (good quality, fast)
      • bicubic         : Standard (balanced)

PROCESSING OPTIONS:
  -d  Denoise strength (Default: $DENOISE)
      none | light | medium | heavy
      Optimized for analog camcorder noise (VHS, Hi8, DV)
      
  -g  Denoise stage (Default: $DENOISE_STAGE)
      • pre  : Before deinterlacing (improves motion vectors)
      • post : After deinterlacing (preserves detail)
      
  -x  Stabilization (Default: $STABILIZE)
      • 0 : Off
      • 1 : On (DePan: range=8, trust=0.5, optimized for handheld)

EXTRACTION OPTIONS:
  -c  Count: Number of frames to extract (Default: $COUNT)
  -p  Step: Frame interval between extractions (Default: $STEP)
      Example: -c 10 -p 5 extracts every 5th frame for 10 frames total
      
  -t  Field order override (Default: auto-detect)
      • 1 : Top Field First (TFF)
      • 0 : Bottom Field First (BFF)
      • Omit to auto-detect from video metadata
      
  -z  Fast mode (Default: $FAST)
      • 0 : Use "Very Slow" QTGMC preset (best quality)
      • 1 : Use "Fast" preset (quick preview)

FRAME DISCOVERY WORKFLOW:
  To find the best frame in a sequence, use -c (count) and -p (step) to
  export a range around a timestamp, then inspect visually.

==============================================================================
EXAMPLES
==============================================================================

1. SPOT-CHECK MODE
   Extract 10 frames around 12-minute mark, every 5th frame, to find
   the best moment for archival extraction:
   
   $0 -i family_video.iso -f 00:12:00.000 -c 10 -p 5 -m original
   
   → Output: 10 PNG files in family_video/reconstructed/
   → Review visually, note the best frame number, then extract in high-quality

2. QUALITY COMPARISON (DEFAULT)
   Generate 2x2 grid comparing all processing stages at 2x resolution:
   
   $0 -i camcorder.iso -f 54644 -s 2
   
   → Output: Single PNG with 4 panels showing incremental improvements
   → Use this to verify deinterlacing/denoising is beneficial

3. PRODUCTION ARCHIVAL
   Extract single high-quality frame with full processing pipeline:
   
   $0 -i birthday_1995.iso -f 00:05:30.000 -m single -d heavy -g pre -x 1 -s 2
   
   → Deinterlaced + Heavy denoise (pre-stage) + Stabilized + 2x upscaled
   → Best quality for scanning/printing

4. BATCH EXTRACTION
   Extract 20 consecutive frames starting at specific timestamp:
   
   $0 -i wedding.mkv -f 00:23:15.000 -c 20 -p 1 -m single -d medium
   
   → Creates 20 sequential PNGs for manual frame selection

5. QUICK PREVIEW
   Fast preview with minimal processing to check content:
   
   $0 -i unknown_tape.iso -f 1000 -z 1 -m original
   
   → Fast mode + No processing = Quick content verification

==============================================================================
OUTPUT LOCATION
All files are saved to: <input_directory>/reconstructed/
Filename format: <basename>_F<frame>_<mode>_<timestamp>.png

For questions or issues, check logs printed during execution.
==============================================================================
EOF
    exit 1
}

# --- Argument Parsing ---
while getopts "i:f:c:p:s:r:m:d:g:x:t:z:h" opt; do
    case $opt in
        i) INPUT_FILE=$(realpath "$OPTARG") ;;
        f) INPUT_VAL="$OPTARG" ;;
        c) COUNT="$OPTARG" ;;
        p) STEP="$OPTARG" ;;
        s) SCALE="$OPTARG" ;;
        r) RESIZER="$OPTARG" ;;
        m) MODE="$OPTARG" ;;
        d) DENOISE="$OPTARG" ;;
        g) DENOISE_STAGE="$OPTARG" ;;
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
    --step "$STEP"
    --scale "$SCALE"
    --resizer "$RESIZER"
    --mode "$MODE"
    --denoise "$DENOISE"
    --denoise-stage "$DENOISE_STAGE"
    --stabilize "$STABILIZE"
)

# Handle conditional flags
[[ "$INPUT_VAL" == *":"* ]] && PY_CMD+=(--time "$INPUT_VAL") || PY_CMD+=(--frame "$INPUT_VAL")
[[ "$FAST" == "1" ]] && PY_CMD+=(--fast)
[[ -n "$TFF" ]] && PY_CMD+=(--tff "$TFF")

# --- Execute Container ---
exec docker run --rm \
    -v "$(pwd):/src" \
    -v "$DATA_DIR:/data" \
    -v "/etc/localtime:/etc/localtime:ro" \
    -v "/etc/timezone:/etc/timezone:ro" \
    -u "$(id -u):$(id -g)" \
    "$IMAGE_NAME:latest" "${PY_CMD[@]}"
