#!/bin/bash
# ==============================================================================
# Script: docker_rebuild.sh
# Purpose: Manages the lifecycle of the 'video-reconstruction-engine' image.
# ==============================================================================
set -euo pipefail

IMAGE_NAME="video-reconstruction-engine"
TAG="latest"

# 1. Usage Documentation
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help    Display this help message and exit."
    echo "  --fresh       Wipes all caches and performs a total rebuild (Step 1-8)."
    echo ""
    echo "Default behavior is an Incremental Build (Faster, uses Docker cache)."
    exit 0
}

# 2. Argument Parsing
# Check for help flags before starting the cleanup process
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
fi

echo "--- 1. Starting Docker Cleanup ---"
# Stops and removes existing containers to prevent resource conflicts 
docker stop $(docker ps -aq -f ancestor=$IMAGE_NAME:$TAG) 2>/dev/null || true
docker rm $(docker ps -aq -f ancestor=$IMAGE_NAME:$TAG) 2>/dev/null || true
docker image prune -f
docker builder prune -f

echo "--- 2. Starting Build ---"
# Toggle for total wipe vs incremental build 
BUILD_ARGS=""
if [[ "${1:-}" == "--fresh" ]]; then
    echo "Performing Total System Rebuild (No Cache)..."
    BUILD_ARGS="--no-cache --pull"
else
    echo "Performing Incremental Build (Faster)..."
fi

# Build the container capturing output for troubleshooting 
if ! docker build $BUILD_ARGS -t $IMAGE_NAME:$TAG . 2>&1 | tee build_log.txt; then
    echo "!!! BUILD FAILED !!!"
    # Original troubleshooting logic: check for common C++ header issues 
    if grep -q "fatal error:" build_log.txt; then
        echo "[ERROR] Missing C++ headers. Check libvapoursynth-dev."
    fi
    exit 1
fi

echo "--- 3. Verification Successful ---"
# Verify environment via the Generative Core 
docker run --rm $IMAGE_NAME:$TAG python3 -c "import vapoursynth as vs; print('Environment Validated.')"
