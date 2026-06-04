"""Tuskr REST API client for the MCP server (no pytest/allure dependencies)."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Literal

import requests
from requests import Session

from tuskr_mcp import custom_fields, parsing
from tuskr_mcp.config import load_env_values, tuskr_projects
from tuskr_mcp.types import (
    AutomatedFilter,
    TuskrBulkAutomatedResult,
    TuskrCaseStep,
    TuskrError,
    TuskrPaginatedCases,
    TuskrProjectStructure,
    TuskrSectionRef,
    TuskrSectionTreeNode,
    TuskrTestCaseDetailed,
    TuskrTestSuiteRef,
)


class TuskrClient:
    BASE_URL: str = "https://api.tuskr.live/api"
    TUSKR_TENANT_ID: str = ""
    TUSKR_API_TOKEN: str = ""
    get_tuskr_case_endpoint: str = ""

    SECTION_CACHE_TTL_SECONDS: int = 120
    REQUEST_TIMEOUT_SECONDS: int = 20
    REQUEST_RETRIES: int = 3
    RETRY_BACKOFF_SECONDS: float = 0.7
    DEFAULT_AUTOGEN_TEST_TYPE_NAME: str = "AutoGen"

    _section_cache: dict[str, dict[str, object]] = {}
    _case_type_cache: dict[str, str] = {}
    _active_session: Session | None = None

    @staticmethod
    def generate_tuskr_vars() -> None:
        tenant_id_env: str = os.getenv("TUSKR_TENANT_ID", "").strip()
        api_token_env: str = os.getenv("TUSKR_API_TOKEN", "").strip()
        if not tenant_id_env or not api_token_env:
            file_values: dict[str, str] = load_env_values()
            tenant_id_env = (
                tenant_id_env or file_values.get("TUSKR_TENANT_ID", "").strip()
            )
            api_token_env = (
                api_token_env or file_values.get("TUSKR_API_TOKEN", "").strip()
            )
        TuskrClient.TUSKR_TENANT_ID = tenant_id_env
        TuskrClient.TUSKR_API_TOKEN = api_token_env
        TuskrClient.get_tuskr_case_endpoint = TuskrClient._tenant_url("test-case")

    @staticmethod
    def _close_active_session() -> None:
        if TuskrClient._active_session:
            TuskrClient._active_session.close()
            TuskrClient._active_session = None

    @staticmethod
    def _tenant_url(resource: str) -> str:
        return f"{TuskrClient.BASE_URL}/tenant/{TuskrClient.TUSKR_TENANT_ID}/{resource}"

    @staticmethod
    def _create_session() -> Session | None:
        try:
            TuskrClient.generate_tuskr_vars()
            session: Session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {TuskrClient.TUSKR_API_TOKEN}",
                    "Content-Type": "application/json",
                }
            )
            TuskrClient._active_session = session
            return session
        except Exception as exc:
            print(f"Tuskr MCP - ERROR creating session: {exc}")
            return None

    @staticmethod
    def get_project_data(project_name: str) -> TuskrProjectStructure | None:
        tuskr_project = tuskr_projects.get(project_name.lower())
        if tuskr_project:
            return tuskr_project
        print(f"Tuskr MCP - Project not found: {project_name}")
        return None

    # --- HTTP ---

    @staticmethod
    def _request_with_retries(
        method: Literal["GET", "POST"],
        url: str,
        params: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        session: Session | None = TuskrClient._create_session()
        if not session:
            return None

        attempts: int = (
            TuskrClient.REQUEST_RETRIES if TuskrClient.REQUEST_RETRIES > 0 else 1
        )
        for attempt in range(1, attempts + 1):
            try:
                if method == "GET":
                    response = session.get(
                        url,
                        params=params,
                        timeout=TuskrClient.REQUEST_TIMEOUT_SECONDS,
                    )
                else:
                    response = session.post(
                        url,
                        json=json_payload,
                        timeout=TuskrClient.REQUEST_TIMEOUT_SECONDS,
                    )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                TuskrClient._close_active_session()
                return payload
            except Exception as exc:
                if attempt == attempts:
                    print(f"Tuskr MCP - ERROR request failed ({method} {url}): {exc}")
                    TuskrClient._close_active_session()
                    return None
                time.sleep(TuskrClient.RETRY_BACKOFF_SECONDS * attempt)
        TuskrClient._close_active_session()
        return None

    # --- Section cache ---

    @staticmethod
    def _get_cached_sections(cache_key: str) -> list[TuskrSectionRef] | None:
        cache_entry: dict[str, object] | None = TuskrClient._section_cache.get(
            cache_key
        )
        if not cache_entry:
            return None

        expires_at: float = parsing.safe_int(cache_entry.get("expires_at"), fallback=0)
        if time.time() > expires_at:
            TuskrClient._section_cache.pop(cache_key, None)
            return None

        cached_sections: object = cache_entry.get("items")
        if isinstance(cached_sections, list):
            return [
                section
                for section in cached_sections
                if isinstance(section, TuskrSectionRef)
            ]
        return None

    @staticmethod
    def _set_cached_sections(cache_key: str, sections: list[TuskrSectionRef]) -> None:
        TuskrClient._section_cache[cache_key] = {
            "expires_at": time.time() + TuskrClient.SECTION_CACHE_TTL_SECONDS,
            "items": sections,
        }

    # --- Suites ---

    @staticmethod
    def list_tuskr_test_suites(app_name: str) -> list[TuskrTestSuiteRef]:
        """Returns all test suites (main folders) for a project."""
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return []
        endpoint: str = TuskrClient._tenant_url("test-suite")
        payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="GET",
            url=endpoint,
            params={"filter[project]": project.project_id, "limit": "500"},
        )
        if not payload:
            return []
        rows: list[dict[str, Any]] = parsing.extract_rows(payload)
        suites: list[TuskrTestSuiteRef] = []
        for row in rows:
            suite_ref: TuskrTestSuiteRef | None = parsing.to_suite_ref(row)
            if suite_ref:
                suites.append(suite_ref)
        suites.sort(key=lambda suite: suite.name.lower())
        return suites

    @staticmethod
    def resolve_tuskr_test_suite(
        app_name: str,
        suite_id: str | None = None,
        suite_name: str | None = None,
    ) -> TuskrTestSuiteRef | None:
        """Resolves a test suite by id or exact name."""
        suites: list[TuskrTestSuiteRef] = TuskrClient.list_tuskr_test_suites(app_name)
        if suite_id:
            for suite in suites:
                if suite.id == suite_id:
                    return suite
            return TuskrTestSuiteRef(id=suite_id, name=suite_name or suite_id)
        if not suite_name:
            return None
        normalized_name: str = suite_name.strip().lower()
        exact_matches: list[TuskrTestSuiteRef] = [
            suite for suite in suites if suite.name.strip().lower() == normalized_name
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            print(f"Tuskr MCP - Ambiguous suite name: {suite_name}")
            return None
        partial_matches: list[TuskrTestSuiteRef] = [
            suite for suite in suites if normalized_name in suite.name.strip().lower()
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            print(f"Tuskr MCP - Ambiguous suite partial match: {suite_name}")
            return None
        return None

    @staticmethod
    def _invalidate_sections_cache_for_project(project_id: str) -> None:
        """Invalidates cached section lists for a specific project."""
        project_prefix: str = f"{project_id}:"
        cache_keys_to_remove: list[str] = [
            cache_key
            for cache_key in TuskrClient._section_cache
            if cache_key.startswith(project_prefix)
        ]
        for cache_key in cache_keys_to_remove:
            TuskrClient._section_cache.pop(cache_key, None)

    @staticmethod
    def create_tuskr_test_suite(
        app_name: str,
        suite_name: str,
        description: str | None = None,
        create_or_get: bool = False,
    ) -> TuskrTestSuiteRef | None:
        """Creates a Tuskr test suite or returns an existing one."""
        trimmed_suite_name: str = suite_name.strip()
        if not trimmed_suite_name:
            print("Tuskr MCP - Cannot create suite: empty suite_name.")
            return None

        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None

        if create_or_get:
            existing_suite: TuskrTestSuiteRef | None = (
                TuskrClient.resolve_tuskr_test_suite(
                    app_name=app_name,
                    suite_name=trimmed_suite_name,
                )
            )
            if existing_suite:
                return existing_suite

        request_data: dict[str, str] = {
            "project": str(project.project_id),
            "name": trimmed_suite_name,
        }
        if description and description.strip():
            request_data["description"] = description.strip()

        payload: dict[str, dict[str, str]] = {"data": request_data}
        endpoint: str = TuskrClient._tenant_url("test-suite")
        response_payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="POST",
            url=endpoint,
            json_payload=payload,
        )
        if not response_payload:
            return None

        raw_suite: Any = (
            response_payload.get("data") if isinstance(response_payload, dict) else None
        )
        if not isinstance(raw_suite, dict):
            raw_suite = response_payload
        if not isinstance(raw_suite, dict):
            return None

        created_suite: TuskrTestSuiteRef | None = parsing.to_suite_ref(raw_suite)
        if created_suite:
            TuskrClient._invalidate_sections_cache_for_project(str(project.project_id))
            return created_suite
        return None

    @staticmethod
    def create_tuskr_section(
        app_name: str,
        section_name: str,
        suite_id: str | None = None,
        suite_name: str | None = None,
        create_or_get: bool = False,
        create_suite_if_missing: bool = False,
    ) -> TuskrSectionRef | None:
        """Creates a Tuskr section in a suite or returns an existing one."""
        trimmed_section_name: str = section_name.strip()
        if not trimmed_section_name:
            print("Tuskr MCP - Cannot create section: empty section_name.")
            return None
        if not suite_id and not suite_name:
            print(
                "Tuskr MCP - Cannot create section: suite_id or suite_name is required."
            )
            return None

        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None

        resolved_suite: TuskrTestSuiteRef | None = TuskrClient.resolve_tuskr_test_suite(
            app_name=app_name,
            suite_id=suite_id,
            suite_name=suite_name,
        )
        if not resolved_suite and suite_name and create_suite_if_missing:
            resolved_suite = TuskrClient.create_tuskr_test_suite(
                app_name=app_name,
                suite_name=suite_name,
                create_or_get=True,
            )
        if not resolved_suite or not resolved_suite.id:
            print(
                f"Tuskr MCP - Cannot create section: suite not found for '{suite_id or suite_name}'."
            )
            return None

        if create_or_get:
            TuskrClient._invalidate_sections_cache_for_project(str(project.project_id))
            existing_sections: list[TuskrSectionRef] = TuskrClient.list_tuskr_sections(
                app_name=app_name,
                suite_id=resolved_suite.id,
            )
            normalized_section_name: str = trimmed_section_name.lower()
            exact_matches: list[TuskrSectionRef] = [
                section
                for section in existing_sections
                if (section.name or "").strip().lower() == normalized_section_name
            ]
            if len(exact_matches) == 1:
                return exact_matches[0]
            if len(exact_matches) > 1:
                print(
                    f"Tuskr MCP - Ambiguous section name in suite '{resolved_suite.name}': {section_name}"
                )
                return None

        payload: dict[str, dict[str, str]] = {
            "data": {
                "project": str(project.project_id),
                "name": trimmed_section_name,
                "testSuite": str(resolved_suite.id),
            }
        }
        endpoint: str = TuskrClient._tenant_url("test-suite-section")
        response_payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="POST",
            url=endpoint,
            json_payload=payload,
        )
        if not response_payload:
            return None

        raw_section: Any = (
            response_payload.get("data") if isinstance(response_payload, dict) else None
        )
        if not isinstance(raw_section, dict):
            raw_section = response_payload
        if not isinstance(raw_section, dict):
            return None

        created_section: TuskrSectionRef | None = parsing.to_section_ref(raw_section)
        if not created_section:
            return None
        created_section.suite_id = resolved_suite.id
        created_section.suite_name = resolved_suite.name
        if not created_section.path:
            created_section.path = (
                f"{resolved_suite.name}/{created_section.name or created_section.id}"
            )
        TuskrClient._invalidate_sections_cache_for_project(str(project.project_id))
        return created_section

    @staticmethod
    def resolve_tuskr_test_case_type_id(
        app_name: str,
        case_type_name: str = DEFAULT_AUTOGEN_TEST_TYPE_NAME,
    ) -> str | None:
        """Resolves test-case-type id by exact name for a project."""
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None
        cache_key: str = f"{project.project_id}:{case_type_name.strip().lower()}"
        cached_type_id: str | None = TuskrClient._case_type_cache.get(cache_key)
        if cached_type_id:
            return cached_type_id

        endpoint: str = TuskrClient._tenant_url("test-case-type")
        payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="GET",
            url=endpoint,
            params={"filter[project]": project.project_id, "limit": "200"},
        )
        if not payload:
            return None
        rows: list[dict[str, Any]] = parsing.extract_rows(payload)
        normalized_name: str = case_type_name.strip().lower()
        for row in rows:
            name_value: str = str(row.get("name") or "").strip().lower()
            if name_value == normalized_name:
                case_type_id: str = str(row.get("id"))
                TuskrClient._case_type_cache[cache_key] = case_type_id
                return case_type_id
        return None

    # --- Sections ---

    @staticmethod
    def list_tuskr_sections(
        app_name: str,
        suite_id: str | None = None,
        suite_name: str | None = None,
    ) -> list[TuskrSectionRef]:
        """Returns sections for a project, optionally filtered by suite."""
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return []
        resolved_suite: TuskrTestSuiteRef | None = TuskrClient.resolve_tuskr_test_suite(
            app_name=app_name,
            suite_id=suite_id,
            suite_name=suite_name,
        )

        cache_suffix: str = resolved_suite.id if resolved_suite else "all"
        cache_key: str = f"{project.project_id}:{cache_suffix}"
        cached_sections: list[TuskrSectionRef] | None = (
            TuskrClient._get_cached_sections(cache_key)
        )
        if cached_sections is not None:
            return cached_sections

        suites_endpoint: str = TuskrClient._tenant_url("test-suite")
        params: dict[str, str] = {"filter[project]": project.project_id, "limit": "500"}
        if resolved_suite:
            params["filter[id]"] = resolved_suite.id
        payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="GET",
            url=suites_endpoint,
            params=params,
        )
        if not payload:
            return []
        rows: list[dict[str, Any]] = parsing.extract_rows(payload)

        resolved_sections: list[TuskrSectionRef] = []
        for suite_row in rows:
            suite_ref: TuskrTestSuiteRef | None = parsing.to_suite_ref(suite_row)
            if not suite_ref:
                continue
            suite_sections: Any = suite_row.get("sections") or []
            if not isinstance(suite_sections, list):
                continue
            for section_row in suite_sections:
                if not isinstance(section_row, dict):
                    continue
                section_ref: TuskrSectionRef | None = parsing.to_section_ref(
                    section_row
                )
                if not section_ref:
                    continue
                section_ref.suite_id = suite_ref.id
                section_ref.suite_name = suite_ref.name
                section_ref.path = (
                    f"{suite_ref.name}/{section_ref.name or section_ref.id}"
                )
                resolved_sections.append(section_ref)

        seen_keys: set[str] = set()
        unique_sections: list[TuskrSectionRef] = []
        for section in resolved_sections:
            if section.id in seen_keys:
                continue
            seen_keys.add(section.id)
            unique_sections.append(section)
        TuskrClient._set_cached_sections(cache_key, unique_sections)
        return unique_sections

    @staticmethod
    def resolve_tuskr_section(
        app_name: str,
        section_id: str | None = None,
        section_name: str | None = None,
        suite_id: str | None = None,
        suite_name: str | None = None,
    ) -> TuskrSectionRef | None:
        """Resolves a section reference by id or name/path."""
        if section_id:
            sections_by_id: list[TuskrSectionRef] = [
                section
                for section in TuskrClient.list_tuskr_sections(
                    app_name=app_name,
                    suite_id=suite_id,
                    suite_name=suite_name,
                )
                if section.id == section_id
            ]
            if sections_by_id:
                return sections_by_id[0]
            return TuskrSectionRef(id=section_id, name=section_name, path=None)

        if not section_name:
            return None

        sections: list[TuskrSectionRef] = TuskrClient.list_tuskr_sections(
            app_name=app_name,
            suite_id=suite_id,
            suite_name=suite_name,
        )
        normalized_name: str = section_name.strip().lower()

        exact_path_matches: list[TuskrSectionRef] = [
            section
            for section in sections
            if (section.path or "").strip().lower() == normalized_name
        ]
        if len(exact_path_matches) == 1:
            return exact_path_matches[0]
        if len(exact_path_matches) > 1:
            print(f"Tuskr MCP - Ambiguous section path '{section_name}'")
            return None

        exact_name_matches: list[TuskrSectionRef] = [
            section
            for section in sections
            if (section.name or "").strip().lower() == normalized_name
        ]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]
        if len(exact_name_matches) > 1:
            print(
                "Tuskr - Ambiguous section name. Use full path instead: "
                + f"'{section_name}'"
            )
            return None

        partial_matches: list[TuskrSectionRef] = [
            section
            for section in sections
            if normalized_name in (section.path or "").strip().lower()
            or normalized_name in (section.name or "").strip().lower()
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            print(
                "Tuskr - Ambiguous partial section match. Use exact path: "
                + f"'{section_name}'"
            )
            return None
        return None

    # --- Cases ---

    @staticmethod
    def get_tuskr_sections_tree(app_name: str) -> list[TuskrSectionTreeNode]:
        """Returns a nested project section tree for prompt-friendly discovery."""
        suites: list[TuskrTestSuiteRef] = TuskrClient.list_tuskr_test_suites(
            app_name=app_name
        )
        tree: list[TuskrSectionTreeNode] = []
        for suite in suites:
            suite_sections: list[TuskrSectionRef] = TuskrClient.list_tuskr_sections(
                app_name=app_name,
                suite_id=suite.id,
            )
            child_nodes: list[TuskrSectionTreeNode] = [
                TuskrSectionTreeNode(
                    id=section.id,
                    name=section.name,
                    path=section.path,
                    children=[],
                )
                for section in suite_sections
            ]
            suite_node: TuskrSectionTreeNode = TuskrSectionTreeNode(
                id=suite.id,
                name=suite.name,
                path=suite.path,
                children=child_nodes,
            )
            tree.append(suite_node)
        return tree

    @staticmethod
    def get_tuskr_cases_by_section_paginated(
        app_name: str,
        section_id: str | None = None,
        section_name: str | None = None,
        suite_id: str | None = None,
        suite_name: str | None = None,
        page: int = 1,
        page_size: int = 100,
        automated_filter: AutomatedFilter = "any",
    ) -> TuskrPaginatedCases:
        """Fetches paginated test-cases for a project section."""
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return TuskrPaginatedCases(items=[], page=page, page_size=page_size)

        resolved_section: TuskrSectionRef | None = TuskrClient.resolve_tuskr_section(
            app_name=app_name,
            section_id=section_id,
            section_name=section_name,
            suite_id=suite_id,
            suite_name=suite_name,
        )
        if not resolved_section or not resolved_section.id:
            print(
                f"Tuskr - Section not found for project '{app_name}' by id/name: {section_id or section_name}"
            )
            return TuskrPaginatedCases(items=[], page=page, page_size=page_size)

        normalized_page: int = page if page > 0 else 1
        normalized_page_size: int = page_size if page_size > 0 else 100
        params: dict[str, str] = {
            "filter[project]": project.project_id,
            "filter[testSuiteSection]": resolved_section.id,
            "sort[name]": "ASC",
            "page": str(normalized_page),
            "limit": str(normalized_page_size),
        }
        if automated_filter != "unset":
            custom_fields.apply_automated_filter_params(params, automated_filter)
        try:
            payload: dict[str, Any] | None = TuskrClient._request_with_retries(
                method="GET",
                url=TuskrClient.get_tuskr_case_endpoint,
                params=params,
            )
            if not payload:
                return TuskrPaginatedCases(
                    items=[],
                    page=normalized_page,
                    page_size=normalized_page_size,
                )

            rows: list[dict[str, Any]] = parsing.extract_rows(payload)
            detailed_cases: list[TuskrTestCaseDetailed] = [
                parsing.normalize_test_case(case_data) for case_data in rows
            ]
            detailed_cases = custom_fields.filter_cases_by_automated(
                detailed_cases, automated_filter
            )
            meta: dict[str, Any] = parsing.extract_meta(payload)
            total_rows: int | None = None
            if meta.get("total") is not None:
                total_rows = parsing.safe_int(meta.get("total"), fallback=0)
            has_more: bool = bool(
                meta.get("hasMore")
                or (
                    total_rows is not None
                    and (normalized_page * normalized_page_size) < total_rows
                )
                or (len(rows) >= normalized_page_size and len(rows) > 0)
            )
            return TuskrPaginatedCases(
                items=detailed_cases,
                page=normalized_page,
                page_size=normalized_page_size,
                total=total_rows,
                has_more=has_more,
            )

        except Exception as e:
            print(f"Tuskr MCP - ERROR getting cases by section: {e}")
            return TuskrPaginatedCases(
                items=[],
                page=normalized_page,
                page_size=normalized_page_size,
            )

    @staticmethod
    def search_tuskr_test_cases(
        app_name: str,
        query: str,
        section_id: str | None = None,
        section_name: str | None = None,
        suite_id: str | None = None,
        suite_name: str | None = None,
        page: int = 1,
        page_size: int = 100,
        automated_filter: AutomatedFilter = "any",
    ) -> TuskrPaginatedCases:
        """Searches test-cases by query in case key, title, and step text."""
        paginated_result: TuskrPaginatedCases = (
            TuskrClient.get_tuskr_cases_by_section_paginated(
                app_name=app_name,
                section_id=section_id,
                section_name=section_name,
                suite_id=suite_id,
                suite_name=suite_name,
                page=page,
                page_size=page_size,
                automated_filter=automated_filter,
            )
        )
        normalized_query: str = query.strip().lower()
        if not normalized_query:
            return paginated_result

        filtered_items: list[TuskrTestCaseDetailed] = []
        for case_data in paginated_result.items:
            joined_value: str = custom_fields.case_search_haystack(
                case_data.key,
                case_data.name,
                case_data,
            )
            if normalized_query in joined_value:
                filtered_items.append(case_data)

        return TuskrPaginatedCases(
            items=filtered_items,
            page=paginated_result.page,
            page_size=paginated_result.page_size,
            total=len(filtered_items),
            has_more=False,
        )

    @staticmethod
    def get_case_steps(app_name: str, case_key_or_id: str) -> list[TuskrCaseStep]:
        """Returns normalized test-steps for one case."""
        is_case_key: bool = case_key_or_id.upper().startswith("C-")
        filter_by: str = "key" if is_case_key else "id"
        case_data: TuskrTestCaseDetailed | None = TuskrClient.get_tuskr_case_detailed(
            app_name=app_name,
            case_name=case_key_or_id,
            filter_by=filter_by,
        )
        if not case_data:
            return []
        return case_data.steps or []

    @staticmethod
    def get_tuskr_case_detailed(
        app_name: str, case_name: str, filter_by: str = "key"
    ) -> TuskrTestCaseDetailed | None:
        """Fetches one detailed Tuskr case, including section and steps."""
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None

        params: dict[str, str] = {
            "filter[project]": project.project_id,
            f"filter[{filter_by}]": case_name,
        }
        try:
            payload: dict[str, Any] | None = TuskrClient._request_with_retries(
                method="GET",
                url=TuskrClient.get_tuskr_case_endpoint,
                params=params,
            )
            if not payload:
                return None
            rows: list[dict[str, Any]] = parsing.extract_rows(payload)
            matched_row: dict[str, Any] | None = parsing.pick_exact_case_row(
                rows,
                case_name,
                filter_by,
            )
            if not matched_row:
                return None
            detailed_case: TuskrTestCaseDetailed = parsing.normalize_test_case(
                matched_row
            )
            return detailed_case
        except Exception as e:
            print(f"Tuskr MCP - ERROR getting detailed case: {e}")
            return None

    @staticmethod
    def _build_minimal_case_steps(
        steps: list[dict[str, str]],
    ) -> list[dict[str, str | int]]:
        """Builds ordered step payload for Tuskr minimal case creation."""
        mapped_steps: list[dict[str, str | int]] = []
        for step_index, step in enumerate(steps, start=1):
            mapped_step: dict[str, str | int] = {
                "index": step_index,
                "action": step.get("action", ""),
                "expectedResult": step.get("expected_result", ""),
            }
            if step.get("title"):
                mapped_step["title"] = step.get("title", "")
            mapped_steps.append(mapped_step)
        return mapped_steps

    @staticmethod
    def _build_minimal_case_external_id(
        project_id: str,
        section_id: str,
        title: str,
    ) -> str:
        """Build a stable upsert key for Tuskr minimal case creation."""
        normalized_title: str = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip(
            "-"
        )
        if not normalized_title:
            normalized_title = "case"
        return f"autogen-{project_id}-{section_id}-{normalized_title}"[:180]

    @staticmethod
    def _validate_minimal_case_input(
        title: str,
        steps: list[dict[str, str]],
    ) -> TuskrError | None:
        """Validates minimal test-case creation input."""
        trimmed_title: str = title.strip()
        if not trimmed_title:
            return TuskrError(
                code="validation_error",
                message="Case title must not be empty.",
                details={"field": "title"},
            )
        if len(trimmed_title) > 255:
            return TuskrError(
                code="validation_error",
                message="Case title exceeds max length (255).",
                details={"field": "title", "max_length": 255},
            )
        if not steps:
            return TuskrError(
                code="validation_error",
                message="At least one step is required.",
                details={"field": "steps"},
            )

        for step_index, step in enumerate(steps, start=1):
            action_value: str = (step.get("action") or "").strip()
            expected_value: str = (step.get("expected_result") or "").strip()
            if not action_value:
                return TuskrError(
                    code="validation_error",
                    message="Each step requires a non-empty action.",
                    details={"field": f"steps[{step_index}].action"},
                )
            if len(action_value) > 2000:
                return TuskrError(
                    code="validation_error",
                    message="Step action exceeds max length (2000).",
                    details={
                        "field": f"steps[{step_index}].action",
                        "max_length": 2000,
                    },
                )
            if len(expected_value) > 2000:
                return TuskrError(
                    code="validation_error",
                    message="Step expected_result exceeds max length (2000).",
                    details={
                        "field": f"steps[{step_index}].expected_result",
                        "max_length": 2000,
                    },
                )

        return None

    @staticmethod
    def _find_case_by_title_in_section(
        app_name: str,
        section_id: str,
        title: str,
    ) -> TuskrTestCaseDetailed | None:
        """Finds an existing case by exact title in section."""
        search_page: int = 1
        max_pages: int = 10
        normalized_title: str = title.strip().lower()

        while search_page <= max_pages:
            page_result: TuskrPaginatedCases = (
                TuskrClient.get_tuskr_cases_by_section_paginated(
                    app_name=app_name,
                    section_id=section_id,
                    page=search_page,
                    page_size=100,
                )
            )
            for case_data in page_result.items:
                if case_data.name.strip().lower() == normalized_title:
                    return case_data
            if not page_result.has_more:
                break
            search_page += 1
        return None

    @staticmethod
    def create_tuskr_test_case_minimal(
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
    ) -> TuskrTestCaseDetailed | None:
        """Creates a test-case in Tuskr from minimal fields and returns normalized data."""
        validation_error: TuskrError | None = TuskrClient._validate_minimal_case_input(
            title=title,
            steps=steps,
        )
        if validation_error:
            print(f"Tuskr MCP - Validation failed: {validation_error.message}")
            return None

        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None

        resolved_section: TuskrSectionRef | None = TuskrClient.resolve_tuskr_section(
            app_name=app_name,
            section_id=section_id,
            section_name=section_name,
            suite_id=suite_id,
            suite_name=suite_name,
        )
        if not resolved_section or not resolved_section.id:
            print(
                f"Tuskr - Cannot create case, section not found for '{app_name}': {section_id or section_name}"
            )
            return None

        if create_or_get:
            existing_case: TuskrTestCaseDetailed | None = (
                TuskrClient._find_case_by_title_in_section(
                    app_name=app_name,
                    section_id=resolved_section.id,
                    title=title,
                )
            )
            if existing_case:
                return existing_case

        autogen_type_id: str | None = TuskrClient.resolve_tuskr_test_case_type_id(
            app_name=app_name,
            case_type_name=TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME,
        )
        if not autogen_type_id:
            print(
                "Tuskr - Cannot create case: test-case-type "
                + f"'{TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME}' not found."
            )
            return None

        mapped_steps: list[dict[str, str | int]] = (
            TuskrClient._build_minimal_case_steps(steps)
        )
        external_id: str = TuskrClient._build_minimal_case_external_id(
            project_id=str(project.project_id),
            section_id=str(resolved_section.id),
            title=title,
        )
        request_payload: dict[str, dict[str, Any]] = {
            "data": {
                "project": str(project.project_id),
                "name": title,
                "section": str(resolved_section.id),
                "externalId": external_id,
                "testCaseTypeId": autogen_type_id,
                "testCaseType": TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME,
                "steps": custom_fields.build_api_steps(mapped_steps),
                "testSuite": str(
                    resolved_section.suite_name
                    or resolved_section.suite_id
                    or suite_name
                    or suite_id
                    or ""
                ),
                "testSuiteSection": str(
                    resolved_section.name or section_name or section_id or ""
                ),
                "customFields": custom_fields.build_create_custom_fields(
                    mapped_steps,
                    automated=automated,
                    pre_conditions=pre_conditions,
                    priority=priority,
                ),
            }
        }
        create_endpoint: str = TuskrClient._tenant_url("test-case/upsert")
        try:
            payload: dict[str, Any] | None = TuskrClient._request_with_retries(
                method="POST",
                url=create_endpoint,
                json_payload=request_payload,
            )
            if not payload:
                return None
            raw_case: dict[str, Any] = payload.get("data") or payload
            normalized_case: TuskrTestCaseDetailed = parsing.normalize_test_case(
                raw_case
            )
            if not normalized_case.section:
                normalized_case.section = resolved_section
            if not normalized_case.steps:
                normalized_case.steps = parsing.extract_case_steps(
                    {"steps": request_payload["data"]["steps"]}
                )
            return normalized_case
        except Exception as e:
            print(f"Tuskr MCP - ERROR creating minimal test case: {e}")
            return None

    # --- Health ---

    @staticmethod
    def tuskr_health_check() -> tuple[bool, TuskrError | None]:
        """Performs auth/config preflight checks for Tuskr API usage."""
        TuskrClient.generate_tuskr_vars()
        if not TuskrClient.TUSKR_TENANT_ID:
            return (
                False,
                TuskrError(
                    code="missing_env",
                    message="Missing TUSKR_TENANT_ID environment variable.",
                    details={"env_var": "TUSKR_TENANT_ID"},
                ),
            )
        if not TuskrClient.TUSKR_API_TOKEN:
            return (
                False,
                TuskrError(
                    code="missing_env",
                    message="Missing TUSKR_API_TOKEN environment variable.",
                    details={"env_var": "TUSKR_API_TOKEN"},
                ),
            )

        sample_endpoint: str = TuskrClient._tenant_url("test-case")
        sample_project: TuskrProjectStructure | None = None
        if tuskr_projects:
            sample_project = next(iter(tuskr_projects.values()))
        if not sample_project:
            return (
                False,
                TuskrError(
                    code="configuration_error",
                    message=(
                        "No Tuskr projects configured. Copy tuskr_projects.example.json "
                        "to tuskr_projects.local.json."
                    ),
                ),
            )
        sample_payload: dict[str, Any] | None = TuskrClient._request_with_retries(
            method="GET",
            url=sample_endpoint,
            params={
                "limit": "1",
                "filter[project]": sample_project.project_id,
            },
        )
        if sample_payload is None:
            return (
                False,
                TuskrError(
                    code="auth_or_connectivity_error",
                    message="Unable to query Tuskr API with current credentials.",
                ),
            )
        return True, None

    @staticmethod
    def set_tuskr_case_automated(
        app_name: str,
        case_key_or_id: str,
        automated: bool,
    ) -> TuskrTestCaseDetailed | None:
        """Sets the custom boolean field `automated` on an existing test case (upsert)."""
        trimmed: str = case_key_or_id.strip()
        if not trimmed:
            print("Tuskr MCP - Cannot set automated: empty case_key_or_id.")
            return None
        project: TuskrProjectStructure | None = TuskrClient.get_project_data(
            app_name.lower()
        )
        if not project:
            return None
        is_case_key: bool = trimmed.upper().startswith("C-")
        filter_by: str = "key" if is_case_key else "id"
        existing: TuskrTestCaseDetailed | None = TuskrClient.get_tuskr_case_detailed(
            app_name=app_name,
            case_name=trimmed,
            filter_by=filter_by,
        )
        if not existing:
            return None
        update_data: dict[str, dict[str, object]] = {
            "data": {
                "project": str(project.project_id),
                "id": str(existing.id),
                "customFields": custom_fields.build_automated_update(automated),
            }
        }
        response: dict[str, Any] | None = TuskrClient.update_tuskr_case(update_data)
        if not response:
            return None
        raw_case: Any = response.get("data") if isinstance(response, dict) else None
        if not isinstance(raw_case, dict):
            raw_case = response
        if not isinstance(raw_case, dict):
            return None
        return parsing.normalize_test_case(raw_case)

    @staticmethod
    def set_test_cases_automated_bulk(
        app_name: str,
        case_keys_or_ids: list[str],
        automated: bool,
        skip_missing: bool = True,
    ) -> TuskrBulkAutomatedResult:
        """Set `automated` on multiple cases; only updates the automated custom field."""
        updated: list[str] = []
        failed: list[dict[str, str]] = []
        skipped: list[str] = []

        for raw_id in case_keys_or_ids:
            trimmed: str = raw_id.strip()
            if not trimmed:
                continue
            result: TuskrTestCaseDetailed | None = TuskrClient.set_tuskr_case_automated(
                app_name=app_name,
                case_key_or_id=trimmed,
                automated=automated,
            )
            if result:
                updated.append(result.key or trimmed)
            elif skip_missing:
                skipped.append(trimmed)
            else:
                failed.append(
                    {
                        "case": trimmed,
                        "reason": "not_found_or_update_failed",
                    }
                )

        return TuskrBulkAutomatedResult(
            automated=automated,
            updated=updated,
            failed=failed,
            skipped=skipped,
        )

    @staticmethod
    def update_tuskr_case(update_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Update a Tuskr test case with new data, including custom fields.
        :param case_id: The case id
        :param update_data: Dict of fields to update. Custom fields should be included as: {"customFields": {"cf_xxxx": true}}
        """
        try:
            print(f"Tuskr MCP - Updating test case with data: {update_data}")
            tuskr_api: Session | None = TuskrClient._create_session()
            if not tuskr_api:
                return None
            update_case_endpoint: str = TuskrClient._tenant_url("test-case/upsert")
            response = tuskr_api.post(update_case_endpoint, json=update_data)
            response.raise_for_status()

            print("Tuskr MCP - Successfully updated test case.")
            return response.json()

        except Exception:
            print("Tuskr MCP - ERROR updating test case.")
            return None

        finally:
            TuskrClient._close_active_session()
