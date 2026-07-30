# STM32 Toolkit Plugin Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned Claude Code plugin foundation that binds every MCP session to one STM32 project, discovers project capabilities, and isolates all user, workspace, and session data before hardware-facing features are added.

**Architecture:** A Python package provides the deterministic CLI, project model, context discovery, and MCP tools. Claude Code loads the plugin once at user scope; its bundled MCP starts per session with `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PLUGIN_DATA}`, then refuses paths outside that project namespace. The first release exposes environment diagnosis and project context only; Keil conversion, Probe Service, Monitor, and autonomous hardware diagnosis are separate plans built on these interfaces.

**Tech Stack:** Python 3.10+, stdlib `argparse`/`dataclasses`/`pathlib`, `jsonschema>=4.23,<5`, official MCP Python SDK `mcp>=1.27,<2`, pytest 8, Claude Code plugin manifest and plugin-bundled `.mcp.json`.

## Global Constraints

- The product remains a Claude Code plugin used from VS Code; do not introduce Codex-specific runtime dependencies.
- Install the plugin once at Claude Code user scope; do not copy Skills or register MCP separately in every project.
- Bind each MCP process permanently to exactly one canonical `${CLAUDE_PROJECT_DIR}`.
- Store immutable code under `${CLAUDE_PLUGIN_ROOT}` and persistent mutable state under `${CLAUDE_PLUGIN_DATA}`.
- Namespace project state by `workspaceId = SHA256(logicalProjectId + canonical absolute path)` and session state by a random `sessionId`.
- Keep user-created Monitor groups out of the source repository; later plans store them under the workspace namespace.
- Do not access a probe, build firmware, modify source, install dependencies, or open network connections in this foundation plan.
- Use Toolkit version `0.2.0`, Project Schema version `1`, and MCP protocol identifier `stm32-toolkit/1` for this foundation release.
- Support one active project root. If multiple MCP roots are present, return an explicit unsupported-multiroot result.
- All public CLI and MCP results use the `OperationResult` envelope defined in Task 1.
- Run every test from `tools/stm32-toolkit` with the bundled or activated Python environment.

---

## Planned File Structure

```text
.claude-plugin/
└── plugin.json                         Plugin metadata and unified version
.mcp.json                               Per-session project-bound MCP startup
bin/
└── stm32-toolkit-mcp.cmd               Versioned-runtime MCP launcher
schemas/
└── stm32-project.schema.json           Version 1 project model contract
skills/
└── setup-stm32-env/SKILL.md            Bootstrap and doctor workflow
tools/stm32-toolkit/
├── pyproject.toml                       Python package and entry points
├── src/stm32_toolkit/
│   ├── __init__.py                      Public version
│   ├── cli.py                           argparse command surface
│   ├── result.py                        OperationResult envelope
│   ├── identity.py                      Project/workspace/session identity
│   ├── paths.py                         Isolated data paths and containment
│   ├── project.py                       Schema loading and validation
│   ├── detection.py                     Project-kind discovery
│   ├── context.py                       Capability and ELF freshness model
│   ├── doctor.py                        Read-only environment checks
│   └── mcp_server.py                    Project-bound FastMCP tools
└── tests/
    ├── fixtures/
    |-- keil-project/
    |   `-- legacy.uvprojx
    │   ├── valid-project.json
    │   └── invalid-project.json
    |-- conftest.py
    ├── test_result.py
    ├── test_identity.py
    ├── test_paths.py
    ├── test_project.py
    ├── test_detection.py
    ├── test_context.py
    ├── test_doctor.py
    ├── test_cli.py
    └── test_mcp_server.py
```

The existing `tools/stm32-monitor` package is not modified in this plan.

---

### Task 1: Create the Versioned Python Package and Result Contract

**Files:**
- Create: `tools/stm32-toolkit/pyproject.toml`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/result.py`
- Create: `tools/stm32-toolkit/tests/test_result.py`

**Interfaces:**
- Produces: `stm32_toolkit.__version__: str = "0.2.0"`
- Produces: `OperationResult[T].success(operation, data)` and `OperationResult[T].failure(operation, code, message, details=None)`
- Produces: `OperationResult.to_dict() -> dict[str, object]`

