import logging
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from app.config import get_settings
from app import logger_util

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when the YouTube API daily upload quota is exhausted."""
    pass


def get_youtube_client():
    """Create an authenticated YouTube API client using the refresh token."""
    settings = get_settings()

    creds = Credentials(
        token=None,
        refresh_token=settings.YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.YOUTUBE_CLIENT_ID,
        client_secret=settings.YOUTUBE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    language: str = "ar",
    category_id: str = "22",
    privacy_status: str = "public",
    is_short: bool = False,
) -> dict:
    """
    Upload a video to YouTube.
    If is_short is True, the video is uploaded as a YouTube Short
    (vertical 9:16, #shorts hashtag added to description for discovery).
    Returns the API response containing the video ID and URL.

    Raises QuotaExceededError when the daily upload quota is exhausted,
    so the caller can reschedule for the next day instead of marking
    the job as permanently failed (B11 fix).

    This is a blocking I/O function — use anyio.to_thread.run_sync() for async.
    """
    if not video_path:
        raise ValueError("video_path is required")

    youtube = get_youtube_client()

    final_tags = list(tags[:30])
    final_description = description[:5000]

    if is_short:
        if "#shorts" not in final_description.lower():
            final_description = final_description.rstrip() + "\n\n#shorts"
        if "shorts" not in [t.lower() for t in final_tags]:
            final_tags.append("shorts")
        short_category = settings_category_for_shorts()
        cat_id = short_category or category_id
        logger.info("Uploading as YouTube Short (vertical 9:16)")
    else:
        cat_id = category_id
        logger.info("Uploading as regular YouTube video (landscape 16:9)")

    logger.info(f"Title: {title[:80]}")
    logger.info(f"Tags: {', '.join(final_tags[:5])}{'...' if len(final_tags) > 5 else ''}")

    body = {
        "snippet": {
            "title": title[:100],
            "description": final_description,
            "tags": final_tags,
            "categoryId": cat_id,
            "defaultLanguage": language,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/*",
        chunksize=256 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100) if status.progress else 0
                logger.info(f"Upload progress: {progress}%")
        except HttpError as e:
            reason = _extract_error_reason(e)
            if reason == "quotaExceeded" or e.resp.status == 429:
                raise QuotaExceededError(
                    "YouTube daily upload quota exceeded. "
                    "The job will be rescheduled for tomorrow."
                ) from e
            raise

    video_id = response.get("id", "")
    if is_short:
        youtube_url = f"https://www.youtube.com/shorts/{video_id}"
    else:
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    logger_util.success(f"YouTube upload complete: {youtube_url}")
    return {
        "video_id": video_id,
        "url": youtube_url,
        "title": title,
        "is_short": is_short,
    }


def _extract_error_reason(e: HttpError) -> str:
    """Extract the error reason string from a googleapiclient HttpError."""
    try:
        content = e.error_details
        if content and isinstance(content, list):
            for err in content:
                if isinstance(err, dict) and "reason" in err:
                    return err["reason"]
    except Exception:
        pass
    return ""


def settings_category_for_shorts() -> str | None:
    """Return a category override for shorts if configured, else None."""
    settings = get_settings()
    short_cat = getattr(settings, "YOUTUBE_SHORTS_CATEGORY_ID", "")
    return short_cat if short_cat else None
