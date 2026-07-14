import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_DIR = "memory"
MEMORY_FILE = os.path.join(MEMORY_DIR, "ai_memory.json")

_DEFAULT_MEMORY = {
    "covered_topics": [],
    "guidelines": [],
    "last_updated": None,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_memory_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)


def load_memory() -> dict:
    """Load the AI memory from the JSON file. Returns a default structure if missing."""
    _ensure_memory_dir()

    if not os.path.exists(MEMORY_FILE):
        logger.info("Memory file not found, creating default")
        save_memory(_DEFAULT_MEMORY.copy())
        return _DEFAULT_MEMORY.copy()

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memory = json.load(f)
        if "covered_topics" not in memory:
            memory["covered_topics"] = []
        if "guidelines" not in memory:
            memory["guidelines"] = []
        return memory
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load memory file: {e}, resetting to default")
        default = _DEFAULT_MEMORY.copy()
        save_memory(default)
        return default


def save_memory(memory: dict):
    """Save the memory dict to the JSON file."""
    _ensure_memory_dir()
    memory["last_updated"] = _utcnow_iso()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    logger.info(f"Memory saved: {len(memory.get('covered_topics', []))} topics, "
                f"{len(memory.get('guidelines', []))} guidelines")


def get_covered_topics() -> list[str]:
    """Return a list of topic titles that have been covered."""
    memory = load_memory()
    return [t.get("topic", "") for t in memory.get("covered_topics", []) if t.get("topic")]


def get_guidelines() -> list[str]:
    """Return the list of guidelines stored in memory."""
    memory = load_memory()
    return memory.get("guidelines", [])


def add_topic(topic: str, title: str = "", language: str = "ar", notes: str = "") -> bool:
    """Add a topic to the covered topics list. Returns True if added, False if duplicate."""
    if not topic or not topic.strip():
        return False

    memory = load_memory()
    topics = memory.get("covered_topics", [])

    existing = [t for t in topics if t.get("topic", "").strip().lower() == topic.strip().lower()]
    if existing:
        existing[0]["topic"] = topic.strip()
        existing[0]["title"] = title or existing[0].get("title", "")
        existing[0]["language"] = language
        if notes:
            existing[0]["notes"] = notes
        existing[0]["date"] = _utcnow_iso()
        save_memory(memory)
        logger.info(f"Updated existing topic in memory: {topic}")
        return True

    topics.append({
        "topic": topic.strip(),
        "title": title,
        "language": language,
        "notes": notes,
        "date": _utcnow_iso(),
    })
    memory["covered_topics"] = topics
    save_memory(memory)
    logger.info(f"Added topic to memory: {topic}")
    return True


def remove_topic(topic: str) -> bool:
    """Remove a topic from memory by matching text. Returns True if removed."""
    memory = load_memory()
    topics = memory.get("covered_topics", [])
    original_count = len(topics)

    topics = [
        t for t in topics
        if t.get("topic", "").strip().lower() != topic.strip().lower()
    ]

    if len(topics) == original_count:
        return False

    memory["covered_topics"] = topics
    save_memory(memory)
    logger.info(f"Removed topic from memory: {topic}")
    return True


def remove_topic_by_index(index: int) -> bool:
    """Remove a topic from memory by its index. Returns True if removed."""
    memory = load_memory()
    topics = memory.get("covered_topics", [])

    if index < 0 or index >= len(topics):
        return False

    removed = topics.pop(index)
    memory["covered_topics"] = topics
    save_memory(memory)
    logger.info(f"Removed topic by index {index}: {removed.get('topic', '')}")
    return True


def add_guideline(guideline: str) -> bool:
    """Add a guideline to memory. Returns True if added."""
    if not guideline or not guideline.strip():
        return False

    memory = load_memory()
    guidelines = memory.get("guidelines", [])

    if guideline.strip() in guidelines:
        return False

    guidelines.append(guideline.strip())
    memory["guidelines"] = guidelines
    save_memory(memory)
    logger.info(f"Added guideline: {guideline[:50]}...")
    return True


def remove_guideline(guideline: str) -> bool:
    """Remove a guideline from memory. Returns True if removed."""
    memory = load_memory()
    guidelines = memory.get("guidelines", [])

    if guideline.strip() in guidelines:
        guidelines.remove(guideline.strip())
        memory["guidelines"] = guidelines
        save_memory(memory)
        return True
    return False


def remove_guideline_by_index(index: int) -> bool:
    """Remove a guideline by index. Returns True if removed."""
    memory = load_memory()
    guidelines = memory.get("guidelines", [])

    if index < 0 or index >= len(guidelines):
        return False

    guidelines.pop(index)
    memory["guidelines"] = guidelines
    save_memory(memory)
    return True


def clear_memory():
    """Clear all memory (topics and guidelines)."""
    save_memory(_DEFAULT_MEMORY.copy())
    logger.info("Memory cleared")


def apply_memory_update(update: dict, title: str = "", language: str = "ar"):
    """
    Apply a memory update dict from the AI response.
    Expected structure:
    {
        "add_topics": ["topic1", "topic2"],
        "remove_topics": ["old topic"],
        "add_guidelines": ["new guideline"],
        "remove_guidelines": ["old guideline"],
        "notes": "optional notes for the current topic"
    }
    """
    if not update or not isinstance(update, dict):
        return

    for topic in update.get("add_topics", []):
        add_topic(topic, title=title, language=language, notes=update.get("notes", ""))

    for topic in update.get("remove_topics", []):
        remove_topic(topic)

    for guideline in update.get("add_guidelines", []):
        add_guideline(guideline)

    for guideline in update.get("remove_guidelines", []):
        remove_guideline(guideline)


def format_memory_for_prompt(memory: Optional[dict] = None) -> str:
    """
    Format the memory into a text block suitable for inclusion in the AI prompt.
    Shows covered topics and guidelines so the AI avoids repeating them.
    """
    if memory is None:
        memory = load_memory()

    topics = memory.get("covered_topics", [])
    guidelines = memory.get("guidelines", [])

    lines = []

    if topics:
        lines.append("=== المواضيع التي تم تناولها مسبقا (لا تكررها) ===")
        for i, t in enumerate(topics, 1):
            topic_text = t.get("topic", "")
            date = t.get("date", "")[:10] if t.get("date") else ""
            lines.append(f"  {i}. {topic_text} ({date})")
        lines.append("")
    else:
        lines.append("=== لا توجد مواضيع سابقة بعد ===")
        lines.append("")

    if guidelines:
        lines.append("=== إرشادات للذاكرة ===")
        for i, g in enumerate(guidelines, 1):
            lines.append(f"  {i}. {g}")
        lines.append("")

    return "\n".join(lines)
