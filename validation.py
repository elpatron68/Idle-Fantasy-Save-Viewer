"""Save validation and import issue reporting."""

from __future__ import annotations

from typing import Any

# Known top-level fields (viewer baseline) – new fields are OK, reported as info.
KNOWN_TOP_LEVEL_KEYS = frozenset({
    "skillLevels", "skillXp", "inventory", "equipped", "flags", "pets", "coins",
    "questProgress", "farmingPatches", "sessions", "exported_at",
})

IMPORTANT_TOP_LEVEL_KEYS = frozenset({
    "skillLevels", "skillXp", "inventory", "flags",
})

Issue = dict[str, Any]


def issue(
    level: str,
    code: str,
    message: str,
    field: str | None = None,
    params: dict[str, Any] | None = None,
) -> Issue:
    out: Issue = {"level": level, "code": code, "message": message, "field": field}
    if params:
        out["params"] = params
    return out


def has_errors(issues: list[Issue]) -> bool:
    return any(i["level"] == "error" for i in issues)


def analyze_save(raw: Any, nested_parse_failures: list[str] | None = None) -> list[Issue]:
    """Structural checks before normalization."""
    issues: list[Issue] = []

    if not isinstance(raw, dict):
        issues.append(issue(
            "error", "invalid_root",
            "The file is not a JSON object – not a valid Idle Fantasy backup.",
        ))
        return issues

    if not raw:
        issues.append(issue("error", "empty_save", "The save file is empty."))
        return issues

    present = set(raw.keys())
    for key in sorted(present - KNOWN_TOP_LEVEL_KEYS):
        issues.append(issue(
            "info", "unknown_top_level",
            f'Unknown field in backup: "{key}" (added by a game update?).',
            field=key,
            params={"field": key},
        ))

    for key in sorted(IMPORTANT_TOP_LEVEL_KEYS - present):
        issues.append(issue(
            "warning", "missing_field",
            f'Expected field missing: "{key}" – related data will be shown empty.',
            field=key,
            params={"field": key},
        ))

    for field in nested_parse_failures or []:
        issues.append(issue(
            "warning", "nested_json_invalid",
            f'Field "{field}" could not be read as JSON – raw value ignored.',
            field=field,
            params={"field": field},
        ))

    _check_dict_field(raw, "skillLevels", issues)
    _check_dict_field(raw, "skillXp", issues)
    _check_dict_field(raw, "inventory", issues)
    _check_dict_field(raw, "equipped", issues)
    _check_dict_field(raw, "flags", issues)
    _check_list_field(raw, "questProgress", issues)
    _check_list_field(raw, "farmingPatches", issues)
    _check_list_field(raw, "sessions", issues)

    if "coins" in raw and not _is_number(raw["coins"]):
        issues.append(issue(
            "warning", "invalid_coins",
            'Field "coins" is not numeric.',
            field="coins",
        ))

    if "exported_at" in raw and not _is_number(raw["exported_at"]):
        issues.append(issue(
            "warning", "invalid_exported_at",
            'Field "exported_at" is not a valid timestamp.',
            field="exported_at",
        ))
    elif "exported_at" not in raw:
        issues.append(issue(
            "warning", "missing_exported_at",
            "No export timestamp – history comparisons may be inaccurate.",
            field="exported_at",
        ))

    skill_levels = raw.get("skillLevels")
    skill_xp = raw.get("skillXp")
    if isinstance(skill_levels, dict) and isinstance(skill_xp, dict):
        only_levels = set(skill_levels) - set(skill_xp)
        only_xp = set(skill_xp) - set(skill_levels)
        if only_levels:
            examples = ", ".join(sorted(only_levels)[:3])
            issues.append(issue(
                "info", "skill_xp_mismatch",
                f"{len(only_levels)} skill(s) without XP entry (e.g. {examples}).",
                field="skillXp",
                params={"count": len(only_levels), "examples": examples},
            ))
        if only_xp:
            issues.append(issue(
                "info", "skill_level_mismatch",
                f"{len(only_xp)} XP entries without skill level.",
                field="skillLevels",
                params={"count": len(only_xp)},
            ))

    return issues


def _check_dict_field(raw: dict, field: str, issues: list[Issue]) -> None:
    if field not in raw:
        return
    value = raw[field]
    if value is None:
        return
    if isinstance(value, str):
        issues.append(issue(
            "warning", "unparsed_nested_json",
            f'Field "{field}" is still a text string – JSON content could not be read.',
            field=field,
            params={"field": field},
        ))
    elif not isinstance(value, dict):
        issues.append(issue(
            "warning", "invalid_type",
            f'Field "{field}" has unexpected type ({type(value).__name__}).',
            field=field,
            params={"field": field, "type": type(value).__name__},
        ))


def _check_list_field(raw: dict, field: str, issues: list[Issue]) -> None:
    if field not in raw:
        return
    value = raw[field]
    if value is None:
        return
    if isinstance(value, str):
        issues.append(issue(
            "warning", "unparsed_nested_json",
            f'Field "{field}" is still a text string – JSON content could not be read.',
            field=field,
            params={"field": field},
        ))
    elif not isinstance(value, list):
        issues.append(issue(
            "warning", "invalid_type",
            f'Field "{field}" has unexpected type ({type(value).__name__}).',
            field=field,
            params={"field": field, "type": type(value).__name__},
        ))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
