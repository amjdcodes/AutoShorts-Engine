import logging
import os
import subprocess
from typing import Optional

from PIL import Image

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from app.services.subtitle_service import create_subtitle_image, generate_subtitles_from_script
from app.config import get_settings
from app import logger_util

logger = logging.getLogger(__name__)

SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
LONG_WIDTH = 1280
LONG_HEIGHT = 720


def _get_target_dimensions(is_short: bool) -> tuple[int, int]:
    """Return (width, height) for the video based on short/long type."""
    if is_short:
        return (SHORT_WIDTH, SHORT_HEIGHT)
    return (LONG_WIDTH, LONG_HEIGHT)


def _ffprobe_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else 0.0
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return 0.0


def _validate_video_file(video_path: str) -> bool:
    """Quick check that a video file is readable and non-empty.
    Runs ffprobe to verify the container has at least one video stream.
    """
    if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0 and result.stdout.strip() == "video"
    except subprocess.TimeoutExpired:
        return False


def _terminate_proc(proc, timeout: float = 5.0) -> None:
    """Terminate a subprocess if still running, then kill if it won't exit."""
    try:
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
        proc.kill()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg process refused to die after SIGKILL")
    except Exception:
        pass


def _kill_proc(proc) -> None:
    """Immediately SIGKILL a subprocess — used during force-close when
    the output file is already written and we don't need graceful exit.
    """
    try:
        if proc is None or proc.poll() is not None:
            return
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg process refused to die after SIGKILL")
    except Exception:
        pass


def _force_close_clip(clip) -> None:
    """Force-close a MoviePy clip and its underlying ffmpeg processes.

    MoviePy's close() methods call proc.wait() which can block forever
    if an ffmpeg subprocess doesn't exit. This helper kills every ffmpeg
    process first and nullifies the proc references, so the subsequent
    close() calls become no-ops.

    Handles three layers of ffmpeg processes:
      1. Video reader:  clip.reader.proc  (FFMPEG_VideoReader)
      2. Audio reader:  clip.audio.reader.proc  (FFMPEG_AudioReader)
      3. Nested clips:  clip.clips[]  (from concatenate/compose)
    """
    # ── 1. Video reader process ──────────────────────────────────
    try:
        reader = getattr(clip, "reader", None)
        if reader:
            proc = getattr(reader, "proc", None)
            if proc:
                _kill_proc(proc)
                try:
                    reader.proc = None
                except Exception:
                    pass
            try:
                reader.close()
            except Exception:
                pass
    except Exception:
        pass

    # ── 2. Audio reader process ──────────────────────────────────
    # AudioFileClip stores proc in clip.audio.reader.proc (NOT clip.audio.proc)
    try:
        audio = getattr(clip, "audio", None)
        if audio:
            # Kill the FFMPEG_AudioReader's proc before close()
            audio_reader = getattr(audio, "reader", None)
            if audio_reader:
                proc = getattr(audio_reader, "proc", None)
                if proc:
                    _kill_proc(proc)
                    try:
                        audio_reader.proc = None
                    except Exception:
                        pass
            # Some MoviePy versions expose proc directly on AudioClip
            proc = getattr(audio, "proc", None)
            if proc:
                _kill_proc(proc)
                try:
                    audio.proc = None
                except Exception:
                    pass
            if hasattr(audio, "close"):
                try:
                    audio.close()
                except Exception:
                    pass
    except Exception:
        pass

    # ── 3. Top-level clip close ──────────────────────────────────
    try:
        clip.close()
    except Exception:
        pass

    # ── 4. Recursively close nested clips (concatenate/compose) ──
    try:
        nested = getattr(clip, "clips", None)
        if nested:
            for sub in nested:
                if sub is not clip:
                    _force_close_clip(sub)
    except Exception:
        pass


def burn_subtitles_ffmpeg(
    video_path: str,
    subtitles: list[dict],
    output_path: str,
    language: str,
    is_short: bool = False,
) -> str:
    """
    Burn subtitles onto video using FFmpeg overlay method.
    Creates PNG images per subtitle, then uses filter_complex to overlay them.
    Runs FFmpeg via subprocess directly (not ffmpeg-python) for reliability.
    """
    settings = get_settings()
    threads = max(1, settings.FFMPEG_THREADS)
    timeout = max(60, settings.FFMPEG_TIMEOUT)

    if not subtitles:
        subprocess.run(
            ["ffmpeg", "-y", "-threads", str(threads),
             "-i", video_path, "-c", "copy", output_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return output_path

    video_width, video_height = _get_target_dimensions(is_short)

    subtitle_images = []
    for i, sub in enumerate(subtitles):
        img = create_subtitle_image(
            text=sub["text"],
            language=language,
            video_width=video_width,
            font_size=settings.SUBTITLE_FONT_SIZE,
            text_color=settings.SUBTITLE_COLOR,
            bg_opacity=settings.SUBTITLE_BG_OPACITY,
        )
        img_path = f"temp/sub_burn_{i}.png"
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        img.save(img_path, format="PNG")
        subtitle_images.append(img_path)

    cmd = ["ffmpeg", "-y", "-threads", str(threads), "-i", video_path]

    for i, (sub, img_path) in enumerate(zip(subtitles, subtitle_images)):
        duration = sub["end"] - sub["start"]
        cmd += ["-loop", "1", "-t", str(duration), "-i", img_path]

    filter_parts = []
    prev_label = "0:v"

    for i, sub in enumerate(subtitles):
        input_index = i + 1
        out_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{input_index}:v]"
            f"overlay=x=(W-w)/2:y=H-h-10:"
            f"enable='between(t,{sub['start']},{sub['end']})'[{out_label}]"
        )
        prev_label = out_label

    final_video_label = prev_label
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{final_video_label}]",
        "-map", "0:a",
        "-vcodec", "libx264",
        "-acodec", "aac",
        "-crf", "23",
        "-preset", settings.FFMPEG_PRESET,
        "-threads", str(threads),
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg subtitle burn failed:\n{e.stderr}") from e
    finally:
        for img_path in subtitle_images:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
            except OSError:
                pass

    logger.info(f"Subtitles burned, output: {output_path}")
    return output_path


