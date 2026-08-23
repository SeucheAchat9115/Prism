"""Thread-safe bounded event subscriptions for local API clients."""

from __future__ import annotations

from collections.abc import Callable
from queue import Full, Queue
from threading import Lock

from vibesound.application.errors import EventStreamOverflowError
from vibesound.application.types import EventEnvelope


class EventSubscription:
    """A bounded event stream owned by one WebSocket client."""

    def __init__(
        self,
        close_callback: Callable[["EventSubscription"], None],
        *,
        queue_capacity: int = 256,
    ) -> None:
        self._queue: Queue[EventEnvelope] = Queue(maxsize=queue_capacity)
        self._close_callback = close_callback
        self._closed = False
        self._overflowed = False
        self._lock = Lock()

    def get(self, timeout: float | None = None) -> EventEnvelope:
        """Wait for one event or raise when the subscription is no longer usable."""

        with self._lock:
            if self._overflowed:
                raise EventStreamOverflowError("Event subscriber queue overflowed")
            if self._closed and self._queue.empty():
                raise EventStreamOverflowError("Event subscription is closed")
        return self._queue.get(timeout=timeout)

    def close(self) -> None:
        """Unregister this subscription; repeated closes are harmless."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._close_callback(self)

    def _enqueue(self, event: EventEnvelope) -> bool:
        with self._lock:
            if self._closed:
                return False
            try:
                self._queue.put_nowait(event)
            except Full:
                self._overflowed = True
                self._closed = True
                return False
        return True


class EventHub:
    """Publish events without allowing slow clients to block service calls."""

    def __init__(self, *, max_subscribers: int = 32, queue_capacity: int = 256) -> None:
        self._lock = Lock()
        self._subscriptions: set[EventSubscription] = set()
        self._max_subscribers = max_subscribers
        self._queue_capacity = queue_capacity

    def subscribe(self) -> EventSubscription:
        with self._lock:
            if len(self._subscriptions) >= self._max_subscribers:
                raise RuntimeError("Event subscriber limit reached")
            subscription = EventSubscription(
                self._remove,
                queue_capacity=self._queue_capacity,
            )
            self._subscriptions.add(subscription)
        return subscription

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            if not subscription._enqueue(event):
                self._remove(subscription)

    def close(self) -> None:
        with self._lock:
            subscriptions = tuple(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.close()

    def _remove(self, subscription: EventSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)
