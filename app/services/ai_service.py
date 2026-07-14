import json
import logging
import re
import google.generativeai as genai
from app.config import get_settings
from app.services.memory_service import (
    load_memory,
    format_memory_for_prompt,
    apply_memory_update,
)
from app import logger_util

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def build_prompt(topic: str, language: str, duration: int, is_short: bool) -> str:
    lang_instruction = "باللغة العربية الفصحى" if language == "ar" else "in English"
    title_lang = "بالعربية" if language == "ar" else "in English"

    memory = load_memory()
    memory_block = format_memory_for_prompt(memory)

    video_type = "فيديو قصير (YouTube Short - عمودي 9:16)" if is_short else "فيديو طويل ( YouTube - أفقي 16:9)"

    if is_short:
        segment_guidance = (
            "- كل مقطع يجب أن يكون 3-6 ثوانٍ (بما يناسب الفيديو القصير)\n"
            "- استعلامات البحث يجب أن تتناسب مع فيديوهات عمودية (portrait/vertical)"
        )
    else:
        segment_guidance = (
            "- كل مقطع يجب أن يكون 5-10 ثوانٍ\n"
            "- استعلامات البحث يجب أن تتناسب مع فيديوهات أفقية (landscape/horizontal)"
        )

    return f"""
أنت كاتب محتوى محترف ومبدع متخصص في إنشاء قصص مشوقة وملهمة على يوتيوب.
مهمتك هي كتابة قصة جذابة عن الموضوع التالي، وليس مجرد سكربت أو معلومات جافة.

الموضوع: {topic}
اللغة: {lang_instruction}
نوع الفيديو: {video_type}
المدة المستهدفة: {duration} ثانية تقريباً

{memory_block}

=== تعليمات كتابة القصة ===
- اكتب قصة ساحرة ومشوقة عن الموضوع، ليست مجرد معلومات أو سكربت عادي
- استخدم بنية قصصية واضحة: بداية جذابة (hook) -> تطوير -> ذروة (climax) -> خاتمة مؤثرة
- اجعل المشاهد يشعر وكأنه يعيش القصة، استخدم لغة حية وصور ذهنية قوية
- ابدأ بسؤال أو مشهد صادم أو عبارة تثير الفضول في أول 5 ثوانٍ
- استخدم أسلوب السرد القصصي: "تخيل أنك..."، "في يوم من الأيام..."، "هل تعلم أن..."
- اجعل النص العاطفي والمؤثر، ليس مجرد نقل حقائق
- ربط القصة بدرس أو رسالة في النهاية تجعل المشاهد يتذكر الفيديو
- القصة يجب أن تتدفق بشكل طبيعي كأنها رحلة يخوضها المشاهد

=== متطلبات تقنية ===
- {segment_guidance}
- لكل مقطع، اكتب جملة من القصة (text) واستعلام بحث بالإنجليزية (pexels_query)
- العنوان والوصف يجب أن يكونا {title_lang}
- الكلمات المفتاحية {title_lang}
- العنوان يجب أن يكون جذاباً ومثيراً للفضول (كعنوان قصة وليس عنوان معلومات)

=== إدارة الذاكرة ===
- لديك ذاكرة تحفظ الموضيع التي تم تناولها مسبقاً (موضحة أعلاه)
- لا تكرر أي موضوع تم تناوله في الذاكرة
- يمكنك تحديث ذاكرتك بإضافة موضوعك الحالي، أو إزالة موضوعات قديمة، أو إضافة إرشادات جديدة
- استخدم حقل "memory_update" في الإجابة لإدارة الذاكرة

IMPORTANT: Return ONLY valid JSON, no markdown, no extra text.
Use double quotes for all strings, escape any double quotes inside strings with backslash.

Return this exact JSON structure:
{{
  "title": "عنوان القصة الجذاب",
  "description": "وصف القصة (150-300 كلمة) يشوق المشاهد لمعرفة النهاية",
  "tags": ["tag1", "tag2", "tag3"],
  "voiceover_script": "نص القصة الكامل - مكتوب بأسلوب سردي مشوق وجذاب",
  "segments": [
    {{
      "text": "جملة من القصة لهذا المقطع",
      "pexels_query": "english search keywords for pexels video",
      "duration": 5
    }}
  ],
  "memory_update": {{
    "add_topics": ["الموضوع الذي تناولته في هذه القصة"],
    "remove_topics": ["أي موضوع قديم تريد إزالته من الذاكرة"],
    "add_guidelines": ["أي إرشاد جديد تريد حفظه للذاكرة"],
    "remove_guidelines": ["أي إرشاد قديم تريد إزالته"],
    "notes": "ملاحظات اختيارية عن هذا الموضوع"
  }}
}}
"""


