from __future__ import annotations

from openbiliclaw.soul.overrides import (
    InterestPolarityEdit,
    ListEdit,
    ProfileOverrides,
    TextPin,
)


def test_profile_overrides_default_is_empty() -> None:
    ov = ProfileOverrides()
    assert ov.is_empty()
    assert ov.to_dict()["text_pins"] == {}
    assert ov.version == 1


def test_profile_overrides_roundtrip() -> None:
    ov = ProfileOverrides(
        updated_at="2026-05-29T10:00:00",
        text_pins={
            "personality_portrait": TextPin(
                value="我改写的画像", ai_value_at_pin="AI 原值", pinned_at="t"
            )
        },
        list_edits={"core.core_traits": ListEdit(add=["务实"], remove=["完美主义"])},
        interest_edits={"dislikes": InterestPolarityEdit(remove_domains=["二次元"])},
    )

    restored = ProfileOverrides.from_dict(ov.to_dict())

    assert not restored.is_empty()
    assert restored.text_pins["personality_portrait"].value == "我改写的画像"
    assert restored.text_pins["personality_portrait"].ai_value_at_pin == "AI 原值"
    assert restored.list_edits["core.core_traits"].add == ["务实"]
    assert restored.list_edits["core.core_traits"].remove == ["完美主义"]
    assert restored.interest_edits["dislikes"].remove_domains == ["二次元"]


def test_profile_overrides_from_dict_handles_garbage() -> None:
    assert ProfileOverrides.from_dict(None).is_empty()
    assert ProfileOverrides.from_dict({"text_pins": "nope", "list_edits": 5}).is_empty()
    # version defaults safely on bad input
    assert ProfileOverrides.from_dict({"version": "bad"}).version == 1
