import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.stats_service import get_job_stats, get_worker_stats

router = APIRouter(tags=["stats"])
logger = logging.getLogger("app.api.stats")


class JobStatsResponse(BaseModel):
    total_jobs: int
    queued: int
    processing: int
    completed: int
    failed: int
    retry_scheduled: int
    failed_permanently: int
    queue_depth: int


class WorkerStatsResponse(BaseModel):
    worker_enabled: bool
    worker_status: str
    poll_interval_seconds: float
    queue_depth: int
    retry_scheduled: int
    failed_permanently: int


@router.get("/stats/jobs", response_model=JobStatsResponse)
async def job_stats() -> JobStatsResponse:
    stats = get_job_stats()
    logger.info(
        "Stats endpoint requested | endpoint=%s queue_depth=%s total_jobs=%s",
        "/stats/jobs",
        stats["queue_depth"],
        stats["total_jobs"],
    )
    return JobStatsResponse(**stats)


@router.get("/stats/worker", response_model=WorkerStatsResponse)
async def worker_stats() -> WorkerStatsResponse:
    job_stats = get_job_stats()
    stats = get_worker_stats()
    logger.info(
        "Stats endpoint requested | endpoint=%s queue_depth=%s total_jobs=%s worker_status=%s",
        "/stats/worker",
        stats["queue_depth"],
        job_stats["total_jobs"],
        stats["worker_status"],
    )
    return WorkerStatsResponse(**stats)
