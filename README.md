---

# Video Reconstruction Engine

An archival restoration toolkit for camcorder footage (ISO, Hi8, VHS, DV). This system uses **VapourSynth**, **QTGMC**, and **DePan** within a containerized environment to extract high-fidelity frames with industrial-strength processing.

## 📥 Prerequisites

* **Docker**: Ensure Docker is installed and the daemon is running.
* **Linux/Unix Shell**: Required for running the `.sh` wrapper.
* **Tooling**: `realpath` must be available in your `$PATH`.

## 🏗️ Installation

Build the reconstruction engine image using the provided `Dockerfile`. This build includes specialized patches to map standard `havsfunc` calls to your specific DePan plugin build.

```bash
docker build -t video-reconstruction-engine:latest .

```

## 🚀 Usage

Use the provided wrapper script to bridge your host filesystem with the container.

```bash
./process_video.sh -i <input_path> -f <frame_or_timestamp> [options]

```

### 🛠️ Core Options

| Flag | Parameter | Description | Default |
| --- | --- | --- | --- |
| **-i** | Input | Path to your video file (ISO, MKV, MP4, etc.) | **Required** |
| **-f** | Target | Frame number (e.g., `54644`) or Timestamp (`HH:MM:SS.mmm`) | **Required** |
| **-m** | Mode | Output type: `composite`, `single`, `deint`, or `original` | `composite` |
| **-s** | Scale | Integer resolution multiplier (e.g., `2` for 2x upscale) | `1` |
| **-d** | Denoise | Strength: `none`, `light`, `medium`, or `heavy` | `medium` |
| **-g** | Stage | Denoise stage: `pre` (best for QTGMC) or `post` | `pre` |
| **-x** | Stabilize | Toggle DePan stabilization: `1` (On) or `0` (Off) | `0` |
| **-p** | Step | Frame interval between extractions (for sequences) | `1` |
| **-z** | Fast | `1` for quick preview; `0` for high-quality "Very Slow" QTGMC | `0` |

---

## 🔍 Workflows

### 1. Frame Discovery (The "Spot-Check")

To find the sharpest frame in a moving sequence (like a dance), extract a range of frames around a timestamp using the `count` and `step` flags.  All files are saved to: <input_directory>/reconstructed/.
```
Filename format: <basename>_F<frame>_<mode>_<timestamp>.png
```

```bash
# Example:
# Extract 10 frames, every 5th frame, around the 12-minute mark
./process_video.sh -i video.iso -f 00:12:00.000 -c 10 -p 5 -m original

```

* **Output**: 10 PNGs saved in your `/reconstructed/` folder.
* **Action**: Review them, pick the sharpest frame number (from the filename), and run a **Production Archival** on that specific index.

### 2. Quality Verification

Generate a 2x2 grid to see exactly what each processing stage is doing to your specific footage.

```bash
./process_video.sh -i video.iso -f 54644 -s 2

```

* **Panel 1**: Original raw interlaced frame.
* **Panel 2**: Deinterlaced (QTGMC Very Slow).
* **Panel 3**: Deinterlaced + Denoised (at specified stage).
* **Panel 4**: Full Pipeline (including DePan stabilization).

### 3. Production Archival Extraction

Once the best frame is identified, run the full pipeline at high quality.

```bash
./process_video.sh -i tape.iso -f 54644 -m single -g pre -d medium -x 1 -s 2

```

* **Denoise Stage**: Using `-g pre` cleans noise *before* deinterlacing, which significantly improves QTGMC's motion vector accuracy for better edges.
* **Color Accuracy**: The engine automatically detects and applies **BT.601** (SD) or **BT.709** (HD) color matrices based on the resolution.

---

## 📂 Output Structure

The system creates a `reconstructed/` folder in the same directory as your input video.

**Filename Format:**
`<BaseName>_F<FrameIndex>_<ProcessingSuffix>_<Timestamp>_0.png`

---

## 🧪 Technical Notes

* **Stabilization**: Handled by DePan with `range=8` and `trust=0.5`, specifically tuned for handheld camcorder jitter.
* **Upscaling**: Supports `nnedi3_resample` (neural network), `lanczos`, and `bicubic`. NNEDI3 is used as the default for its superior edge reconstruction.
* **Field Order**: Automatically detected from video metadata. Overrides can be forced with `-t 1` (TFF) or `-t 0` (BFF).
