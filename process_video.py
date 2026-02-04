#!/usr/bin/env python3
"""
Video Frame Reconstruction & Quality Analysis Tool.

This module provides a pipeline for high-quality video restoration using 
VapourSynth. It supports incremental quality comparisons through a 
2x2 composite grid.
"""

import argparse
import datetime
import logging
import math
import os
import sys
from typing import Optional, Tuple, List, Dict

import havsfunc as haf
import vapoursynth as vs

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize VapourSynth core
core = vs.core
core.num_threads = os.cpu_count()


def to_pascal_case(text: str) -> str:
    """
    Normalizes a string to PascalCase for CLI compatibility.

    Args:
        text: The input string containing spaces or underscores.

    Returns:
        A capitalized string with all whitespace removed.
    """
    return "".join(word.capitalize() for word in text.split())


def apply_stabilization(clip: vs.VideoNode, enable: bool = False) -> vs.VideoNode:
    """
    Applies global motion stabilization via DePan.

    Uses range=8 and trust=0.5 for family footage consistency.

    Args:
        clip: Input video node.
        enable: Whether to apply the filter.

    Returns:
        Stabilized or original VideoNode.
    """
    if not enable:
        return clip
    
    try:
        mdata = core.depan.DePanEstimate(clip, range=8, trust=0.5)
        return core.depan.DePan(clip, data=mdata, offset=0.5, mirror=1)
    except Exception as e:
        logger.error(f"Stabilization failed: {e}")
        return clip


