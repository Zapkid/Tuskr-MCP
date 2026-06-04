# tuskr-mcp

MCP server for [Tuskr](https://tuskr.app) test management — browse, search, and manage test cases from [Cursor](https://cursor.com) or any MCP host.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/tuskr-mcp)](https://pypi.org/project/tuskr-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

## Requirements

| Requirement              | Notes                                                  |
| ------------------------ | ------------------------------------------------------ |
| Python **3.10–3.13**     | 3.9 and older cannot install from PyPI                 |
| Tuskr API access         | Tenant ID + API token from **Settings → API**          |
| Custom field `automated` | Checkbox on test cases (required for automation tools) |
| Test case type `AutoGen` | Only if you use `create_test_case_minimal`             |

`pip install tuskr-mcp` pulls in [`mcp`](https://pypi.org/project/mcp/) and `requests` automatically.

## Install

```bash
python3 --version   # must be 3.10+
pip install tuskr-mcp
```

**From source** ([GitHub](https://github.com/Zapkid/tuskr-mcp)):

```bash
git clone https://github.com/Zapkid/tuskr-mcp.git
cd tuskr-mcp
uv sync
# or: python -m venv .venv && source .venv/bin/activate && pip install -e .
```

## Setup

### Copy config files

Pick **one** config location (both files must live in the **same** folder):

| Option | Folder | Typical use |
| ------ | ------ | ----------- |
| **A. Project folder** | Your QA/automation repo root | Same repo as your tests |
| **B. User config** | `~/.config/tuskr-mcp/` | One Tuskr setup for all Cursor projects |

**Option A** — e.g. `~/projects/my-qa-repo/`:

```bash
cd ~/projects/my-qa-repo
# copy from the tuskr-mcp repo if you cloned it, or create the files manually
cp /path/to/tuskr-mcp/.env.example .env
cp /path/to/tuskr-mcp/tuskr_projects.example.json tuskr_projects.local.json
```

**Option B** — shared config:

```bash
mkdir -p ~/.config/tuskr-mcp
cp /path/to/tuskr-mcp/.env.example ~/.config/tuskr-mcp/.env
cp /path/to/tuskr-mcp/tuskr_projects.example.json ~/.config/tuskr-mcp/tuskr_projects.local.json
```

(`projects.json` also works in `~/.config/tuskr-mcp/`.)

### Configure `.env`

```env
TUSKR_TENANT_ID=your-tenant-id
TUSKR_API_TOKEN=your-api-token
```

### Configure projects

Edit `tuskr_projects.local.json` in that same folder and set `project_id` per app (from the Tuskr project URL).

### Connect Cursor

Add to `~/.cursor/mcp.json`.

**After `pip install`** — set `cwd` to the folder where you put `.env` and `tuskr_projects.local.json` (Option A or B above). Cursor starts the server in that directory so tuskr-mcp can find your files:

```json
{
  "mcpServers": {
    "tuskr": {
      "command": "python3",
      "args": ["-m", "tuskr_mcp"],
      "cwd": "/Users/you/projects/my-qa-repo"
    }
  }
}
```

Examples:

- Option A: `"cwd": "/Users/you/projects/my-qa-repo"`
- Option B: `"cwd": "/Users/you/.config/tuskr-mcp"`

Use the same Python you installed with (`which python3` if needed). To pin a venv: `"command": "/path/to/venv/bin/python"`.

**From source** (editable install in the tuskr-mcp clone):

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

### Verify

Restart Cursor, enable the **tuskr** server, then run `health_check` and `validate_tuskr_setup` with your `app_name`.

### Tuskr custom fields (test cases)

| Label         | Key              | Type     | When needed                             |
| ------------- | ---------------- | -------- | --------------------------------------- |
| Automated     | `automated`      | Checkbox | Automation filtering and updates        |
| Preconditions | `pre_conditions` | Text     | Optional on create                      |
| Priority      | `priority`       | Dropdown | Optional on create                      |
| Steps         | `steps`          | Steps    | Required for `create_test_case_minimal` |

## Safe by design

| Allowed                                        | Not allowed                       |
| ---------------------------------------------- | --------------------------------- |
| List, search, read cases, steps, and test runs | Update cases (except `automated`) |
| Create suites, sections, and new cases         | Delete anything                   |
| Set `automated` on existing cases              |                                   |

API calls use **GET** and **POST** only. Credentials stay in local `.env` and `tuskr_projects.local.json` (never committed).

## Tools

| Tool                                                                | Purpose                                                                    |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `health_check`                                                      | Env, projects file, API connectivity                                       |
| `validate_tuskr_setup`                                              | Verify custom fields, `AutoGen` type, and API for one app                  |
| `list_projects`                                                     | Apps defined in `tuskr_projects.local.json`                                |
| `list_test_suites` / `list_sections` / `get_sections_tree`          | Project structure                                                          |
| `get_test_cases_by_section`                                         | Paginated cases; `automated_filter`: `any`, `automated`, `manual`, `unset` |
| `get_test_case` / `get_case_steps`                                  | Single case and steps                                                      |
| `search_test_cases`                                                 | Search by key, title, or step text                                         |
| `list_test_runs` / `get_test_run`                                   | Read-only test runs                                                        |
| `create_test_suite` / `create_section` / `create_test_case_minimal` | Create resources                                                           |
| `set_test_case_automated` / `set_test_cases_automated_bulk`         | Update `automated` only                                                    |

## Configuration

| Variable              | Required | Description                    |
| --------------------- | -------- | ------------------------------ |
| `TUSKR_TENANT_ID`     | Yes      | Tuskr tenant ID                |
| `TUSKR_API_TOKEN`     | Yes      | API token                      |
| `TUSKR_MCP_ENV_FILE`  | No       | Override path to `.env`        |
| `TUSKR_PROJECTS_FILE` | No       | Override path to projects JSON |

Lookup order: MCP `cwd` (see above), then the installed package directory (source install), then `~/.config/tuskr-mcp/`. Override with `TUSKR_MCP_ENV_FILE` / `TUSKR_PROJECTS_FILE` (absolute paths recommended after `pip install`).

## Troubleshooting

| Problem                                 | What to do                                                                               |
| --------------------------------------- | ---------------------------------------------------------------------------------------- |
| `pip install` finds no version          | Use Python 3.10+; check with `python3 --version`                                         |
| `missing_env`                           | Create `.env` with tenant ID and token; restart Cursor                                   |
| Empty `list_projects`                   | Add apps to `tuskr_projects.local.json`                                                  |
| `No module named tuskr_mcp`             | Run `pip install tuskr-mcp`, or set `cwd` and use a venv Python when running from source |
| `set_test_case_automated` has no effect | Add Tuskr custom field `automated` (Checkbox)                                            |
| `create_test_case_minimal` fails        | Add test case type **AutoGen** in Tuskr                                                  |
| `automated_filter` returns nothing      | Confirm `automated` field exists; try filter `any`                                       |
| Wrong case for `C-2` vs `C-20`          | Pass the full case key                                                                   |

## License

[MIT](LICENSE) — Copyright (c) Rowan Kendal