- [ ] **Step 1: Create package metadata with pinned major versions**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "stm32-toolkit"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = [
  "jsonschema>=4.23,<5",
  "mcp>=1.27,<2",
]

[project.optional-dependencies]
test = ["pytest>=8,<9", "pytest-cov>=5,<7"]

[project.scripts]
stm32-toolkit = "stm32_toolkit.cli:main"
stm32-toolkit-mcp = "stm32_toolkit.mcp_server:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Write the failing result-envelope tests**

```python
from stm32_toolkit.result import OperationResult


def test_success_result_has_stable_envelope():
    result = OperationResult.success("project.detect", {"kind": "keil"})
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "operation": "project.detect",
        "code": "OK",
        "message": "",
        "data": {"kind": "keil"},
        "details": {},
    }


def test_failure_result_has_machine_readable_code():
    result = OperationResult.failure(
        "project.load", "PROJECT_SCHEMA_INVALID", "Project manifest is invalid",
        {"field": "logicalProjectId"},
    )
    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["code"] == "PROJECT_SCHEMA_INVALID"
    assert payload["details"] == {"field": "logicalProjectId"}
```

- [ ] **Step 3: Run the tests and verify import failure**

Run: `python -m pytest tests/test_result.py -q`

Expected: FAIL because `stm32_toolkit.result` does not exist.

- [ ] **Step 4: Implement the immutable result envelope**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Generic, Mapping, TypeVar

