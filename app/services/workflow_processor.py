import logging
from datetime import datetime, timedelta, timezone

from app.models.workflow import WorkflowJob
from app.services.event_store import get_event_store
from app.services.job_store import get_job_store

logger = logging.getLogger("app.services.workflow_processor")
RETRY_BACKOFF_SECONDS = (5, 15, 30)


class WorkflowProcessingError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        job: WorkflowJob | None = None,
        previous_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.job = job
        self.previous_status = previous_status


def _processing_rejection_message(status: str) -> str:
    if status == "processing":
        return "Job is already processing"
    if status == "completed":
        return "Completed jobs cannot be processed again"
    if status == "failed":
        return "Failed jobs must be retried before processing again"
    if status == "retry_scheduled":
        return "Job is waiting for its scheduled retry window"
    if status == "failed_permanently":
        return "Permanently failed jobs cannot be processed again"
    return "Job can only be processed from queued status"


def _retry_rejection_message(status: str) -> str:
    if status == "queued":
        return "Queued jobs cannot be retried"
    if status == "processing":
        return "Processing jobs cannot be retried"
    if status == "completed":
        return "Completed jobs cannot be retried"
    if status == "retry_scheduled":
        return "Job retry is already scheduled"
    if status == "failed_permanently":
        return "Permanently failed jobs cannot be retried"
    return "Job can only be retried from failed status"


def _should_simulate_failure(job: WorkflowJob) -> bool:
    event_store = get_event_store()
    event = event_store.get_event(job.event_id)
    if event is None:
        return True

    payload = event.payload
    if payload.get("simulate_failure") is True:
        return True

    simulate_failures = payload.get("simulate_failures", 0)
    if isinstance(simulate_failures, bool):
        simulate_failures = int(simulate_failures)

    if isinstance(simulate_failures, int) and simulate_failures > 0:
        return job.attempts <= simulate_failures

    return False


