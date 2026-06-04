"""Tuskr test-case custom field keys and payload helpers.

Keys must match Tuskr → Settings → Custom Fields (Applicable To: Test Cases).
"""

from __future__ import annotations

from typing import Any

from tuskr_mcp.types import TuskrCaseStep, TuskrTestCaseDetailed

# --- Keys (must match Tuskr UI) ---
FIELD_AUTOMATED: str = "automated"
FIELD_PRE_CONDITIONS: str = "pre_conditions"
FIELD_PRIORITY: str = "priority"
FIELD_STEPS: str = "steps"

# Required for set_test_case_automated; steps + automated used on create.
REQUIRED_FIELD_KEYS: tuple[str, ...] = (FIELD_AUTOMATED,)
CREATE_FIELD_KEYS: tuple[str, ...] = (
    FIELD_AUTOMATED,
    FIELD_STEPS,
    FIELD_PRE_CONDITIONS,
    FIELD_PRIORITY,
)

CUSTOM_FIELDS_SETUP: tuple[dict[str, str], ...] = (
    {
        "label": "Automated",
        "key": FIELD_AUTOMATED,
        "type": "Checkbox",
        "applicable_to": "Test Cases",
    },
    {
        "label": "Preconditions",
        "key": FIELD_PRE_CONDITIONS,
        "type": "Text (Multi-line)",
        "applicable_to": "Test Cases",
    },
    {
        "label": "Priority",
        "key": FIELD_PRIORITY,
        "type": "Dropdown",
        "applicable_to": "Test Cases",
    },
    {
        "label": "Steps",
        "key": FIELD_STEPS,
        "type": "Steps",
        "applicable_to": "Test Cases",
    },
)


def build_api_steps(mapped_steps: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    """API body `steps` array for test-case upsert."""
    return mapped_steps


def build_custom_field_steps(
    mapped_steps: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    """Custom field `steps` shape (step / description / expectedResult)."""
    return [
        {
            "step": int(mapped_step.get("index") or 0),
            "description": str(mapped_step.get("action") or ""),
            "expectedResult": str(mapped_step.get("expectedResult") or ""),
        }
        for mapped_step in mapped_steps
    ]


def build_create_custom_fields(
    mapped_steps: list[dict[str, str | int]],
    *,
    automated: bool = True,
    pre_conditions: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    """Build `customFields` for minimal test-case creation."""
    custom_fields: dict[str, Any] = {
        FIELD_STEPS: build_custom_field_steps(mapped_steps),
        FIELD_AUTOMATED: automated,
    }
    if pre_conditions is not None and pre_conditions.strip():
        custom_fields[FIELD_PRE_CONDITIONS] = pre_conditions.strip()
    if priority is not None and priority.strip():
        custom_fields[FIELD_PRIORITY] = priority.strip()
    return custom_fields


def build_automated_update(automated: bool) -> dict[str, bool]:
    return {FIELD_AUTOMATED: automated}


def get_custom_fields_dict(case_data: dict[str, Any]) -> dict[str, Any]:
    raw: object = case_data.get("customFields")
    if isinstance(raw, dict):
        return raw
    return {}


def get_automated(custom_fields: dict[str, Any] | None) -> bool | None:
    if not custom_fields:
        return None
    value: object = custom_fields.get(FIELD_AUTOMATED)
    if isinstance(value, bool):
        return value
    if value in ("true", "True", "1", 1):
        return True
    if value in ("false", "False", "0", 0):
        return False
    return None


def get_pre_conditions(custom_fields: dict[str, Any] | None) -> str | None:
    if not custom_fields:
        return None
    value: object = custom_fields.get(FIELD_PRE_CONDITIONS)
    return str(value).strip() if value else None


def resolve_priority(
    case_data: dict[str, Any],
    custom_fields: dict[str, Any] | None,
) -> str | None:
    top_level: object = case_data.get("priority")
    if top_level:
        return str(top_level)
    if custom_fields:
        cf_priority: object = custom_fields.get(FIELD_PRIORITY)
        if cf_priority:
            return str(cf_priority)
    return None


def extract_steps_from_custom_fields(
    custom_fields: dict[str, Any] | None,
) -> list[TuskrCaseStep]:
    """Parse Tuskr custom field `steps` when native `steps` are empty."""
    if not custom_fields:
        return []
    raw_steps: object = custom_fields.get(FIELD_STEPS)
    if not isinstance(raw_steps, list):
        return []

    normalized: list[TuskrCaseStep] = []
    for step_index, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            continue
        position: int = int(step.get("step") or step.get("index") or step_index)
        action: str | None = (
            step.get("description")
            or step.get("action")
            or step.get("step")
        )
        expected: str | None = step.get("expectedResult") or step.get("expected")
        normalized.append(
            TuskrCaseStep(
                index=position,
                title=step.get("title"),
                action=str(action) if action else None,
                expected_result=str(expected) if expected else None,
                raw=step,
            )
        )
    return normalized


def apply_automated_filter_params(
    params: dict[str, str],
    automated_filter: str | None,
) -> None:
    """Add Tuskr API filter for the `automated` checkbox custom field."""
    if not automated_filter or automated_filter == "any":
        return
    if automated_filter == "automated":
        params[f"filter[customFields][{FIELD_AUTOMATED}]"] = "1"
    elif automated_filter == "manual":
        params[f"filter[customFields][{FIELD_AUTOMATED}]"] = "0"


def filter_cases_by_automated(
    cases: list[TuskrTestCaseDetailed],
    automated_filter: str | None,
) -> list[TuskrTestCaseDetailed]:
    """Client-side filter (used for `unset` and to refine API results)."""
    if not automated_filter or automated_filter == "any":
        return cases
    if automated_filter == "automated":
        return [case for case in cases if case.automated is True]
    if automated_filter == "manual":
        return [case for case in cases if case.automated is False]
    if automated_filter == "unset":
        return [case for case in cases if case.automated is None]
    return cases


def case_search_haystack(case_key: str, case_name: str, case: object) -> str:
    """Text blob for search_tuskr_test_cases filtering."""
    from tuskr_mcp.types import TuskrTestCaseDetailed

    values: list[str] = [case_key, case_name]
    if isinstance(case, TuskrTestCaseDetailed):
        if case.priority:
            values.append(case.priority)
        pre: str | None = get_pre_conditions(case.custom_fields)
        if pre:
            values.append(pre)
        for step in case.steps or []:
            if step.action:
                values.append(step.action)
            if step.expected_result:
                values.append(step.expected_result)
            if step.title:
                values.append(step.title)
    return " ".join(values).lower()
