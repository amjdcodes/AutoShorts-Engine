import logging
import os

logger = logging.getLogger(__name__)

_MODELS_FALLBACK = ["eleven_v3", "eleven_multilingual_v2", "eleven_turbo_v2_5"]

# Default edge-tts voices per language
_DEFAULT_EDGE_VOICES = {
    "ar": "ar-SA-HamedNeural",
    "en": "en-US-EmmaMultilingualNeural",
}


def _is_quota_exceeded(error: Exception) -> bool:
    """Check if an ElevenLabs error indicates quota/credit exhaustion."""
    error_str = str(error).lower()
    return (
        "quota_exceeded" in error_str
        or "insufficient_quota" in error_str
        or "credits remaining" in error_str
        or ("quota" in error_str and "exceed" in error_str)
    )


async def _edge_tts_generate(text: str, output_path: str, voice: str) -> str:
    """Generate speech using edge-tts (Microsoft Edge online TTS).

    Free, no API key required. Falls back automatically when ElevenLabs
    quota is exhausted.
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    logger.info(
        f"edge-tts audio saved: {output_path} (voice={voice}, "
        f"{file_size / 1024:.1f} KB)"
    )
    return output_path


async def text_to_speech(text: str, output_path: str = "temp/audio.mp3") -> str:
    """Convert text to speech. Tries ElevenLabs first, then falls back to
    edge-tts (free) when quota is exhausted or all models fail.

    Priority:
      1. ElevenLabs (eleven_v3 -> eleven_multilingual_v2 -> eleven_turbo_v2_5)
      2. edge-tts (Microsoft Edge online TTS — free, no key needed)

    Saves the audio as an MP3 file and returns the path.
    """
    from app.config import get_settings

    settings = get_settings()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # ── Try ElevenLabs first ──────────────────────────────────────
    api_key = settings.ELEVENLABS_API_KEY
    voice_id = settings.ELEVENLABS_VOICE_ID

    if api_key and voice_id:
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError:
            logger.warning(
                "ElevenLabs SDK not installed — falling back to edge-tts"
            )
        else:
            client = ElevenLabs(api_key=api_key)
            quota_hit = False
            last_error = None

            for model_id in _MODELS_FALLBACK:
                try:
                    audio = client.text_to_speech.convert(
                        text=text,
                        voice_id=voice_id,
                        model_id=model_id,
                        output_format="mp3_44100_128",
                    )

                    if isinstance(audio, (bytes, bytearray)):
                        with open(output_path, "wb") as f:
                            f.write(audio)
                    elif hasattr(audio, "__iter__"):
                        with open(output_path, "wb") as f:
                            for chunk in audio:
                                if isinstance(chunk, (bytes, bytearray)):
                                    f.write(chunk)
                                else:
                                    f.write(
                                        chunk if isinstance(chunk, bytes) else chunk
                                    )
                    else:
                        with open(output_path, "wb") as f:
                            f.write(audio)

                    logger.info(f"TTS audio saved: {output_path} (model={model_id})")
                    return output_path

                except Exception as e:
                    last_error = e
                    if _is_quota_exceeded(e):
                        quota_hit = True
                        logger.warning(
                            f"ElevenLabs quota exceeded on model '{model_id}': {e}"
                        )
                        break  # No point trying other models — same quota
                    logger.warning(
                        f"TTS model '{model_id}' failed: {e}, trying next..."
                    )

            if quota_hit:
                logger.warning(
                    "ElevenLabs quota exhausted — falling back to edge-tts"
                )
            elif last_error:
                logger.warning(
                    f"All ElevenLabs models failed — falling back to edge-tts. "
                    f"Last error: {last_error}"
                )
    else:
        logger.info("ElevenLabs not configured — using edge-tts directly")

    # ── Fallback to edge-tts ──────────────────────────────────────
    if not settings.TTS_FALLBACK_EDGE:
        raise RuntimeError(
            "All TTS providers failed and edge-tts fallback is disabled "
            "(TTS_FALLBACK_EDGE=false)"
        )

    # Determine the edge-tts voice to use
    edge_voice = settings.EDGE_TTS_VOICE
    if not edge_voice:
        edge_voice = _DEFAULT_EDGE_VOICES.get(
            settings.CONTENT_LANGUAGE, "en-US-EmmaMultilingualNeural"
        )

    try:
        return await _edge_tts_generate(text, output_path, edge_voice)
    except Exception as e:
        raise RuntimeError(
            f"All TTS providers failed. edge-tts error: {e}"
        ) from e
