"""
Video Frame Extraction & Reconstruction Script
Handles high-quality deinterlacing and upscaling with automatic metadata naming.
Enhanced with Noise Reduction for camcorder footage and Host-aware path logging.
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

def apply_noise_reduction(clip, strength="medium"):
    """
    Applies temporal noise reduction optimized for analog camcorder footage.
    """
    strength_map = {
        "light": 1.0,
        "medium": 2.0,
        "heavy": 3.5
    }
    
    sigma = strength_map.get(strength, 2.0)
    
    try:
        # FFT3DFilter: Excellent for analog noise (VHS, Hi8, DV)
        denoised = core.fft3dfilter.FFT3DFilter(clip, sigma=sigma, bt=3, bw=32, bh=32, ow=16, oh=16)
        return denoised
    except AttributeError:
        print("Warning: fft3dfilter not available, skipping noise reduction")
        return clip

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
                  host_dir=None, host_input=None, denoise="medium"):
    """
    Primary processing pipeline with High-Quality QTGMC and Noise Reduction.
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
        sample_frame = video.get_frame(min(start_frame, video.num_frames - 1))
        prop_field = sample_frame.props.get('_FieldBased', 2) 
        tff = (prop_field != 1) 
        print(f"Detected Field Order: {'TFF' if tff else 'BFF'} (Source Prop: {prop_field})")

    # --- Noise Reduction (applied BEFORE deinterlacing) ---
    if denoise and denoise != "none":
        print(f"Applying {denoise} noise reduction...")
        video = apply_noise_reduction(video, strength=denoise)

    # --- Progressive Path ---
    video_prog = apply_scaling(video, scale, resizer)
    video_prog = core.resize.Bicubic(video_prog, format=vs.RGB24, matrix_in_s="709")
    prog_label = core.text.Text(video_prog, text=f"Original ({resizer} {scale}x)")

    # --- Deinterlaced Path (Optimized for Still Extraction) ---
    video_int = None
    qtgmc_fps_divisor = 2  # 2 = 1:1 frames, 1 = bob (double rate)
    # frame_multiplier is now 1 because FPSDivisor=2 maintains original frame count
    frame_multiplier = 1

    if mode in ["both", "int"] and not fast:
        try:
            print("Running QTGMC with Scene-Aware Processing...")
            # Best configuration for interlaced camcorder footage with scene changes:
            # InputType=0: Pure interlaced (camcorders) - maintains quality
            # FPSDivisor=2: Output same framerate as input (60i->30p, 50i->25p)
            # SourceMatch=3: Helps with DVD authoring artifacts
            # Lossless=2: Maximum detail preservation (compatible with InputType=0)
            # 
            # Scene change handling: QTGMC automatically detects scene changes
            # via motion analysis - when motion vectors are inconsistent, it
            # falls back to spatial interpolation for that frame.
            video_int = haf.QTGMC(
                video, 
                Preset="Very Slow",
                TFF=tff,
                InputType=0,                    # Pure interlaced - best quality
                FPSDivisor=qtgmc_fps_divisor,   # Keeps original framerate if 2
                SourceMatch=3,                  # DVD-optimized
                Lossless=2,                     # Maximum detail
                Border=True
            )
            print("✓ High-quality 1:1 deinterlacing complete")
        except (AttributeError, TypeError) as e:
            print(f"Warning: QTGMC 'Very Slow' failed ({e}), trying 'Slow' preset...")
            video_int = haf.QTGMC(video, Preset="Slow", TFF=tff, FPSDivisor=2)

        video_int = apply_scaling(video_int, scale, resizer)
        video_int = core.resize.Bicubic(video_int, format=vs.RGB24, matrix_in_s="709")
        int_label = core.text.Text(video_int, text=f"QTGMC Deint ({resizer} {scale}x)")

    # Sanity check: FPSDivisor=2 should guarantee 1:1 frame mapping
    if video_int and qtgmc_fps_divisor == 2:
        assert video.fps == video_int.fps, (
            f"FPS mismatch despite FPSDivisor=2 "
            f"({video.fps} vs {video_int.fps})"
        )

    # Handle change in haf.QTGMC FPSDivisor setting (e.g. bob mode)
    if video_int and qtgmc_fps_divisor != 2:
        fps_orig = video.fps.numerator / video.fps.denominator
        fps_int  = video_int.fps.numerator / video_int.fps.denominator
        frame_multiplier = 2 if fps_int > fps_orig * 1.5 else 1

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Path translation for logging
    log_dir = host_dir if host_dir else output_dir
    input_ref = host_input if host_input else file_path

    # Build Re-run Commands
    denoise_arg = f" {denoise}" if denoise != "medium" else ""
    base_cmd = f"./process_video.sh \"{input_ref}\" {frame_ref} {count} {scale} {resizer} {1 if fast else 0}"
    cmd_prog = f"{base_cmd} prog {1 if tff else ''}{denoise_arg}"
    cmd_int  = f"{base_cmd} int {1 if tff else ''}{denoise_arg}"

    for i in range(count):
        current_target = start_frame + (i * step)
        if current_target >= video.num_frames:
            break

        out_name = ""
        if mode == "both" and video_int:
            # target_int is now equal to current_target due to FPSDivisor=2
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
        if count == 1:
            print(f"COMPLETE: {os.path.join(log_dir, final_filename)}")
        else:
            print(f"Saved: {final_filename} to {log_dir}")
        
        if mode == "both":
            print(f"\nTo extract ONLY your preferred version, run:")
            print(f" LEFT (Original)    : {cmd_prog}")
            print(f" RIGHT (Deinterlaced): {cmd_int}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video Reconstruction Engine: High-quality 1:1 Still frame extraction.")
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
    parser.add_argument("--denoise", default="medium", choices=["none", "light", "medium", "heavy"])

    args = parser.parse_args()
    process_frame(args.input, args.time, args.out, args.count, args.step, args.fast, 
                  args.frame, args.scale, args.resizer, args.mode, args.tff, 
                  args.host_dir, args.host_input, args.denoise)
