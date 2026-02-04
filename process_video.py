#!/usr/bin/env python3
"""
Video Frame Reconstruction & Quality Analysis Tool.

A high-quality VapourSynth pipeline specifically designed for archival camcorder 
restoration. Supports field-aware deinterlacing, configurable noise reduction 
stages (pre/post), global motion stabilization, and resolution-aware color 
matrix detection.
"""

import argparse
import datetime
import logging
import math
import os
import re
import sys
from typing import Optional, Tuple, Dict

import havsfunc as haf
import vapoursynth as vs

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# VapourSynth Environment Initialization
# -----------------------------------------------------------------------------
core = vs.core
core.num_threads = os.cpu_count()

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def to_pascal_case(text: str) -> str:
    """
    Normalizes a filename to PascalCase for cross-platform CLI safety.
    
    Splits input on whitespace, underscores, or dashes to ensure robust
    normalization regardless of source naming convention.
    """
    parts = re.split(r"[\s_-]+", text)
    return "".join(p.capitalize() for p in parts if p)


def detect_matrix(c: vs.VideoNode) -> str:
    """
    Infers the correct color matrix based on frame resolution.
    
    Uses BT.601 for Standard Definition (SD) and BT.709 for High Definition (HD)
    to prevent chroma shifts during RGB conversion.
    """
    return "709" if c.width >= 1280 else "601"


def apply_stabilization(clip: vs.VideoNode, enable: bool) -> vs.VideoNode:
    """
    Applies global motion stabilization via DePan internal estimator.
    
    Uses range=8 and trust=0.5 optimized for family camcorder footage.
    """
    if not enable:
        return clip
    try:
        logger.info("Applying global motion stabilization (DePan: range=8, trust=0.5)")
        mdata = core.depan.DePanEstimate(clip, range=8, trust=0.5)
        return core.depan.DePan(clip, data=mdata, offset=0.5, mirror=1)
    except Exception as e:
        logger.error(f"Stabilization failed: {e}")
        return clip


def apply_noise_reduction(clip: vs.VideoNode, strength: str) -> vs.VideoNode:
    """
    Applies temporal noise reduction using FFT3DFilter.
    
    Uses bt=4 for a larger temporal radius, which provides better stability
    for archival footage with consistent background noise.
    """
    strength_map: Dict[str, float] = {
        "none": 0.0, "light": 1.0, "medium": 2.0, "heavy": 3.5
    }
    sigma = strength_map.get(strength, 2.0)
    
    if sigma == 0.0:
        return clip
        
    try:
        return core.fft3dfilter.FFT3DFilter(
            clip, sigma=sigma, bt=4, bw=32, bh=32, ow=16, oh=16
        )
    except AttributeError:
        logger.warning("FFT3DFilter plugin not found. Skipping denoise.")
        return clip

# -----------------------------------------------------------------------------
# Pipeline Assembly Logic
# -----------------------------------------------------------------------------

