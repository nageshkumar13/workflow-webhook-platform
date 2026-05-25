from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, field_validator

from app.models.workflow import WorkflowJob


class WebhookIngestRequest(BaseModel):
    source: str
    event_type: str
    payload: dict[str, Any]

    @field_validator("source", "event_type")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("value cannot be empty")
        return cleaned_value


class WebhookEvent(BaseModel):
    event_id: str
    source: str
    event_type: str
    payload: dict[str, Any]
    status: str
    received_at: datetime

    @classmethod
    def from_ingest_request(cls, request: WebhookIngestRequest) -> "WebhookEvent":
        return cls(
            event_id=str(uuid4()),
            source=request.source,
            event_type=request.event_type,
            payload=request.payload,
            status="received",
            received_at=datetime.now(timezone.utc),
        )


class WebhookIngestResponse(BaseModel):
    event_id: str
    job_id: str
    status: str
    job_status: str
    source: str
    event_type: str

    @classmethod
    def from_event_and_job(
        cls,
        event: WebhookEvent,
        job: WorkflowJob,
    ) -> "WebhookIngestResponse":
        return cls(
            event_id=event.event_id,
            job_id=job.job_id,
            status=event.status,
            job_status=job.status,
            source=event.source,
            event_type=event.event_type,
        )
