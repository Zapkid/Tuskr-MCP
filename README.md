# tuskr-mcp

MCP server for [Tuskr](https://tuskr.app) test management. Browse, search, and read cases from Cursor or any MCP host — standalone from your test automation repo.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-server-6366f1)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Repository: [github.com/zapkid/tuskr-mcp](https://github.com/Zapkid/tuskr-mcp)

## Requirements

- **Python 3.10+** (`requires-python >=3.10` — Python 3.9 and older cannot install from PyPI)
- **Runtime dependencies** (installed automatically with `pip install tuskr-mcp`):
  - [`mcp`](https://pypi.org/project/mcp/) `>=1.26.0` (Model Context Protocol SDK, includes FastMCP)
  - `requests` `>=2.31.0`

Check your interpreter before installing:

```bash
python3 --version   # must be 3.10, 3.11, 3.12, or 3.13
```

## Safe by design

| Capability                                      | Supported |
| ----------------------------------------------- | --------- |
| List, search, read cases, steps, test runs      | Yes       |
| Create suite, section, or new case              | Yes       |
| Update existing case (except `automated` field) | No        |
| Set `automated` on existing case(s)             | Yes       |
| Delete anything                                 | No        |

API calls use **GET** and **POST** only. Secrets stay in local `.env` and `tuskr_projects.local.json` (gitignored).

## Prerequisites

- Python **3.10+** (see [Requirements](#requirements))
- Tuskr API credentials (**Settings → API**)
- Custom field **`automated`** (Checkbox) on test cases
- Test case type **`AutoGen`** if you use `create_test_case_minimal`
- Optional fields: `pre_conditions`, `priority`, `steps` — see `tuskr_mcp/custom_fields.py`

Run `validate_tuskr_setup` after setup to confirm fields and `AutoGen`.

### Custom fields (Test Cases)

| Label         | Key              | Type     | Notes                                   |
| ------------- | ---------------- | -------- | --------------------------------------- |
| Automated     | `automated`      | Checkbox | Required for automated tools            |
| Preconditions | `pre_conditions` | Text     | Optional on create                      |
| Priority      | `priority`       | Dropdown | Optional on create                      |
| Steps         | `steps`          | Steps    | Required for `create_test_case_minimal` |

## Quick start

```bash
python3 --version              # 3.10+ required
pip install tuskr-mcp          # or: git clone … && pip install -e .
cp .env.example .env
cp tuskr_projects.example.json tuskr_projects.local.json
# Edit .env and tuskr_projects.local.json (project_id from Tuskr URL)
```

**Cursor** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "tuskr": {
      "command": "/path/to/tuskr-mcp/.venv/bin/python",
      "args": ["-m", "tuskr_mcp"],
      "cwd": "/path/to/tuskr-mcp"
    }
  }
}
```

Restart Cursor, enable **tuskr**, then run `health_check` and `validate_tuskr_setup` with your `app_name`.

## Clone from GitHub

```bash
git clone https://github.com/zapkid/tuskr-mcp.git
cd tuskr-mcp
uv sync    # preferred: uses uv.lock, creates .venv, editable install
```

Without uv: `python -m venv .venv && source .venv/bin/activate && pip install -e .`

## MCP tools

| Tool                                                                | Description                                                                |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `health_check`                                                      | Env, projects file, API connectivity                                       |
| `validate_tuskr_setup`                                              | Custom fields, `AutoGen` type, API for one app                             |
| `list_projects`                                                     | Apps in `tuskr_projects.local.json`                                        |
| `list_test_suites` / `list_sections` / `get_sections_tree`          | Structure discovery                                                        |
| `get_test_cases_by_section`                                         | Paginated cases; `automated_filter`: `any`, `automated`, `manual`, `unset` |
| `get_test_case` / `get_case_steps`                                  | Single case                                                                |
| `search_test_cases`                                                 | Key, title, step text; optional `automated_filter`                         |
| `list_test_runs` / `get_test_run`                                   | Read-only runs; `include_results` on get                                   |
| `create_test_suite` / `create_section` / `create_test_case_minimal` | Create resources                                                           |
| `set_test_case_automated` / `set_test_cases_automated_bulk`         | Update `automated` only                                                    |

## Configuration

| Variable              | Required | Description                 |
| --------------------- | -------- | --------------------------- |
| `TUSKR_TENANT_ID`     | Yes      | Tenant ID                   |
| `TUSKR_API_TOKEN`     | Yes      | API token                   |
| `TUSKR_MCP_ENV_FILE`  | No       | Override `.env` path        |
| `TUSKR_PROJECTS_FILE` | No       | Override projects JSON path |

Defaults: `./.env` and `./tuskr_projects.local.json`, or `~/.config/tuskr-mcp/`.

`.gitignore`, `.cursorignore`, and `.claudeignore` exclude secrets from git and IDE indexing.

## Troubleshooting

| Issue                               | Fix                                               |
| ----------------------------------- | ------------------------------------------------- |
| `pip install` finds no versions / ignores 0.2.x | Use Python **3.10+** (`python3 --version`); upgrade or recreate venv |
| `missing_env`                       | Create `.env` with tenant + token; restart MCP    |
| Empty `list_projects`               | Add entries to `tuskr_projects.local.json`        |
| `No module named tuskr_mcp`         | Set MCP `cwd` to repo; run `uv sync` or `pip install -e .` |
| `set_test_case_automated` no effect | Add custom field key `automated` (Checkbox)       |
| `create_test_case_minimal` fails    | Add test case type **AutoGen** in Tuskr           |
| `automated_filter` empty            | Confirm `automated` field exists; try `any` first |
| Wrong case for `C-2` vs `C-20`      | Pass full case key                                |

## License

[MIT](LICENSE) — Copyright (c) Rowan Kendal
