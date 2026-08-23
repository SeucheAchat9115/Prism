from __future__ import annotations

from uuid import uuid4

import pytest

from prism.application.errors import EventStreamOverflowError
from prism.application.events import EventHub
from prism.application.types import EventEnvelope


def test_subscriber_count_and_queue_capacity_are_bounded() -> None:
    hub = EventHub(max_subscribers=1, queue_capacity=1)
    subscription = hub.subscribe()
    with pytest.raises(RuntimeError, match="limit"):
        hub.subscribe()

    first = EventEnvelope(type="first", project_id=uuid4(), revision=0)
    second = EventEnvelope(type="second", project_id=first.project_id, revision=0)
    hub.publish(first)
    hub.publish(second)

    with pytest.raises(EventStreamOverflowError, match="overflowed"):
        subscription.get(timeout=0.01)
    subscription.close()
    hub.close()
