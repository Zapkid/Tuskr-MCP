"""Read-only Tuskr test run API helpers."""

from __future__ import annotations

from typing import Any

from tuskr_mcp.client import TuskrClient
from tuskr_mcp import parsing
from tuskr_mcp.types import TuskrProjectStructure, TuskrTestRunSummary


def _normalize_test_run(row: dict[str, Any]) -> TuskrTestRunSummary:
    return TuskrTestRunSummary(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or ""),
        key=str(row.get("key")) if row.get("key") else None,
        status=str(row.get("status")) if row.get("status") else None,
        project=str(row.get("project")) if row.get("project") else None,
        raw=row,
    )


def list_test_runs(
    app_name: str,
    page: int = 1,
    page_size: int = 100,
    name_contains: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """List test runs for a project (read-only)."""
    project: TuskrProjectStructure | None = TuskrClient.get_project_data(app_name.lower())
    if not project:
        return {"items": [], "page": page, "page_size": page_size, "total": 0, "has_more": False}

    normalized_page: int = page if page > 0 else 1
    normalized_page_size: int = min(page_size if page_size > 0 else 100, 100)
    params: dict[str, str] = {
        "filter[project]": project.project_id,
        "page": str(normalized_page),
        "limit": str(normalized_page_size),
    }
    if name_contains and name_contains.strip():
        params["filter[name]"] = name_contains.strip()
    if status and status.strip():
        params["filter[status]"] = status.strip()

    payload: dict[str, Any] | None = TuskrClient._request_with_retries(
        method="GET",
        url=TuskrClient._tenant_url("test-run"),
        params=params,
    )
    if not payload:
        return {
            "items": [],
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": 0,
            "has_more": False,
        }

    rows: list[dict[str, Any]] = parsing.extract_rows(payload)
    items: list[TuskrTestRunSummary] = [_normalize_test_run(row) for row in rows]
    meta: dict[str, Any] = parsing.extract_meta(payload)
    total: int | None = None
    if meta.get("total") is not None:
        total = parsing.safe_int(meta.get("total"), fallback=0)
    has_more: bool = bool(
        meta.get("hasMore")
        or (
            total is not None
            and (normalized_page * normalized_page_size) < total
        )
        or (len(rows) >= normalized_page_size and len(rows) > 0)
    )
    return {
        "items": items,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "has_more": has_more,
    }


def get_test_run(
    app_name: str,
    run_id: str,
    include_results: bool = False,
    results_page: int = 1,
    result_status: str | None = None,
    test_cases: str | None = None,
) -> dict[str, Any] | None:
    """Fetch one test run by id; optionally include paginated results (read-only)."""
    trimmed_run_id: str = run_id.strip()
    if not trimmed_run_id:
        return None

    project: TuskrProjectStructure | None = TuskrClient.get_project_data(app_name.lower())
    if not project:
        return None

    endpoint: str = TuskrClient._tenant_url(f"test-run/{trimmed_run_id}")
    params: dict[str, str] = {}
    if include_results:
        endpoint = TuskrClient._tenant_url(f"test-run/{trimmed_run_id}/results")
        params["page"] = str(results_page if results_page > 0 else 1)
        if result_status and result_status.strip():
            params["status"] = result_status.strip()
        if test_cases and test_cases.strip():
            params["testCases"] = test_cases.strip()

    payload: dict[str, Any] | None = TuskrClient._request_with_retries(
        method="GET",
        url=endpoint,
        params=params or None,
    )
    return payload


def get_test_run_all_results(
    app_name: str,
    run_id: str,
    max_pages: int = 50,
) -> dict[str, Any]:
    """Fetch all result pages for a test run (read-only, capped)."""
    combined: dict[str, Any] = {"meta": {}, "data": []}
    page: int = 1
    while page <= max_pages:
        payload: dict[str, Any] | None = get_test_run(
            app_name=app_name,
            run_id=run_id,
            include_results=True,
            results_page=page,
        )
        if not payload:
            break
        page_rows: list[dict[str, Any]] = parsing.extract_rows(payload)
        if not combined["meta"] and payload.get("meta"):
            combined["meta"] = payload.get("meta")
        data_list: list[dict[str, Any]] = combined.get("data") or []
        if isinstance(data_list, list):
            data_list.extend(page_rows)
            combined["data"] = data_list
        if len(page_rows) < 100:
            break
        page += 1
    return combined
