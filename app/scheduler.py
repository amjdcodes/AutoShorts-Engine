import logging
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import anyio
from sqlmodel import Session, select

from app.config import get_settings
from app.database import engine
from app.models import Job
from app import logger_util

logger = logging.getLogger(__name__)

_tz: ZoneInfo = ZoneInfo("UTC")
scheduler = AsyncIOScheduler(timezone="UTC")


def _get_tz() -> ZoneInfo:
    """Return the configured timezone, caching the ZoneInfo object."""
    global _tz
    settings = get_settings()
    tz_name = settings.TIMEZONE or "UTC"
    if _tz.key != tz_name:
        _tz = ZoneInfo(tz_name)
    return _tz


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _now() -> datetime:
    """Return current time in the configured timezone."""
    return datetime.now(_get_tz())

_pipeline_lock = asyncio.Lock()
_pipeline_running = asyncio.Event()

# Maximum time for video rendering (download + TTS + MoviePy + subtitle burn).
# Read from FFMPEG_TIMEOUT in .env (default 900s) — allows tuning for slow devices.
_VIDEO_TIMEOUT_SECONDS = 900


def calculate_publish_times(
    videos_per_day: int, publish_times_str: str
) -> list[datetime]:
    """
    Calculate publish times for today (in the configured timezone).
    - If PUBLISH_TIMES is set: use those times.
    - If empty: distribute evenly from 08:00 to 22:00.
    - If a calculated time has already passed today, advance it to tomorrow
      so DateTrigger always targets a future date.
    Returns timezone-aware datetimes.
    """
    tz = _get_tz()
    now = datetime.now(tz)
    today = now.replace(second=0, microsecond=0)

    if publish_times_str and publish_times_str.strip():
        times = []
        parts = [p.strip() for p in publish_times_str.split(",") if p.strip()]
        for t in parts[:videos_per_day]:
            try:
                h, m = map(int, t.split(":"))
                dt = today.replace(hour=h, minute=m)
                if dt <= now:
                    dt += timedelta(days=1)
                times.append(dt)
            except (ValueError, TypeError):
                logger.warning(f"Invalid publish time format: {t}")
                continue
        return times

    start_hour = 8
    end_hour = 22
    total_minutes = (end_hour - start_hour) * 60

    if videos_per_day <= 1:
        intervals = [0]
    else:
        interval = total_minutes // (videos_per_day - 1)
        intervals = [i * interval for i in range(videos_per_day)]

    times = []
    for minutes_offset in intervals:
        dt = today.replace(hour=start_hour, minute=0) + timedelta(
            minutes=minutes_offset
        )
        if dt <= now:
            dt += timedelta(days=1)
        times.append(dt)
    return times


def get_job(job_id: int) -> Job | None:
    """Get a job from the database by ID."""
    with Session(engine) as session:
        return session.get(Job, job_id)


