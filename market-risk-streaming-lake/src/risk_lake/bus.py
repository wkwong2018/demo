"""Message bus used by the producer and the consumer.

``InMemoryBus`` keeps one ordered list per topic inside the process. The
default demo and the tests use it, so they do not need Docker or a broker.

``KafkaBus`` talks to Apache Kafka. It is constructed only when the caller
asks for ``--bus kafka``. The client library is an optional extra.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from risk_lake.errors import RiskLakeError


@dataclass(frozen=True)
class BusMessage:
    """One delivered payload."""

    topic: str
    key: str | None
    value: dict[str, object]


class MessageBus(Protocol):
    """Publish and then read JSON payloads."""

    def publish(self, topic: str, value: Mapping[str, object], key: str | None = None) -> None:
        """Append one message."""

    def consume(self, topics: Sequence[str]) -> list[BusMessage]:
        """Return messages for ``topics`` in publish order within each topic."""

    def close(self) -> None:
        """Release client resources. The in-memory bus has none."""


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise RiskLakeError("event payload is not JSON") from exc
    if not isinstance(decoded, dict):
        raise RiskLakeError("event payload must be a JSON object")
    return decoded


class InMemoryBus:
    """Process-local stand-in for a topic log.

    ``consume`` returns a copy of every message still on the topic. It does
    not commit an offset. That is enough for one batch demo, and it is not a
    test of retention, rebalancing, or delivery guarantees.
    """

    def __init__(self) -> None:
        self._topics: dict[str, list[BusMessage]] = {}
        self._closed = False

    def publish(self, topic: str, value: Mapping[str, object], key: str | None = None) -> None:
        self._check_open()
        if not topic:
            raise RiskLakeError("topic is required")
        message = BusMessage(topic=topic, key=key, value=_json_object(value))
        self._topics.setdefault(topic, []).append(message)

    def consume(self, topics: Sequence[str]) -> list[BusMessage]:
        self._check_open()
        messages: list[BusMessage] = []
        for topic in topics:
            messages.extend(self._topics.get(topic, []))
        return list(messages)

    def close(self) -> None:
        self._closed = True

    def _check_open(self) -> None:
        if self._closed:
            raise RiskLakeError("the in-memory bus is closed")


class KafkaBus:
    """Apache Kafka producer and consumer.

    The consumer uses a new group id on every read and ``auto_offset_reset``
    of ``earliest``, then stops after the log is idle. That reads the batch
    this process just wrote. It is the right shape for the demo and a poor
    shape for a long-running service, which would keep a stable group id.
    """

    def __init__(self, bootstrap_servers: str, *, client_id: str = "risk-lake") -> None:
        servers = [part.strip() for part in bootstrap_servers.split(",") if part.strip()]
        if not servers:
            raise RiskLakeError("bootstrap servers are required for the Kafka bus")
        self._servers = servers
        self._client_id = client_id
        self._producer = None
        self._closed = False
        self._load_client()

    def publish(self, topic: str, value: Mapping[str, object], key: str | None = None) -> None:
        self._check_open()
        payload = _json_object(value)
        producer = self._producer_client()
        producer.send(
            topic,
            key=None if key is None else key.encode("utf-8"),
            value=payload,
        )

    def consume(self, topics: Sequence[str]) -> list[BusMessage]:
        self._check_open()
        if self._producer is not None:
            self._producer.flush(timeout=30)
        kafka_consumer, _kafka_producer = self._load_client()
        consumer = kafka_consumer(
            *topics,
            bootstrap_servers=self._servers,
            client_id=f"{self._client_id}-consumer",
            group_id=f"risk-lake-{uuid.uuid4().hex}",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=_decode_value,
            key_deserializer=_decode_key,
        )
        try:
            return _poll_until_idle(consumer, idle_seconds=1.0, deadline_seconds=30.0)
        finally:
            consumer.close()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.flush(timeout=30)
            self._producer.close(timeout=10)
            self._producer = None
        self._closed = True

    def _producer_client(self):
        if self._producer is None:
            _kafka_consumer, kafka_producer = self._load_client()
            self._producer = kafka_producer(
                bootstrap_servers=self._servers,
                client_id=f"{self._client_id}-producer",
                acks="all",
                retries=5,
                linger_ms=10,
                value_serializer=_encode_value,
            )
        return self._producer

    def _check_open(self) -> None:
        if self._closed:
            raise RiskLakeError("the Kafka bus is closed")

    @staticmethod
    def _load_client():
        try:
            from kafka import KafkaConsumer, KafkaProducer
        except ImportError as exc:
            raise RiskLakeError(
                'Kafka support is not installed. Run: python -m pip install -e ".[kafka]"'
            ) from exc
        return KafkaConsumer, KafkaProducer


def build_bus(kind: str, bootstrap_servers: str | None = None) -> MessageBus:
    """Return the in-memory bus or a Kafka bus."""
    if kind == "memory":
        return InMemoryBus()
    if kind == "kafka":
        servers = bootstrap_servers or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        return KafkaBus(servers)
    raise RiskLakeError("bus must be memory or kafka")


def _encode_value(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_value(raw: bytes) -> dict[str, object]:
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RiskLakeError("Kafka payload is not a JSON object")
    return decoded


def _decode_key(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    return raw.decode("utf-8")


def _poll_until_idle(consumer, *, idle_seconds: float, deadline_seconds: float) -> list[BusMessage]:
    messages: list[BusMessage] = []
    deadline = time.monotonic() + deadline_seconds
    idle_after: float | None = None
    while time.monotonic() < deadline:
        batch = consumer.poll(timeout_ms=500, max_records=500)
        if not batch:
            if messages and idle_after is None:
                idle_after = time.monotonic() + idle_seconds
            if idle_after is not None and time.monotonic() >= idle_after:
                break
            continue
        idle_after = None
        for records in batch.values():
            for record in records:
                if not isinstance(record.value, dict):
                    raise RiskLakeError("Kafka payload is not a JSON object")
                messages.append(
                    BusMessage(topic=record.topic, key=record.key, value=dict(record.value))
                )
    if not messages:
        raise RiskLakeError(
            "Kafka returned no messages. Check that the broker is up and the topics were written."
        )
    return messages
