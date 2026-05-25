from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock

from app.models.workflow import WorkflowJob, WorkflowJobStatus


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, WorkflowJob] = {}
        self._lock = Lock()

    def create_job(self, event_id: str) -> WorkflowJob:
        job = WorkflowJob.create(event_id=event_id)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def list_jobs(self) -> list[WorkflowJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, job_id: str) -> WorkflowJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_next_queued_job(self) -> WorkflowJob | None:
        with self._lock:
            queued_jobs = [job for job in self._jobs.values() if job.status == "queued"]
            if not queued_jobs:
                return None
            return min(queued_jobs, key=lambda job: job.created_at)

    def get_jobs_by_event_id(self, event_id: str) -> list[WorkflowJob]:
        with self._lock:
            return [job for job in self._jobs.values() if job.event_id == event_id]

    def release_due_retries(self) -> list[WorkflowJob]:
        now = datetime.now(timezone.utc)
        released_jobs: list[WorkflowJob] = []

        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status != "retry_scheduled":
                    continue
                if job.next_retry_at is None or job.next_retry_at > now:
                    continue

                released_job = job.model_copy(
                    update={
                        "status": "queued",
                        "updated_at": now,
                        "next_retry_at": None,
                    }
                )
                self._jobs[job_id] = released_job
                released_jobs.append(released_job)

        return released_jobs

    def update_job_status(
        self,
        job_id: str,
        status: WorkflowJobStatus,
        attempts_increment: int = 0,
        last_error: str | None = None,
        next_retry_at: datetime | None = None,
        expected_current_status: WorkflowJobStatus | None = None,
    ) -> WorkflowJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if expected_current_status is not None and job.status != expected_current_status:
                return None

            updated_job = job.model_copy(
                update={
                    "status": status,
                    "attempts": job.attempts + attempts_increment,
                    "updated_at": datetime.now(timezone.utc),
                    "last_error": last_error,
                    "next_retry_at": next_retry_at,
                }
            )
            self._jobs[job_id] = updated_job
            return updated_job


@lru_cache
def get_job_store() -> InMemoryJobStore:
    return InMemoryJobStore()
