# Video Reconstruction Engine

This project provides a high-performance environment for extracting and reconstructing frames from video media, specifically optimized for **DVD sources (.ISO, .VOB)**. It utilizes **VapourSynth** and the **QTGMC** deinterlacer to produce high-quality, stable images from interlaced content.

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

## 2. Extracting Frames

The engine is primarily tested for **DVD-based workflows**. Use the `process_video.sh` wrapper to handle path mounting and environment variables automatically.

### Basic Usage

```bash
./process_video.sh <input_file> <time_or_frame> [count] [scale] [resizer] [fast] [mode]

```

### Parameters

| Parameter | Description |
| --- | --- |
| `input_file` | Path to the `.iso` or `.vob` file. |
| `time_or_frame` | Timestamp (`HH:MM:SS.mmm`) or an integer frame number. |
| `count` | Number of sequential frames to extract (default: 1). |
| `scale` | Upscaling factor integer (default: 1). |
| `resizer` | `bicubic`, `lanczos`, or `nnedi3_resample`. |
| `mode` | `int` (Deinterlaced), `prog` (Original), or `both`. |

---

## 3. Practical Examples (DVD Focus)

### Extracting a Single Deinterlaced Frame

To extract a high-quality deinterlaced frame from a DVD ISO at a specific timestamp:

```bash
./process_video.sh movie.iso 00:15:30.000 1 1 bicubic 0 int

```

### Neural Upscaling (2x)

To double the resolution of a frame using the `znedi3` neural plugin:

```bash
./process_video.sh VTS_01_1.VOB 54644 1 2 nnedi3_resample 0 int

```

### Batch Extraction for Analysis

To extract 10 sequential frames starting at frame 1000 to compare original vs. deinterlaced:

```bash
./process_video.sh movie.iso 1000 10 1 bicubic 0 both

```

---

## Technical Notes

* **Performance**: The engine automatically detects your CPU core count to parallelize motion analysis.
* **Plugin Path**: Plugins are stored in `/usr/lib/x86_64-linux-gnu/vapoursynth`.
* **Memory**: When processing high-bitrate DVD content or using "Very Slow" presets, ensure the Docker daemon has at least 4GB of RAM allocated.