def update_job(job_id: int, **kwargs):
    """Update job fields in the database."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)
            job.updated_at = _utcnow()
            session.add(job)
            session.commit()


def create_new_job(language: str = "ar") -> int:
    """Create a new pending job and return its ID."""
    with Session(engine) as session:
        job = Job(status="pending", language=language)
        session.add(job)
        session.commit()
        session.refresh(job)
        logger.info(f"Created new job id={job.id}")
        return job.id


def recover_stuck_jobs() -> tuple[int, list[int]]:
    """Recover jobs from an interrupted previous run.

    - Jobs stuck in 'processing' are marked as 'failed' (they will never complete).
    - Jobs in 'ready' status (video created but never uploaded) are collected
      for re-publishing when AUTO_PUBLISH is enabled.

    Returns (recovered_count, ready_job_ids).
    """
    recovered = 0
    ready_ids: list[int] = []
    with Session(engine) as session:
        # Mark stuck 'processing' jobs as failed
        stuck = session.exec(
            select(Job).where(Job.status == "processing")
        ).all()
        for job in stuck:
            job.status = "failed"
            job.error_message = (
                "Job was interrupted (server restarted while processing)"
            )
            job.updated_at = _utcnow()
            session.add(job)
            recovered += 1

        # Collect 'ready' jobs that were never published
        ready_jobs = session.exec(
            select(Job).where(Job.status == "ready")
        ).all()
        for job in ready_jobs:
            ready_ids.append(job.id)

        if recovered:
            session.commit()
            logger_util.warning_box(
                f"Recovered {recovered} stuck job(s)",
                "These jobs were left in 'processing' from a previous run "
                "and have been marked as 'failed'. Check the database for details.",
            )

    if ready_ids:
        logger_util.warning_box(
            f"{len(ready_ids)} ready job(s) awaiting upload",
            f"Job IDs: {ready_ids}. These videos were created but never "
            "uploaded to YouTube. They will be re-published on startup.",
        )

    return recovered, ready_ids


# ─── YouTube upload helper ───────────────────────────────────────────


def _build_yt_kwargs(job: Job, settings) -> dict:
    """Build the keyword arguments dict for yt_upload from a job."""
    return {
        "video_path": job.video_path,
        "title": job.title,
        "description": job.description,
        "tags": job.get_tags_list(),
        "language": job.language,
        "category_id": settings.YOUTUBE_CATEGORY_ID,
        "privacy_status": settings.YOUTUBE_PRIVACY,
        "is_short": job.is_short,
    }


async def _upload_to_youtube(job_id: int) -> bool:
    """Upload a ready/approved job to YouTube. Returns True on success.

    Handles retry with exponential backoff and quota-exceeded detection.
    On quota exhaustion, marks job as 'quota_exceeded' and reschedules
    for the next day. Used by publish_or_approve, handle_approval_callback,
    and the approve endpoint.
    """
    from app.services.youtube_service import upload_video as yt_upload, QuotaExceededError

    settings = get_settings()
    job = get_job(job_id)
    if not job:
        logger_util.warning_box(f"Cannot upload job #{job_id}", "Job not found")
        return False

    is_short = job.is_short
    yt_kwargs = _build_yt_kwargs(job, settings)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger_util.phase("Uploading to YouTube", job_id)
            logger.info(
                f"Mode: upload | Type: {'Short (9:16)' if is_short else 'Long (16:9)'}"
                f" | Attempt {attempt}/{max_retries}"
            )
            result = await anyio.to_thread.run_sync(
                lambda: yt_upload(**yt_kwargs)
            )
            update_job(
                job.id,
                status="published",
                youtube_video_id=result.get("video_id", ""),
                youtube_url=result.get("url", ""),
                published_at=_utcnow(),
            )
            logger_util.success(f"YouTube upload complete: {result.get('url')}")
            return True

        except QuotaExceededError as e:
            update_job(job.id, status="quota_exceeded", error_message=str(e))
            logger_util.error_box(
                f"YouTube quota exceeded for job #{job_id}",
                str(e),
                hint="Daily upload quota exhausted. Job will be retried tomorrow.",
            )
            _reschedule_for_tomorrow(job_id)
            return False

        except Exception as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    f"YouTube upload attempt {attempt} failed, "
                    f"retrying in {wait}s: {e}"
                )
                await asyncio.sleep(wait)
            else:
                update_job(job.id, status="failed", error_message=str(e))
                logger_util.error_box(
                    f"YouTube upload failed for job #{job_id} after {max_retries} attempts",
                    str(e),
                    hint="Check YOUTUBE_REFRESH_TOKEN, network, and quota.",
                )
                return False
    return False


def _reschedule_for_tomorrow(job_id: int):
    """Reschedule a quota-exceeded job for the same time tomorrow."""
    job = get_job(job_id)
    if not job:
        return
    tz = _get_tz()
    tomorrow = datetime.now(tz) + timedelta(days=1)
    if job.scheduled_publish_time:
        original = job.scheduled_publish_time
        if original.tzinfo is None:
            original = original.replace(tzinfo=tz)
        run_date = tomorrow.replace(
            hour=original.hour, minute=original.minute, second=0, microsecond=0
        )
    else:
        run_date = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)

    scheduler.add_job(
        _retry_quota_job,
        trigger=DateTrigger(run_date=run_date),
        args=[job_id],
        id=f"quota_retry_{job_id}",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        f"Job #{job_id} rescheduled for tomorrow at "
        f"{run_date.strftime('%H:%M %Z')}"
    )


async def _retry_quota_job(job_id: int):
    """Retry a job that was previously quota-exceeded."""
    job = get_job(job_id)
    if not job or job.status != "quota_exceeded":
        return
    logger.info(f"Retrying job #{job_id} after quota reset")
    await _upload_to_youtube(job_id)


async def publish_or_approve(job_id: int):
    """Publish video automatically or send for approval via Telegram.

    Accepts jobs in 'ready' or 'awaiting_approval' status.
    """
    settings = get_settings()
    job = get_job(job_id)
    if not job:
        logger_util.warning_box(
            f"Cannot publish job #{job_id}", "Job not found"
        )
        return
    if job.status not in ("ready", "awaiting_approval"):
        logger_util.warning_box(
            f"Cannot publish job #{job_id}",
            f"Job status is '{job.status}', expected 'ready' or 'awaiting_approval'. Skipping.",
        )
        return

    if settings.AUTO_PUBLISH or job.status == "awaiting_approval":
        await _upload_to_youtube(job_id)
    else:
        from app.telegram_bot import send_approval_request

        update_job(job.id, status="awaiting_approval")
        await send_approval_request(job.to_dict(), job.id)
        logger_util.success(f"Approval request sent to Telegram for job #{job_id}")


async def handle_approval_callback(job_id: int, action: str):
    """Handle approval/cancel actions from Telegram callback."""
    if action == "approve":
        job = get_job(job_id)
        if job and job.status == "awaiting_approval":
            await _upload_to_youtube(job_id)

    elif action == "cancel":
        update_job(job_id, status="cancelled")
        logger.info(f"Job #{job_id} cancelled via Telegram")


# ─── Main automation pipeline ────────────────────────────────────────


async def run_automation_pipeline(produce_only: bool = False) -> int | None:
    """
    Full automation pipeline: generate content, download videos,
    create TTS, montage, subtitle burning.
    Memory of previously covered topics is included in generation to avoid repetition.
    Returns job_id on success, None on failure.
    """
    from app.services.ai_service import generate_content as ai_generate, is_short_video
    from app.services.pexels_service import download_videos_for_segments
    from app.services.tts_service import text_to_speech
    from app.services.video_service import create_final_video, cleanup_temp_files

    settings = get_settings()
    duration = settings.VIDEO_DURATION_SECONDS
    short = is_short_video(duration, settings.SHORT_MAX_DURATION_SECONDS)
    video_type = "short" if short else "long"

    job_id = create_new_job(settings.CONTENT_LANGUAGE)
    update_job(
        job_id,
        status="processing",
        is_short=short,
        duration_seconds=duration,
        video_type=video_type,
    )

    logger_util.banner(
        f"Pipeline Started — Job #{job_id}",
        f"{video_type.upper()} | {duration}s | {'9:16 SHORT' if short else '16:9 LONG'}",
    )

    total_steps = 5
    start_time = _utcnow()

    try:
        # ── Step 1: AI content generation ──────────────────────────
        logger_util.step(1, total_steps, "AI content generation (Gemini)")
        content = await ai_generate()
        update_job(
            job_id,
            title=content["title"],
            description=content["description"],
            script=content["voiceover_script"],
        )
        job = get_job(job_id)
        if job and content.get("tags"):
            job.set_tags_list(content["tags"])
            update_job(job_id, tags=job.tags)
        logger_util.success(
            f"Content generated: '{content['title']}' "
            f"({len(content['segments'])} segments)"
        )

        # ── Step 2: Download stock videos ──────────────────────────
        logger_util.step(2, total_steps, "Downloading stock videos (Pexels)")
        seg_info = await download_videos_for_segments(
            content["segments"], is_short=short
        )
        logger_util.success(f"Downloaded {len(seg_info)} video segments")

        # ── Step 3: Text-to-speech ─────────────────────────────────
        logger_util.step(3, total_steps, "Text-to-speech (ElevenLabs)")
        audio_path = await text_to_speech(
            content["voiceover_script"], f"temp/audio_{job_id}.mp3"
        )
        update_job(job_id, audio_path=audio_path)
        logger_util.success(f"Audio generated: {audio_path}")

        # ── Step 4: Video montage ──────────────────────────────────
        logger_util.step(4, total_steps, "Video montage (MoviePy + FFmpeg)")

        # Subtitles are generated inside create_final_video after the
        # actual audio duration is known (B5 fix), using the downloaded
        # segments (seg_info) for correct alignment (B7 fix).

        # Use FFMPEG_TIMEOUT from settings (default 900s) — allows tuning
        # for slow devices. The timeout covers the full create_final_video call.
        video_timeout = max(300, settings.FFMPEG_TIMEOUT)
        try:
            final_video = await asyncio.wait_for(
                anyio.to_thread.run_sync(
                    lambda: create_final_video(
                        segments=content["segments"],
                        video_paths=seg_info,
                        audio_path=audio_path,
                        language=settings.CONTENT_LANGUAGE,
                        output_path=f"output/job_{job_id}.mp4",
                        subtitle_segments=seg_info if settings.SUBTITLE_ENABLED else None,
                        is_short=short,
                    )
                ),
                timeout=video_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Video rendering timed out after {video_timeout}s — "
                "the FFmpeg/MoviePy process may be stuck. Check CPU and disk I/O. "
                f"Increase FFMPEG_TIMEOUT in .env if your device is slow."
            )

        update_job(job_id, status="ready", video_path=final_video)
        logger_util.success(f"Video ready: {final_video}")

        # ── Step 5: Memory update ──────────────────────────────────
        # The AI already updates memory via apply_memory_update in ai_service.py.
        # No duplicate topic registration here (B9).
        logger_util.step(5, total_steps, "Memory update")
        logger_util.success("Memory managed by AI service")

        # ── Summary ────────────────────────────────────────────────
        elapsed = (_utcnow() - start_time).total_seconds()
        logger_util.summary(
            f"Pipeline Complete — Job #{job_id}",
            [
                ("Title", content["title"]),
                ("Type", video_type.upper()),
                ("Segments", str(len(seg_info))),
                ("Duration", f"{duration}s"),
                ("Video file", final_video),
                ("Elapsed", f"{elapsed:.1f}s"),
            ],
        )

        if not produce_only:
            await publish_or_approve(job_id)

        return job_id

    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        logger_util.error_box(
            f"Pipeline FAILED — Job #{job_id}",
            str(e),
            hint="Check the full traceback below for the root cause.",
        )
        logger.debug(traceback.format_exc())
        return None
    finally:
        # Clean up temp files regardless of success or failure (B2)
        cleanup_temp_files(job_id)


# ─── Daily cycle orchestration ───────────────────────────────────────


async def create_and_schedule_daily_videos():
    """Run daily cycle: create all videos, then schedule each for publishing
    at its designated time. All videos are scheduled uniformly — no special
    immediate publish for the first one (B3 fix).

    Protected by a lock to prevent concurrent pipeline runs.
    """
    if _pipeline_running.is_set():
        logger_util.warning_box(
            "Daily cycle already running",
            "A previous cycle is still in progress — skipping this trigger.",
        )
        return

    async with _pipeline_lock:
        if _pipeline_running.is_set():
            return
        _pipeline_running.set()
        try:
            settings = get_settings()
            logger_util.banner(
                "Daily Video Cycle",
                f"{settings.VIDEOS_PER_DAY} video(s) to create",
            )

            publish_times = calculate_publish_times(
                settings.VIDEOS_PER_DAY, settings.PUBLISH_TIMES
            )

            created_jobs = []

            for i in range(settings.VIDEOS_PER_DAY):
                logger.info(f"  Creating video {i + 1}/{settings.VIDEOS_PER_DAY}...")
                job_id = await run_automation_pipeline(produce_only=True)
                if job_id:
                    publish_time = publish_times[i] if i < len(publish_times) else None
                    if publish_time:
                        update_job(
                            job_id,
                            scheduled_publish_time=publish_time,
                            publish_time_iso=publish_time.isoformat(),
                        )
                    created_jobs.append((job_id, publish_time))

            # Schedule ALL jobs uniformly — including the first one.
            # If publish_time has already passed, publish immediately.
            now = _now()
            for job_id, publish_time in created_jobs:
                if publish_time and publish_time > now:
                    scheduler.add_job(
                        publish_or_approve,
                        trigger=DateTrigger(run_date=publish_time),
                        args=[job_id],
                        id=f"publish_{job_id}",
                        replace_existing=True,
                        misfire_grace_time=3600,
                    )
                    logger.info(
                        f"Scheduled job #{job_id} for "
                        f"{publish_time.strftime('%H:%M %Z')}"
                    )
                else:
                    if publish_time:
                        logger.info(
                            f"Publish time {publish_time.strftime('%H:%M %Z')} "
                            f"has passed for job #{job_id} — publishing now"
                        )
                    else:
                        logger.info(
                            f"No publish time for job #{job_id} — publishing now"
                        )
                    await publish_or_approve(job_id)

            logger_util.divider()
        finally:
            _pipeline_running.clear()


def setup_scheduler(settings):
    """Configure the daily scheduler."""
    from app.telegram_bot import set_approval_callback

    set_approval_callback(handle_approval_callback)

    scheduler.remove_all_jobs()

    tz = _get_tz()
    # misfire_grace_time: if a trigger fires late (e.g. server was busy or
    # DateTrigger run_date is in the past), allow up to 1 hour of grace
    # before the job is considered a misfire and skipped. Without this,
    # APScheduler silently drops jobs whose run_date is even 2 seconds in
    # the past — causing videos to never be uploaded.
    scheduler.add_job(
        create_and_schedule_daily_videos,
        CronTrigger(hour=0, minute=1, timezone=tz),
        id="daily_cycle",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if not scheduler.running:
        scheduler.start()

    logger.info(f"Scheduler ready — daily cycle at 00:01 {tz.key}")
