import logging
import os
import textwrap
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_ARABIC_PATH = "assets/fonts/NotoSansArabic-Bold.ttf"
FONT_ENGLISH_PATH = "assets/fonts/NotoSans-Bold.ttf"


def prepare_text(text: str, language: str) -> str:
    if language == "ar":
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    return text


def get_font(language: str, size: int = 40) -> ImageFont.FreeTypeFont:
    if language == "ar":
        font_path = FONT_ARABIC_PATH
    else:
        font_path = FONT_ENGLISH_PATH

    if not os.path.exists(font_path):
        logger.warning(f"Font not found at {font_path}, using default")
        return ImageFont.load_default()

    return ImageFont.truetype(font_path, size)


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    draw: ImageDraw.ImageDraw,
    max_width: int,
) -> list[str]:
    """Wrap text to fit within max_width pixels. Returns list of lines."""
    if not text:
        return [""]

    words = text.split()
    if len(words) <= 1:
        return [text]

    lines = []
    current_line = words[0]

    for word in words[1:]:
        test_line = current_line + " " + word
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            test_width = bbox[2] - bbox[0]
        except Exception:
            test_width = max_width

        if test_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


def create_subtitle_image(
    text: str,
    language: str,
    video_width: int = 1280,
    font_size: int = 42,
    text_color: str = "#FFFFFF",
    bg_opacity: float = 0.6,
) -> Image.Image:
    """
    Create a transparent PNG image with the subtitle text rendered on it.
    Supports multi-line wrapping to fit within video width (B6 fix).
    Returns a PIL Image in RGBA mode.
    """
    processed_text = prepare_text(text, language)
    font = get_font(language, size=font_size)

    max_text_width = video_width - 80  # 40px margin each side
    temp_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)

    lines = _wrap_text(processed_text, font, temp_draw, max_text_width)

    line_height = font_size + 12
    box_height = len(lines) * line_height + 40

    img = Image.new("RGBA", (video_width, box_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg_alpha = int(bg_opacity * 255)
    draw.rectangle(
        [0, 10, video_width, box_height - 10],
        fill=(0, 0, 0, bg_alpha),
    )

    try:
        r = int(text_color.lstrip("#")[0:2], 16) if text_color.startswith("#") else 255
        g = int(text_color.lstrip("#")[2:4], 16) if text_color.startswith("#") else 255
        b = int(text_color.lstrip("#")[4:6], 16) if text_color.startswith("#") else 255
    except (ValueError, IndexError):
        r, g, b = 255, 255, 255

    total_text_height = len(lines) * line_height
    y_start = (box_height - total_text_height) // 2

    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
        except Exception:
            text_width = video_width
        x = max(0, (video_width - text_width) // 2)
        y = y_start + i * line_height
        draw.text((x, y), line, fill=(r, g, b, 255), font=font)

    return img


def generate_subtitles_from_script(
    script: str,
    segments: list[dict],
    language: str,
    audio_duration: float | None = None,
) -> list[dict]:
    """
    Generate subtitle entries with timing based on segment durations.

    If audio_duration is provided, timings are scaled proportionally to
    match the actual audio length (B5 fix), rather than trusting Gemini's
    per-segment duration estimates.

    Each entry has: start, end, text.
    Time starts at 0 and accumulates per segment.
    """
    subtitles = []
    time_cursor = 0.0

    # Filter segments that have text
    text_segments = []
    total_estimated = 0.0
    for segment in segments:
        text = segment.get("text", "")
        duration = float(segment.get("duration", 5))
        if text.strip():
            text_segments.append({"text": text, "duration": duration})
            total_estimated += duration

    # If we have actual audio duration, scale segment durations proportionally (B5)
    if audio_duration and total_estimated > 0:
        scale = audio_duration / total_estimated
    else:
        scale = 1.0

    for seg in text_segments:
        duration = seg["duration"] * scale
        start = time_cursor
        end = time_cursor + duration
        subtitles.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": seg["text"],
        })
        time_cursor = end

    return subtitles