def schedule_retry(job_id: str) -> WorkflowJob:
    job_store = get_job_store()
    job = job_store.get_job(job_id)

    if job is None:
        raise WorkflowProcessingError(
            "Job not found",
            status_code=404,
            previous_status="unknown",
        )

    if job.status != "failed":
        raise WorkflowProcessingError(
            "Job can only be scheduled for retry from failed status",
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    if job.attempts >= job.max_attempts:
        permanently_failed_job = job_store.update_job_status(
            job_id=job.job_id,
            status="failed_permanently",
            last_error=job.last_error,
            next_retry_at=None,
            expected_current_status="failed",
        )
        if permanently_failed_job is None:
            raise WorkflowProcessingError(
                "Job can only be scheduled for retry from failed status",
                status_code=409,
                job=job,
                previous_status=job.status,
            )

        logger.info(
            "Job marked as permanently failed | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s max_attempts=%s error=%s",
            permanently_failed_job.job_id,
            permanently_failed_job.event_id,
            "failed",
            permanently_failed_job.status,
            permanently_failed_job.attempts,
            permanently_failed_job.max_attempts,
            permanently_failed_job.last_error or "none",
        )
        return permanently_failed_job

    backoff_index = min(max(job.attempts - 1, 0), len(RETRY_BACKOFF_SECONDS) - 1)
    retry_delay_seconds = RETRY_BACKOFF_SECONDS[backoff_index]
    next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds)
    scheduled_retry_job = job_store.update_job_status(
        job_id=job.job_id,
        status="retry_scheduled",
        last_error=job.last_error,
        next_retry_at=next_retry_at,
        expected_current_status="failed",
    )
    if scheduled_retry_job is None:
        raise WorkflowProcessingError(
            "Job can only be scheduled for retry from failed status",
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    logger.info(
        "Automatic retry scheduled | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s max_attempts=%s next_retry_at=%s error=%s",
        scheduled_retry_job.job_id,
        scheduled_retry_job.event_id,
        "failed",
        scheduled_retry_job.status,
        scheduled_retry_job.attempts,
        scheduled_retry_job.max_attempts,
        scheduled_retry_job.next_retry_at.isoformat() if scheduled_retry_job.next_retry_at else "none",
        scheduled_retry_job.last_error or "none",
    )
    return scheduled_retry_job


def retry_job(job_id: str) -> WorkflowJob:
    job_store = get_job_store()
    job = job_store.get_job(job_id)

    if job is None:
        logger.info(
            "Retry rejected | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s previous_error=%s reason=%s",
            job_id,
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            "Job not found",
        )
        raise WorkflowProcessingError(
            "Job not found",
            status_code=404,
            previous_status="unknown",
        )

    logger.info(
        "Retry requested | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s previous_error=%s",
        job.job_id,
        job.event_id,
        job.status,
        job.attempts,
        job.max_attempts,
        job.last_error or "none",
    )

    if job.status != "failed":
        rejection_message = _retry_rejection_message(job.status)
        logger.info(
            "Retry rejected | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s previous_error=%s reason=%s",
            job.job_id,
            job.event_id,
            job.status,
            job.attempts,
            job.max_attempts,
            job.last_error or "none",
            rejection_message,
        )
        raise WorkflowProcessingError(
            rejection_message,
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    if job.attempts >= job.max_attempts:
        logger.info(
            "Max attempts reached | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s previous_error=%s reason=%s",
            job.job_id,
            job.event_id,
            job.status,
            job.attempts,
            job.max_attempts,
            job.last_error or "none",
            "Job has reached maximum retry attempts",
        )
        raise WorkflowProcessingError(
            "Job has reached maximum retry attempts",
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    retried_job = job_store.update_job_status(
        job_id=job.job_id,
        status="queued",
        last_error=None,
        next_retry_at=None,
        expected_current_status="failed",
    )
    if retried_job is None:
        raise WorkflowProcessingError(
            _retry_rejection_message(job.status),
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    logger.info(
        "Retry accepted | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s previous_error=%s",
        retried_job.job_id,
        retried_job.event_id,
        retried_job.status,
        retried_job.attempts,
        retried_job.max_attempts,
        job.last_error or "none",
    )
    return retried_job


def process_job(job_id: str, simulate_failure: bool | None = None) -> WorkflowJob:
    job_store = get_job_store()
    job = job_store.get_job(job_id)

    if job is None:
        logger.info(
            "Invalid processing attempt | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
            job_id,
            "unknown",
            "unknown",
            "rejected",
            "unknown",
            "Job not found",
        )
        raise WorkflowProcessingError(
            "Job not found",
            status_code=404,
            previous_status="unknown",
        )

    logger.info(
        "Job processing requested | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
        job.job_id,
        job.event_id,
        job.status,
        "processing_requested",
        job.attempts,
        "none",
    )

    if job.status != "queued":
        rejection_message = _processing_rejection_message(job.status)
        logger.info(
            "Invalid processing attempt | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
            job.job_id,
            job.event_id,
            job.status,
            "rejected",
            job.attempts,
            rejection_message,
        )
        raise WorkflowProcessingError(
            rejection_message,
            status_code=409,
            job=job,
            previous_status=job.status,
        )

    processing_job = job_store.update_job_status(
        job_id=job.job_id,
        status="processing",
        attempts_increment=1,
        last_error=None,
        next_retry_at=None,
        expected_current_status="queued",
    )
    if processing_job is None:
        latest_job = job_store.get_job(job.job_id)
        latest_status = latest_job.status if latest_job is not None else "unknown"
        raise WorkflowProcessingError(
            _processing_rejection_message(latest_status),
            status_code=409,
            job=latest_job,
            previous_status=latest_status,
        )

    logger.info(
        "Job moved to processing | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
        processing_job.job_id,
        processing_job.event_id,
        "queued",
        processing_job.status,
        processing_job.attempts,
        "none",
    )

    should_fail = simulate_failure if simulate_failure is not None else _should_simulate_failure(processing_job)

    if should_fail:
        failed_job = job_store.update_job_status(
            job_id=processing_job.job_id,
            status="failed",
            last_error="Simulated workflow processing failure",
            next_retry_at=None,
            expected_current_status="processing",
        )
        if failed_job is None:
            raise WorkflowProcessingError(
                "Job can only be marked failed from processing status",
                status_code=409,
                job=job_store.get_job(processing_job.job_id),
                previous_status="processing",
            )

        logger.info(
            "Job failed | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
            failed_job.job_id,
            failed_job.event_id,
            "processing",
            failed_job.status,
            failed_job.attempts,
            failed_job.last_error,
        )
        return failed_job

    completed_job = job_store.update_job_status(
        job_id=processing_job.job_id,
        status="completed",
        last_error=None,
        next_retry_at=None,
        expected_current_status="processing",
    )
    if completed_job is None:
        raise WorkflowProcessingError(
            "Job can only be completed from processing status",
            status_code=409,
            job=job_store.get_job(processing_job.job_id),
            previous_status="processing",
        )

    logger.info(
        "Job completed | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s error=%s",
        completed_job.job_id,
        completed_job.event_id,
        "processing",
        completed_job.status,
        completed_job.attempts,
        "none",
    )
    return completed_job
