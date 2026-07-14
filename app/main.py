import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.config import get_settings
from app.database import create_db
from app.scheduler import (
    setup_scheduler,
    create_and_schedule_daily_videos,
    recover_stuck_jobs,
    publish_or_approve,
)
from app.routers import jobs_router, stats_router, memory_router
from app.limiter import limiter
from app import logger_util

logger = logging.getLogger(__name__)

# Use professional color-coded formatter
logger_util.setup_logging(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logger_util.banner("Brambet Server — Starting Up", "YouTube Automation | Headless Mode")

    create_db()
    logger.info("Database initialized (SQLite WAL mode, chmod 600)")

    # Recover jobs stuck in 'processing' from a previous run,
    # and collect 'ready' jobs that were never uploaded to YouTube.
    recovered, ready_ids = recover_stuck_jobs()

    required = [
        "GOOGLE_AI_STUDIO_API_KEY",
        "ELEVENLABS_API_KEY",
        "PEXELS_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "SECRET_KEY",
        "API_ACCESS_TOKEN",
    ]
    missing = [k for k in required if not getattr(settings, k, None)]
    if missing:
        logger_util.error_box(
            "Missing required environment variables",
            ", ".join(missing),
            hint="Fill these in your .env file before starting the server.",
        )
        raise RuntimeError(f"Missing required env vars: {missing}")

    setup_scheduler(settings)

    if settings.TELEGRAM_BOT_TOKEN:
        import app.telegram_bot as telegram_bot

        try:
            await telegram_bot.start_bot()
        except Exception as e:
            logger_util.error_box("Telegram bot failed to start", str(e))
    else:
        logger.info("Telegram bot token not set — skipping bot startup")

    # Show configuration summary
    logger_util.summary(
        "Configuration",
        [
            ("Auto-publish", "ENABLED" if settings.AUTO_PUBLISH else "DISABLED (manual approval)"),
            ("Subtitles", "ENABLED" if settings.SUBTITLE_ENABLED else "DISABLED"),
            ("Videos/day", str(settings.VIDEOS_PER_DAY)),
            ("Duration", f"{settings.VIDEO_DURATION_SECONDS}s"),
            ("Language", settings.CONTENT_LANGUAGE),
            ("Content type", "SHORT (9:16)" if settings.VIDEO_DURATION_SECONDS <= settings.SHORT_MAX_DURATION_SECONDS else "LONG (16:9)"),
        ],
    )

    logger_util.success("Server running — Headless Mode")

    # Kick off the initial daily cycle in the background so it does NOT
    # block application startup. The full pipeline (download + TTS + MoviePy
    # render + subtitle burn) can take several minutes; awaiting it inside
    # lifespan would keep "Application startup complete" from ever printing
    # and the server would refuse HTTP requests the whole time.
    async def _initial_cycle():
        try:
            # Re-publish any 'ready' jobs from a previous run
            if ready_ids and settings.AUTO_PUBLISH:
                logger.info(f"Re-publishing {len(ready_ids)} ready job(s) from previous run...")
                for jid in ready_ids:
                    await publish_or_approve(jid)

            await create_and_schedule_daily_videos()
        except Exception as e:
            logger_util.error_box("Initial daily cycle failed", str(e))

    asyncio.create_task(_initial_cycle())

    yield

    logger.info("Shutting down server...")
    import app.telegram_bot as telegram_bot

    try:
        await telegram_bot.stop_bot()
    except Exception:
        pass


app = FastAPI(
    title="Brambet — YouTube Automation Server",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

settings = get_settings()

allowed_hosts = [h.strip() for h in settings.ALLOWED_HOSTS.split(",")]
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=allowed_hosts + ["localhost", "127.0.0.1"]
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(jobs_router.router, prefix="/api/jobs")
app.include_router(stats_router.router, prefix="/api/stats")
app.include_router(memory_router.router, prefix="/api/memory")


@app.get("/health")
@limiter.limit("10/minute")
async def health_check(request: Request):
    return {"status": "running", "mode": "headless"}
