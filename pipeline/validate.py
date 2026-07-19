"""Stdlib validation for public fork scenario packs.

Enforces the required shape of ``scenarios/schema/fork_scenario.schema.json``
without adding a jsonschema dependency. Used on every load so corrupt or
partial packs never reach the studio or video pipeline.
"""

from __future__ import annotations

from typing import Any


class ScenarioValidationError(ValueError):
    """Raised when a public pack fails structural validation."""

    def __init__(self, message: str, *, path: str = "$"):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


_SPECULATION = frozenset({"documented", "dramatized", "simulated"})


def _req(obj: dict, key: str, path: str) -> Any:
    if key not in obj:
        raise ScenarioValidationError(f"missing required field '{key}'", path=path)
    return obj[key]


def _str(val: Any, path: str, *, min_len: int = 1, max_len: int = 20_000) -> str:
    if not isinstance(val, str):
        raise ScenarioValidationError("expected string", path=path)
    s = val.strip()
    if len(s) < min_len:
        raise ScenarioValidationError("string too short", path=path)
    if len(val) > max_len:
        raise ScenarioValidationError(f"string exceeds {max_len} chars", path=path)
    return val


def _bool(val: Any, path: str) -> bool:
    if not isinstance(val, bool):
        raise ScenarioValidationError("expected boolean", path=path)
    return val


def validate_scenario(data: Any) -> dict:
    """Validate and return the scenario dict. Raises ScenarioValidationError."""
    if not isinstance(data, dict):
        raise ScenarioValidationError("scenario root must be an object", path="$")

    scenario_id = _str(_req(data, "scenario_id", "$"), "$.scenario_id", max_len=64)
    if ".." in scenario_id or "/" in scenario_id or "\\" in scenario_id:
        raise ScenarioValidationError("scenario_id must not contain path separators", path="$.scenario_id")

    _str(_req(data, "title", "$"), "$.title", max_len=300)
    _str(_req(data, "era", "$"), "$.era", max_len=120)
    _str(_req(data, "location", "$"), "$.location", max_len=500)
    _str(_req(data, "datetime", "$"), "$.datetime", max_len=200)
    _str(_req(data, "known_outcome", "$"), "$.known_outcome", max_len=8_000)
    _str(_req(data, "decision_question", "$"), "$.decision_question", max_len=2_000)

    opening = _req(data, "opening", "$")
    if not isinstance(opening, dict):
        raise ScenarioValidationError("opening must be an object", path="$.opening")
    _str(_req(opening, "cold_open", "$.opening"), "$.opening.cold_open", max_len=8_000)
    _str(_req(opening, "what_they_knew", "$.opening"), "$.opening.what_they_knew", max_len=8_000)
    if "pressure" in opening and opening["pressure"] is not None:
        _str(opening["pressure"], "$.opening.pressure", max_len=4_000)

    choices = _req(data, "choices", "$")
    if not isinstance(choices, list) or len(choices) < 2:
        raise ScenarioValidationError("choices must be an array with at least 2 items", path="$.choices")

    seen_ids: set[str] = set()
    historical_count = 0
    for i, choice in enumerate(choices):
        cpath = f"$.choices[{i}]"
        if not isinstance(choice, dict):
            raise ScenarioValidationError("choice must be an object", path=cpath)
        cid = _str(_req(choice, "id", cpath), f"{cpath}.id", max_len=64)
        if cid in seen_ids:
            raise ScenarioValidationError(f"duplicate choice id '{cid}'", path=cpath)
        seen_ids.add(cid)
        _str(_req(choice, "label", cpath), f"{cpath}.label", max_len=400)
        is_hist = _bool(_req(choice, "is_historical", cpath), f"{cpath}.is_historical")
        if is_hist:
            historical_count += 1
        _str(_req(choice, "summary", cpath), f"{cpath}.summary", max_len=4_000)
        level = _str(_req(choice, "speculation_level", cpath), f"{cpath}.speculation_level", max_len=32)
        if level not in _SPECULATION:
            raise ScenarioValidationError(
                f"speculation_level must be one of {sorted(_SPECULATION)}",
                path=f"{cpath}.speculation_level",
            )
        if is_hist and level != "documented":
            raise ScenarioValidationError(
                "historical choice must have speculation_level 'documented'",
                path=f"{cpath}.speculation_level",
            )
        # Optional narrative fields
        for opt in ("immediate", "near_term", "longer_arc", "image_prompt", "vo_script"):
            if opt in choice and choice[opt] is not None:
                _str(choice[opt], f"{cpath}.{opt}", min_len=0, max_len=8_000)

    if historical_count != 1:
        raise ScenarioValidationError(
            f"exactly one choice must be is_historical=true (found {historical_count})",
            path="$.choices",
        )

    provenance = _req(data, "provenance", "$")
    if not isinstance(provenance, dict):
        raise ScenarioValidationError("provenance must be an object", path="$.provenance")
    _str(_req(provenance, "discipline", "$.provenance"), "$.provenance.discipline", max_len=1_000)
    _str(_req(provenance, "notes", "$.provenance"), "$.provenance.notes", max_len=4_000)

    if "sources" in data and data["sources"] is not None:
        if not isinstance(data["sources"], list):
            raise ScenarioValidationError("sources must be an array", path="$.sources")
        for i, src in enumerate(data["sources"]):
            _str(src, f"$.sources[{i}]", max_len=1_000)

    if "tags" in data and data["tags"] is not None:
        if not isinstance(data["tags"], list):
            raise ScenarioValidationError("tags must be an array", path="$.tags")
        for i, tag in enumerate(data["tags"]):
            _str(tag, f"$.tags[{i}]", max_len=64)

    return data
