import logging
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

_app_instance: Application | None = None
_approval_callback = None


def set_approval_callback(callback):
    """Register a callback to handle approve/cancel actions from Telegram."""
    global _approval_callback
    _approval_callback = callback


async def send_approval_request(video_info: dict, job_id: int):
    """
    Send an approval request to the configured Telegram chat.
    Uses Bot directly for sending (B10 fix) — no Application lifecycle issues.
    Includes publish/cancel buttons.
    """
    settings = get_settings()

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping approval request")
        return

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    keyboard = [
        [
            InlineKeyboardButton("Publish Now", callback_data=f"publish_{job_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel_{job_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    title = video_info.get("title", "Untitled")
    description = video_info.get("description", "")[:200]
    tags = video_info.get("tags", [])
    duration = video_info.get("duration_seconds", 0)
    is_short = video_info.get("is_short", False)
    video_type = "Short" if is_short else "Long"
    created = video_info.get("created_at")

    caption = (
        f"🎬 *New Video Ready for Publishing*\n\n"
        f"📌 Title: {title}\n"
        f"📝 Description: {description}...\n"
        f"🏷️ Tags: {', '.join(tags) if isinstance(tags, list) else tags}\n"
        f"⏱️ Duration: {duration} seconds\n"
        f"📹 Type: {video_type} ({'9:16 Shorts' if is_short else '16:9'})\n"
    )
    if created:
        time_str = (
            created.isoformat() if isinstance(created, datetime) else str(created)
        )
        caption += f"🕐 Created: {time_str}\n"

    caption += "\nChoose an action:"

    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID,
        text=caption,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    logger.info(f"Telegram approval request sent for job {job_id}")


async def handle_callback(update: Update, context):
    """Handle inline button callbacks from Telegram."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data:
        return

    try:
        if "_" not in data:
            return
        action, job_id_str = data.split("_", 1)
        job_id = int(job_id_str)
    except (ValueError, IndexError):
        logger.error(f"Invalid callback data: {data}")
        return

    if action == "publish":
        if _approval_callback:
            await _approval_callback(job_id, "approve")
        await query.edit_message_text(f"✅ Video (job #{job_id}) approved for publishing!")
        logger.info(f"Telegram approved publish for job {job_id}")

    elif action == "cancel":
        if _approval_callback:
            await _approval_callback(job_id, "cancel")
        await query.edit_message_text(f"❌ Video (job #{job_id}) cancelled.")
        logger.info(f"Telegram cancelled job {job_id}")

    else:
        await query.edit_message_text(f"Unknown action: {action}")


async def start_bot():
    """Start the Telegram bot in polling mode for handling callbacks."""
    settings = get_settings()

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot token not set — skipping bot startup")
        return

    global _app_instance
    _app_instance = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    _app_instance.add_handler(CallbackQueryHandler(handle_callback))

    await _app_instance.initialize()
    await _app_instance.start()
    # drop_pending_updates clears any leftover getUpdates offset from a
    # previous run, which otherwise causes 409 Conflict on the first poll.
    await _app_instance.updater.start_polling(drop_pending_updates=True)

    logger.info("Telegram bot started")
    logger.info(
        "If you see repeated '409 Conflict' errors, another process is still "
        "polling this bot token — kill it before restarting."
    )


async def stop_bot():
    """Stop the Telegram bot gracefully."""
    global _app_instance
    if _app_instance:
        await _app_instance.updater.stop()
        await _app_instance.stop()
        await _app_instance.shutdown()
        _app_instance = None
        logger.info("Telegram bot stopped")
