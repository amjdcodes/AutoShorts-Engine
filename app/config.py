import logging
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    GOOGLE_AI_STUDIO_API_KEY: str
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"

    # edge-tts fallback (free, no API key needed)
    # When ElevenLabs quota is exhausted, TTS falls back to edge-tts automatically.
    # Voices: ar-SA-HamedNeural, ar-EG-SalmaNeural, en-US-EmmaMultilingualNeural, etc.
    # Run `edge-tts --list-voices` to see all options.
    EDGE_TTS_VOICE: str = ""
    TTS_FALLBACK_EDGE: bool = True
    PEXELS_API_KEY: str
    YOUTUBE_CLIENT_ID: str
    YOUTUBE_CLIENT_SECRET: str
    YOUTUBE_REFRESH_TOKEN: str
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    CONTENT_LANGUAGE: str = "ar"
    VIDEO_TOPIC: str = ""
    VIDEO_DURATION_SECONDS: int = 60
    SHORT_MAX_DURATION_SECONDS: int = 180

    VIDEOS_PER_DAY: int = 1
    PUBLISH_TIMES: str = ""
    AUTO_PUBLISH: bool = False

    YOUTUBE_CATEGORY_ID: str = "22"
    YOUTUBE_SHORTS_CATEGORY_ID: str = ""
    YOUTUBE_PRIVACY: str = "public"

    SUBTITLE_ENABLED: bool = True
    SUBTITLE_FONT_SIZE: int = 42
    SUBTITLE_COLOR: str = "#FFFFFF"
    SUBTITLE_BG_OPACITY: float = 0.6

    FFMPEG_THREADS: int = 2
    FFMPEG_PRESET: str = "fast"
    FFMPEG_TIMEOUT: int = 900

    SECRET_KEY: str
    API_ACCESS_TOKEN: str
    ALLOWED_HOSTS: str = "127.0.0.1"

    TIMEZONE: str = "UTC"

    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
