from functools import lru_cache
from threading import Lock

from app.models.webhook import WebhookEvent


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: dict[str, WebhookEvent] = {}
        self._lock = Lock()

    def store_event(self, event: WebhookEvent) -> None:
        with self._lock:
            self._events[event.event_id] = event

    def list_events(self) -> list[WebhookEvent]:
        with self._lock:
            return list(self._events.values())

    def get_event(self, event_id: str) -> WebhookEvent | None:
        with self._lock:
            return self._events.get(event_id)


@lru_cache
def get_event_store() -> InMemoryEventStore:
    return InMemoryEventStore()