def create_final_video(
    segments: list[dict],
    video_paths: list[dict],
    audio_path: str,
    language: str,
    output_path: str,
    subtitle_segments: Optional[list[dict]] = None,
    is_short: bool = False,
) -> str:
    """
    Create the final video from segments:
    1. Trim and concatenate video clips
    2. Add audio track
    3. Generate subtitles with actual audio duration (B5)
    4. Burn subtitles via FFmpeg overlay

    subtitle_segments: list of actual downloaded segments (seg_info).
    If provided and SUBTITLE_ENABLED is True, subtitles are generated
    inside this function using the real audio duration for accurate timing.

    is_short controls the output resolution:
      - True  -> 1080x1920 (9:16 vertical, for YouTube Shorts)
      - False -> 1280x720  (16:9 horizontal, for long YouTube videos)

    This is a CPU-bound function — call via anyio.to_thread.run_sync().
    """
    from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

    settings = get_settings()
    target_w, target_h = _get_target_dimensions(is_short)
    threads = max(1, settings.FFMPEG_THREADS)

    clips = []
    for seg_info in video_paths:
        vp = seg_info.get("video_path", "")
        dur = seg_info.get("duration", 5)
        if not vp or not os.path.exists(vp):
            logger.warning(f"Video segment file not found: {vp}, skipping")
            continue

        if not _validate_video_file(vp):
            logger.warning(f"Corrupt/unreadable video segment: {vp}, skipping")
            continue

        clip = VideoFileClip(vp)
        if clip.duration < dur:
            dur = clip.duration
        clip = clip.subclip(0, dur)
        clip = clip.resize((target_w, target_h))
        clips.append(clip)

    if not clips:
        raise RuntimeError("No valid video clips to produce final video")

    logger.info(
        f"Rendering: {len(clips)} clips, target {target_w}x{target_h}, "
        f"short={'yes' if is_short else 'no'}"
    )
    # Use "chain" method — all clips are already resized to the same
    # dimensions, so "compose" is unnecessary and leaks ffmpeg processes.
    final_clip = concatenate_videoclips(clips, method="chain")

    audio_duration = None
    if os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
        audio_duration = audio.duration
        if audio.duration < final_clip.duration:
            final_clip = final_clip.subclip(0, audio.duration)
        final_clip = final_clip.set_audio(audio)
    else:
        logger.warning(f"Audio file not found: {audio_path}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    temp_output = output_path.replace(".mp4", "_no_subs.mp4")
    logger.info(f"Writing video (no subs) to {temp_output} ...")
    final_clip.write_videofile(
        temp_output,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        logger=None,
        threads=threads,
        preset=settings.FFMPEG_PRESET,
        ffmpeg_params=["-threads", str(threads)],
    )
    logger_util.success(f"Base video written: {temp_output}")

    # ── Close all clips and release ffmpeg processes ──────────────
    # Close BEFORE any further processing to release file handles and
    # ffmpeg subprocesses. Force-close prevents proc.wait() from hanging.
    try:
        _force_close_clip(final_clip)
    except Exception:
        pass
    for clip in clips:
        _force_close_clip(clip)

    if settings.SUBTITLE_ENABLED and subtitle_segments:
        # Generate subtitles with actual audio duration for accurate timing (B5)
        subtitles = generate_subtitles_from_script(
            script="",
            segments=subtitle_segments,
            language=language,
            audio_duration=audio_duration,
        )
        logger.info(
            f"Burning {len(subtitles)} subtitles onto {temp_output} -> {output_path}"
        )
        burn_subtitles_ffmpeg(
            temp_output, subtitles, output_path, language, is_short=is_short
        )
        try:
            if os.path.exists(temp_output):
                os.remove(temp_output)
        except OSError:
            pass
    else:
        if temp_output != output_path:
            os.rename(temp_output, output_path)

    file_size_mb = (
        os.path.getsize(output_path) / (1024 * 1024)
        if os.path.exists(output_path)
        else 0
    )
    logger_util.success(
        f"Final video ready: {output_path} "
        f"({target_w}x{target_h}, {file_size_mb:.1f} MB)"
    )
    return output_path


def cleanup_temp_files(job_id: int):
    """Remove temporary files for a completed job."""
    import glob
    patterns = [
        "temp/segment_*.mp4",
        f"temp/audio_{job_id}.mp3",
        "temp/sub_*.png",
        "temp/sub_burn_*.png",
        f"output/job_{job_id}_no_subs.mp4",
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass
    logger.info(f"Cleaned temp files for job {job_id}")
