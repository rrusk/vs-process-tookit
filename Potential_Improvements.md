This document outlines the roadmap for enhancing the **Video Reconstruction Engine**. It categorizes improvements based on whether they require a **C++ environment update** (rebuilding the Docker image) or can be implemented via **logic updates** to the existing Python and Bash scripts.

---

## 🚀 Engine Improvement Roadmap

### Category A: Requires New Docker Image (C++ Layer)

These features require additional compiled plugins or system libraries to be present within the container environment.

| Feature | Description | Requirement |
| --- | --- | --- |
| **Combing Detection** | Automatically identifies if a frame contains interlacing artifacts to determine if deinterlacing is necessary. | Requires adding `VapourSynth-TDM` to the build process in the `Dockerfile`. |
| **GPU Acceleration** | Shifts motion analysis (QTGMC) and neural upscaling (znedi3) to the GPU for 5x–10x speed increases. | Requires `nvidia-docker2` base, CUDA toolkit, and OpenCL/CUDA versions of plugins. |
| **VMAF/SSIM Metrics** | Provides mathematical quality scores comparing the original source to the reconstructed output. | Requires `libvmaf` and `VapourSynth-VMAF` plugins compiled in the environment. |
| **Advanced Cropping** | Automatically detects and removes black letterbox bars from DVD sources. | Requires `VapourSynth-Descale` or `Znecrop` C++ binaries. |

---

### Category B: Script-Only Updates (Existing Image)

These features leverage the powerful libraries already present in the current image (VapourSynth, `havsfunc`, `mvsfunc`, and standard Python libraries).

| Feature | Description | Implementation |
| --- | --- | --- |
| **Scene Change Detection** | Prevents ghosting/blending by forcing filters to reset at camera cuts. | Uses existing `_SceneChangeNext` frame properties in Python. |
| **Side-by-Side Comparison** | Outputs a single image containing both the original and deinterlaced frame for validation. | Uses the `core.std.StackHorizontal` function available in the core library. |
| **Custom Filename Templates** | Allows users to define their own output naming patterns via CLI arguments. | Pure Python string formatting updates in `process_video.py`. |
| **Multi-Container Batching** | Spawns multiple Docker instances to process different video segments simultaneously. | Updates to the `process_video.sh` loop logic to handle parallel `docker run` calls. |

---

## 🛠️ Implementation Priority

### 1. The "Hybrid" Update (Intelligence)

The most valuable next step is **Combing Detection**. While it requires one new C++ plugin in the `Dockerfile`, the Python logic will allow the engine to function in a "Smart Mode":

* **If Combed**: Run `QTGMC` deinterlacing.
* **If Progressive**: Skip deinterlacing to save time and preserve original detail.

### 2. Quality Assurance Update

**(Done)** Implementing the **Side-by-Side Comparison** is a "quick win" that requires no Docker changes. It provides immediate visual feedback to the developer that the deinterlacer is working correctly without checking two separate files.

---

