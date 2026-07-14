import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select, func
from app.database import engine
from app.models import Job
from app.security import verify_access_token
from app.limiter import limiter
from app.scheduler import scheduler, _get_tz

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_access_token)])


@router.get("/")
@limiter.limit("30/minute")
async def get_stats(request: Request):
    with Session(engine) as session:
        total = session.exec(select(func.count(Job.id))).one()

        published = session.exec(
            select(func.count(Job.id)).where(Job.status == "published")
        ).one()

        failed = session.exec(
            select(func.count(Job.id)).where(Job.status == "failed")
        ).one()

        pending = session.exec(
            select(func.count(Job.id)).where(Job.status == "pending")
        ).one()

        processing = session.exec(
            select(func.count(Job.id)).where(Job.status == "processing")
        ).one()

        awaiting = session.exec(
            select(func.count(Job.id)).where(Job.status == "awaiting_approval")
        ).one()

        ready = session.exec(
            select(func.count(Job.id)).where(Job.status == "ready")
        ).one()

        quota_exceeded = session.exec(
            select(func.count(Job.id)).where(Job.status == "quota_exceeded")
        ).one()

        tz = _get_tz()
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        today_published = session.exec(
            select(func.count(Job.id)).where(
                Job.status == "published",
                Job.published_at >= today,
            )
        ).one()

        latest_job = session.exec(
            select(Job).where(Job.status == "published").order_by(Job.published_at.desc()).limit(1)
        ).first()

    success_rate = (published / total * 100) if total > 0 else 0.0

    return {
        "total_jobs": total,
        "published": published,
        "failed": failed,
        "pending": pending,
        "processing": processing,
        "awaiting_approval": awaiting,
        "ready": ready,
        "quota_exceeded": quota_exceeded,
        "today_published": today_published,
        "success_rate": round(success_rate, 1),
        "last_published": latest_job.to_dict() if latest_job else None,
    }


@router.get("/scheduler")
@limiter.limit("30/minute")
async def get_scheduler_status(request: Request):
    jobs = scheduler.get_jobs()
    upcoming = []
    for job in jobs:
        if hasattr(job, "next_run_time") and job.next_run_time:
            upcoming.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat(),
                "trigger": str(job.trigger),
            })

    return {
        "scheduler_running": scheduler.running,
        "upcoming_jobs": upcoming,
    }
