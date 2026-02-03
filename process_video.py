"""
Video Frame Extraction & Reconstruction Script
Handles high-quality deinterlacing and upscaling with automatic metadata naming.
"""

import argparse
import math
import os
import sys
import datetime
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

def process_frame(file_path, timestamp, output_dir, count=1, step=1,
                  fast=False, target_frame_num=None, scale=1,
                  resizer="bicubic", mode="both", tff_override=None, 
                  host_dir=None, host_input=None):
    """
    Primary processing pipeline with Side-by-Side comparison and Command generation.
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)

    # Load source using Index-based seeking
    video = core.ffms2.Source(source=file_path)

    # Metadata for naming
    base_filename = os.path.splitext(os.path.basename(file_path))[0]
    run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine frame index
    if target_frame_num is not None:
        start_frame = target_frame_num
        frame_ref = str(target_frame_num)
    else:
        try:
            fps = video.fps.numerator / video.fps.denominator
            h, m, s = map(float, timestamp.split(':'))
            target_sec = h * 3600 + m * 60 + s
            start_frame = int(math.floor(target_sec * fps + 0.5))
            frame_ref = timestamp
        except ValueError:
            print("Error: Invalid timestamp format (use HH:MM:SS.mmm).")
            sys.exit(1)

    # --- Automatic Field Order Detection ---
    if tff_override is not None:
        tff = bool(tff_override)
        print(f"Using explicit Field Order: {'TFF' if tff else 'BFF'}")
    else:
        # Check frame properties for field order
        sample_frame = video.get_frame(min(start_frame, video.num_frames - 1))
        prop_field = sample_frame.props.get('_FieldBased', 2) 
        tff = (prop_field != 1) 
        print(f"Detected Field Order: {'TFF' if tff else 'BFF'} (Source Prop: {prop_field})")

    # --- Video Processing ---
    video_prog = apply_scaling(video, scale, resizer)
    video_prog = core.resize.Bicubic(video_prog, format=vs.RGB24, matrix_in_s="709")
    prog_label = core.text.Text(video_prog, text=f"Original ({resizer} {scale}x)")

    # --- Deinterlaced Path (QTGMC) ---
    video_int = None
    frame_multiplier = 1
    if mode in ["both", "int"] and not fast:
        try:
            # High-quality motion-compensated deinterlacing
            video_int = haf.QTGMC(video, Preset="Very Slow", TFF=tff)
        except (AttributeError, TypeError):
            video_int = haf.QTGMC(video, Preset="Slow", TFF=tff)

        video_int = apply_scaling(video_int, scale, resizer)
        video_int = core.resize.Bicubic(video_int, format=vs.RGB24, matrix_in_s="709")
        int_label = core.text.Text(video_int, text=f"QTGMC Deint ({resizer} {scale}x)")

        fps_orig = video.fps.numerator / video.fps.denominator
        fps_int = video_int.fps.numerator / video_int.fps.denominator
        frame_multiplier = 2 if fps_int > fps_orig * 1.5 else 1

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    log_dir = host_dir if host_dir else output_dir
    input_ref = host_input if host_input else file_path

    # Build Re-run Commands
    base_cmd = f"./process_video.sh \"{input_ref}\" {frame_ref} {count} {scale} {resizer} {1 if fast else 0}"
    cmd_prog = f"{base_cmd} prog"
    cmd_int  = f"{base_cmd} int {1 if tff else 0}"

    for i in range(count):
        current_target = start_frame + (i * step)
        if current_target >= video.num_frames:
            break

        out_name = ""
        if mode == "both" and video_int:
            target_int = current_target * frame_multiplier
            combined = core.std.StackHorizontal([prog_label[current_target], int_label[target_int]])
            out_name = f"{base_filename}_f{current_target:06d}_compare_{run_timestamp}_%d.png"
            core.imwri.Write(combined, "png", os.path.join(output_dir, out_name)).get_frame(0)
        else:
            if mode in ["both", "prog"]:
                frame = video_prog[current_target]
                out_name = f"{base_filename}_f{current_target:06d}_prog_{run_timestamp}_%d.png"
                core.imwri.Write(frame, "png", os.path.join(output_dir, out_name)).get_frame(0)

            if video_int and mode in ["both", "int"]:
                target_int = current_target * frame_multiplier
                out_name = f"{base_filename}_f{target_int:06d}_int_{run_timestamp}_%d.png"
                core.imwri.Write(video_int[target_int], "png", os.path.join(output_dir, out_name)).get_frame(0)

        final_filename = out_name.replace('%d', '0')
        print(f"\n--- EXTRACTION COMPLETE ---")
        print(f"FILE: {os.path.join(log_dir, final_filename)}")
        
        if mode == "both":
            print(f"\nTo extract ONLY your preferred version, run:")
            print(f" LEFT (Original)    : {cmd_prog}")
            print(f" RIGHT (Deinterlaced): {cmd_int}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video Reconstruction Engine: High-quality frame extraction.")
    parser.add_argument("--input", required=True, help="Path to source video (.ISO, .MKV, etc.)")
    parser.add_argument("--time", default="00:00:00.000", help="Timestamp (HH:MM:SS.mmm) for extraction.")
    parser.add_argument("--out", default="output", help="Internal container directory for writing.")
    parser.add_argument("--host-dir", help="The absolute path on the host machine for accurate logging.")
    parser.add_argument("--host-input")
    parser.add_argument("--count", type=int, default=1, help="Number of frames to extract in sequence.")
    parser.add_argument("--step", type=int, default=1, help="Frame interval (e.g., step=2 extracts every other frame).")
    parser.add_argument("--fast", action="store_true", help="Skips QTGMC (fast test).")
    parser.add_argument("--frame", type=int, help="Override --time with direct frame number.")
    parser.add_argument("--scale", type=int, default=1, help="Upscaling factor (integer).")
    parser.add_argument("--resizer", default="bicubic", choices=["bicubic", "lanczos", "nnedi3_resample"], 
                        help="Scaling method. 'nnedi3_resample' is recommended for high-quality doubling.")
    parser.add_argument("--mode", default="both", choices=["both", "prog", "int"], 
                        help="'both' = side-by-side comparison; 'prog' = source only; 'int' = deinterlaced only.")
    parser.add_argument("--tff", type=int, choices=[0, 1], help="Field order: 1 for Top Field First, 0 for Bottom. Leave blank for auto-detect.")

    args = parser.parse_args()
    process_frame(args.input, args.time, args.out, args.count, args.step, args.fast, 
                  args.frame, args.scale, args.resizer, args.mode, args.tff, 
                  args.host_dir, args.host_input)
