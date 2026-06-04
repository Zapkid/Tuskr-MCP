"""Tuskr MCP tool handlers and FastMCP server entrypoint."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tuskr_mcp import runs as tuskr_runs
from tuskr_mcp.client import TuskrClient
from tuskr_mcp.config import tuskr_projects
from tuskr_mcp.types import (
    AutomatedFilter,
    TuskrBulkAutomatedResult,
    TuskrCaseStep,
    TuskrError,
    TuskrPaginatedCases,
    TuskrSectionRef,
    TuskrSectionTreeNode,
    TuskrSetupValidation,
    TuskrTestCaseDetailed,
    TuskrTestRunSummary,
    TuskrTestSuiteRef,
)
from tuskr_mcp.validation import validate_tuskr_setup as run_validate_tuskr_setup

from mcp.server.fastmcp import FastMCP


def _ok(data: object) -> dict[str, object]:
    return {"ok": True, "data": data}


def _err(
    code: str, message: str, details: dict[str, object] | None = None
) -> dict[str, object]:
    error: TuskrError = TuskrError(code=code, message=message, details=details)
    return {"ok": False, "error": asdict(error)}


def _serialize_step(step: TuskrCaseStep) -> dict[str, Any]:
    return asdict(step)


def _serialize_section(section: TuskrSectionRef | None) -> dict[str, Any] | None:
    if not section:
        return None
    return asdict(section)


def _serialize_case(case_data: TuskrTestCaseDetailed) -> dict[str, Any]:
    case_dict: dict[str, Any] = asdict(case_data)
    case_dict["section"] = _serialize_section(case_data.section)
    case_dict["steps"] = (
        [_serialize_step(step) for step in (case_data.steps or [])]
        if case_data.steps is not None
        else []
    )
    return case_dict


_CASE_METADATA_FIELDS: tuple[str, ...] = (
    "priority",
    "pre_conditions",
    "automated",
    "owner",
    "status",
    "updated_at",
    "raw",
)


def _without_case_metadata(case: dict[str, Any]) -> dict[str, Any]:
    stripped: dict[str, Any] = dict(case)
    for field in _CASE_METADATA_FIELDS:
        stripped.pop(field, None)
    return stripped


def _serialize_paginated_cases(result: TuskrPaginatedCases) -> dict[str, object]:
    return {
        "items": [_serialize_case(case_data) for case_data in result.items],
        "page": result.page,
        "page_size": result.page_size,
        "total": result.total,
        "has_more": result.has_more,
    }


_VALID_AUTOMATED_FILTERS: tuple[AutomatedFilter, ...] = (
    "any",
    "automated",
    "manual",
    "unset",
)


def _parse_automated_filter(value: str) -> AutomatedFilter | None:
    normalized: str = value.strip().lower()
    if normalized in _VALID_AUTOMATED_FILTERS:
        return normalized  # type: ignore[return-value]
    return None


def _serialize_setup_validation(result: TuskrSetupValidation) -> dict[str, object]:
    return {
        "app_name": result.app_name,
        "ready": result.ready,
        "checks": [asdict(check) for check in result.checks],
    }


def _serialize_section_tree_node(node: TuskrSectionTreeNode) -> dict[str, object]:
    children: list[dict[str, object]] = [
        _serialize_section_tree_node(child) for child in (node.children or [])
    ]
    return {
        "id": node.id,
        "name": node.name,
        "path": node.path,
        "children": children,
    }


def list_projects_data() -> dict[str, object]:
    projects: list[dict[str, str]] = [
        {
            "app": project.app,
            "project_name": project.project_name,
            "project_id": project.project_id,
        }
        for project in tuskr_projects.values()
    ]
    projects.sort(key=lambda item: item["app"])
    return _ok(projects)


def list_sections_data(
    app_name: str,
    suite_id: str | None = None,
    suite_name: str | None = None,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    sections: list[TuskrSectionRef] = TuskrClient.list_tuskr_sections(
        app_name=app_name,
        suite_id=suite_id,
        suite_name=suite_name,
    )
    return _ok([asdict(section) for section in sections])


def list_test_suites_data(app_name: str) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    suites: list[TuskrTestSuiteRef] = TuskrClient.list_tuskr_test_suites(
        app_name=app_name
    )
    return _ok([asdict(suite) for suite in suites])


def create_test_suite_data(
    app_name: str,
    suite_name: str,
    description: str | None = None,
    create_or_get: bool = False,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    if not suite_name.strip():
        return _err(
            "validation_error",
            "suite_name must not be empty.",
            {"field": "suite_name"},
        )
    suite: TuskrTestSuiteRef | None = TuskrClient.create_tuskr_test_suite(
        app_name=app_name,
        suite_name=suite_name,
        description=description,
        create_or_get=create_or_get,
    )
    if not suite:
        return _err("create_failed", "Could not create or fetch test suite.")
    return _ok(asdict(suite))


def create_section_data(
    app_name: str,
    section_name: str,
    suite_id: str | None = None,
    suite_name: str | None = None,
    create_or_get: bool = False,
    create_suite_if_missing: bool = False,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    if not section_name.strip():
        return _err(
            "validation_error",
            "section_name must not be empty.",
            {"field": "section_name"},
        )
    if not suite_id and not suite_name:
        return _err(
            "validation_error",
            "Provide suite_id or suite_name.",
            {"field": "suite_id|suite_name"},
        )
    section: TuskrSectionRef | None = TuskrClient.create_tuskr_section(
        app_name=app_name,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        create_or_get=create_or_get,
        create_suite_if_missing=create_suite_if_missing,
    )
    if not section:
        return _err("create_failed", "Could not create or fetch section.")
    return _ok(asdict(section))


def get_sections_tree_data(app_name: str) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    section_tree: list[TuskrSectionTreeNode] = TuskrClient.get_tuskr_sections_tree(
        app_name=app_name
    )
    serialized: list[dict[str, object]] = [
        _serialize_section_tree_node(node) for node in section_tree
    ]
    return _ok(serialized)


def get_test_cases_by_section_data(
    app_name: str,
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    page: int = 1,
    page_size: int = 100,
    include_metadata: bool = True,
    automated_filter: str = "any",
) -> dict[str, object]:
    if not section_id and not section_name:
        return _err(
            "validation_error",
            "Provide section_id or section_name.",
            {"field": "section_id|section_name"},
        )
    parsed_filter: AutomatedFilter | None = _parse_automated_filter(automated_filter)
    if parsed_filter is None:
        return _err(
            "validation_error",
            "automated_filter must be one of: any, automated, manual, unset.",
            {"field": "automated_filter"},
        )
    paged: TuskrPaginatedCases = TuskrClient.get_tuskr_cases_by_section_paginated(
        app_name=app_name,
        section_id=section_id,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        page=page,
        page_size=page_size,
        automated_filter=parsed_filter,
    )
    items: list[dict[str, Any]] = [_serialize_case(case) for case in paged.items]
    if not include_metadata:
        items = [_without_case_metadata(case) for case in items]
    return _ok(
        {
            "items": items,
            "page": paged.page,
            "page_size": paged.page_size,
            "total": paged.total,
            "has_more": paged.has_more,
        }
    )


def get_test_case_data(
    app_name: str,
    case_key_or_id: str,
    include_metadata: bool = True,
) -> dict[str, object]:
    if not case_key_or_id.strip():
        return _err("validation_error", "case_key_or_id must not be empty.")
    is_case_key: bool = case_key_or_id.upper().startswith("C-")
    filter_by: str = "key" if is_case_key else "id"
    case_data: TuskrTestCaseDetailed | None = TuskrClient.get_tuskr_case_detailed(
        app_name=app_name,
        case_name=case_key_or_id,
        filter_by=filter_by,
    )
    if not case_data:
        return _err(
            "not_found",
            f"Case '{case_key_or_id}' was not found in app '{app_name}'.",
        )
    serialized_case: dict[str, Any] = _serialize_case(case_data)
    if not include_metadata:
        serialized_case = _without_case_metadata(serialized_case)
    return _ok(serialized_case)


def create_test_case_minimal_data(
    app_name: str,
    title: str,
    steps: list[dict[str, str]],
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    create_or_get: bool = False,
    pre_conditions: str | None = None,
    priority: str | None = None,
    automated: bool = True,
) -> dict[str, object]:
    if not section_id and not section_name:
        return _err(
            "validation_error",
            "Provide section_id or section_name.",
            {"field": "section_id|section_name"},
        )
    created_case: TuskrTestCaseDetailed | None = (
        TuskrClient.create_tuskr_test_case_minimal(
            app_name=app_name,
            title=title,
            steps=steps,
            section_id=section_id,
            section_name=section_name,
            suite_id=suite_id,
            suite_name=suite_name,
            create_or_get=create_or_get,
            pre_conditions=pre_conditions,
            priority=priority,
            automated=automated,
        )
    )
    if not created_case:
        return _err(
            "create_failed",
            "Could not create or fetch test case with provided payload.",
        )
    return _ok(_serialize_case(created_case))


def search_test_cases_data(
    app_name: str,
    query: str,
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    page: int = 1,
    page_size: int = 100,
    automated_filter: str = "any",
) -> dict[str, object]:
    if not query.strip():
        return _err("validation_error", "query must not be empty.", {"field": "query"})
    parsed_filter: AutomatedFilter | None = _parse_automated_filter(automated_filter)
    if parsed_filter is None:
        return _err(
            "validation_error",
            "automated_filter must be one of: any, automated, manual, unset.",
            {"field": "automated_filter"},
        )
    paged: TuskrPaginatedCases = TuskrClient.search_tuskr_test_cases(
        app_name=app_name,
        query=query,
        section_id=section_id,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        page=page,
        page_size=page_size,
        automated_filter=parsed_filter,
    )
    return _ok(_serialize_paginated_cases(paged))


def get_case_steps_data(app_name: str, case_key_or_id: str) -> dict[str, object]:
    steps: list[TuskrCaseStep] = TuskrClient.get_case_steps(
        app_name=app_name,
        case_key_or_id=case_key_or_id,
    )
    if not steps:
        return _err(
            "not_found",
            f"No steps found for case '{case_key_or_id}' in app '{app_name}'.",
        )
    return _ok([_serialize_step(step) for step in steps])


def set_test_case_automated_data(
    app_name: str,
    case_key_or_id: str,
    automated: bool,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    if not case_key_or_id.strip():
        return _err(
            "validation_error",
            "case_key_or_id must not be empty.",
            {"field": "case_key_or_id"},
        )
    updated_case: TuskrTestCaseDetailed | None = TuskrClient.set_tuskr_case_automated(
        app_name=app_name,
        case_key_or_id=case_key_or_id,
        automated=automated,
    )
    if not updated_case:
        return _err(
            "update_failed",
            f"Case '{case_key_or_id}' was not found in app '{app_name}' or update failed.",
        )
    return _ok(_serialize_case(updated_case))


def validate_tuskr_setup_data(app_name: str) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    result: TuskrSetupValidation = run_validate_tuskr_setup(app_name=app_name)
    return _ok(_serialize_setup_validation(result))


def set_test_cases_automated_bulk_data(
    app_name: str,
    case_keys_or_ids: list[str],
    automated: bool,
    skip_missing: bool = True,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    if not case_keys_or_ids:
        return _err(
            "validation_error",
            "case_keys_or_ids must not be empty.",
            {"field": "case_keys_or_ids"},
        )
    bulk_result: TuskrBulkAutomatedResult = TuskrClient.set_test_cases_automated_bulk(
        app_name=app_name,
        case_keys_or_ids=case_keys_or_ids,
        automated=automated,
        skip_missing=skip_missing,
    )
    return _ok(asdict(bulk_result))


def list_test_runs_data(
    app_name: str,
    page: int = 1,
    page_size: int = 100,
    name_contains: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    paged: dict[str, object] = tuskr_runs.list_test_runs(
        app_name=app_name,
        page=page,
        page_size=page_size,
        name_contains=name_contains,
        status=status,
    )
    raw_items: object = paged.get("items")
    items: list[TuskrTestRunSummary] = raw_items if isinstance(raw_items, list) else []
    serialized: dict[str, object] = {
        "items": [asdict(run) for run in items],
        "page": paged.get("page"),
        "page_size": paged.get("page_size"),
        "total": paged.get("total"),
        "has_more": paged.get("has_more"),
    }
    return _ok(serialized)


def get_test_run_data(
    app_name: str,
    run_id: str,
    include_results: bool = False,
    results_page: int = 1,
    result_status: str | None = None,
    test_cases: str | None = None,
) -> dict[str, object]:
    if not app_name.strip():
        return _err("validation_error", "app_name must not be empty.")
    if not run_id.strip():
        return _err(
            "validation_error", "run_id must not be empty.", {"field": "run_id"}
        )
    payload: dict[str, Any] | None = tuskr_runs.get_test_run(
        app_name=app_name,
        run_id=run_id,
        include_results=include_results,
        results_page=results_page,
        result_status=result_status,
        test_cases=test_cases,
    )
    if not payload:
        return _err(
            "not_found",
            f"Test run '{run_id}' was not found in app '{app_name}'.",
        )
    return _ok(payload)


def health_check_data() -> dict[str, object]:
    is_ok: bool
    error: TuskrError | None
    is_ok, error = TuskrClient.tuskr_health_check()
    if not is_ok:
        if error:
            return {"ok": False, "error": asdict(error)}
        return _err("unknown_error", "Health check failed.")
    return _ok({"status": "healthy"})


mcp = FastMCP("tuskr")


@mcp.tool()
def list_projects() -> dict[str, object]:
    """List Tuskr projects from your local projects config."""
    return list_projects_data()


@mcp.tool()
def list_sections(
    app_name: str,
    suite_id: str | None = None,
    suite_name: str | None = None,
) -> dict[str, object]:
    """List Tuskr project sections."""
    return list_sections_data(
        app_name=app_name,
        suite_id=suite_id,
        suite_name=suite_name,
    )


@mcp.tool()
def list_test_suites(app_name: str) -> dict[str, object]:
    """List Tuskr test suites (main folders) for a project."""
    return list_test_suites_data(app_name=app_name)


@mcp.tool()
def create_test_suite(
    app_name: str,
    suite_name: str,
    description: str | None = None,
    create_or_get: bool = False,
) -> dict[str, object]:
    """Create a Tuskr test suite (main folder)."""
    return create_test_suite_data(
        app_name=app_name,
        suite_name=suite_name,
        description=description,
        create_or_get=create_or_get,
    )


@mcp.tool()
def create_section(
    app_name: str,
    section_name: str,
    suite_id: str | None = None,
    suite_name: str | None = None,
    create_or_get: bool = False,
    create_suite_if_missing: bool = False,
) -> dict[str, object]:
    """Create a Tuskr section under a suite."""
    return create_section_data(
        app_name=app_name,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        create_or_get=create_or_get,
        create_suite_if_missing=create_suite_if_missing,
    )


@mcp.tool()
def get_sections_tree(app_name: str) -> dict[str, object]:
    """List Tuskr project sections in nested tree form."""
    return get_sections_tree_data(app_name=app_name)


@mcp.tool()
def get_test_cases_by_section(
    app_name: str,
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    page: int = 1,
    page_size: int = 100,
    include_metadata: bool = True,
    automated_filter: str = "any",
) -> dict[str, object]:
    """Get project test-cases by section; optional automated_filter: any, automated, manual, unset."""
    return get_test_cases_by_section_data(
        app_name=app_name,
        section_id=section_id,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        page=page,
        page_size=page_size,
        include_metadata=include_metadata,
        automated_filter=automated_filter,
    )


@mcp.tool()
def get_test_case(
    app_name: str,
    case_key_or_id: str,
    include_metadata: bool = True,
) -> dict[str, object]:
    """Get one detailed test-case by key (C-xxxx) or id."""
    return get_test_case_data(
        app_name=app_name,
        case_key_or_id=case_key_or_id,
        include_metadata=include_metadata,
    )


@mcp.tool()
def create_test_case_minimal(
    app_name: str,
    title: str,
    steps: list[dict[str, str]],
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    create_or_get: bool = False,
    pre_conditions: str | None = None,
    priority: str | None = None,
    automated: bool = True,
) -> dict[str, object]:
    """Create a Tuskr test-case with steps and Tuskr custom fields (automated, steps, optional pre_conditions/priority)."""
    return create_test_case_minimal_data(
        app_name=app_name,
        title=title,
        steps=steps,
        section_id=section_id,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        create_or_get=create_or_get,
        pre_conditions=pre_conditions,
        priority=priority,
        automated=automated,
    )


@mcp.tool()
def search_test_cases(
    app_name: str,
    query: str,
    section_id: str | None = None,
    section_name: str | None = None,
    suite_id: str | None = None,
    suite_name: str | None = None,
    page: int = 1,
    page_size: int = 100,
    automated_filter: str = "any",
) -> dict[str, object]:
    """Search test-cases by key/title/steps text; optional automated_filter."""
    return search_test_cases_data(
        app_name=app_name,
        query=query,
        section_id=section_id,
        section_name=section_name,
        suite_id=suite_id,
        suite_name=suite_name,
        page=page,
        page_size=page_size,
        automated_filter=automated_filter,
    )


@mcp.tool()
def get_case_steps(app_name: str, case_key_or_id: str) -> dict[str, object]:
    """Get normalized ordered steps for one case."""
    return get_case_steps_data(app_name=app_name, case_key_or_id=case_key_or_id)


@mcp.tool()
def set_test_case_automated(
    app_name: str,
    case_key_or_id: str,
    automated: bool,
) -> dict[str, object]:
    """Set the custom Tuskr field `automated` on an existing case (true or false)."""
    return set_test_case_automated_data(
        app_name=app_name,
        case_key_or_id=case_key_or_id,
        automated=automated,
    )


@mcp.tool()
def set_test_cases_automated_bulk(
    app_name: str,
    case_keys_or_ids: list[str],
    automated: bool,
    skip_missing: bool = True,
) -> dict[str, object]:
    """Set `automated` on multiple cases by key or id (automated field only)."""
    return set_test_cases_automated_bulk_data(
        app_name=app_name,
        case_keys_or_ids=case_keys_or_ids,
        automated=automated,
        skip_missing=skip_missing,
    )


@mcp.tool()
def validate_tuskr_setup(app_name: str) -> dict[str, object]:
    """Check env, project mapping, AutoGen test-case type, and custom fields for an app."""
    return validate_tuskr_setup_data(app_name=app_name)


@mcp.tool()
def list_test_runs(
    app_name: str,
    page: int = 1,
    page_size: int = 100,
    name_contains: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """List test runs for a project (read-only)."""
    return list_test_runs_data(
        app_name=app_name,
        page=page,
        page_size=page_size,
        name_contains=name_contains,
        status=status,
    )


@mcp.tool()
def get_test_run(
    app_name: str,
    run_id: str,
    include_results: bool = False,
    results_page: int = 1,
    result_status: str | None = None,
    test_cases: str | None = None,
) -> dict[str, object]:
    """Get one test run by id; set include_results=true for paginated run results (read-only)."""
    return get_test_run_data(
        app_name=app_name,
        run_id=run_id,
        include_results=include_results,
        results_page=results_page,
        result_status=result_status,
        test_cases=test_cases,
    )


@mcp.tool()
def health_check() -> dict[str, object]:
    """Validate Tuskr env/auth and API connectivity."""
    return health_check_data()


def main() -> None:
    mcp.run()
