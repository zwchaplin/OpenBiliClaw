"""Tests for the OpenClaw adapter CLI bridge."""

from __future__ import annotations

import json
from pathlib import Path

from openbiliclaw.integrations.openclaw.errors import AdapterValidationError
from openbiliclaw.integrations.openclaw.schemas import (
    DelightItem,
    DelightResponse,
    FeedbackResponse,
    ProfileResponse,
    RecommendationItem,
    RecommendationResponse,
    RuntimeStatusResponse,
    SyncAccountResponse,
)


class _FakeCliAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def sync_account(self) -> SyncAccountResponse:
        self.calls.append(("sync_account",))
        return SyncAccountResponse(synced=True, new_event_count=8, errors=[])

    async def get_profile(self) -> ProfileResponse:
        self.calls.append(("get_profile",))
        return ProfileResponse(
            initialized=True,
            personality_portrait="你会自己往深处追问题。",
            core_traits=["深究"],
            deep_needs=["把问题想透"],
            top_interests=["国际时事"],
        )

    async def recommend(
        self,
        *,
        limit: int = 5,
        refresh_if_needed: bool = True,
    ) -> RecommendationResponse:
        self.calls.append(("recommend", limit, refresh_if_needed))
        return RecommendationResponse(
            items=[
                RecommendationItem(
                    recommendation_id=21,
                    bvid="BV1CLI",
                    title="把议题讲到结构层",
                    up_name="结构控",
                    cover_url="https://example.com/cover.jpg",
                    reason="这条会对上你最近那股继续往深处看的劲头。",
                    topic_label="你最近那股继续往深处看的劲头",
                    confidence=0.93,
                )
            ]
        )

    async def submit_feedback(self, request) -> FeedbackResponse:  # noqa: ANN001
        self.calls.append(
            ("submit_feedback", request.recommendation_id, request.feedback_type, request.note)
        )
        return FeedbackResponse(
            ok=True,
            recommendation_id=request.recommendation_id,
            feedback_type=request.feedback_type,
        )

    async def get_delight(self) -> DelightResponse:
        self.calls.append(("get_delight",))
        return DelightResponse(
            item=DelightItem(
                bvid="BV1CLIDELIGHT",
                title="意外的跨域发现",
                delight_reason="这条会戳到你一直想搞明白的那个方向。",
                delight_score=0.91,
                delight_hook="跨域惊喜",
                cover_url="https://example.com/delight.jpg",
            ),
        )

    async def get_runtime_status(self) -> RuntimeStatusResponse:
        self.calls.append(("get_runtime_status",))
        return RuntimeStatusResponse(
            initialized=True,
            recommendation_count=4,
            pending_signal_events=1,
            unread_count=2,
            pool_available_count=12,
            pool_target_count=30,
            last_refresh_at="2026-03-15T12:00:00+08:00",
            last_account_sync_at="2026-03-15T12:05:00+08:00",
            last_account_sync_error="",
        )


def test_recommend_cli_emits_json_and_returns_zero(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(
        ["recommend", "--limit", "3", "--skip-refresh"],
        adapter=adapter,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "data": {
            "items": [
                {
                    "recommendation_id": 21,
                    "bvid": "BV1CLI",
                    "title": "把议题讲到结构层",
                    "up_name": "结构控",
                    "cover_url": "https://example.com/cover.jpg",
                    "reason": "这条会对上你最近那股继续往深处看的劲头。",
                    "topic_label": "你最近那股继续往深处看的劲头",
                    "confidence": 0.93,
                }
            ]
        },
    }
    assert adapter.calls == [("recommend", 3, False)]


def test_recommend_cli_defaults_to_fast_path_without_refresh(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(["recommend"], adapter=adapter)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["ok"] is True
    assert adapter.calls == [("recommend", 5, False)]


def test_recommend_cli_can_explicitly_enable_refresh(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(["recommend", "--refresh-if-needed"], adapter=adapter)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["ok"] is True
    assert adapter.calls == [("recommend", 5, True)]


def test_submit_feedback_cli_emits_error_json_and_returns_one(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    class BadAdapter(_FakeCliAdapter):
        async def submit_feedback(self, request) -> FeedbackResponse:  # noqa: ANN001
            raise AdapterValidationError(f"bad input: {request.feedback_type}")

    exit_code = main(
        [
            "submit-feedback",
            "--recommendation-id",
            "9",
            "--feedback-type",
            "like",
        ],
        adapter=BadAdapter(),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out) == {
        "ok": False,
        "error": "bad input: like",
        "error_type": "validation_error",
    }


def test_doctor_cli_reports_skill_pack_and_registered_skill_names(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(["doctor"], adapter=adapter)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "data": {
            "skill_pack_path": (
                "/Users/white/workspace/OpenBiliClaw/"
                "skills/openbiliclaw-adapter/SKILL.md"
            ),
            "skill_pack_exists": True,
            "skill_count": 6,
            "skill_names": [
                "openbiliclaw_sync_account",
                "openbiliclaw_get_profile",
                "openbiliclaw_recommend",
                "openbiliclaw_submit_feedback",
                "openbiliclaw_get_delight",
                "openbiliclaw_get_runtime_status",
            ],
            "cli_module": "openbiliclaw.integrations.openclaw.cli",
        },
    }
    assert adapter.calls == []


def test_emit_skill_descriptors_cli_outputs_serializable_descriptors(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(["emit-skill-descriptors"], adapter=adapter)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["data"]["skills"][0]["name"] == "openbiliclaw_sync_account"
    assert payload["data"]["skills"][2]["name"] == "openbiliclaw_recommend"
    assert "handler" not in payload["data"]["skills"][0]
    assert adapter.calls == []


def test_get_delight_cli_emits_json_and_returns_zero(capsys) -> None:
    from openbiliclaw.integrations.openclaw.cli import main

    adapter = _FakeCliAdapter()

    exit_code = main(["get-delight"], adapter=adapter)

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["data"]["item"]["bvid"] == "BV1CLIDELIGHT"
    assert payload["data"]["item"]["delight_hook"] == "跨域惊喜"
    assert payload["data"]["item"]["delight_score"] == 0.91
    assert adapter.calls == [("get_delight",)]


def test_listen_parser_accepts_default_flags() -> None:
    from openbiliclaw.integrations.openclaw.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["listen"])

    assert args.command == "listen"
    assert args.ws_url == "ws://127.0.0.1:8420/api/runtime-stream"
    assert "delight.candidate" in args.events


def test_listen_parser_accepts_custom_flags() -> None:
    from openbiliclaw.integrations.openclaw.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args([
        "listen",
        "--ws-url", "ws://custom:9999/api/runtime-stream",
        "--events", "delight.candidate,refresh.pool_updated",
    ])

    assert args.ws_url == "ws://custom:9999/api/runtime-stream"
    assert "delight.candidate" in args.events
    assert "refresh.pool_updated" in args.events


def test_workspace_skill_pack_exists_and_mentions_cli_bridge() -> None:
    skill_path = Path("/Users/white/workspace/OpenBiliClaw/skills/openbiliclaw-adapter/SKILL.md")

    content = skill_path.read_text(encoding="utf-8")

    assert "name: openbiliclaw_adapter" in content
    assert "uv run python -m openbiliclaw.integrations.openclaw.cli" in content
    assert "recommend --limit" in content
    assert "get-delight" in content
    assert "listen" in content
