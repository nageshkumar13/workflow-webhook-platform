# workflow-webhook-platform

`workflow-webhook-platform` is a backend portfolio project focused on operational webhook and workflow processing. The long-term goal is a lightweight platform that can receive inbound webhooks, validate payloads, queue work, retry failures, track execution history, and expose useful operational status for engineers.

Webhook and workflow systems matter because they sit at the edge of automation. They connect external events to internal processing, and they need to be reliable, observable, and easy to operate when deliveries fail, retries pile up, or downstream systems become unstable.

## Chunk 7 Status

The repository now includes a lightweight operational observability layer:

- FastAPI ingests webhook events and creates queued jobs
- A background worker thread polls for queued jobs
- Jobs are processed automatically outside route handlers
- Failures schedule automatic retries with backoff
- Exhausted jobs become permanently failed
- Operator-facing stats endpoints expose current in-memory job and worker state

This is still intentionally lightweight and in-memory, but it now feels much more operable for a single-process prototype.

## Architecture Shift

The major change in the worker-based architecture is separation of concerns:

- API layer: accepts webhook requests, stores events, creates jobs, exposes status endpoints
- Worker layer: picks queued jobs, processes them, schedules retries, and finalizes failures
- Observability layer: summarizes current in-memory job state and worker runtime state for operators

That keeps route handlers thin and moves execution logic into dedicated worker and service modules.

## Event vs Job

Event = what happened.

Job = work the system must perform because the event happened.

The event records the inbound webhook signal. The job tracks the execution lifecycle triggered by that signal. That distinction becomes much more important now that job execution can happen later in a background loop instead of during the request itself.

## Current Operational Flow

1. A webhook request arrives at `POST /webhooks/ingest`.
2. The payload is validated.
3. The event is stored with `status="received"`.
4. A linked workflow job is created with `status="queued"`.
5. The background worker polls for queued jobs.
6. The worker moves the job to `processing`.
7. Simulated work finishes in `completed` or `failed`.
8. Failed jobs with remaining attempts move to `retry_scheduled`.
9. Once `next_retry_at` is reached, the worker re-queues the job and tries again.
10. If attempts are exhausted, the job becomes `failed_permanently`.

## Job Lifecycle Statuses

- `queued`
- `processing`
- `completed`
- `failed`
- `retry_scheduled`
- `failed_permanently`

Jobs start with:

- `attempts = 0`
- `max_attempts = 3`
- `last_error = null`
- `next_retry_at = null`

## Automatic Retry Behavior

Automatic retry is handled by the worker, not by the API request path.

Current retry backoff:

- attempt 1 failure -> retry after 5 seconds
- attempt 2 failure -> retry after 15 seconds
- attempt 3 failure -> no retry, job becomes `failed_permanently`

This introduces a realistic resilience concept: retry does not happen immediately, which helps avoid retry storms and teaches eventual consistency behavior.

## Operational Observability

The API now exposes lightweight operator-facing stats endpoints:

- `GET /stats/jobs`
- `GET /stats/worker`

These are in-memory operational summaries, not production metrics or external monitoring integrations. They are intended to make the current prototype inspectable and believable for local operations and portfolio review.

`GET /stats/jobs` returns current lifecycle counts:

```json
{
  "total_jobs": 10,
  "queued": 2,
  "processing": 0,
  "completed": 5,
  "failed": 0,
  "retry_scheduled": 2,
  "failed_permanently": 1,
  "queue_depth": 2
}
```

`queue_depth` is calculated as the number of jobs currently eligible for worker processing, which in this prototype means jobs with `status == "queued"`.

`GET /stats/worker` returns a lightweight worker runtime summary:

```json
{
  "worker_enabled": true,
  "worker_status": "running",
  "poll_interval_seconds": 2.0,
  "queue_depth": 2,
  "retry_scheduled": 1,
  "failed_permanently": 0
}
```

## Failure Simulation

To exercise automatic retries without external systems, the worker inspects optional payload flags:

- `"simulate_failure": true`
  The job fails on every processing attempt.
