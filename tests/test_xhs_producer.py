"""Tests for the Soul-driven xhs search task producer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openbiliclaw.runtime.xhs_producer import XhsTaskProducer
from openbiliclaw.soul.profile import (
    InterestLayer,
    InterestDomain,
    InterestSpecific,
    OnionProfile,
)
from openbiliclaw.sources.xhs_tasks import XhsTaskQueue
from openbiliclaw.storage.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "producer.db")
    d.initialize()
    return d


@pytest.fixture
def queue(db: Database) -> XhsTaskQueue:
    return XhsTaskQueue(db)


def _profile_with_interests() -> OnionProfile:
    return OnionProfile(
        interest=InterestLayer(
            likes=[
                InterestDomain(
                    domain="机械键盘",
                    weight=0.9,
                    specifics=[InterestSpecific(name="客制化", weight=0.8)],
                ),
                InterestDomain(domain="咖啡", weight=0.7),
            ]
        )
    )


class _FakeSoulEngine:
    def __init__(self, profile: Any) -> None:
        self._profile = profile

    async def get_profile(self) -> Any:
        return self._profile


class _FakeLLMService:
    """Bypass the real LLM. ``generate_xhs_keywords`` is monkeypatched
    in tests, so this stub is never actually called — but the producer
    still type-checks against it."""

    async def complete_structured_task(self, **_kwargs: Any) -> Any:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_producer_skips_when_disabled(queue: XhsTaskQueue) -> None:
    producer = XhsTaskProducer(
        task_queue=queue,
        soul_engine=_FakeSoulEngine(_profile_with_interests()),
        llm_service=_FakeLLMService(),
        enabled=False,
    )
    result = await producer.produce_if_due()
    assert result == {"enqueued": 0, "attempted": 0, "reason": "disabled"}
    assert queue.next_pending() is None


@pytest.mark.asyncio
async def test_producer_enqueues_keywords_up_to_budget(
    queue: XhsTaskQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_keywords(_llm: Any, _profile: Any, *, count: int) -> list[str]:
        return [f"kw-{i}" for i in range(count)]

    monkeypatch.setattr(
        "openbiliclaw.runtime.xhs_producer.generate_xhs_keywords",
        fake_keywords,
    )

    producer = XhsTaskProducer(
        task_queue=queue,
        soul_engine=_FakeSoulEngine(_profile_with_interests()),
        llm_service=_FakeLLMService(),
        enabled=True,
        daily_budget=3,
        keywords_per_cycle=5,
        min_interval_hours=0,
    )
    result = await producer.produce_if_due()
    assert result["reason"] == "ok"
    assert result["enqueued"] == 3
    assert result["attempted"] == 5


@pytest.mark.asyncio
async def test_producer_throttled_when_recent_task_exists(
    queue: XhsTaskQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed a search task so the producer sees "recent activity"
    queue.enqueue("search", {"keyword": "existing"})

    async def fake_keywords(_llm: Any, _profile: Any, *, count: int) -> list[str]:
        return ["should-not-run"]

    monkeypatch.setattr(
        "openbiliclaw.runtime.xhs_producer.generate_xhs_keywords",
        fake_keywords,
    )

    producer = XhsTaskProducer(
        task_queue=queue,
        soul_engine=_FakeSoulEngine(_profile_with_interests()),
        llm_service=_FakeLLMService(),
        enabled=True,
        min_interval_hours=4,
    )
    result = await producer.produce_if_due()
    assert result["reason"] == "throttled"
    assert result["enqueued"] == 0


@pytest.mark.asyncio
async def test_producer_handles_empty_keywords(
    queue: XhsTaskQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_keywords(_llm: Any, _profile: Any, *, count: int) -> list[str]:
        return []

    monkeypatch.setattr(
        "openbiliclaw.runtime.xhs_producer.generate_xhs_keywords",
        fake_keywords,
    )

    producer = XhsTaskProducer(
        task_queue=queue,
        soul_engine=_FakeSoulEngine(_profile_with_interests()),
        llm_service=_FakeLLMService(),
        min_interval_hours=0,
    )
    result = await producer.produce_if_due()
    assert result["reason"] == "no_keywords"


@pytest.mark.asyncio
async def test_producer_handles_missing_profile(queue: XhsTaskQueue) -> None:
    producer = XhsTaskProducer(
        task_queue=queue,
        soul_engine=_FakeSoulEngine(None),
        llm_service=_FakeLLMService(),
        min_interval_hours=0,
    )
    result = await producer.produce_if_due()
    assert result["reason"] == "no_profile"
