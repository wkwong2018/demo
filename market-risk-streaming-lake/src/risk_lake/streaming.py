"""Producer and consumer over either bus adapter."""

from __future__ import annotations

from typing import Sequence

from risk_lake.bus import BusMessage, MessageBus
from risk_lake.errors import RiskLakeError
from risk_lake.events import TOPICS, RiskEvent


class EventProducer:
    """Write events to the topic named on each event."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    def publish(self, events: Sequence[RiskEvent]) -> int:
        count = 0
        for event in events:
            self._bus.publish(event.topic, event.to_dict(), key=event.key)
            count += 1
        return count


class EventConsumer:
    """Read the demo topics into one list of payloads per topic."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    def read(self, topics: Sequence[str] = TOPICS) -> dict[str, list[dict[str, object]]]:
        grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in topics}
        message: BusMessage
        for message in self._bus.consume(topics):
            if message.topic not in grouped:
                raise RiskLakeError(f"unexpected topic {message.topic}")
            grouped[message.topic].append(dict(message.value))
        return grouped