def get_output_node(
    video: vs.VideoNode,
    mode: str,
    fast: bool,
    tff: bool,
    denoise: str,
    stabilize: bool,
    scale: int,
    resizer: str,
    denoise_stage: str
) -> Tuple[vs.VideoNode, str, bool]:
    """
    Constructs the VapourSynth processing graph based on the requested mode.
    
    Returns:
        A tuple containing (processed_node, filename_suffix, is_grid_mode).
    """
    v_raw = video
    
    # Canonical Preset handling
    q_preset_name = "Very Slow" if not fast else "Fast"
    q_suffix = q_preset_name.replace(" ", "")
    field_str = "TFF" if tff else "BFF"

    # Stage 1: Optional PRE denoise (Improves QTGMC motion vectors)
    if denoise_stage == "pre" and denoise != "none":
        logger.info(f"Applying {denoise} noise reduction (PRE-deinterlacing stage)")
        
    v_prefilt = (
        apply_noise_reduction(video, denoise) 
        if denoise_stage == "pre" else video
    )

    # Stage 2: Deinterlacing (QTGMC with edge preservation)
    # Border=True prevents artifacts at frame boundaries.
    v_deint = haf.QTGMC(
        v_prefilt,
        Preset=q_preset_name,
        TFF=tff,
        FPSDivisor=2,
        InputType=0,
        SourceMatch=3,
        Lossless=2,
        ChromaMotion=True,
        Border=True
    )

    # Stage 3: Optional POST denoise (Alternative for specific sources)
    if denoise_stage == "post" and denoise != "none":
        logger.info(f"Applying {denoise} noise reduction (POST-deinterlacing stage)")

    v_dn = (
        apply_noise_reduction(v_deint, denoise) 
        if denoise_stage == "post" else v_deint
    )

    # Stage 4: Stabilization
    v_stab = apply_stabilization(v_dn, stabilize)

    # Scaling Logic Factory
    def scale_node(c: vs.VideoNode) -> vs.VideoNode:
        if scale == 1:
            return c
        w, h = c.width * scale, c.height * scale
        logger.info(f"Scaling output to {w}x{h} using {resizer}")
        if resizer == "nnedi3_resample":
            c = core.znedi3.nnedi3(c, field=0, dh=True)
            c = core.std.Transpose(c)
            c = core.znedi3.nnedi3(c, field=0, dh=True)
            c = core.std.Transpose(c)
            return core.resize.Bicubic(c, width=w, height=h)
        elif resizer == "lanczos":
            return core.resize.Lanczos(c, width=w, height=h)
        return core.resize.Bicubic(c, width=w, height=h)

    # 2x2 Composite Grid Generation
    if mode == "composite":
        if fast:
            logger.warning("Composite grid mode is intentionally simplified when --fast is used.")
        else:
            def prep(c: vs.VideoNode, lbl: str) -> vs.VideoNode:
                c = scale_node(c)
                matrix = detect_matrix(c)
                c = core.resize.Bicubic(c, format=vs.RGB24, matrix_in_s=matrix)
                return core.text.Text(c, lbl)

            q1 = prep(v_raw, f"1. ORIGINAL ({field_str})")
            q2 = prep(v_deint, f"2. DE-INT (QTGMC {q_preset_name}, {field_str})")
            q3 = prep(v_dn, f"3. DE-INT + DN ({denoise}, {denoise_stage})")
            q4 = prep(v_stab, f"4. ALL + STAB")

            top = core.std.StackHorizontal([q1, q2])
            bot = core.std.StackHorizontal([q3, q4])
            return core.std.StackVertical([top, bot]), "PriorityGrid", True

    # Individual Output Mode Mapping
    if mode == "original":
        node, suffix = v_raw, "Original"
    elif mode == "single":
        node = v_stab
        parts = [f"Deint{q_suffix}"]
        if denoise != "none":
            parts.append(f"DN{denoise.capitalize()}{denoise_stage.capitalize()}")
        if stabilize:
            parts.append("Stab")
        suffix = "".join(parts)
    else:
        node, suffix = v_deint, f"Deint{q_suffix}"

    node = scale_node(node)
    matrix = detect_matrix(node)
    return core.resize.Bicubic(node, format=vs.RGB24, matrix_in_s=matrix), suffix, False

# -----------------------------------------------------------------------------
# Frame Extraction Loop
# -----------------------------------------------------------------------------

