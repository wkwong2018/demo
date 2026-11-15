"""Producer and consumer on the in-memory bus."""

from __future__ import annotations

from risk_lake.bus import InMemoryBus
from risk_lake.events import TOPIC_MARKET_FACTORS, TOPIC_PNL, TOPIC_POSITIONS
from risk_lake.streaming import EventConsumer, EventProducer
from risk_lake.synthetic import generate_events


def test_producer_publishes_each_topic_in_order() -> None:
    events = generate_events(sessions=4, seed=3)
    bus = InMemoryBus()
    assert EventProducer(bus).publish(events) == len(events)

    grouped = EventConsumer(bus).read()
    assert set(grouped) == {TOPIC_MARKET_FACTORS, TOPIC_POSITIONS, TOPIC_PNL}
    assert len(grouped[TOPIC_MARKET_FACTORS]) == 4 * 5
    assert len(grouped[TOPIC_POSITIONS]) == 4 * 5
    assert len(grouped[TOPIC_PNL]) == 4 * 5

    factor_ids = [row["event_id"] for row in grouped[TOPIC_MARKET_FACTORS]]
    assert factor_ids == sorted(factor_ids)
    assert grouped[TOPIC_MARKET_FACTORS][0]["source"] == "synthetic"
    assert grouped[TOPIC_PNL][0]["event_type"] == "pnl"


def test_consumer_copies_payloads() -> None:
    events = generate_events(sessions=2, seed=1)
    bus = InMemoryBus()
    EventProducer(bus).publish(events)
    first = EventConsumer(bus).read()
    first[TOPIC_PNL][0]["pnl"] = 999
    second = EventConsumer(bus).read()
    assert second[TOPIC_PNL][0]["pnl"] != 999
