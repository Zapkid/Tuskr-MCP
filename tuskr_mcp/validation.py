"""Tuskr project setup validation (custom fields, test case types)."""

from __future__ import annotations

from typing import Any

from tuskr_mcp import custom_fields
from tuskr_mcp.client import TuskrClient
from tuskr_mcp.config import tuskr_projects
from tuskr_mcp.types import TuskrSetupCheck, TuskrSetupValidation


def _check(
    name: str,
    ok: bool,
    message: str,
    details: dict[str, object] | None = None,
) -> TuskrSetupCheck:
    return TuskrSetupCheck(name=name, ok=ok, message=message, details=details)


def _probe_custom_field_filter(
    project_id: str,
    field_key: str,
    probe_value: str,
) -> bool:
    params: dict[str, str] = {
        "filter[project]": project_id,
        f"filter[customFields][{field_key}]": probe_value,
        "limit": "1",
    }
    payload: dict[str, Any] | None = TuskrClient._request_with_retries(
        method="GET",
        url=TuskrClient.get_tuskr_case_endpoint,
        params=params,
    )
    return payload is not None


def validate_tuskr_setup(app_name: str) -> TuskrSetupValidation:
    """
    Validate env, project mapping, AutoGen test-case type, and custom field keys.
    """
    checks: list[TuskrSetupCheck] = []
    normalized_app: str = app_name.strip().lower()

    TuskrClient.generate_tuskr_vars()
    if not TuskrClient.TUSKR_TENANT_ID:
        checks.append(
            _check("env_tenant", False, "Missing TUSKR_TENANT_ID.", {"env_var": "TUSKR_TENANT_ID"})
        )
    else:
        checks.append(_check("env_tenant", True, "TUSKR_TENANT_ID is set."))

    if not TuskrClient.TUSKR_API_TOKEN:
        checks.append(
            _check("env_token", False, "Missing TUSKR_API_TOKEN.", {"env_var": "TUSKR_API_TOKEN"})
        )
    else:
        checks.append(_check("env_token", True, "TUSKR_API_TOKEN is set."))

    project = TuskrClient.get_project_data(normalized_app)
    if not project:
        checks.append(
            _check(
                "project_mapping",
                False,
                f"App '{app_name}' not found in tuskr_projects.local.json.",
            )
        )
        return TuskrSetupValidation(
            app_name=normalized_app,
            ready=False,
            checks=checks,
        )
    checks.append(
        _check(
            "project_mapping",
            True,
            f"Mapped to project '{project.project_name}'.",
            {"project_id": project.project_id},
        )
    )

    if not tuskr_projects:
        checks.append(
            _check(
                "projects_file",
                False,
                "No projects in tuskr_projects.local.json.",
            )
        )

    sample_payload: dict[str, Any] | None = TuskrClient._request_with_retries(
        method="GET",
        url=TuskrClient._tenant_url("test-case"),
        params={"filter[project]": project.project_id, "limit": "1"},
    )
    if sample_payload is None:
        checks.append(
            _check(
                "api_connectivity",
                False,
                "Could not reach Tuskr test-case API for this project.",
            )
        )
    else:
        checks.append(_check("api_connectivity", True, "Tuskr API is reachable."))

    autogen_id: str | None = TuskrClient.resolve_tuskr_test_case_type_id(
        app_name=normalized_app,
        case_type_name=TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME,
    )
    if autogen_id:
        checks.append(
            _check(
                "test_case_type_autogen",
                True,
                f"Test case type '{TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME}' exists.",
                {"id": autogen_id},
            )
        )
    else:
        checks.append(
            _check(
                "test_case_type_autogen",
                False,
                f"Create test case type '{TuskrClient.DEFAULT_AUTOGEN_TEST_TYPE_NAME}' in Tuskr "
                "(required for create_test_case_minimal).",
            )
        )

    sample_keys: set[str] = set()
    rows: list[dict[str, Any]] = []
    if sample_payload:
        from tuskr_mcp import parsing

        rows = parsing.extract_rows(sample_payload)
        if rows:
            sample_cf: dict[str, Any] = custom_fields.get_custom_fields_dict(rows[0])
            sample_keys = set(sample_cf.keys())

    for field_def in custom_fields.CUSTOM_FIELDS_SETUP:
        key: str = field_def["key"]
        label: str = field_def["label"]
        required: bool = key in custom_fields.REQUIRED_FIELD_KEYS

        if key == custom_fields.FIELD_AUTOMATED:
            probe_ok: bool = _probe_custom_field_filter(project.project_id, key, "1")
            if probe_ok:
                checks.append(
                    _check(
                        f"custom_field_{key}",
                        True,
                        f"Custom field '{label}' (key `{key}`) accepts API filters.",
                    )
                )
            else:
                checks.append(
                    _check(
                        f"custom_field_{key}",
                        False,
                        f"Add custom field '{label}' with key `{key}` (Checkbox) on Test Cases.",
                    )
                )
            continue

        if key in sample_keys:
            checks.append(
                _check(
                    f"custom_field_{key}",
                    True,
                    f"Sample case exposes custom field `{key}`.",
                    {"label": label},
                )
            )
        elif required:
            checks.append(
                _check(
                    f"custom_field_{key}",
                    False,
                    f"Required field '{label}' (key `{key}`) not seen on a sample case — "
                    "add it under Settings → Custom Fields.",
                    {"expected_type": field_def["type"]},
                )
            )
        else:
            checks.append(
                _check(
                    f"custom_field_{key}",
                    True,
                    f"Optional field '{label}' (key `{key}`) — add in Tuskr UI if you use it.",
                    {"seen_on_sample": False},
                )
            )

    ready: bool = all(check.ok for check in checks)
    return TuskrSetupValidation(
        app_name=normalized_app,
        ready=ready,
        checks=checks,
    )
