import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.security import verify_access_token
from app.limiter import limiter
from app.services import memory_service

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_access_token)])


class TopicCreate(BaseModel):
    topic: str
    title: str = ""
    language: str = "ar"
    notes: str = ""


class TopicRemove(BaseModel):
    topic: str = ""
    index: int | None = None


class GuidelineCreate(BaseModel):
    guideline: str


class GuidelineRemove(BaseModel):
    guideline: str = ""
    index: int | None = None


@router.get("/")
@limiter.limit("30/minute")
async def get_memory(request: Request):
    """Get the full AI memory (covered topics and guidelines)."""
    return memory_service.load_memory()


@router.get("/topics")
@limiter.limit("30/minute")
async def get_topics(request: Request):
    """Get the list of covered topics."""
    return {"topics": memory_service.get_covered_topics()}


@router.get("/guidelines")
@limiter.limit("30/minute")
async def get_guidelines(request: Request):
    """Get the list of guidelines."""
    return {"guidelines": memory_service.get_guidelines()}


@router.post("/topics")
@limiter.limit("10/minute")
async def add_topic(request: Request, body: TopicCreate):
    """Add a topic to the AI memory."""
    success = memory_service.add_topic(
        topic=body.topic,
        title=body.title,
        language=body.language,
        notes=body.notes,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add topic")
    return {"status": "added", "topic": body.topic}


@router.delete("/topics")
@limiter.limit("10/minute")
async def remove_topic(request: Request, body: TopicRemove):
    """Remove a topic from the AI memory by name or index."""
    if body.index is not None:
        success = memory_service.remove_topic_by_index(body.index)
    elif body.topic:
        success = memory_service.remove_topic(body.topic)
    else:
        raise HTTPException(status_code=400, detail="Provide topic or index")

    if not success:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"status": "removed"}


@router.post("/guidelines")
@limiter.limit("10/minute")
async def add_guideline(request: Request, body: GuidelineCreate):
    """Add a guideline to the AI memory."""
    success = memory_service.add_guideline(body.guideline)
    if not success:
        raise HTTPException(status_code=400, detail="Guideline already exists or empty")
    return {"status": "added", "guideline": body.guideline}


@router.delete("/guidelines")
@limiter.limit("10/minute")
async def remove_guideline(request: Request, body: GuidelineRemove):
    """Remove a guideline from the AI memory by text or index."""
    if body.index is not None:
        success = memory_service.remove_guideline_by_index(body.index)
    elif body.guideline:
        success = memory_service.remove_guideline(body.guideline)
    else:
        raise HTTPException(status_code=400, detail="Provide guideline or index")

    if not success:
        raise HTTPException(status_code=404, detail="Guideline not found")
    return {"status": "removed"}


@router.delete("/")
@limiter.limit("5/minute")
async def clear_memory(request: Request):
    """Clear all AI memory."""
    memory_service.clear_memory()
    return {"status": "cleared"}