def process_frame(
    file_path: str,
    timestamp: str,
    output_dir: str,
    count: int,
    step: int,
    fast: bool,
    target_frame_num: Optional[int],
    scale: int,
    resizer: str,
    mode: str,
    tff_override: Optional[int],
    denoise: str,
    stabilize: bool,
    denoise_stage: str,
    host_input: Optional[str],
    host_dir: Optional[str]
) -> None:
    """Primary entry point for frame extraction and archival output."""
    if not os.path.exists(file_path):
        logger.error(f"Source file not found: {file_path}")
        sys.exit(1)

    video = core.ffms2.Source(source=file_path)
    base_fn = to_pascal_case(os.path.splitext(os.path.basename(file_path))[0])
    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Target Frame Indexing Logic
    if target_frame_num is not None:
        start_frame = target_frame_num
    else:
        fps = video.fps.numerator / video.fps.denominator
        h, m, s = map(float, timestamp.split(':'))
        start_frame = int((h * 3600 + m * 60 + s) * fps + 0.5)

    # Field Order Detection with Transparency
    if tff_override is not None:
        tff = bool(tff_override)
    else:
        sample = video.get_frame(min(start_frame, video.num_frames - 1))
        fb = sample.props.get('_FieldBased', 2)
        if fb == 1:
            tff = False
            logger.info("Detected field order: BFF")
        elif fb == 2:
            tff = True
            logger.info("Detected field order: TFF")
        elif fb == 0:
            logger.warning("Source is progressive (_FieldBased=0). Using TFF as default for QTGMC compatibility.")
            tff = True
        else:
            logger.warning(f"Unknown _FieldBased value: {fb}. Defaulting to TFF.")
            tff = True

    out_node, suffix, is_grid = get_output_node(
        video, mode, fast, tff, denoise, stabilize, scale, resizer, denoise_stage
    )

    os.makedirs(output_dir, exist_ok=True)

    for i in range(count):
        idx = start_frame + i * step
        if idx >= video.num_frames:
            break

        name = f"{base_fn}_F{idx:06d}_{suffix}_{run_ts}_%d.png"
        path = os.path.join(output_dir, name)
        
        try:
            core.imwri.Write(out_node[idx], "png", path).get_frame(0)
            logger.info(f"Saved: {os.path.join(host_dir or output_dir, name.replace('%d','0'))}")
        except Exception as e:
            logger.error(f"Failed to write frame {idx}: {e}")

    # Docker-Aware Suggestion Terminal Output
    if mode == "composite" and not fast:
        print("\n" + "=" * 60)
        print("COMPOSITE BREAKDOWN - INDIVIDUAL EXTRACTION COMMANDS")
        print("=" * 60)
        u_in = host_input or file_path
        f_val = target_frame_num if target_frame_num is not None else timestamp
        tff_flag = "" if tff_override is None else f" -t {int(tff)}"
        
        base = f"./process_video.sh -i \"{u_in}\" -f \"{f_val}\" -s {scale} -r {resizer}"
        print(f"1. ORIGINAL:  {base} -m original{tff_flag}")
        print(f"2. DE-INT:    {base} -m deint -d none{tff_flag}")
        print(f"3. DE-INT+DN: {base} -m single -d {denoise}{tff_flag}")
        print(f"4. FULL PIPE: {base} -m single -d {denoise} -x 1{tff_flag}")
        print("=" * 60)

# -----------------------------------------------------------------------------
# Main CLI Execution
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Professional Archival Reconstruction CLI")
    p.add_argument("--input", required=True)
    p.add_argument("--time", default="00:00:00.000")
    p.add_argument("--out", default="output")
    p.add_argument("--host-dir")
    p.add_argument("--host-input")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--fast", action="store_true")
    p.add_argument("--frame", type=int)
    p.add_argument("--scale", type=int, default=1)
    p.add_argument("--resizer", default="bicubic", choices=["bicubic", "lanczos", "nnedi3_resample"])
    p.add_argument("--mode", default="composite", choices=["composite", "original", "single", "deint"])
    p.add_argument("--tff", type=int, choices=[0, 1])
    p.add_argument("--denoise", default="medium", choices=["none", "light", "medium", "heavy"])
    p.add_argument("--denoise-stage", default="pre", choices=["pre", "post"])
    p.add_argument("--stabilize", type=int, default=0)

    a = p.parse_args()

    process_frame(
        file_path=a.input, timestamp=a.time, output_dir=a.out,
        count=a.count, step=a.step, fast=a.fast, target_frame_num=a.frame,
        scale=a.scale, resizer=a.resizer, mode=a.mode, tff_override=a.tff,
        denoise=a.denoise, stabilize=bool(a.stabilize), denoise_stage=a.denoise_stage,
        host_input=a.host_input, host_dir=a.host_dir
    )