def apply_noise_reduction(clip: vs.VideoNode, strength: str = "medium") -> vs.VideoNode:
    """
    Applies temporal noise reduction using FFT3DFilter.

    Uses bt=4 for a larger temporal radius, optimized for stationary subjects.

    Args:
        clip: Input video node.
        strength: Magnitude of denoising (light, medium, heavy).

    Returns:
        Denoised VideoNode.
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


def get_output_node(
    video: vs.VideoNode, 
    mode: str, 
    fast: bool, 
    tff: bool, 
    denoise: str, 
    stabilize: bool, 
    scale: int, 
    resizer: str
) -> Tuple[vs.VideoNode, str, bool]:
    """
    Assembles the VapourSynth processing graph based on requested mode.

    Returns:
        A tuple of (processed_node, filename_suffix, is_grid_mode).
    """
    v_raw = video
    q_preset = "VerySlow" if not fast else "Fast"
    field_str = "TFF" if tff else "BFF"

    # Priority 1: De-interlace
    v_deint = haf.QTGMC(
        video, Preset="Very Slow" if not fast else "Fast",
        TFF=tff, FPSDivisor=2, InputType=0,
        SourceMatch=3, Lossless=2, ChromaMotion=True,
        Border=True
    )
    
    # Priority 2: De-noise
    v_denoised = apply_noise_reduction(v_deint, strength=denoise)
    
    # Priority 3: Stabilize
    v_stab = apply_stabilization(v_denoised, enable=stabilize)

    # Scale helper
    def scale_node(c: vs.VideoNode) -> vs.VideoNode:
        if scale == 1:
            return c
        w, h = c.width * scale, c.height * scale
        if resizer == "nnedi3_resample":
            c = core.znedi3.nnedi3(c, field=0, dh=True)
            c = core.std.Transpose(c)
            c = core.znedi3.nnedi3(c, field=0, dh=True)
            c = core.std.Transpose(c)
            return core.resize.Bicubic(c, width=w, height=h)
        return core.resize.Bicubic(c, width=w, height=h)

    if mode == "composite" and not fast:
        def prep(c: vs.VideoNode, lbl: str) -> vs.VideoNode:
            c = scale_node(c)
            c = core.resize.Bicubic(c, format=vs.RGB24, matrix_in_s="709")
            return core.text.Text(c, lbl)

        q1 = prep(v_raw, f"1. ORIGINAL ({field_str})")
        q2 = prep(v_deint, f"2. DE-INT (QTGMC: {q_preset}, {field_str})")
        q3 = prep(v_denoised, f"3. DE-INT + DE-NOISE ({denoise.capitalize()}, Bt4, {field_str})")
        q4 = prep(v_stab, f"4. ALL (+ STAB: R8, T0.5, {field_str})")

        top = core.std.StackHorizontal([q1, q2])
        bot = core.std.StackHorizontal([q3, q4])
        return core.std.StackVertical([top, bot]), "PriorityGrid", True

    # Individual mode logic
    if mode == "original":
        node, suffix = v_raw, "Original"
    elif mode == "single":
        node = v_stab
        comps = [f"Deint{q_preset}"]
        if denoise != "none":
            comps.append(f"Denoise{denoise.capitalize()}Bt4")
        if stabilize:
            comps.append("StabR8T05")
        suffix = "".join(comps)
    else:
        node, suffix = v_deint, f"Deint{q_preset}"

    node = scale_node(node)
    return core.resize.Bicubic(node, format=vs.RGB24, matrix_in_s="709"), suffix, False


def process_frame(
    file_path: str, 
    timestamp: str, 
    output_dir: str, 
    count: int = 1, 
    step: int = 1,
    fast: bool = False, 
    target_frame_num: Optional[int] = None, 
    scale: int = 1,
    resizer: str = "bicubic", 
    mode: str = "composite", 
    tff_override: Optional[int] = None,
    denoise: str = "medium", 
    stabilize: bool = False, 
    host_input: Optional[str] = None,
    host_dir: Optional[str] = None
) -> None:
    """Core logic to extract and save processed frames."""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        sys.exit(1)

    try:
        video = core.ffms2.Source(source=file_path)
    except Exception as e:
        logger.error(f"Failed to open source: {e}")
        sys.exit(1)

    base_fn = to_pascal_case(os.path.splitext(os.path.basename(file_path))[0])
    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Indexing logic
    if target_frame_num is not None:
        start_frame = target_frame_num
    else:
        fps = video.fps.numerator / video.fps.denominator
        h, m, s = map(float, timestamp.split(':'))
        start_frame = int(math.floor((h * 3600 + m * 60 + s) * fps + 0.5))

    # Field Order Detection
    if tff_override is not None:
        tff = bool(tff_override)
    else:
        sample = video.get_frame(min(start_frame, video.num_frames - 1))
        tff = (sample.props.get('_FieldBased', 2) != 1)

    out_node, suffix, is_grid = get_output_node(
        video, mode, fast, tff, denoise, stabilize, scale, resizer
    )

    os.makedirs(output_dir, exist_ok=True)

    for i in range(count):
        curr_idx = start_frame + (i * step)
        if curr_idx >= video.num_frames:
            break

        out_name = f"{base_fn}_F{curr_idx:06d}_{suffix}_{run_ts}_0.png"
        write_path = os.path.join(output_dir, out_name.replace('_0.png', '_%d.png'))
        
        try:
            core.imwri.Write(out_node[curr_idx], "png", write_path).get_frame(0)
            host_path = os.path.join(host_dir or output_dir, out_name)
            logger.info(f"Saved: {host_path}")
        except Exception as e:
            logger.error(f"Failed to write frame {curr_idx}: {e}")

    if mode == "composite":
        print("\n" + "="*40 + "\n INDIVIDUAL EXTRACTION SUGGESTIONS\n" + "="*40)
        u_in = host_input or file_path
        f_o = int(tff)
        cmd_base = f"./process_video.sh -i \"{u_in}\" -f {start_frame} -s {scale}"

        # 1. Raw Interlaced Source
        print(f"1. ORIGINAL:      {cmd_base} -m original -t {f_o}")

        # 2. De-interlaced only (No Denoise, No Stab)
        print(f"2. DE-INT ONLY:   {cmd_base} -m deint -t {f_o} -d none")

        # 3. De-interlaced + De-noised (No Stab)
        print(f"3. DE-INT + DN:   {cmd_base} -m single -t {f_o} -d {denoise} -x 0")

        # 4. Full Suite (De-int + DN + Stab)
        print(f"4. FULL SUITE:    {cmd_base} -m single -t {f_o} -d {denoise} -x 1")
        print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconstruction Engine CLI")
    parser.add_argument("--input", required=True)
    parser.add_argument("--time", default="00:00:00.000")
    parser.add_argument("--out", default="output")
    parser.add_argument("--host-dir")
    parser.add_argument("--host-input")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--resizer", default="bicubic")
    parser.add_argument("--mode", default="composite")
    parser.add_argument("--tff", type=int)
    parser.add_argument("--denoise", default="medium")
    parser.add_argument("--stabilize", type=int, default=0)
    
    args = parser.parse_args()

    process_frame(
        file_path=args.input, timestamp=args.time, output_dir=args.out,
        count=args.count, step=args.step, fast=args.fast,
        target_frame_num=args.frame, scale=args.scale, resizer=args.resizer,
        mode=args.mode, tff_override=args.tff, denoise=args.denoise,
        stabilize=bool(args.stabilize), host_input=args.host_input,
        host_dir=args.host_dir
    )
