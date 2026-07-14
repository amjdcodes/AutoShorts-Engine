import json
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = Field(default="pending")
    title: str = Field(default="")
    description: str = Field(default="")
    tags: str = Field(default="")
    script: str = Field(default="")
    audio_path: str = Field(default="")
    video_path: str = Field(default="")
    youtube_url: str = Field(default="")
    youtube_video_id: str = Field(default="")
    error_message: str = Field(default="")
    language: str = Field(default="ar")
    is_short: bool = Field(default=False)
    duration_seconds: int = Field(default=0)
    video_type: str = Field(default="")
    scheduled_publish_time: Optional[datetime] = Field(default=None)
    publish_time_iso: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = Field(default=None)

    def get_tags_list(self) -> list[str]:
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except (json.JSONDecodeError, TypeError):
            return [t.strip() for t in self.tags.split(",") if t.strip()]

    def set_tags_list(self, tags: list[str]):
        self.tags = json.dumps(tags, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "tags": self.get_tags_list(),
            "language": self.language,
            "is_short": self.is_short,
            "duration_seconds": self.duration_seconds,
            "video_type": self.video_type,
            "youtube_url": self.youtube_url,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "scheduled_publish_time": (
                self.scheduled_publish_time.isoformat()
                if self.scheduled_publish_time
                else None
            ),
        }
