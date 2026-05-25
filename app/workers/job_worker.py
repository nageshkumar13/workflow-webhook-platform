import logging
from functools import lru_cache
from threading import Lock
from threading import Event, Thread

from app.services.job_store import get_job_store
from app.services.workflow_processor import WorkflowProcessingError, process_job, schedule_retry

logger = logging.getLogger("app.workers.job_worker")


class JobWorker:
    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._state_lock = Lock()
        self._status = "stopped"

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="job-worker",
            daemon=True,
        )
        self._thread.start()
        with self._state_lock:
            self._status = "running"
        logger.info(
            "Background job worker started | poll_interval_seconds=%s",
            self._poll_interval_seconds,
        )

    def stop(self) -> None:
        logger.info("Background job worker stopping")
        with self._state_lock:
            self._status = "stopping"
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        with self._state_lock:
            self._status = "stopped"
        logger.info("Background job worker stopped")

    @property
    def poll_interval_seconds(self) -> float:
        return self._poll_interval_seconds

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def get_status(self) -> str:
        with self._state_lock:
            if self._status == "running" and not self.is_running():
                return "stopped"
            return self._status

    def _run(self) -> None:
        job_store = get_job_store()

        while not self._stop_event.is_set():
            try:
                released_jobs = job_store.release_due_retries()
                for job in released_jobs:
                    logger.info(
                        "Scheduled retry released to queue | job_id=%s event_id=%s previous_status=%s new_status=%s attempts=%s next_retry_at=%s error=%s",
                        job.job_id,
                        job.event_id,
                        "retry_scheduled",
                        job.status,
                        job.attempts,
                        "cleared",
                        job.last_error or "none",
                    )

                if self._stop_event.is_set():
                    break

                job = job_store.get_next_queued_job()
                if job is None:
                    self._stop_event.wait(self._poll_interval_seconds)
                    continue

                if self._stop_event.is_set():
                    break

                try:
                    processed_job = process_job(job.job_id)
                except WorkflowProcessingError as exc:
                    logger.info(
                        "Worker processing skipped | job_id=%s previous_status=%s error=%s",
                        job.job_id,
                        exc.previous_status or "unknown",
                        exc.message,
                    )
                    continue

                if processed_job.status == "failed":
                    try:
                        scheduled_job = schedule_retry(processed_job.job_id)
                    except WorkflowProcessingError as exc:
                        logger.info(
                            "Worker retry scheduling skipped | job_id=%s previous_status=%s error=%s",
                            processed_job.job_id,
                            exc.previous_status or "unknown",
                            exc.message,
                        )
                        continue

                    if scheduled_job.status == "failed_permanently":
                        logger.info(
                            "Worker left job permanently failed | job_id=%s event_id=%s status=%s attempts=%s max_attempts=%s error=%s",
                            scheduled_job.job_id,
                            scheduled_job.event_id,
                            scheduled_job.status,
                            scheduled_job.attempts,
                            scheduled_job.max_attempts,
                            scheduled_job.last_error or "none",
                        )
            except Exception:
                logger.exception("Background job worker encountered an unexpected error")
                continue


@lru_cache
def get_job_worker() -> JobWorker:
    return JobWorker()