T = TypeVar("T")
PROTOCOL_VERSION = "stm32-toolkit/1"


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    protocol: str
    ok: bool
    operation: str
    code: str
    message: str
    data: T | None
    details: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def success(cls, operation: str, data: T) -> "OperationResult[T]":
        return cls(PROTOCOL_VERSION, True, operation, "OK", "", data, {})

    @classmethod
    def failure(
        cls,
        operation: str,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> "OperationResult[None]":
        return cls(PROTOCOL_VERSION, False, operation, code, message, None, details or {})

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Set `tools/stm32-toolkit/src/stm32_toolkit/__init__.py` to:

```python
__version__ = "0.2.0"
```

- [ ] **Step 5: Install the package in editable test mode and run tests**

Run: `python -m pip install -e ".[test]"`

Run: `python -m pytest tests/test_result.py -q`

Expected: 2 passed.

- [ ] **Step 6: Commit the package contract**

```bash
git add tools/stm32-toolkit
git commit -m "feat: add toolkit result contract"
```

---

### Task 2: Implement Stable Project Identity and Isolated Data Paths

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/identity.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/paths.py`
- Create: `tools/stm32-toolkit/tests/test_identity.py`
- Create: `tools/stm32-toolkit/tests/test_paths.py`

**Interfaces:**
- Produces: `canonical_project_root(path: Path) -> Path`
- Produces: `compute_workspace_id(logical_project_id: UUID, project_root: Path) -> str`
- Produces: `new_session_id() -> str`
- Produces: `WorkspacePaths.from_roots(data_root, project_root, logical_project_id, session_id=None)`
- Produces: `WorkspacePaths.ensure() -> None` and `WorkspacePaths.require_project_path(path) -> Path`

- [ ] **Step 1: Write identity tests**

```python
from pathlib import Path
from uuid import UUID

from stm32_toolkit.identity import compute_workspace_id, new_session_id


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_workspace_id_is_stable_for_same_root(tmp_path: Path):
    first = compute_workspace_id(PROJECT_ID, tmp_path)
    second = compute_workspace_id(PROJECT_ID, tmp_path / ".")
    assert first == second
    assert len(first) == 24


def test_workspace_id_changes_for_second_clone(tmp_path: Path):
    first_root = tmp_path / "clone-a"
    second_root = tmp_path / "clone-b"
    first_root.mkdir()
    second_root.mkdir()
    assert compute_workspace_id(PROJECT_ID, first_root) != compute_workspace_id(PROJECT_ID, second_root)


def test_session_ids_are_unique():
    assert new_session_id() != new_session_id()
```

- [ ] **Step 2: Write containment tests**

```python
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.paths import WorkspacePaths


def test_workspace_paths_are_namespaced(tmp_path: Path):
    project = tmp_path / "project"
    data = tmp_path / "plugin-data"
    project.mkdir()
    paths = WorkspacePaths.from_roots(
        data, project, UUID("12345678-1234-5678-1234-567812345678"), "session-1"
    )
    paths.ensure()
    assert paths.workspace_root.parent.name == "projects"
    assert paths.session_root.parent.name == "sessions"
    assert paths.session_root.name == "session-1"


def test_project_path_rejects_escape(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    paths = WorkspacePaths.from_roots(
        tmp_path / "data", project,
        UUID("12345678-1234-5678-1234-567812345678"), "session-1",
    )
    with pytest.raises(ValueError, match="outside project root"):
        paths.require_project_path(tmp_path / "other" / "file.c")
```

- [ ] **Step 3: Run focused tests and verify failure**

Run: `python -m pytest tests/test_identity.py tests/test_paths.py -q`

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement identity functions**

```python
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4


def canonical_project_root(path: Path) -> Path:
    return path.expanduser().resolve(strict=True)


def compute_workspace_id(logical_project_id: UUID, project_root: Path) -> str:
    canonical = str(canonical_project_root(project_root)).replace("\\", "/").casefold()
    value = f"{logical_project_id}\0{canonical}".encode("utf-8")
    return sha256(value).hexdigest()[:24]


def new_session_id() -> str:
    return uuid4().hex
```

- [ ] **Step 5: Implement workspace path ownership**

Implement `WorkspacePaths` as a frozen dataclass with these fields:

```python
project_root: Path
data_root: Path
workspace_id: str
session_id: str
workspace_root: Path
monitor_root: Path
diagnostics_root: Path
logs_root: Path
cache_root: Path
session_root: Path
```

`ensure()` creates only `monitor_root`, `diagnostics_root`, `logs_root`, `cache_root`, and `session_root`. `require_project_path()` resolves the requested path and raises `ValueError("path is outside project root")` unless it is equal to or below `project_root`.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_identity.py tests/test_paths.py -q`

Expected: 5 passed.

- [ ] **Step 7: Commit identity and isolation**

```bash
git add tools/stm32-toolkit/src/stm32_toolkit/identity.py tools/stm32-toolkit/src/stm32_toolkit/paths.py tools/stm32-toolkit/tests
git commit -m "feat: isolate toolkit workspace data"
```

---

### Task 3: Define and Validate Project Schema Version 1

**Files:**
- Create: `schemas/stm32-project.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/project.py`
- Create: `tools/stm32-toolkit/tests/fixtures/valid-project.json`
- Create: `tools/stm32-toolkit/tests/fixtures/invalid-project.json`
- Create: `tools/stm32-toolkit/tests/conftest.py`
- Create: `tools/stm32-toolkit/tests/test_project.py`

**Interfaces:**
- Produces: `ProjectManifest.load(project_root: Path, schema_path: Path | None = None) -> ProjectManifest`
- Produces properties: `logical_project_id: UUID`, `target_device: str`, `framework_type: str`, `source_paths: tuple[Path, ...]`, `elf_path: Path | None`
- Raises: `ProjectManifestError(code: str, message: str, details: dict[str, object])`

- [ ] **Step 1: Write valid and invalid fixture files**

The valid fixture uses logical project ID `12345678-1234-5678-1234-567812345678`, target `STM32F429ZGTx`, framework `spl`, source `App/main.c`, and ELF `build-fw/firmware.elf`.

The invalid fixture omits `logicalProjectId` and uses `schemaVersion: 99`.

- [ ] **Step 2: Write schema-loading tests**

```python
from pathlib import Path

import pytest

from stm32_toolkit.project import ProjectManifest, ProjectManifestError


def test_load_valid_project(tmp_path: Path, copy_fixture):
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")
    (tmp_path / "App").mkdir()
    (tmp_path / "App/main.c").write_text("int main(void) { return 0; }", encoding="utf-8")
    manifest = ProjectManifest.load(tmp_path)
    assert manifest.target_device == "STM32F429ZGTx"
    assert manifest.framework_type == "spl"
    assert manifest.source_paths == (tmp_path / "App/main.c",)


def test_invalid_project_returns_schema_error(tmp_path: Path, copy_fixture):
    copy_fixture("invalid-project.json", tmp_path / ".stm32-project.json")
    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)
    assert error.value.code == "PROJECT_SCHEMA_INVALID"
```

Add `tests/conftest.py` with these complete fixtures:

```python
import shutil
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def copy_fixture():
    def copy(name: str, destination: Path) -> None:
        shutil.copyfile(FIXTURES / name, destination)
    return copy


@pytest.fixture
def configured_project(tmp_path: Path, copy_fixture) -> Path:
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")
    (tmp_path / "App").mkdir()
    (tmp_path / "App/main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (tmp_path / "build-fw").mkdir()
    (tmp_path / "build-fw/firmware.elf").write_bytes(b"ELF fixture")
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n", encoding="utf-8"
    )
    return tmp_path
```

- [ ] **Step 3: Run the tests and verify failure**

Run: `python -m pytest tests/test_project.py -q`

Expected: FAIL because the schema and loader do not exist.

- [ ] **Step 4: Create the JSON Schema**

Require these top-level fields:

```json
["schemaVersion", "logicalProjectId", "project", "target", "framework", "build", "debug"]
```

Set `schemaVersion` to `const: 1`, `logicalProjectId` to UUID format, framework type to one of `spl`, `hal`, `ll`, `cmsis`, `bare-metal`, and require target `device`, `core`, and build arrays `sources`, `includePaths`, `defines`, `compileOptions`, `assemblySources`.

- [ ] **Step 5: Implement manifest loading**

`ProjectManifest.load()` must:

1. Read `<project_root>/.stm32-project.json` as UTF-8.
2. Load `schemas/stm32-project.schema.json` from the repository/plugin root discovered relative to the package or from an explicit `schema_path` argument.
3. Validate with `jsonschema.Draft202012Validator` and `FormatChecker`.
4. Convert the logical ID to `UUID`.
5. Resolve source and ELF paths through the project root.
6. Raise `PROJECT_NOT_CONFIGURED`, `PROJECT_JSON_INVALID`, or `PROJECT_SCHEMA_INVALID` with field paths in `details`.

- [ ] **Step 6: Run schema tests**

Run: `python -m pytest tests/test_project.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit the schema**

```bash
git add schemas/stm32-project.schema.json tools/stm32-toolkit/src/stm32_toolkit/project.py tools/stm32-toolkit/tests
git commit -m "feat: define STM32 project schema"
```

---

### Task 4: Detect Unconfigured Project Types Without Mutation

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/detection.py`
- Create: `tools/stm32-toolkit/tests/fixtures/keil-project/legacy.uvprojx`
- Create: `tools/stm32-toolkit/tests/test_detection.py`

**Interfaces:**
- Produces: `PlannedAction(id: Literal["migrate-keil", "configure-project", "create-project"], explanation: str, available: bool = False)`
- Produces: `ProjectDetection(kind: Literal["configured", "keil", "cubemx", "cmake", "unknown"], files: tuple[str, ...], recommended_action: PlannedAction)`
- Produces: `ProjectDetection.to_dict() -> dict[str, object]`
- Produces: `detect_project(project_root: Path) -> ProjectDetection`

- [ ] **Step 1: Write precedence tests**

```python
from pathlib import Path

from stm32_toolkit.detection import detect_project


def test_manifest_wins_over_other_markers(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    assert detect_project(tmp_path).kind == "configured"


def test_keil_project_recommends_migration(tmp_path: Path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    result = detect_project(tmp_path)
    assert result.kind == "keil"
    assert result.recommended_action.id == "migrate-keil"
    assert result.recommended_action.available is False


def test_cubemx_project_recommends_configuration(tmp_path: Path):
    (tmp_path / "board.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    action = detect_project(tmp_path).recommended_action
    assert (action.id, action.available) == ("configure-project", False)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_detection.py -q`

Expected: FAIL because `detection.py` does not exist.

- [ ] **Step 3: Implement deterministic precedence**

Use this precedence:

1. `.stm32-project.json` → `configured`, planned action `configure-project`;
2. sorted `*.uvprojx` → `keil`, planned action `migrate-keil`;
3. sorted `*.ioc` → `cubemx`, planned action `configure-project`;
4. `CMakeLists.txt` → `cmake`, planned action `configure-project`;
5. otherwise `unknown`, planned action `create-project`.

Every planned action serializes as `{id, available: false, explanation}`. These identifiers describe unavailable future work and must not be rendered as slash commands.

The function only reads directory entries and never creates files.

Create `tests/fixtures/keil-project/legacy.uvprojx` with the minimal marker content `<Project/>` for CLI smoke tests.

- [ ] **Step 4: Run detection tests**

Run: `python -m pytest tests/test_detection.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit project detection**

```bash
git add tools/stm32-toolkit/src/stm32_toolkit/detection.py tools/stm32-toolkit/tests/test_detection.py
git commit -m "feat: detect STM32 project kind"
```

---

### Task 5: Build Project Context and Capability Reporting

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/context.py`
- Create: `tools/stm32-toolkit/tests/test_context.py`

**Interfaces:**
- Consumes: `ProjectManifest`, `ProjectDetection`, `WorkspacePaths`
- Produces: `build_project_context(project_root: Path, data_root: Path, session_id: str | None = None) -> OperationResult[dict[str, object]]`
- Result data keys: `project`, `workspace`, `build`, `hardware`, `capabilities`, `recommendedActions`
- Unconfigured result shape: `project.recommendedAction` and each `recommendedActions` entry contain the same `{id, available: false, explanation}` object.

- [ ] **Step 1: Write configured-context tests**

```python
def test_configured_context_is_bound_to_workspace(configured_project, tmp_path):
    result = build_project_context(configured_project, tmp_path / "data", "session-a")
    payload = result.to_dict()
    assert payload["ok"] is True
    assert payload["data"]["project"]["target"] == "STM32F429ZGTx"
    assert payload["data"]["workspace"]["sessionId"] == "session-a"
    assert payload["data"]["capabilities"]["build"] is True
    assert payload["data"]["capabilities"]["monitor"] is False
```

- [ ] **Step 2: Write unconfigured-context tests**

```python
def test_keil_context_recommends_migration(tmp_path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    result = build_project_context(tmp_path, tmp_path / "data", "session-a")
    assert result.ok is True
    assert result.data["project"]["kind"] == "keil"
    assert result.data["recommendedActions"] == [{
        "id": "migrate-keil",
        "available": False,
        "explanation": "Keil migration is planned but unavailable in this foundation release.",
    }]
```

- [ ] **Step 3: Run tests and verify failure**

Run: `python -m pytest tests/test_context.py -q`

Expected: FAIL because `context.py` does not exist.

- [ ] **Step 4: Implement context assembly**

For configured projects:

- Compute `workspaceId` and `sessionId`.
- Create workspace/session data directories.
- Mark `build=true` only when a manifest and `CMakeLists.txt` exist.
- Mark `elfFresh=true` only when the ELF exists and its modification time is not older than any existing manifest source.
- Keep `flash`, `hostTest`, `targetTest`, `monitor`, and `breakpointDebug` false in this foundation plan.
- Return `hardware.probe = null` and `hardware.state = "unavailable"` without probing USB.

For unconfigured projects, return detection evidence and unavailable planned-action objects without creating a logical project ID or workspace directory.

- [ ] **Step 5: Run context tests**

Run: `python -m pytest tests/test_context.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit context reporting**

```bash
git add tools/stm32-toolkit/src/stm32_toolkit/context.py tools/stm32-toolkit/tests/test_context.py
git commit -m "feat: report project capabilities"
```

---

### Task 6: Add Read-Only Doctor and JSON CLI

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/doctor.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Create: `tools/stm32-toolkit/tests/test_doctor.py`
- Create: `tools/stm32-toolkit/tests/test_cli.py`

**Interfaces:**
- Produces: `run_doctor(project_root: Path) -> OperationResult[dict[str, object]]`
- Produces CLI commands: `version`, `doctor --json`, `project detect --json`, `project context --data-root PATH --session-id ID --json`
- CLI success exit code: `0`; environment/project problems represented by a valid result use `2`; malformed CLI input uses argparse exit code `2`.

- [ ] **Step 1: Write doctor tests with mocked executable discovery**

```python
def test_doctor_reports_tools_without_installing(monkeypatch, tmp_path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)
    result = run_doctor(tmp_path)
    assert result.ok is True
    assert result.data["tools"]["arm-none-eabi-gcc"]["available"] is False
    assert result.data["tools"]["cmake"]["available"] is False
    assert result.data["mutated"] is False
```

- [ ] **Step 2: Write CLI JSON tests**

```python
import json

from stm32_toolkit.cli import main


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "0.2.0"


def test_detect_command_emits_result_envelope(tmp_path, capsys):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    assert main(["--project-root", str(tmp_path), "project", "detect", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "project.detect"
    assert payload["data"]["kind"] == "keil"
```

- [ ] **Step 3: Run focused tests and verify failure**

Run: `python -m pytest tests/test_doctor.py tests/test_cli.py -q`

Expected: FAIL because doctor and CLI modules do not exist.

- [ ] **Step 4: Implement read-only doctor**

Check with `shutil.which` only:

```python
TOOLS = (
    "arm-none-eabi-gcc",
    "arm-none-eabi-gdb",
    "cmake",
    "ninja",
    "pyocd",
    "STM32CubeMX",
    "code",
)
```

For discovered tools, run only their read-only version command with a five-second timeout. Do not download, install, update, enumerate probes, or access the network. Return Python version, operating system, project detection, tool availability, and `mutated: false`.

- [ ] **Step 5: Implement argparse CLI**

`main(argv: list[str] | None = None) -> int` must:

- accept global `--project-root`, defaulting to `Path.cwd()`;
- serialize result envelopes with `json.dumps(..., ensure_ascii=False, indent=2)` when `--json` is used;
- send valid machine-readable results to stdout and unexpected internal errors to stderr;
- never change the current working directory.

- [ ] **Step 6: Run doctor and CLI tests**

Run: `python -m pytest tests/test_doctor.py tests/test_cli.py -q`

Expected: all tests pass.

- [ ] **Step 7: Run the full package suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 8: Commit doctor and CLI**

```bash
git add tools/stm32-toolkit/src/stm32_toolkit/doctor.py tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/tests
git commit -m "feat: add toolkit doctor CLI"
```

---

### Task 7: Expose Project-Bound MCP Tools

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Create: `tools/stm32-toolkit/tests/test_mcp_server.py`, `tools/stm32-toolkit/tests/test_mcp_roots.py`

**Interfaces:**
- Consumes: `run_doctor`, `detect_project`, `build_project_context`
- Produces: `create_server(project_root: Path, data_root: Path, session_id: str | None = None) -> FastMCP`
- Produces tools: `stm32_doctor`, `stm32_project_detect`, `stm32_project_context`
- Produces: `main(argv: list[str] | None = None) -> int`, running stdio transport

- [ ] **Step 1: Write bound-server tests**

```python
from pathlib import Path

import pytest

from stm32_toolkit.mcp_server import ServerRuntime, tool_project_detect


def test_tool_uses_bound_project_root(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    runtime = ServerRuntime.create(project, tmp_path / "data", "session-a")
    result = tool_project_detect(runtime)
    assert result["data"]["kind"] == "keil"


def test_runtime_rejects_missing_project_root(tmp_path: Path):
    with pytest.raises(ValueError, match="project root does not exist"):
        ServerRuntime.create(tmp_path / "missing", tmp_path / "data", "session-a")
```

- [ ] **Step 2: Run MCP tests and verify failure**

Run: `python -m pytest tests/test_mcp_server.py -q`

Expected: FAIL because `mcp_server.py` does not exist.

- [ ] **Step 3: Implement immutable server runtime**

`ServerRuntime` is a frozen dataclass containing canonical `project_root`, canonical `data_root`, and `session_id`. Its `create()` method rejects nonexistent project roots and creates only the plugin data root.

- [ ] **Step 4: Implement testable tool functions**

Define plain functions returning result dictionaries:

```python
def tool_doctor(runtime: ServerRuntime) -> dict[str, object]:
    return run_doctor(runtime.project_root).to_dict()


def tool_project_detect(runtime: ServerRuntime) -> dict[str, object]:
    detection = detect_project(runtime.project_root)
    return OperationResult.success("project.detect", detection.to_dict()).to_dict()


def tool_project_context(runtime: ServerRuntime) -> dict[str, object]:
    return build_project_context(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
    ).to_dict()
```

Registered wrappers accept an injected FastMCP `Context`, while their advertised input schemas remain zero-argument. If the client does not advertise the roots capability (or the plain functions are called directly), use the bound runtime. If it does, call `roots/list` on every request and accept exactly one canonical root equal to `runtime.project_root`. Return `UNSUPPORTED_MULTIROOT` for multiple or mismatched roots, and `MCP_ROOTS_UNAVAILABLE` if roots cannot be inspected. Never add, remove, or cache client roots.

Register thin `@mcp.tool()` wrappers around these functions. Do not accept a project path argument in any MCP tool; the server runtime is the only source of project identity.

- [ ] **Step 5: Implement stdio startup**

Parse required `--project-root` and `--data-root`, optional `--session-id`, construct the server, then call:

```python
mcp.run(transport="stdio")
```

Set FastMCP name to `STM32 Toolkit` and instructions to state that the server is permanently bound to one project and exposes read-only foundation tools.

- [ ] **Step 6: Run MCP and full tests**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_roots.py -q`


Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 7: Commit MCP tools**

```bash
git add tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/tests/test_mcp_server.py
git commit -m "feat: expose project-bound MCP tools"
```

---

### Task 8: Wire the Claude Code Plugin and Setup Skill

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Create: `.mcp.json`
- Create: `bin/stm32-toolkit-mcp.cmd`
- Modify: `skills/setup-stm32-env/SKILL.md`
- Create: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `stm32-toolkit-mcp` Python entry point
- Produces: Claude Code plugin version `0.2.0`
- Produces: automatic MCP startup using `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PLUGIN_DATA}`
- Produces: setup workflow that installs one plugin runtime under `${CLAUDE_PLUGIN_DATA}` and validates with `stm32-toolkit doctor`

- [ ] **Step 1: Write plugin-layout tests**

```python
import json
from pathlib import Path


from stm32_toolkit import __version__

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_plugin_and_python_versions_match():
    plugin = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == __version__ == "0.2.0"


def test_mcp_config_uses_claude_path_variables():
    config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["stm32-toolkit"]
    joined = " ".join([server["command"], *server.get("args", [])])
    assert "${CLAUDE_PLUGIN_ROOT}" in joined
    assert "${CLAUDE_PLUGIN_DATA}" in joined
    assert "${CLAUDE_PROJECT_DIR}" in joined
    assert "D:/" not in joined and "C:/" not in joined
    assert server["command"] == "${CLAUDE_PLUGIN_ROOT}/bin/stm32-toolkit-mcp.cmd"
    assert "python" not in server["command"].lower()
```

- [ ] **Step 2: Run layout tests and verify failure**

Run: `python -m pytest tests/test_plugin_layout.py -q`

Expected: FAIL because plugin version and MCP configuration do not match the foundation contract.

- [ ] **Step 3: Update the plugin manifest**

Set `.claude-plugin/plugin.json` to valid metadata with:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "stm32-toolkit",
  "version": "0.2.0",
  "description": "Foundation for AI-assisted STM32 development with read-only project detection and environment diagnosis",
  "author": {
    "name": "STM32 Toolkit Team"
  }
}
```

Rely on standard `skills/` auto-discovery instead of listing bare skill names in the manifest.

- [ ] **Step 4: Create the plugin MCP configuration**

Use:

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "${CLAUDE_PLUGIN_ROOT}/bin/stm32-toolkit-mcp.cmd",
      "args": [
        "--project-root",
        "${CLAUDE_PROJECT_DIR}",
        "--data-root",
        "${CLAUDE_PLUGIN_DATA}"
      ],
      "env": {
        "STM32_TOOLKIT_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
        "STM32_TOOLKIT_DATA_ROOT": "${CLAUDE_PLUGIN_DATA}",
        "STM32_TOOLKIT_PROJECT_ROOT": "${CLAUDE_PROJECT_DIR}"
      }
    }
  }
}
```

The Windows launcher must invoke `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe -m stm32_toolkit.mcp_server` and forward all MCP arguments. If that interpreter is absent, it must print a clear instruction to run `/stm32-toolkit:setup-stm32-env` and exit nonzero. It must never fall back to `python`, `py`, or another system interpreter. The one-time setup installs this plugin version and its dependencies into that exact virtual environment, so every project uses the same Toolkit runtime while project and session data remain isolated. CHECK is a Skill-only pre-MCP operation and returns structured `missing`, `healthy`, or `broken` evidence. Authorized Bootstrap/Repair operations build in a unique plugin-data staging directory, validate exact version and doctor before promotion, and quarantine a broken runtime during Repair.

- [ ] **Step 5: Rewrite setup responsibilities without installing hardware tools automatically**

Update `skills/setup-stm32-env/SKILL.md` so it:

1. Checks Python 3.10+ first.
2. Creates `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0` and installs the plugin Python package and dependencies into its `Scripts/python.exe` only after user authorization.
3. Runs `stm32-toolkit doctor --json`.
4. Reports ARM GCC, CMake, Ninja, PyOCD, CubeMX, VS Code extension, and CMSIS-Pack gaps.
5. Does not probe hardware, kill processes, install packs, or register a second MCP during the check phase.
6. Explains that the plugin-bundled `.mcp.json` replaces manual `claude mcp add` registration.

- [ ] **Step 6: Update README installation and isolation documentation**

Document:

- one user-scope plugin installation;
- one-time `/stm32-toolkit:setup-stm32-env` bootstrap;
- automatic per-project MCP binding;
- `.stm32-project.json` as shared project configuration;
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` as isolated user state;
- `stm32-toolkit doctor --json` as the first troubleshooting command.

- [ ] **Step 7: Run plugin validation and tests**

Run: `python -m pytest -q`

Run: `claude plugin validate .`

Expected: all Python tests pass and Claude reports a valid plugin manifest, Skills layout, and MCP configuration.

- [ ] **Step 8: Run a two-project isolation smoke test**

Create two temporary directories, give each a different Keil marker, then run `stm32-toolkit project context` against both with the same plugin data root. Verify their `workspaceId` and session directories differ. Do not connect hardware.

Expected: two distinct workspace namespaces and no files written to either project except files explicitly created by the test fixture.

- [ ] **Step 9: Commit the plugin foundation**

```bash
git add .claude-plugin/plugin.json .mcp.json bin/stm32-toolkit-mcp.cmd skills/setup-stm32-env/SKILL.md README.md tools/stm32-toolkit/tests/test_plugin_layout.py
git commit -m "feat: wire project-isolated Claude plugin"
```

---

## Final Verification

- [ ] Run: `python -m pytest -q`

Expected: all foundation tests pass.

- [ ] Run: `python -m pytest --cov=stm32_toolkit --cov-report=term-missing -q`

Expected: no untested branch in identity, containment, schema validation, project detection, context assembly, doctor, CLI, or MCP wrappers.

- [ ] Run: `stm32-toolkit --project-root tests/fixtures/keil-project project detect --json`

Expected: `kind=keil`, `recommended_action.id=migrate-keil`, `recommended_action.available=false`, and no project mutation.

- [ ] Run: `claude plugin validate .`

Expected: plugin validation succeeds.

- [ ] Start Claude Code in two fixture projects with the plugin enabled and call `stm32_project_context` in both.

Expected: each MCP reports only its own project root and uses a distinct workspace/session namespace.

- [ ] Run: `git status --short`

Expected: clean working tree after the final task commit.

## Follow-on Plans

After this plan is implemented and reviewed, write separate implementation plans in this order:

1. Keil inspection, one-way GCC conversion, project configuration, and migration verification.
2. Probe Service, lease registry, DWARF/SVD decoding, and `stm32-monitor` requirement-preserving refactor.
3. AI diagnostic sessions, hypothesis/evidence model, safe debug operations, and host/target tests.
4. CubeMX/CMSIS/HAL/LL new-project creation.
