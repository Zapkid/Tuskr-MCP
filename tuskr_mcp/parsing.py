"""Normalize Tuskr API JSON payloads into typed models."""

from __future__ import annotations

from typing import Any

from tuskr_mcp import custom_fields
from tuskr_mcp.types import (
    TuskrCaseStep,
    TuskrSectionRef,
    TuskrTestCaseDetailed,
    TuskrTestSuiteRef,
)


def extract_result_history_rows(
    result_history: dict[str, dict] | None,
) -> list[dict[str, str]]:
    if not result_history:
        return []
    return [
        {"runId": entry["runId"], "status": entry["status"]}
        for entry in result_history.values()
        if isinstance(entry, dict)
        and "runId" in entry
        and "status" in entry
        and entry.get("runId")
        and entry.get("status")
    ]


def extract_case_section(case_data: dict[str, Any]) -> TuskrSectionRef | None:
    section_raw: dict[str, Any] | None = case_data.get("section")
    section_id: str | None = None
    section_name: str | None = None
    section_path: str | None = None

    if isinstance(section_raw, dict):
        section_id = section_raw.get("id") or section_raw.get("sectionId")
        section_name = section_raw.get("name") or section_raw.get("title")
        section_path = section_raw.get("path") or section_raw.get("fullPath")

    section_id = section_id or case_data.get("sectionId") or case_data.get("folderId")
    section_id = section_id or case_data.get("testSuiteSectionId")
    section_name = section_name or case_data.get("sectionName") or case_data.get(
        "folderName"
    )
    section_path = section_path or case_data.get("sectionPath") or case_data.get(
        "folderPath"
    )
    suite_id_value: str | None = (
        str(case_data.get("testSuiteId")) if case_data.get("testSuiteId") else None
    )

    if not section_id and not section_name and not section_path:
        return None

    return TuskrSectionRef(
        id=str(section_id) if section_id else "",
        name=str(section_name) if section_name else None,
        path=str(section_path) if section_path else None,
        suite_id=suite_id_value,
        suite_name=None,
    )


def extract_case_steps(case_data: dict[str, Any]) -> list[TuskrCaseStep]:
    raw_steps: Any = (
        case_data.get("steps")
        or case_data.get("testSteps")
        or case_data.get("scenarioSteps")
        or []
    )
    normalized_steps: list[TuskrCaseStep] = []
    if isinstance(raw_steps, list):
        for step_index, step in enumerate(raw_steps, start=1):
            if not isinstance(step, dict):
                continue
            title: str | None = step.get("title") or step.get("name")
            action: str | None = (
                step.get("action") or step.get("step") or step.get("description")
            )
            expected_result: str | None = step.get("expectedResult") or step.get(
                "expected"
            )
            step_position: int = int(
                step.get("index")
                or step.get("position")
                or step.get("order")
                or step_index
            )
            normalized_steps.append(
                TuskrCaseStep(
                    index=step_position,
                    title=str(title) if title else None,
                    action=str(action) if action else None,
                    expected_result=str(expected_result) if expected_result else None,
                    raw=step,
                )
            )
    if normalized_steps:
        return normalized_steps

    cf: dict[str, Any] = custom_fields.get_custom_fields_dict(case_data)
    return custom_fields.extract_steps_from_custom_fields(cf)


def normalize_test_case(case_data: dict[str, Any]) -> TuskrTestCaseDetailed:
    cf: dict[str, Any] = custom_fields.get_custom_fields_dict(case_data)
    return TuskrTestCaseDetailed(
        id=str(case_data.get("id") or ""),
        name=str(case_data.get("name") or ""),
        key=str(case_data.get("key") or ""),
        section=extract_case_section(case_data),
        steps=extract_case_steps(case_data),
        estimated_time_in_minutes=case_data.get("estimatedTimeInMinutes"),
        automation_id=case_data.get("automationId"),
        reference_links=case_data.get("referenceLinks"),
        issue_links=case_data.get("issueLinks"),
        results=extract_result_history_rows(case_data.get("resultHistory")),
        custom_fields=cf or None,
        priority=custom_fields.resolve_priority(case_data, cf),
        pre_conditions=custom_fields.get_pre_conditions(cf),
        automated=custom_fields.get_automated(cf),
        owner=case_data.get("assignedTo") or case_data.get("owner"),
        status=case_data.get("status"),
        updated_at=case_data.get("updatedAt"),
        raw=case_data,
    )


def extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: Any = payload.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    data: Any = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def pick_exact_case_row(
    rows: list[dict[str, Any]],
    case_name: str,
    filter_by: str,
) -> dict[str, Any] | None:
    trimmed: str = case_name.strip()
    if not trimmed or not rows:
        return None
    if filter_by == "key":
        target_key: str = trimmed.upper()
        for row in rows:
            if str(row.get("key") or "").upper() == target_key:
                return row
    elif filter_by == "id":
        target_id: str = trimmed.lower()
        for row in rows:
            if str(row.get("id") or "").lower() == target_id:
                return row
    return None


def safe_int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def extract_meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta_raw: object = payload.get("meta")
    if isinstance(meta_raw, dict):
        return meta_raw
    return {}


def to_section_ref(section_raw: dict[str, Any]) -> TuskrSectionRef | None:
    section_id: Any = (
        section_raw.get("id")
        or section_raw.get("sectionId")
        or section_raw.get("folderId")
    )
    section_name: Any = section_raw.get("name") or section_raw.get("title")
    section_path: Any = section_raw.get("path") or section_raw.get("fullPath")
    if not section_id and not section_name and not section_path:
        return None
    return TuskrSectionRef(
        id=str(section_id) if section_id else "",
        name=str(section_name) if section_name else None,
        path=str(section_path) if section_path else None,
    )


def to_suite_ref(suite_raw: dict[str, Any]) -> TuskrTestSuiteRef | None:
    suite_id: Any = suite_raw.get("id")
    suite_name: Any = suite_raw.get("name")
    if not suite_id or not suite_name:
        return None
    return TuskrTestSuiteRef(
        id=str(suite_id),
        name=str(suite_name),
        key=str(suite_raw.get("key")) if suite_raw.get("key") else None,
        path=str(suite_name),
    )