def _clean_json_response(text: str) -> str:
    """Remove markdown code fences, control characters, and extract pure JSON."""
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    text = text.strip()

    if not text.startswith("{"):
        match = re.search(r"\{", text)
        if match:
            text = text[match.start():]
    if not text.endswith("}"):
        match = re.search(r"\}[^}]*$", text)
        if match:
            text = text[:match.start() + 1]

    return text.strip()


def _try_repair_json(text: str) -> str:
    """Attempt to repair common JSON issues like unescaped quotes in strings."""
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


def _validate_content(content: dict) -> dict:
    """Validate that all required fields exist with proper types."""
    required_fields = {
        "title": str,
        "description": str,
        "tags": list,
        "voiceover_script": str,
        "segments": list,
    }
    for field, expected_type in required_fields.items():
        if field not in content:
            raise ValueError(f"AI response missing required field: {field}")
        if not isinstance(content[field], expected_type):
            raise ValueError(f"Field '{field}' has wrong type: {type(content[field])}")

    if len(content["segments"]) == 0:
        raise ValueError("AI response has no segments")

    for i, seg in enumerate(content["segments"]):
        if not isinstance(seg, dict):
            raise ValueError(f"Segment {i} is not a dict")
        if "text" not in seg or "pexels_query" not in seg:
            raise ValueError(f"Segment {i} missing required fields")
        if "duration" not in seg:
            seg["duration"] = 5

    if "memory_update" not in content:
        content["memory_update"] = {}
    if not isinstance(content["memory_update"], dict):
        content["memory_update"] = {}

    return content


async def _try_generate(model, prompt: str) -> str:
    """Make one generation attempt, return raw text."""
    response = await model.generate_content_async(prompt)
    return response.text


def is_short_video(duration: int, short_max: int = 180) -> bool:
    """Determine if a video should be a Short based on its duration.
    Videos of 3s to 3 minutes (180s) are Shorts. Over 180s are long videos.
    YouTube Shorts require at least 3 seconds (B22)."""
    return 3 <= duration <= short_max


async def generate_content() -> dict:
    """
    Generate video content (title, script, segments) using Google AI Studio (Gemini).
    The prompt asks for an engaging story, not a dry script.
    Memory of previously covered topics is included to avoid repetition.
    Returns the parsed JSON dict from the AI response.
    Retries up to MAX_RETRIES times on parse failure.
    """
    settings = get_settings()

    genai.configure(api_key=settings.GOOGLE_AI_STUDIO_API_KEY)

    duration = settings.VIDEO_DURATION_SECONDS
    short = is_short_video(duration, settings.SHORT_MAX_DURATION_SECONDS)

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        },
    )

    prompt = build_prompt(
        topic=settings.VIDEO_TOPIC,
        language=settings.CONTENT_LANGUAGE,
        duration=duration,
        is_short=short,
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_text = await _try_generate(model, prompt)
            cleaned = _clean_json_response(raw_text)
            repaired = _try_repair_json(cleaned)
            content = json.loads(repaired)
            content = _validate_content(content)

            if content.get("memory_update"):
                apply_memory_update(
                    content["memory_update"],
                    title=content.get("title", ""),
                    language=settings.CONTENT_LANGUAGE,
                )
                logger.info("Applied AI memory update from response")

            logger.info(
                f"Generated content (attempt {attempt}): "
                f"title='{content['title']}', "
                f"{len(content['segments'])} segments, "
                f"{len(content['voiceover_script'])} chars, "
                f"is_short={short}"
            )
            return content

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                f"JSON parse failed (attempt {attempt}/{MAX_RETRIES}): {e}"
            )
        except ValueError as e:
            last_error = e
            logger.warning(
                f"Content validation failed (attempt {attempt}/{MAX_RETRIES}): {e}"
            )

    logger_util.error_box(
        f"AI generation failed after {MAX_RETRIES} attempts",
        f"Last error: {last_error}",
        hint="Try increasing MAX_RETRIES or switching to gemini-2.5-pro.",
    )
    raise ValueError(
        f"AI failed to return valid JSON after {MAX_RETRIES} attempts: {last_error}"
    )
