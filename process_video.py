"""
Video Frame Extraction & Reconstruction Script
Supports: .ISO, .VOB, .MTS, .MKV, .MP4
Functionality: Progressive extraction, QTGMC deinterlacing, and Neural Upscaling.
"""

import argparse
import math
import os
import sys
import vapoursynth as vs
import havsfunc as haf

# Initialize VapourSynth core
core = vs.core
# Performance: Utilize all available CPU cores for motion analysis
core.num_threads = os.cpu_count()


def apply_scaling(clip, target_scale, method):
    """
    Applies spatial upscaling based on the selected method.
    """
    if target_scale == 1:
        return clip

    w, h = clip.width * target_scale, clip.height * target_scale

    if method == "lanczos":
        return core.resize.Lanczos(clip, width=w, height=h)
    elif method == "nnedi3_resample":
        # Neural doubling using the znedi3 plugin
        clip = core.znedi3.nnedi3(clip, field=0, dh=True)
        clip = core.std.Transpose(clip)
        clip = core.znedi3.nnedi3(clip, field=0, dh=True)
        clip = core.std.Transpose(clip)
        # Ensure exact dimensions with a bicubic fallback
        return core.resize.Bicubic(clip, width=w, height=h)
    else:
        return core.resize.Bicubic(clip, width=w, height=h)


def process_frame(file_path, timestamp, output_base, count=1, step=1,
                  fast=False, target_frame_num=None, scale=1,
                  resizer="bicubic", mode="both"):
    """
    Primary processing pipeline for frame extraction.
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)

    # Load source using Index-based seeking
    video = core.ffms2.Source(source=file_path)

    # Determine start frame (Direct Frame Override vs Timestamp)
    if target_frame_num is not None:
        start_frame = target_frame_num
    else:
        try:
            fps = video.fps.numerator / video.fps.denominator
            h, m, s = map(float, timestamp.split(':'))
            target_sec = h * 3600 + m * 60 + s
            start_frame = int(math.floor(target_sec * fps + 0.5))
        except ValueError:
            print("Error: Invalid timestamp format (use HH:MM:SS.mmm).")
            sys.exit(1)

    # --- Progressive Path ---
    video_prog = None
    if mode in ["both", "prog"]:
        video_prog = apply_scaling(video, scale, resizer)
        video_prog = core.resize.Bicubic(video_prog, format=vs.RGB24,
                                         matrix_in_s="709")
        if mode == "both":
            video_prog = core.text.Text(video_prog,
                                        text=f"Original ({resizer} {scale}x)")

    # --- Deinterlaced Path (QTGMC) ---
    video_int = None
    frame_multiplier = 1
    if mode in ["both", "int"] and not fast:
        try:
            # High-quality motion-compensated deinterlacing
            video_int = haf.QTGMC(video, Preset="Very Slow", TFF=True)
        except (AttributeError, TypeError):
            video_int = haf.QTGMC(video, Preset="Slow", TFF=True)

        video_int = apply_scaling(video_int, scale, resizer)
        video_int = core.resize.Bicubic(video_int, format=vs.RGB24,
                                         matrix_in_s="709")
        if mode == "both":
            video_int = core.text.Text(video_int,
                                       text=f"QTGMC Deint ({resizer} {scale}x)")

        fps_orig = video.fps.numerator / video.fps.denominator
        fps_int = video_int.fps.numerator / video_int.fps.denominator
        frame_multiplier = 2 if fps_int > fps_orig * 1.5 else 1

    # --- Execution Loop ---
    for i in range(count):
        current_target = start_frame + (i * step)
        if current_target >= video.num_frames:
            break

        if video_prog:
            frame = video_prog[current_target]
            out_path = f"{output_base}_prog_{current_target:04d}_%d.png"
            core.imwri.Write(frame, "png", out_path).get_frame(0)

        if video_int:
            frame = video_int[current_target * frame_multiplier]
            out_path = f"{output_base}_int_{current_target:04d}_%d.png"
            core.imwri.Write(frame, "png", out_path).get_frame(0)

        print(f"Processed frame {current_target} ({i+1}/{count})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video Reconstruction Engine")
    parser.add_argument("--input", required=True)
    parser.add_argument("--time", default="00:00:00.000")
    parser.add_argument("--out", default="output")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--resizer", default="bicubic",
                        choices=["bicubic", "lanczos", "nnedi3_resample"])
    parser.add_argument("--mode", default="both",
                        choices=["both", "prog", "int"])

    args = parser.parse_args()
    process_frame(
        args.input, args.time, args.out, args.count, args.step,
        args.fast, args.frame, args.scale, args.resizer, args.mode
    )
