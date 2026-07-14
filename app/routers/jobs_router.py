import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from app.database import engine
from app.models import Job
from app.security import verify_access_token
from app.limiter import limiter
from app.scheduler import (
    get_job,
    update_job,
    publish_or_approve,
    create_and_schedule_daily_videos,
    run_automation_pipeline,
    _pipeline_running,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_access_token)])


@router.get("/")
@limiter.limit("30/minute")
async def list_jobs(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    with Session(engine) as session:
        statement = select(Job).order_by(Job.created_at.desc())
        if status:
            statement = statement.where(Job.status == status)
        if date_from:
            try:
                from datetime import datetime as _dt
                dt_from = _dt.fromisoformat(date_from)
                statement = statement.where(Job.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as _dt
                dt_to = _dt.fromisoformat(date_to)
                statement = statement.where(Job.created_at <= dt_to)
            except ValueError:
                pass
        statement = statement.offset(skip).limit(limit)
        jobs = session.exec(statement).all()
        return [job.to_dict() for job in jobs]


@router.get("/{job_id}")
@limiter.limit("30/minute")
async def get_job_details(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/run-now")
@limiter.limit("5/minute")
async def run_now(request: Request):
    """Manually trigger the daily video creation cycle (fire-and-forget)."""
    if _pipeline_running.is_set():
        raise HTTPException(
            status_code=409,
            detail="Pipeline already running — wait for it to finish",
        )
    logger.info("Manual daily cycle triggered via API")
    asyncio.create_task(create_and_schedule_daily_videos())
    return {"status": "started", "message": "Daily video cycle triggered"}


@router.put("/{job_id}/approve")
@limiter.limit("10/minute")
async def approve_job(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve job with status '{job.status}'",
        )
    await publish_or_approve(job_id)
    return {"status": "approved", "job_id": job_id}


@router.put("/{job_id}/cancel")
@limiter.limit("10/minute")
async def cancel_job(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "awaiting_approval", "ready", "quota_exceeded"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'",
        )
    update_job(job_id, status="cancelled")
    return {"status": "cancelled", "job_id": job_id}


@router.delete("/{job_id}")
@limiter.limit("10/minute")
async def delete_job(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    with Session(engine) as session:
        session.delete(job)
        session.commit()
    _delete_job_files(job_id)
    return {"status": "deleted", "job_id": job_id}


def _delete_job_files(job_id: int):
    """Remove video and audio files associated with a deleted job."""
    import os
    import glob
    patterns = [
        f"output/job_{job_id}.mp4",
        f"output/job_{job_id}_no_subs.mp4",
        f"temp/audio_{job_id}.mp3",
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass
