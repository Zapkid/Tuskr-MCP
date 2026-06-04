from dataclasses import dataclass
from typing import Literal

AutomatedFilter = Literal["any", "automated", "manual", "unset"]


@dataclass
class TuskrProjectStructure:
    app: str
    project_name: str
    project_id: str


@dataclass
class TuskrSectionRef:
    id: str
    name: str | None = None
    path: str | None = None
    suite_id: str | None = None
    suite_name: str | None = None


@dataclass
class TuskrTestSuiteRef:
    id: str
    name: str
    key: str | None = None
    path: str | None = None


@dataclass
class TuskrSectionTreeNode:
    id: str
    name: str | None = None
    path: str | None = None
    children: list["TuskrSectionTreeNode"] | None = None


@dataclass
class TuskrCaseStep:
    index: int
    title: str | None = None
    action: str | None = None
    expected_result: str | None = None
    raw: dict | None = None


@dataclass
class TuskrError:
    code: str
    message: str
    details: dict | None = None


@dataclass
class TuskrTestCaseDetailed:
    id: str
    name: str
    key: str
    section: TuskrSectionRef | None = None
    steps: list[TuskrCaseStep] | None = None
    estimated_time_in_minutes: int | None = None
    automation_id: str | None = None
    reference_links: list[str] | None = None
    issue_links: list[str] | None = None
    results: list[object] | None = None
    custom_fields: dict | None = None
    priority: str | None = None
    pre_conditions: str | None = None
    automated: bool | None = None
    owner: str | None = None
    status: str | None = None
    updated_at: str | None = None
    raw: dict | None = None


@dataclass
class TuskrPaginatedCases:
    items: list[TuskrTestCaseDetailed]
    page: int
    page_size: int
    total: int | None = None
    has_more: bool = False


@dataclass
class TuskrTestRunSummary:
    id: str
    name: str
    key: str | None = None
    status: str | None = None
    project: str | None = None
    raw: dict | None = None


@dataclass
class TuskrBulkAutomatedResult:
    automated: bool
    updated: list[str]
    failed: list[dict[str, str]]
    skipped: list[str]


@dataclass
class TuskrSetupCheck:
    name: str
    ok: bool
    message: str
    details: dict[str, object] | None = None


@dataclass
class TuskrSetupValidation:
    app_name: str
    ready: bool
    checks: list[TuskrSetupCheck]