- `"simulate_failures": 1`
  The first processing attempt fails, then the next attempt succeeds.
- `"simulate_failures": 3`
  The job fails three times and becomes permanently failed.

These flags live inside the generic webhook `payload`, so the ingestion schema stays lightweight.

## Project Structure

```text
workflow-webhook-platform/
|-- app/
|   |-- __init__.py
|   |-- main.py
|   |-- api/
|   |   |-- __init__.py
|   |   `-- routes/
|   |       |-- __init__.py
|   |       |-- health.py
|   |       |-- stats.py
|   |       `-- webhooks.py
|   |-- core/
|   |   |-- __init__.py
|   |   |-- config.py
|   |   `-- logging.py
|   |-- models/
|   |   |-- __init__.py
|   |   |-- webhook.py
|   |   `-- workflow.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- event_store.py
|   |   |-- job_store.py
|   |   |-- stats_service.py
|   |   `-- workflow_processor.py
|   `-- workers/
|       |-- __init__.py
|       `-- job_worker.py
|-- logs/
|   `-- .gitkeep
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## API Endpoints

- `GET /health`
- `GET /ready`
- `GET /stats/jobs`
- `GET /stats/worker`
- `POST /webhooks/ingest`
- `GET /events`
- `GET /events/{event_id}`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /events/{event_id}/jobs`
- `POST /jobs/{job_id}/process`
- `POST /jobs/{job_id}/retry`

Existing manual process and retry endpoints remain available for controlled testing, but the primary lifecycle is worker-driven.

Manual process and retry endpoints are best treated as operator/debug tools at this stage. Because the worker runs in the same process, manual lifecycle calls can race with automatic worker activity during testing if you target the same queued job at the same time.

## Example Webhook Payloads

Normal success:

```json
{
  "source": "github",
  "event_type": "push",
  "payload": {
    "repository": "workflow-webhook-platform",
    "branch": "main"
  }
}
```

Fail once, then recover automatically:

```json
{
  "source": "github",
  "event_type": "push",
  "payload": {
    "repository": "workflow-webhook-platform",
    "branch": "main",
    "simulate_failures": 1
  }
}
```

Fail until permanently failed:

```json
{
  "source": "github",
  "event_type": "push",
  "payload": {
    "repository": "workflow-webhook-platform",
    "branch": "main",
    "simulate_failures": 3
  }
}
```

## What This Chunk Proves

This chunk proves the core async architecture before adding a real queue or database:

- jobs can be queued without blocking the request
- background work can happen independently of ingestion
- failures can be retried automatically
- retry delay can be modeled explicitly
- permanent failure can be represented as a stable terminal state
- operators can inspect lifecycle state without reading raw logs only

That is the key systems jump from a synchronous demo API to an operational workflow platform.

## Temporary In-Memory Limitation

Events, jobs, worker state, and observability summaries are all in memory only. Restarting the service clears everything. That is intentional for this phase so the worker model, lifecycle transitions, retry backoff behavior, and stats views can be proven clearly before persistent storage and external queue infrastructure are introduced.

## Current Architecture Limitations

- There is no persistent database yet, so all events and jobs disappear on restart.
- The worker is single-process and runs inside the FastAPI application process.
- There is no distributed queue yet, so this is not horizontally scalable.
- Automatic retries depend on in-process polling rather than durable scheduling.
- Stats endpoints expose lightweight in-memory summaries, not production-grade metrics.
- Manual operator endpoints still exist for debugging, but they are not a substitute for a real external worker system.

## Run Locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a local `.env` file from `.env.example`.
4. Start the API:

```bash
uvicorn app.main:app --reload
```

5. Ingest a webhook and inspect the system over time:

- `POST /webhooks/ingest`
- `GET /jobs/{job_id}`
- `GET /stats/jobs`
- `GET /stats/worker`
- `logs/app.log`

For retry behavior, use a payload with `simulate_failures`.

## Planned Next Steps

- Persistent storage for events and jobs
- External queue integration
- Multiple workers
- Metrics and operational monitoring
- Deployment packaging
