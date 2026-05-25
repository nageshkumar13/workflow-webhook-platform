from collections import Counter

from app.models.workflow import WorkflowJob
from app.services.job_store import get_job_store
from app.workers.job_worker import get_job_worker


def _job_status_counts(jobs: list[WorkflowJob]) -> Counter[str]:
    return Counter(job.status for job in jobs)


def get_job_stats() -> dict[str, int]:
    jobs = get_job_store().list_jobs()
    counts = _job_status_counts(jobs)
    queue_depth = counts.get("queued", 0)

    return {
        "total_jobs": len(jobs),
        "queued": counts.get("queued", 0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "retry_scheduled": counts.get("retry_scheduled", 0),
        "failed_permanently": counts.get("failed_permanently", 0),
        "queue_depth": queue_depth,
    }


def get_worker_stats() -> dict[str, int | float | bool | str]:
    worker = get_job_worker()
    job_stats = get_job_stats()

    return {
        "worker_enabled": True,
        "worker_status": worker.get_status(),
        "poll_interval_seconds": worker.poll_interval_seconds,
        "queue_depth": job_stats["queue_depth"],
        "retry_scheduled": job_stats["retry_scheduled"],
        "failed_permanently": job_stats["failed_permanently"],
    }
