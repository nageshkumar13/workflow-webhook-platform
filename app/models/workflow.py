from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

WorkflowJobStatus = Literal[
    "queued",
    "processing",
    "completed",
    "failed",
    "retry_scheduled",
    "failed_permanently",
]


class WorkflowJob(BaseModel):
    job_id: str
    event_id: str
    status: WorkflowJobStatus
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None
    next_retry_at: datetime | None = None

    @classmethod
    def create(cls, event_id: str) -> "WorkflowJob":
        now = datetime.now(timezone.utc)
        return cls(
            job_id=str(uuid4()),
            event_id=event_id,
            status="queued",
            attempts=0,
            max_attempts=3,
            created_at=now,
            updated_at=now,
            last_error=None,
            next_retry_at=None,
        )


class WorkflowProcessRequest(BaseModel):
    simulate_failure: bool = False


class WorkflowProcessResponse(BaseModel):
    job_id: str
    event_id: str
    status: WorkflowJobStatus
    attempts: int
    last_error: str | None

    @classmethod
    def from_job(cls, job: WorkflowJob) -> "WorkflowProcessResponse":
        return cls(
            job_id=job.job_id,
            event_id=job.event_id,
            status=job.status,
            attempts=job.attempts,
            last_error=job.last_error,
        )


class WorkflowRetryResponse(BaseModel):
    job_id: str
    event_id: str
    status: WorkflowJobStatus
    attempts: int
    max_attempts: int
    last_error: str | None

    @classmethod
    def from_job(cls, job: WorkflowJob) -> "WorkflowRetryResponse":
        return cls(
            job_id=job.job_id,
            event_id=job.event_id,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            last_error=job.last_error,
        )
