import logging

from fastapi import APIRouter, Body, HTTPException, status

from app.models.webhook import WebhookEvent, WebhookIngestRequest, WebhookIngestResponse
from app.models.workflow import (
    WorkflowJob,
    WorkflowProcessRequest,
    WorkflowProcessResponse,
    WorkflowRetryResponse,
)
from app.services.event_store import get_event_store
from app.services.job_store import get_job_store
from app.services.workflow_processor import WorkflowProcessingError, process_job, retry_job

router = APIRouter(tags=["operations"])
logger = logging.getLogger("app.api.webhooks")


@router.post(
    "/webhooks/ingest",
    response_model=WebhookIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_webhook(request: WebhookIngestRequest) -> WebhookIngestResponse:
    event = WebhookEvent.from_ingest_request(request)

    logger.info(
        "Webhook received | event_id=%s source=%s event_type=%s status=%s",
        event.event_id,
        event.source,
        event.event_type,
        event.status,
    )

    event_store = get_event_store()
    event_store.store_event(event)

    logger.info(
        "Event stored | event_id=%s source=%s event_type=%s status=%s",
        event.event_id,
        event.source,
        event.event_type,
        event.status,
    )

    job_store = get_job_store()
    job = job_store.create_job(event_id=event.event_id)

    logger.info(
        "Workflow job created | event_id=%s job_id=%s status=%s",
        job.event_id,
        job.job_id,
        job.status,
    )

    return WebhookIngestResponse.from_event_and_job(event, job)


@router.get("/events", response_model=list[WebhookEvent])
async def list_events() -> list[WebhookEvent]:
    event_store = get_event_store()
    events = event_store.list_events()

    logger.info(
        "Event lookup requested | event_id=%s source=%s event_type=%s status=%s event_count=%s",
        "all",
        "all",
        "all",
        "listed",
        len(events),
    )

    return events


@router.get("/events/{event_id}", response_model=WebhookEvent)
async def get_event(event_id: str) -> WebhookEvent:
    event_store = get_event_store()
    event = event_store.get_event(event_id)

    if event is None:
        logger.info(
            "Event lookup requested | event_id=%s source=%s event_type=%s status=%s",
            event_id,
            "unknown",
            "unknown",
            "not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    logger.info(
        "Event lookup requested | event_id=%s source=%s event_type=%s status=%s",
        event.event_id,
        event.source,
        event.event_type,
        event.status,
    )

    return event


@router.get("/jobs", response_model=list[WorkflowJob])
async def list_jobs() -> list[WorkflowJob]:
    job_store = get_job_store()
    jobs = job_store.list_jobs()

    logger.info(
        "Jobs listed | event_id=%s job_id=%s status=%s job_count=%s",
        "all",
        "all",
        "listed",
        len(jobs),
    )

    return jobs


@router.get("/jobs/{job_id}", response_model=WorkflowJob)
async def get_job(job_id: str) -> WorkflowJob:
    job_store = get_job_store()
    job = job_store.get_job(job_id)

    if job is None:
        logger.info(
            "Job lookup requested | event_id=%s job_id=%s status=%s",
            "unknown",
            job_id,
            "not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    logger.info(
        "Job lookup requested | event_id=%s job_id=%s status=%s",
        job.event_id,
        job.job_id,
        job.status,
    )

    return job


@router.post("/jobs/{job_id}/process", response_model=WorkflowProcessResponse)
async def process_workflow_job(
    job_id: str,
    request: WorkflowProcessRequest = Body(default_factory=WorkflowProcessRequest),
) -> WorkflowProcessResponse:
    try:
        processed_job = process_job(job_id=job_id, simulate_failure=request.simulate_failure)
    except WorkflowProcessingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return WorkflowProcessResponse.from_job(processed_job)


@router.post("/jobs/{job_id}/retry", response_model=WorkflowRetryResponse)
async def retry_workflow_job(job_id: str) -> WorkflowRetryResponse:
    try:
        retried_job = retry_job(job_id=job_id)
    except WorkflowProcessingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return WorkflowRetryResponse.from_job(retried_job)


@router.get("/events/{event_id}/jobs", response_model=list[WorkflowJob])
async def get_jobs_for_event(event_id: str) -> list[WorkflowJob]:
    event_store = get_event_store()
    event = event_store.get_event(event_id)
    if event is None:
        logger.info(
            "Jobs by event requested | event_id=%s job_id=%s status=%s",
            event_id,
            "none",
            "event_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    job_store = get_job_store()
    jobs = job_store.get_jobs_by_event_id(event_id=event_id)

    logger.info(
        "Jobs by event requested | event_id=%s job_id=%s status=%s job_count=%s",
        event_id,
        "multiple" if jobs else "none",
        "listed",
        len(jobs),
    )

    return jobs
