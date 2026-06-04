"""Load Tuskr credentials and project registry from local files (never commit secrets)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tuskr_mcp.types import TuskrProjectStructure

PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent
_USER_CONFIG_DIR: Path = Path.home() / ".config" / "tuskr-mcp"
_PROJECTS_FILENAMES: tuple[str, ...] = ("tuskr_projects.local.json", "projects.json")


def _resolve_config_path(raw_path: str) -> Path:
    """Resolve an override path: absolute as-is, else relative to cwd then package root."""
    candidate: Path = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    cwd_path: Path = (Path.cwd() / candidate).resolve()
    if cwd_path.is_file():
        return cwd_path
    return (PACKAGE_ROOT / candidate).resolve()


def parse_env_file(env_file_path: Path) -> dict[str, str]:
    parsed_values: dict[str, str] = {}
    try:
        raw_text: str = env_file_path.read_text(encoding="utf-8")
    except OSError:
        return parsed_values

    for line in raw_text.splitlines():
        normalized_line: str = line.strip()
        if not normalized_line or normalized_line.startswith("#"):
            continue
        if normalized_line.startswith("export "):
            normalized_line = normalized_line[len("export ") :].strip()
        if "=" not in normalized_line:
            continue
        key, raw_value = normalized_line.split("=", 1)
        normalized_key: str = key.strip()
        normalized_value: str = raw_value.strip().strip("'").strip('"')
        if normalized_key:
            parsed_values[normalized_key] = normalized_value
    return parsed_values


def load_env_values() -> dict[str, str]:
    explicit_env_path: str = os.getenv("TUSKR_MCP_ENV_FILE", "").strip()
    candidate_paths: list[Path] = []

    if explicit_env_path:
        candidate_paths.append(_resolve_config_path(explicit_env_path))

    candidate_paths.extend(
        [
            Path.cwd() / ".env",
            PACKAGE_ROOT / ".env",
            _USER_CONFIG_DIR / ".env",
        ]
    )

    for candidate_path in candidate_paths:
        if not candidate_path.is_file():
            continue
        file_values: dict[str, str] = parse_env_file(candidate_path)
        tenant_id: str = file_values.get("TUSKR_TENANT_ID", "").strip()
        api_token: str = file_values.get("TUSKR_API_TOKEN", "").strip()
        if tenant_id or api_token:
            return file_values
    return {}


def resolve_projects_file() -> Path | None:
    explicit_path: str = os.getenv("TUSKR_PROJECTS_FILE", "").strip()
    if explicit_path:
        resolved: Path = _resolve_config_path(explicit_path)
        return resolved if resolved.is_file() else None

    search_dirs: tuple[Path, ...] = (Path.cwd(), PACKAGE_ROOT, _USER_CONFIG_DIR)
    for directory in search_dirs:
        for filename in _PROJECTS_FILENAMES:
            candidate_path: Path = directory / filename
            if candidate_path.is_file():
                return candidate_path
    return None


def _parse_project_entry(
    app_key: str, raw_entry: object
) -> TuskrProjectStructure | None:
    if not isinstance(raw_entry, dict):
        return None

    app: str = str(raw_entry.get("app", app_key)).strip()
    project_name: str = str(raw_entry.get("project_name", "")).strip()
    project_id: str = str(raw_entry.get("project_id", "")).strip()

    if not app or not project_name or not project_id:
        return None

    return TuskrProjectStructure(
        app=app,
        project_name=project_name,
        project_id=project_id,
    )


def load_tuskr_projects() -> dict[str, TuskrProjectStructure]:
    projects_file: Path | None = resolve_projects_file()
    if not projects_file:
        return {}

    try:
        raw_payload: object = json.loads(projects_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Tuskr MCP - ERROR reading projects file '{projects_file}': {exc}")
        return {}

    if not isinstance(raw_payload, dict):
        print(f"Tuskr MCP - ERROR: '{projects_file}' must be a JSON object.")
        return {}

    loaded: dict[str, TuskrProjectStructure] = {}
    for app_key, raw_entry in raw_payload.items():
        normalized_key: str = str(app_key).strip().lower()
        if not normalized_key:
            continue
        project: TuskrProjectStructure | None = _parse_project_entry(
            normalized_key, raw_entry
        )
        if project:
            loaded[normalized_key] = project
    return loaded


tuskr_projects: dict[str, TuskrProjectStructure] = load_tuskr_projects()
