"""User-authored overrides layered on top of the AI-generated profile.

The soul profile (``OnionProfile``) is regenerated periodically by the
SoulEngine, which fully overwrites ``soul.json``. To let users edit their
profile *and have those edits survive regeneration*, edits are stored
separately in ``data/memory/profile_overrides.json`` and merged onto the
generated profile at read time (``apply_overrides``, added later) and when
rendering the human-readable mirror (``MemoryManager.sync_profile_files``).

This module owns the override data model + serialization. The deterministic
merge (``apply_overrides``) and the edit reducer (``apply_edit``) are added
on top of these structures in subsequent changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _as_str_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _as_float(raw: object, default: float) -> float:
    if isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def _as_int(raw: object, default: int) -> int:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return default
    return default


@dataclass
class TextPin:
    """A pinned free-text / prose field; overrides the AI value at read time."""

    value: str = ""
    ai_value_at_pin: str = ""
    pinned_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "ai_value_at_pin": self.ai_value_at_pin,
            "pinned_at": self.pinned_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> TextPin:
        data = raw if isinstance(raw, dict) else {}
        return cls(
            value=str(data.get("value", "")),
            ai_value_at_pin=str(data.get("ai_value_at_pin", "")),
            pinned_at=str(data.get("pinned_at", "")),
        )


@dataclass
class ScalarPin:
    """A pinned numeric (0-1) field."""

    value: float = 0.0
    ai_value_at_pin: float = 0.0
    pinned_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "ai_value_at_pin": self.ai_value_at_pin,
            "pinned_at": self.pinned_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ScalarPin:
        data = raw if isinstance(raw, dict) else {}
        return cls(
            value=_as_float(data.get("value", 0.0), 0.0),
            ai_value_at_pin=_as_float(data.get("ai_value_at_pin", 0.0), 0.0),
            pinned_at=str(data.get("pinned_at", "")),
        )


@dataclass
class ListEdit:
    """Add / remove sets for a flat list-typed field (e.g. core_traits)."""

    add: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.add and not self.remove

    def to_dict(self) -> dict[str, object]:
        return {"add": list(self.add), "remove": list(self.remove)}

    @classmethod
    def from_dict(cls, raw: object) -> ListEdit:
        data = raw if isinstance(raw, dict) else {}
        return cls(add=_as_str_list(data.get("add")), remove=_as_str_list(data.get("remove")))


@dataclass
class DomainAdd:
    """A user-added interest domain (with optional narrow specifics)."""

    domain: str = ""
    weight: float = 0.5
    specifics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"domain": self.domain, "weight": self.weight, "specifics": list(self.specifics)}

    @classmethod
    def from_dict(cls, raw: object) -> DomainAdd:
        data = raw if isinstance(raw, dict) else {}
        return cls(
            domain=str(data.get("domain", "")),
            weight=_as_float(data.get("weight", 0.5), 0.5),
            specifics=_as_str_list(data.get("specifics")),
        )


@dataclass
class InterestPolarityEdit:
    """Edits for one polarity of the interest tree (``likes`` or ``dislikes``)."""

    add_domains: list[DomainAdd] = field(default_factory=list)
    remove_domains: list[str] = field(default_factory=list)
    weight_pins: dict[str, float] = field(default_factory=dict)
    specific_edits: dict[str, ListEdit] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            not self.add_domains
            and not self.remove_domains
            and not self.weight_pins
            and not self.specific_edits
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "add_domains": [d.to_dict() for d in self.add_domains],
            "remove_domains": list(self.remove_domains),
            "weight_pins": dict(self.weight_pins),
            "specific_edits": {k: v.to_dict() for k, v in self.specific_edits.items()},
        }

    @classmethod
    def from_dict(cls, raw: object) -> InterestPolarityEdit:
        data = raw if isinstance(raw, dict) else {}

        raw_add = data.get("add_domains")
        add_domains: list[DomainAdd] = []
        if isinstance(raw_add, list):
            add_domains = [DomainAdd.from_dict(item) for item in raw_add if isinstance(item, dict)]

        weight_pins: dict[str, float] = {}
        raw_weight = data.get("weight_pins")
        if isinstance(raw_weight, dict):
            for key, value in raw_weight.items():
                if isinstance(key, str) and key:
                    weight_pins[key] = _as_float(value, 0.5)

        specific_edits: dict[str, ListEdit] = {}
        raw_specific = data.get("specific_edits")
        if isinstance(raw_specific, dict):
            for key, value in raw_specific.items():
                if isinstance(key, str) and key:
                    specific_edits[key] = ListEdit.from_dict(value)

        return cls(
            add_domains=add_domains,
            remove_domains=_as_str_list(data.get("remove_domains")),
            weight_pins=weight_pins,
            specific_edits=specific_edits,
        )


@dataclass
class ProfileOverrides:
    """User edits layered on top of the AI-generated ``OnionProfile``.

    Keys in ``text_pins`` / ``scalar_pins`` / ``list_edits`` are onion field
    paths (e.g. ``"personality_portrait"``, ``"core.core_traits"``,
    ``"surface.exploration_openness"``). ``interest_edits`` is keyed by
    polarity: ``"likes"`` / ``"dislikes"``.
    """

    version: int = 1
    updated_at: str = ""
    text_pins: dict[str, TextPin] = field(default_factory=dict)
    scalar_pins: dict[str, ScalarPin] = field(default_factory=dict)
    list_edits: dict[str, ListEdit] = field(default_factory=dict)
    interest_edits: dict[str, InterestPolarityEdit] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            not self.text_pins
            and not self.scalar_pins
            and not self.list_edits
            and not self.interest_edits
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "text_pins": {k: v.to_dict() for k, v in self.text_pins.items()},
            "scalar_pins": {k: v.to_dict() for k, v in self.scalar_pins.items()},
            "list_edits": {k: v.to_dict() for k, v in self.list_edits.items()},
            "interest_edits": {k: v.to_dict() for k, v in self.interest_edits.items()},
        }

    @classmethod
    def from_dict(cls, raw: object) -> ProfileOverrides:
        data = raw if isinstance(raw, dict) else {}

        text_pins: dict[str, TextPin] = {}
        raw_text = data.get("text_pins")
        if isinstance(raw_text, dict):
            for key, value in raw_text.items():
                if isinstance(key, str) and key:
                    text_pins[key] = TextPin.from_dict(value)

        scalar_pins: dict[str, ScalarPin] = {}
        raw_scalar = data.get("scalar_pins")
        if isinstance(raw_scalar, dict):
            for key, value in raw_scalar.items():
                if isinstance(key, str) and key:
                    scalar_pins[key] = ScalarPin.from_dict(value)

        list_edits: dict[str, ListEdit] = {}
        raw_list = data.get("list_edits")
        if isinstance(raw_list, dict):
            for key, value in raw_list.items():
                if isinstance(key, str) and key:
                    list_edits[key] = ListEdit.from_dict(value)

        interest_edits: dict[str, InterestPolarityEdit] = {}
        raw_interest = data.get("interest_edits")
        if isinstance(raw_interest, dict):
            for key, value in raw_interest.items():
                if isinstance(key, str) and key:
                    interest_edits[key] = InterestPolarityEdit.from_dict(value)

        return cls(
            version=_as_int(data.get("version", 1), 1),
            updated_at=str(data.get("updated_at", "")),
            text_pins=text_pins,
            scalar_pins=scalar_pins,
            list_edits=list_edits,
            interest_edits=interest_edits,
        )
