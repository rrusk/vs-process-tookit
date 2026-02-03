# Video Reconstruction Engine

This project provides a high-performance environment for extracting and reconstructing frames from video media, specifically optimized for **DVD sources (.ISO, .VOB)**. It utilizes **VapourSynth** and the **QTGMC** deinterlacer to produce high-quality, stable images from interlaced content.

## New Features

* **Side-by-Side Comparison**: Generate a single wide image comparing original vs. deinterlaced results.
* **Automatic Field Detection**: Automatically detects TFF/BFF field order from video metadata.
* **Command Hinting**: Provides the exact shell command to re-run your preferred version after a comparison.
* **Absolute Path Mapping**: Displays the exact local file path on your host machine for all generated images.

---

## Architecture Overview

The engine is built on a Linux-based containerized stack to ensure all complex C++ dependencies (FFmpeg, L-SMASH, ZNEDIE3) are correctly linked and isolated.

### Core Components

* **VapourSynth**: A modern video processing framework.
* **QTGMC**: The industry-standard motion-compensated deinterlacer for temporal consistency.
* **L-SMASH Works**: High-performance file indexing and seeking.
* **ZNEDI3**: CPU-optimized neural network for spatial upscaling.

---

## 1. Building the Docker Image

The build process compiles several high-performance plugins from source to ensure compatibility with **Ubuntu 22.04** and **FFmpeg 4**.

### Prerequisites

* Docker installed and running.
* Approximately 4GB of free disk space for the build layers.

### Standard Build

To build the image using the provided management script:

```bash
chmod +x docker_rebuild.sh
./docker_rebuild.sh

```

### Fresh Rebuild

If you update the C++ source code or encounter library linking errors, perform a clean build:

```bash
./docker_rebuild.sh --fresh

```

---

## 2. Usage & Parameters

```bash
./process_video.sh <input_file> <time_or_frame> [count] [scale] [resizer] [fast] [mode] [tff]

```

### Detailed Parameter Guide

| Parameter | Type | Description |
| --- | --- | --- |
| **input_file** | Path | The video file (ISO, MKV, MP4, etc.). Files must be reachable by the script. |
| **time_or_frame** | String/Int | The extraction point. Use `HH:MM:SS.mmm` (e.g., `00:15:30.000`) or a frame index (e.g., `54644`). |
| **count** | Integer | Number of frames to extract in sequence. (Default: `1`). |
| **scale** | Integer | Upscaling multiplier. Use `2` to double the width/height. (Default: `1`). |
| **resizer** | String | `bicubic` (fast), `lanczos` (sharp), or `nnedi3_resample` (best for quality doubling). |
| **fast** | Boolean | `0` = High-quality QTGMC; `1` = Skip QTGMC (fast test for progressive sources). |
| **mode** | String | `both`: Comparison image; `prog`: Original only; `int`: Deinterlaced only. |
| **tff** | Integer | `1` = Top Field First; `0` = Bottom; `blank` = Script auto-detects from metadata. |

---

## 3. Practical Examples

### Comparison Mode (Recommended for Testing)

Extract a 2x Neural Upscaled comparison. The output will show the Original on the left and QTGMC on the right to help you decide which look is better.

```bash
./process_video.sh movie.iso 54644 1 2 nnedi3_resample 0 both

```

### Production Extraction

Once you know deinterlacing is needed, extract only the high-quality deinterlaced frames:

```bash
./process_video.sh movie.iso 00:15:30.000 1 1 bicubic 0 int

```

### Batch Extraction

Extract 10 sequential original frames starting at 1 minute (skipping deinterlacing for speed):

```bash
./process_video.sh clip.mp4 00:01:00.000 10 1 bicubic 1 prog

```

---

## Technical Notes

* **Performance**: The engine automatically detects your CPU core count to parallelize motion analysis.
* **Plugin Path**: Plugins are stored in `/usr/lib/x86_64-linux-gnu/vapoursynth`.
* **Memory**: When processing high-bitrate DVD content or using "Very Slow" presets, ensure the Docker daemon has at least 4GB of RAM allocated.
* **Output Location**: Images are saved to a `reconstructed/` folder inside your video's source directory.
* **Metadata Awareness**: The script reads `_FieldBased` properties to guess field order but allows manual override via the `tff` parameter.
* **Filenames**: Files are named using the pattern `[BaseName]_[Frame]_[Mode]_[Timestamp]_%d.png` to prevent accidental overwrites.
