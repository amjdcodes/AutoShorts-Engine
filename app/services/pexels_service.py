import logging
import os
import asyncio
from typing import Optional
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 120.0


async def search_videos(
    query: str,
    per_page: int = 5,
    orientation: str = "landscape",
) -> list[dict]:
    """
    Search for videos on Pexels matching the given query.
    orientation: "landscape" (16:9) for long videos, "portrait" (9:16) for shorts.
    Returns a list of video file objects sorted by relevance.
    """
    settings = get_settings()
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": settings.PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "size": "medium",
        "orientation": orientation,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    videos = data.get("videos", [])
    logger.info(
        f"Pexels search: '{query}' -> {len(videos)} results (orientation={orientation})"
    )
    return videos


def _pick_best_video_file(video: dict, is_short: bool = False) -> Optional[dict]:
    """Select the best video file from a Pexels video object.

    For shorts (is_short=True): prefer vertical files (height > width),
    target 1080x1920.
    For long videos (is_short=False): prefer landscape files (width > height),
    target 1280x720.
    """
    files = video.get("video_files", [])
    if not files:
        return None

    if is_short:
        portrait_files = [f for f in files if f.get("height", 0) > f.get("width", 0)]
        candidate_pool = portrait_files if portrait_files else files

        hd_files = [
            f for f in candidate_pool
            if f.get("width") == 1080 and f.get("height") == 1920
        ]
        if hd_files:
            return hd_files[0]

        closest = sorted(
            [f for f in candidate_pool if f.get("height", 0) > 0],
            key=lambda f: (
                abs(f.get("height", 0) - 1920),
                f.get("file_type", "") != "video/mp4",
            ),
        )
        if closest:
            return closest[0]
        return candidate_pool[0]

    else:
        hd_files = [
            f for f in files
            if f.get("width") == 1280 and f.get("quality") == "hd"
        ]
        if hd_files:
            return hd_files[0]

        medium_files = [f for f in files if f.get("width") == 1280]
        if medium_files:
            return medium_files[0]

        closest = sorted(
            [f for f in files if f.get("width", 0) > 0],
            key=lambda f: (
                abs(f.get("width", 0) - 1280),
                f.get("file_type", "") != "video/mp4",
            ),
        )
        if closest:
            return closest[0]

        return files[0]


async def download_video(video_url: str, output_path: str) -> str:
    """Download a video file from a URL to the given path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    async with httpx.AsyncClient() as client:
        async with client.stream("GET", video_url, timeout=120.0) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    logger.info(f"Downloaded video to {output_path}")
    return output_path


async def download_videos_for_segments(
    segments: list[dict],
    is_short: bool = False,
) -> list[dict]:
    """
    For each segment, search Pexels and download the best matching video.
    is_short controls the search orientation and file selection:
      - True  -> portrait (9:16) videos for YouTube Shorts
      - False -> landscape (16:9) videos for long YouTube videos
    Returns list of dicts with video_path, duration, and text for each
    **successfully downloaded** segment (skipped segments are excluded,
    so subtitle alignment stays correct — B7 fix).

    Downloads run concurrently via asyncio.gather (B16 fix), and the
    same Pexels video is never selected for two different segments (B17 fix).
    """
    orientation = "portrait" if is_short else "landscape"
    total = len(segments)
    used_video_ids: set[int] = set()

    async def _process_segment(i: int, segment: dict) -> dict | None:
        query = segment.get("pexels_query", "nature landscape")
        duration = segment.get("duration", 5)

        logger.info(f"  Segment {i + 1}/{total}: searching '{query}'...")
        videos = await search_videos(query, per_page=5, orientation=orientation)

        best_file = None
        selected_url = None

        for video in videos:
            vid_id = video.get("id")
            if vid_id in used_video_ids:
                continue
            vf = _pick_best_video_file(video, is_short=is_short)
            if vf:
                best_file = vf
                selected_url = vf.get("link")
                used_video_ids.add(vid_id)
                break

        if not selected_url:
            logger.warning(
                f"  No video found for segment {i + 1} (query='{query}') — skipping"
            )
            return None

        output_path = f"temp/segment_{i}.mp4"
        await download_video(selected_url, output_path)

        return {
            "video_path": output_path,
            "duration": duration,
            "text": segment.get("text", ""),
        }

    tasks = [_process_segment(i, seg) for i, seg in enumerate(segments)]
    results = await asyncio.gather(*tasks)

    # Filter out None (skipped) results while preserving order
    result = [r for r in results if r is not None]
    return result
