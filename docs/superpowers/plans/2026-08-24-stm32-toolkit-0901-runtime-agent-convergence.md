# STM32 Toolkit VS09-A Runtime and Agent Adapter Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository governance overrides the skill's fresh-agent-per-task default: this plan has exactly one implementation task and exactly one `gpt-5.6-luna`/`max` implementation owner for the entire slice.

**Goal:** Converge STM32 Toolkit on one CPython 3.12, Agent-neutral 0.9.0 local runtime with explicit project-bound CLI/MCP roots, one generic launcher contract, one retained Claude thin adapter, and consistent version and public inventory evidence.

**Architecture:** Keep the existing CLI, MCP server, Monitor, setup engine, and Claude plugin. Replace Claude-only interpreter selection with the single `STM32_TOOLKIT_DATA_ROOT` contract, remove the CLI current-directory fallback, and centralize public release/inventory facts for doctor and the existing server registrations. No domain workflow, state machine, backend, provider, controller, runtime, or MCP registration is added.

**Tech Stack:** CPython `>=3.12,<3.13`, setuptools, pytest, FastMCP, PowerShell 5+/Windows cmd, existing STM32 Toolkit and Monitor packages, existing Claude plugin/Skills.

## Global Constraints

- Full accepted base is `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Governing specification is `docs/superpowers/specs/2026-08-24-stm32-toolkit-0901-runtime-agent-convergence-design.md`, committed at `4073ea1e8450bd189d416350bf5742befd222399`.
- Release SemVer is exactly `0.9.0`; supported Python is exactly CPython `>=3.12,<3.13`.
- The slice has exactly one `gpt-5.6-luna` implementation owner with reasoning effort `max`; GPT-5.6-sol owns the complete-diff review and acceptance.
- `STM32_TOOLKIT_DATA_ROOT` is the only ambient variable consumed by the two generic launchers; all project/data roots passed to CLI/MCP remain explicit arguments.
- `stm32-toolkit version` is the only root-free CLI command. Every other CLI command requires exactly one explicit project root and never uses the current directory as fallback.
- The existing MCP server remains one project-bound stdio server with exactly 48 tools; the Claude adapter retains exactly eight Skills and one `.mcp.json` server registration.
- Do not add Agent-specific product logic, a second runtime, MCP registration, controller, scheduler, provider, backend, state store, Python version, platform, CI, or collaboration automation.
- Do not change VS08 workflow semantics, public schemas/protocol versions, Project/Probe/Monitor/Test/Diagnostic/Acceptance state machines, or historical evidence identity.
- Do not run hardware, full release/coverage/browser/performance matrices, external installation, push, PR, merge, tag, release, remote branch mutation, or any other remote mutation.
- Run-scoped basetemps, venvs, wheelhouses, logs, JUnit files, build outputs, extracted artifacts, and review worktrees must be removed after evidence reconciliation; preserve source tests/fixtures, user files, shared caches, and still-needed failure evidence.

---

## File structure and responsibility map

**Create:**

- `tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py` — the closed Python/Python-range/MCP/Skill public inventory consumed by doctor and MCP registration names.
- `tools/stm32-toolkit/tests/test_public_inventory.py` — behavior and cross-artifact inventory/version contract.
- `docs/codex/returns/STM32TK-0901-RUNTIME-AGENT-CONVERGENCE/implementation-report.md` — accepted-base, product CodeHead, TDD, verification, classification, cleanup, and remote-state evidence.

**Modify product/package code:**

- `tools/stm32-toolkit/src/stm32_toolkit/__init__.py` — in-process `0.9.0` authority.
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py` — import the authority and reject every missing project root instead of using `Path.cwd()`.
- `tools/stm32-toolkit/src/stm32_toolkit/doctor.py` — closed runtime and public inventory evidence.
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` — consume the closed MCP name map without changing registered behavior.
- `tools/stm32-toolkit/pyproject.toml` — `0.9.0` and `>=3.12,<3.13`.
- `tools/stm32-monitor/src/stm32_monitor/__init__.py` — expose the aligned Toolkit release authority.
- `tools/stm32-monitor/src/stm32_monitor/cli.py` — expose the aligned Monitor `version` command used by the local runtime smoke.
- `tools/stm32-monitor/src/stm32_monitor/protocol.py` — use the aligned authority as `MONITOR_VERSION`.
- `tools/stm32-monitor/src/stm32_monitor/runtime.py` — remove hard-coded Monitor release copies.
- `tools/stm32-monitor/pyproject.toml` — aligned package version, Python range, and exact Toolkit dependency.
- `tools/stm32-monitor/ui/package.json`, `tools/stm32-monitor/ui/package-lock.json` — aligned private UI package and lockfile identity only; browser behavior is unchanged.
- `tools/stm32-monitor/ui/e2e/fake_runtime.py`, `tools/stm32-monitor/ui/tests/main.test.tsx`, `tools/stm32-monitor/ui/tests/bootstrap.test.ts` — aligned current-runtime protocol fixtures; historical release/replay fixtures remain unchanged.
- `.claude-plugin/plugin.json` — aligned thin-adapter version and current description.
- `.mcp.json` — the same single Claude registration mapped to `STM32_TOOLKIT_DATA_ROOT`.
- `bin/stm32-toolkit-mcp.cmd`, `bin/stm32-monitor.cmd` — generic 0.9 runtime selection and fail-closed forwarding.
- `bin/setup-stm32-env.ps1` — generic parameter names, 3.12-only bootstrap discovery, 0.9 lifecycle, and legacy evidence.

**Modify thin adapter and documentation:**

- `skills/setup-stm32-env/SKILL.md`, `skills/stm32-monitor/SKILL.md` — map Claude path substitutions to the generic helper/launcher contract.
- `skills/migrate-keil/SKILL.md`, `skills/configure-stm32-project/SKILL.md`, `skills/build-firmware/SKILL.md`, `skills/flash-firmware/SKILL.md`, `skills/debug-firmware/SKILL.md`, `skills/read-var/SKILL.md` — only release/inventory wording if present; no workflow change.
- `README.md`, `README_zh-CN.md` — generic explicit-root usage, Claude mapping, 0.9/Python/inventory truth, and an explicit VS09-B boundary.

**Modify focused/current-runtime tests:**

- `tools/stm32-toolkit/tests/test_cli.py`
- `tools/stm32-toolkit/tests/test_doctor.py`
- `tools/stm32-toolkit/tests/test_mcp_server.py`
- `tools/stm32-toolkit/tests/test_mcp_roots.py`
- `tools/stm32-toolkit/tests/test_plugin_layout.py`
- `tools/stm32-toolkit/tests/test_setup_runtime.py`
- `tools/stm32-toolkit/tests/test_build_runner.py`
- `tools/stm32-toolkit/tests/test_cubemx_project.py`
- `tools/stm32-toolkit/tests/test_generation.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_mcp_migration_build.py`
- `tools/stm32-toolkit/tests/test_migration_plan.py`
- `tools/stm32-toolkit/tests/test_probe_protocol.py`
- `tools/stm32-toolkit/tests/test_result.py`
- `tools/stm32-toolkit/tests/test_target_transports.py`
- `tools/stm32-monitor/tests/test_cli.py`
- `tools/stm32-monitor/tests/test_exports.py`
- `tools/stm32-monitor/tests/test_models.py`
- `tools/stm32-monitor/tests/test_package_boundary.py`
- `tools/stm32-monitor/tests/test_protocol.py`
- `tools/stm32-monitor/tests/test_runtime.py`
- `tools/stm32-monitor/tests/test_service.py`

`tools/release/run_0502_windows_gates.ps1`, `tools/stm32-toolkit/tests/test_0502_release_gate_controller.py`, and historical Evidence/replay fixtures retain their original 0.5 producer facts.

## Interfaces

**Consumes:**

- `stm32_toolkit.__version__: str`
- `run_doctor(project_root: Path, *, data_root: Path | None = None, support_profile: ToolSupportProfile | None = None) -> OperationResult[dict[str, object]]`
- `create_server(project_root: Path, data_root: Path, session_id: str | None = None) -> FastMCP`
- existing CLI/MCP/Monitor workflows and the existing setup `Check|Bootstrap|Repair` lifecycle

**Produces:**

```python
TOOLKIT_VERSION = "0.9.0"
REQUIRED_PYTHON = ">=3.12,<3.13"
SUPPORTED_PYTHON = (3, 12)
MCP_TOOL_NAMES: Mapping[str, str]
SKILL_NAMES: tuple[str, ...]
```

Doctor adds `data.runtime` and `data.publicInventory` exactly as specified. It does not change the
`OperationResult` envelope. The launchers consume only `STM32_TOOLKIT_DATA_ROOT`; the setup helper
consumes `-ToolkitRoot`, `-DataRoot`, and `-ProjectRoot`.

---

### Task 1: Complete VS09-A runtime and Agent adapter convergence

One Luna/max implementer owns every step below in this worktree. Internal checkpoints and commits
do not create additional implementation owners.

- [ ] **Step 1: Reconstruct the clean implementation ledger and run the affected baseline**

Run from `C:/tmp/stm32tk-0901-runtime-agent-convergence`:

```powershell
git status --short --branch
git rev-parse HEAD
git log --oneline 9a5a132b74638a39b346848cfad0eeb7db9a0539..HEAD
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_cli.py `
  tools/stm32-toolkit/tests/test_doctor.py `
  tools/stm32-toolkit/tests/test_mcp_server.py `
  tools/stm32-toolkit/tests/test_mcp_roots.py `
  tools/stm32-toolkit/tests/test_plugin_layout.py `
  tools/stm32-toolkit/tests/test_setup_runtime.py `
  tools/stm32-monitor/tests/test_package_boundary.py `
  tools/stm32-monitor/tests/test_protocol.py `
  -q --basetemp C:/tmp/p0901-baseline
```

Expected starting identity: HEAD contains only the approved specification/plan commits above the
full accepted base; no product/report change exists. Record baseline counts and classify any
failure before product edits. After recording useful evidence, verify
`C:/tmp/p0901-baseline` resolves under `C:/tmp`, then remove only that run directory.

Create this plan's ignored SDD workspace with the skill's `scripts/sdd-workspace` command and write
the first ledger line exactly:

```markdown
# SDD ledger — plan: docs/superpowers/plans/2026-08-24-stm32-toolkit-0901-runtime-agent-convergence.md
```

Append the full ownership ledger from the specification, the implementer agent identity returned
by dispatch, starting HEAD, clean tracked/untracked state, no upstream, no remote authority, and
the baseline command/result.

- [ ] **Step 2: Write the failing release/inventory/doctor/package tests**

Create `tools/stm32-toolkit/tests/test_public_inventory.py` with these assertions and normal path
constants rooted from `Path(__file__).resolve().parents[3]`:

```python
from __future__ import annotations

import asyncio
import json
import sys
import tomllib
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.public_inventory import (
    MCP_TOOL_NAMES,
    REQUIRED_PYTHON,
    SKILL_NAMES,
    SUPPORTED_PYTHON,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_release_python_and_static_package_versions_are_one_contract(tmp_path: Path) -> None:
    toolkit = tomllib.loads((REPO_ROOT / "tools/stm32-toolkit/pyproject.toml").read_text("utf-8"))
    monitor = tomllib.loads((REPO_ROOT / "tools/stm32-monitor/pyproject.toml").read_text("utf-8"))
    plugin = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text("utf-8"))
    ui = json.loads((REPO_ROOT / "tools/stm32-monitor/ui/package.json").read_text("utf-8"))
    assert __version__ == "0.9.0"
    assert REQUIRED_PYTHON == ">=3.12,<3.13"
    assert SUPPORTED_PYTHON == (3, 12)
    assert toolkit["project"]["version"] == __version__
    assert toolkit["project"]["requires-python"] == REQUIRED_PYTHON
    assert monitor["project"]["version"] == __version__
    assert monitor["project"]["requires-python"] == REQUIRED_PYTHON
    assert monitor["project"]["dependencies"][0] == f"stm32-toolkit=={__version__}"
    assert plugin["version"] == ui["version"] == __version__


def test_actual_mcp_and_skill_inventory_matches_the_closed_public_inventory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    actual = {tool.name for tool in asyncio.run(create_server(project, tmp_path / "data", "session-a").list_tools())}
    discovered = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    assert len(MCP_TOOL_NAMES) == 48
    assert actual == set(MCP_TOOL_NAMES.values())
    assert len(SKILL_NAMES) == 8
    assert discovered == set(SKILL_NAMES)
```

Extend `test_doctor.py` with real-behavior tests that monkeypatch only distribution metadata and
external discovery seams. Add `import importlib.metadata` and `import sys` to its module imports:

```python
def test_doctor_reports_closed_runtime_and_public_inventory(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.importlib.metadata.version", lambda name: "0.9.0")
    result = run_doctor(tmp_path)
    runtime = result.data["runtime"]
    assert runtime == {
        "requiredPython": ">=3.12,<3.13",
        "pythonVersion": ".".join(str(part) for part in sys.version_info[:3]),
        "pythonSupported": sys.version_info[:2] == (3, 12),
        "toolkitVersion": "0.9.0",
        "monitorVersion": "0.9.0",
        "versionsCompatible": True,
    }
    assert len(result.data["publicInventory"]["mcpTools"]) == 48
    assert len(result.data["publicInventory"]["skills"]) == 8


def test_doctor_reports_missing_monitor_metadata_without_fabrication(monkeypatch, tmp_path: Path):
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError
    monkeypatch.setattr("stm32_toolkit.doctor.importlib.metadata.version", missing)
    runtime = run_doctor(tmp_path).data["runtime"]
    assert runtime["monitorVersion"] is None
    assert runtime["versionsCompatible"] is False
```

Update the current-runtime assertions in `test_package_boundary.py`, `test_plugin_layout.py`, and
the named Toolkit/Monitor current-runtime tests to expect `0.9.0` and `>=3.12,<3.13`. Do not edit
the 0502 release controller/test or historical Evidence/replay producer identities.

- [ ] **Step 3: Run the release/inventory RED and confirm the expected cause**

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_public_inventory.py `
  tools/stm32-toolkit/tests/test_doctor.py `
  tools/stm32-toolkit/tests/test_plugin_layout.py `
  tools/stm32-monitor/tests/test_package_boundary.py `
  tools/stm32-monitor/tests/test_protocol.py `
  -q --basetemp C:/tmp/p0901-version-red
```

Expected: collection fails because `stm32_toolkit.public_inventory` does not exist, or the first
executable assertions fail because current product declarations are 0.5.0/3.10. A typo,
filesystem ACL, missing dependency, or unrelated test error is not an accepted RED.

- [ ] **Step 4: Implement the closed release and inventory authority**

Set `stm32_toolkit.__version__ = "0.9.0"`. In `cli.py`, delete `_VERSION` and print imported
`__version__` for the version command.

Create `public_inventory.py` with this exact header and ordered maps. The values are copied
verbatim from the specification:

```python
from __future__ import annotations

from types import MappingProxyType
from typing import Final

from stm32_toolkit import __version__

TOOLKIT_VERSION: Final = __version__
REQUIRED_PYTHON: Final = ">=3.12,<3.13"
SUPPORTED_PYTHON: Final = (3, 12)

MCP_TOOL_NAMES = MappingProxyType({
    "doctor": "stm32_doctor",
    "project_detect": "stm32_project_detect",
    "project_context": "stm32_project_context",
    "project_create_plan": "stm32_project_create_plan",
    "project_create_prepare": "stm32_project_create_prepare",
    "project_create_apply": "stm32_project_create_apply",
    "project_regenerate_plan": "stm32_project_regenerate_plan",
    "project_regenerate_prepare": "stm32_project_regenerate_prepare",
    "project_regenerate_apply": "stm32_project_regenerate_apply",
    "keil_inspect": "stm32_keil_inspect",
    "keil_convert": "stm32_keil_convert",
    "project_configure": "stm32_project_configure",
    "build": "stm32_build",
    "probe_list": "stm32_probe_list",
    "flash": "stm32_flash",
    "debug_handoff_begin": "stm32_debug_handoff_begin",
    "debug_handoff_end": "stm32_debug_handoff_end",
    "variable_read": "stm32_variable_read",
    "variable_sample": "stm32_variable_sample",
    "register_read": "stm32_register_read",
    "fault_analyze": "stm32_fault_analyze",
    "diagnostic_start": "stm32_diagnostic_start",
    "diagnostic_show": "stm32_diagnostic_show",
    "diagnostic_begin": "stm32_diagnostic_begin",
    "diagnostic_hypothesis_add": "stm32_diagnostic_hypothesis_add",
    "diagnostic_hypothesis_assess": "stm32_diagnostic_hypothesis_assess",
    "diagnostic_plan_add": "stm32_diagnostic_plan_add",
    "diagnostic_plan_run": "stm32_diagnostic_plan_run",
    "test_target_replay": "stm32_test_target_replay",
    "diagnostic_source_change_declare": "stm32_diagnostic_source_change_declare",
    "diagnostic_verification_plan_add": "stm32_diagnostic_verification_plan_add",
    "diagnostic_verification_start": "stm32_diagnostic_verification_start",
    "diagnostic_marker_attach": "stm32_diagnostic_marker_attach",
    "diagnostic_verification_complete": "stm32_diagnostic_verification_complete",
    "diagnostic_verification_show": "stm32_diagnostic_verification_show",
    "test_host_discover": "stm32_test_host_discover",
    "test_host_run": "stm32_test_host_run",
    "test_show": "stm32_test_show",
    "test_target_prepare": "stm32_test_target_prepare",
    "test_target_execute": "stm32_test_target_execute",
    "acceptance_scenario_describe": "stm32_acceptance_scenario_describe",
    "acceptance_scenario_record": "stm32_acceptance_scenario_record",
    "acceptance_scenario_show": "stm32_acceptance_scenario_show",
    "acceptance_attempt_begin": "stm32_acceptance_attempt_begin",
    "acceptance_attempt_checkpoint": "stm32_acceptance_attempt_checkpoint",
    "acceptance_attempt_authorize_source_change": "stm32_acceptance_attempt_authorize_source_change",
    "acceptance_attempt_show": "stm32_acceptance_attempt_show",
    "acceptance_attempt_resume": "stm32_acceptance_attempt_resume",
})

SKILL_NAMES: Final = (
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor",
)
```

Replace every `@mcp.tool(name="...")` literal with its exact
`MCP_TOOL_NAMES["..."]` entry above. Keep wrapper names, schemas, registration order, and behavior
unchanged. Update the existing exact-registration test to compare actual names to
`set(MCP_TOOL_NAMES.values())`; this test is the executable guard against map/decorator drift.

Update both pyprojects to `version = "0.9.0"` and
`requires-python = ">=3.12,<3.13"`; Monitor's first dependency is
`stm32-toolkit==0.9.0`. Set the plugin and UI package versions to `0.9.0`.

In Monitor, import Toolkit `__version__` as the exported `__version__`, set
`MONITOR_VERSION = TOOLKIT_VERSION`, and replace the three hard-coded runtime-record/endpoint
`"0.5.0"` values with `MONITOR_VERSION`. Do not change protocol version strings.

Implement doctor helpers exactly in this shape:

```python
def _monitor_version() -> str | None:
    try:
        return importlib.metadata.version("stm32-monitor")
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None


def _runtime_evidence() -> dict[str, object]:
    monitor_version = _monitor_version()
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    return {
        "requiredPython": REQUIRED_PYTHON,
        "pythonVersion": python_version,
        "pythonSupported": sys.version_info[:2] == SUPPORTED_PYTHON,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": monitor_version,
        "versionsCompatible": monitor_version == TOOLKIT_VERSION,
    }


def _public_inventory() -> dict[str, object]:
    return {
        "mcpTools": list(MCP_TOOL_NAMES.values()),
        "skills": list(SKILL_NAMES),
    }
```

Insert both results in `run_doctor(...).data` without changing existing evidence fields or causing
filesystem writes.

- [ ] **Step 5: Run release/inventory GREEN and affected identity regressions**

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_public_inventory.py `
  tools/stm32-toolkit/tests/test_doctor.py `
  tools/stm32-toolkit/tests/test_mcp_server.py `
  tools/stm32-toolkit/tests/test_build_runner.py `
  tools/stm32-toolkit/tests/test_cubemx_project.py `
  tools/stm32-toolkit/tests/test_generation.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_mcp_migration_build.py `
  tools/stm32-toolkit/tests/test_migration_plan.py `
  tools/stm32-toolkit/tests/test_probe_protocol.py `
  tools/stm32-toolkit/tests/test_result.py `
  tools/stm32-toolkit/tests/test_target_transports.py `
  tools/stm32-monitor/tests/test_cli.py `
  tools/stm32-monitor/tests/test_exports.py `
  tools/stm32-monitor/tests/test_models.py `
  tools/stm32-monitor/tests/test_package_boundary.py `
  tools/stm32-monitor/tests/test_protocol.py `
  tools/stm32-monitor/tests/test_runtime.py `
  tools/stm32-monitor/tests/test_service.py `
  -q --basetemp C:/tmp/p0901-version-green
```

Expected: exit 0. When an exact digest fixture changes solely because current Toolkit version is a
canonical input, rebuild the expected canonical payload from literal fields in the test and hash it
with `hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()`;
do not call the production serializer to compute the expected value. Leave historical producer
versions unchanged.

- [ ] **Step 6: Write and run the explicit-root CLI RED**

Add these behavior tests to `test_cli.py`:

```python
def test_doctor_without_explicit_project_root_fails_before_workflow(monkeypatch, capsys):
    called = False
    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("workflow must not run")
    monkeypatch.setattr("stm32_toolkit.cli._operation_result", unexpected)
    assert main(["doctor", "--json"]) == 2
    assert called is False
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


def test_project_detect_without_explicit_root_never_uses_current_directory(monkeypatch, capsys):
    monkeypatch.setattr("stm32_toolkit.cli.Path.cwd", lambda: (_ for _ in ()).throw(AssertionError("cwd fallback")))
    assert main(["project", "detect", "--json"]) == 2
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


def test_version_is_the_only_root_free_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out == "0.9.0\n"
```

Run:

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src'
py -3.12 -m pytest tools/stm32-toolkit/tests/test_cli.py `
  -k 'explicit_project_root or current_directory or only_root_free' `
  -q --basetemp C:/tmp/p0901-cli-red
```

Expected: the two project-bound tests fail because current code still reaches the `Path.cwd()`
fallback; the version test passes.

- [ ] **Step 7: Remove the CLI fallback and run CLI/MCP root GREEN**

Inside the existing `parse_args` exception boundary, require the root before workflow dispatch:

```python
def _require_explicit_project_root(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if args.command != "version" and not hasattr(args, "project_root"):
        parser.error("project root is required")
```

Call it immediately after `_validate_cli_modes(parser, args)`. Keep the version early return, then
assign only `project_root = args.project_root`; delete `getattr(..., Path.cwd())`. Preserve existing
aliases and duplicate rejection.

Run:

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_cli.py `
  tools/stm32-toolkit/tests/test_mcp_server.py `
  tools/stm32-toolkit/tests/test_mcp_roots.py `
  tools/stm32-toolkit/tests/test_mcp_migration_build.py `
  -q --basetemp C:/tmp/p0901-roots-green
```

Expected: exit 0; no test observes current-directory project selection, and MCP remains explicitly
bound with the same client-root checks.

- [ ] **Step 8: Write and run the generic launcher/setup RED**

Update `test_plugin_layout.py` launcher helpers to remove `CLAUDE_PLUGIN_DATA`, set only
`STM32_TOOLKIT_DATA_ROOT`, and expect `runtime/0.9.0/Scripts/python.exe`. The manifest assertion is
exactly:

```python
assert server["env"] == {
    "STM32_TOOLKIT_DATA_ROOT": "${CLAUDE_PLUGIN_DATA}",
}
```

Assert neither launcher contains `CLAUDE_PLUGIN_DATA`, `python`, `py`, or `uv` as a fallback
command; module names and error prose do not count as fallback commands. Update setup invocations
to the exact generic parameters:

```text
-ToolkitRoot REPOSITORY_ROOT
-DataRoot DATA_ROOT
-ProjectRoot PROJECT_ROOT
```

In `test_setup_runtime.py`, update the test backend/current package identities to 0.9.0 and add a
fake executable test whose reported `3.11.9` Python has `supported=false`; assert Bootstrap exits 2
before the selected data root's `runtime` directory is created. Retain the hostile environment, bounded output,
redirect-ancestor, staging cleanup, quarantine, rollback, probe-extra, and UI-asset cases.

Run:

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_plugin_layout.py `
  tools/stm32-toolkit/tests/test_setup_runtime.py `
  -q --basetemp C:/tmp/p0901-runtime-red
```

Expected: failures identify Claude-only launcher selection, 0.5 runtime paths, old helper parameter
names, and 3.10/3.11 acceptance. Environment/test-harness failures are not accepted RED evidence.

- [ ] **Step 9: Implement the generic launchers and setup lifecycle**

Both cmd launchers use this exact selection pattern, with their existing module/exit variables:

```batch
if not defined STM32_TOOLKIT_DATA_ROOT (
  >&2 echo stm32-toolkit: STM32_TOOLKIT_DATA_ROOT is not set. Run the generic runtime Check, then retry.
  exit /b 2
)
set "STM32_TOOLKIT_RUNTIME=%STM32_TOOLKIT_DATA_ROOT%\runtime\0.9.0\Scripts\python.exe"
if not exist "%STM32_TOOLKIT_RUNTIME%" (
  >&2 echo stm32-toolkit: runtime/0.9.0/Scripts/python.exe is missing under STM32_TOOLKIT_DATA_ROOT.
  exit /b 2
)
```

Use `stm32-toolkit-mcp` or `stm32-monitor` in the error prefix as appropriate. Keep quoted
interpreter invocation, `%*`, and exact child exit-code forwarding.

Change setup parameters to:

```powershell
[Parameter(Mandatory = $true)][string]$ToolkitRoot,
[Parameter(Mandatory = $true)][string]$DataRoot,
[Parameter(Mandatory = $true)][string]$ProjectRoot
```

Rename `Resolve-ClaudePath` to `Resolve-ExplicitPath`; reject empty values, any unresolved
`${...}` token, non-absolute paths, missing required directories, and redirect ancestors without
mentioning an Agent. Use `$RuntimeVersion = "0.9.0"` and
`$LegacyRuntimeVersions = @("0.5.0", "0.3.0")`.

Probe bootstrap candidates in this order:

```powershell
@(
    [ordered]@{ name = "py"; prefix = @("-3.12") },
    [ordered]@{ name = "python"; prefix = @() },
    [ordered]@{ name = "python3"; prefix = @() }
)
```

The isolated metadata probe sets `supported` only when
`sys.version_info[:2] == (3, 12)`. Return the candidate's `prefix`; prepend it to both the probe and
`-I -m venv` invocations. Bootstrap/Repair error text states
`CPython >=3.12,<3.13 is required`.

For Check, select the current 0.9 directory if present; otherwise report the first present legacy
directory in the ordered list as `broken` and recommend Repair. Repair rejects multiple present
legacy directories as ambiguous before mutation, otherwise quarantines the single selected legacy
runtime and retains the existing rollback rules. Bootstrap rejects any current or legacy runtime.
No launcher ever selects a legacy path.

Update the embedded Monitor validation to compare metadata/UI assets against 0.9.0. Keep isolated
Python flags, environment scrubbing, output bounds, timeouts, no-cache local source installation,
staging safety, and project read-only checks.

- [ ] **Step 10: Run launcher/setup GREEN**

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_plugin_layout.py `
  tools/stm32-toolkit/tests/test_setup_runtime.py `
  -q --basetemp C:/tmp/p0901-runtime-green
```

Expected: exit 0; Windows launcher tests use only `STM32_TOOLKIT_DATA_ROOT`, setup uses only generic
parameters, 3.11 is refused before mutation, and current/legacy/repair paths remain fail closed.

- [ ] **Step 11: Update the Claude thin adapter, Skills, and bilingual documentation**

Keep `.mcp.json` at one server. Its command and args remain the existing Claude substitutions; its
only environment mapping is:

```json
"env": {
  "STM32_TOOLKIT_DATA_ROOT": "${CLAUDE_PLUGIN_DATA}"
}
```

In the setup Skill, use generic helper parameters while still substituting Claude paths inline:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

Use the same argument names for Bootstrap and Repair. State one CPython 3.12 runtime and generic
launcher contract; do not put STM32 business behavior into the Skill.

In the Monitor Skill, preserve any prior process value, set the generic data root only for the
launcher invocation, and restore it:

```powershell
$previousStm32ToolkitDataRoot = [Environment]::GetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', 'Process')
try {
  [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', '${CLAUDE_PLUGIN_DATA}', 'Process')
  & '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
} finally {
  [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', $previousStm32ToolkitDataRoot, 'Process')
}
```

README and README_zh-CN must include equivalent English/Chinese versions of:

- local 0.9.0 VS09-A candidate, not pushed/tagged/released;
- CPython `>=3.12,<3.13` and the generic `DATA_ROOT/runtime/0.9.0` layout;
- a CLI example with explicit `--project-root`;
- a generic MCP JSON template using an absolute launcher, explicit project/data args, and only
  `STM32_TOOLKIT_DATA_ROOT` in `env`;
- Claude `.mcp.json` as a mapping to the same contract;
- the exact eight Skills and all 48 names from `MCP_TOOL_NAMES.values()` grouped by existing
  Project/Build/Probe/Diagnostic/Test/Acceptance responsibilities; and
- a clear statement that pinned-source install, secure upgrade/downgrade, malicious-name tests,
  checksums, archives, SBOM, licenses, compatibility, and troubleshooting are VS09-B work and are
  not yet release claims.

Remove every current claim of fifteen MCP tools, current 0.5 runtime, or supported host Python
3.10+. Keep historical 0.5 release statements only when explicitly labelled historical rather
than current.

- [ ] **Step 12: Run the exact affected slice matrix**

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest `
  tools/stm32-toolkit/tests/test_public_inventory.py `
  tools/stm32-toolkit/tests/test_cli.py `
  tools/stm32-toolkit/tests/test_doctor.py `
  tools/stm32-toolkit/tests/test_mcp_server.py `
  tools/stm32-toolkit/tests/test_mcp_roots.py `
  tools/stm32-toolkit/tests/test_plugin_layout.py `
  tools/stm32-toolkit/tests/test_setup_runtime.py `
  tools/stm32-toolkit/tests/test_build_runner.py `
  tools/stm32-toolkit/tests/test_cubemx_project.py `
  tools/stm32-toolkit/tests/test_generation.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_mcp_migration_build.py `
  tools/stm32-toolkit/tests/test_migration_plan.py `
  tools/stm32-toolkit/tests/test_probe_protocol.py `
  tools/stm32-toolkit/tests/test_result.py `
  tools/stm32-toolkit/tests/test_target_transports.py `
  tools/stm32-monitor/tests/test_cli.py `
  tools/stm32-monitor/tests/test_exports.py `
  tools/stm32-monitor/tests/test_models.py `
  tools/stm32-monitor/tests/test_package_boundary.py `
  tools/stm32-monitor/tests/test_protocol.py `
  tools/stm32-monitor/tests/test_runtime.py `
  tools/stm32-monitor/tests/test_service.py `
  -q --basetemp C:/tmp/p0901-slice --junitxml=C:/tmp/p0901-slice.xml
py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests tools/stm32-monitor/src tools/stm32-monitor/tests
git diff --check 9a5a132b74638a39b346848cfad0eeb7db9a0539..HEAD
```

Expected: pytest exit 0 with zero failures/errors; any existing platform skip is reported by exact
node id and not relabelled as product or physical PASS. `compileall` and diff check exit 0.

- [ ] **Step 13: Build and exercise one fresh local 3.12 wheel/runtime smoke**

Resolve each path below and verify it remains below `C:/tmp` before creation or cleanup:

```powershell
$wheelhouse = 'C:/tmp/p0901-wheelhouse'
$runtime = 'C:/tmp/p0901-runtime'
$project = 'C:/tmp/p0901-project'
$data = 'C:/tmp/p0901-data'
New-Item -ItemType Directory -Force $wheelhouse, $project, $data | Out-Null
py -3.12 -m pip wheel --no-deps --no-build-isolation -w $wheelhouse tools/stm32-toolkit
py -3.12 -m pip wheel --no-deps --no-build-isolation -w $wheelhouse tools/stm32-monitor
py -3.12 -m venv --system-site-packages $runtime
& "$runtime/Scripts/python.exe" -I -m pip install --no-deps --no-index --find-links $wheelhouse stm32-toolkit==0.9.0 stm32-monitor==0.9.0
& "$runtime/Scripts/python.exe" -I -m stm32_toolkit.cli version
& "$runtime/Scripts/python.exe" -I -m stm32_toolkit.cli --project-root $project doctor --json
& "$runtime/Scripts/python.exe" -I -c "import asyncio, pathlib; from stm32_toolkit.mcp_server import create_server; s=create_server(pathlib.Path(r'$project'), pathlib.Path(r'$data'), 'session-a'); print(len(asyncio.run(s.list_tools())))"
& "$runtime/Scripts/python.exe" -I -c "import importlib.metadata as m, json; from importlib import resources; import stm32_monitor, stm32_toolkit; ui=resources.files('stm32_monitor')/'ui_dist'; print(json.dumps({'toolkit':stm32_toolkit.__version__,'monitor':stm32_monitor.__version__,'metadata':m.version('stm32-monitor'),'index':(ui/'index.html').is_file(),'manifest':(ui/'.vite/manifest.json').is_file()}))"
& "$runtime/Scripts/python.exe" -I -m stm32_monitor version
```

Expected: both wheels are `0.9.0`; install is offline from that wheelhouse; Toolkit/Monitor version
outputs are 0.9.0; doctor is successful and reports compatible 0.9.0/3.12/48/8 evidence; MCP prints
48; UI index and manifest are true; Monitor version is 0.9.0. `--system-site-packages` supplies the
already-verified host dependencies without network acquisition; VS09-B owns fully pinned clean
dependency acquisition.

Record wheel names and SHA-256 only as slice evidence, not as VS09-B release checksums. Remove the
four exact run roots after evidence is copied into the report/ledger. Remove generated `__pycache__`
and `.pyc` under source/tests after `compileall`; do not remove source-controlled UI assets or
fixtures.

- [ ] **Step 14: Self-review the complete implementation and commit product/tests/docs**

Run:

```powershell
git status --short
git diff --stat 4073ea1e8450bd189d416350bf5742befd222399..HEAD
git diff --check
rg -n 'CLAUDE_PLUGIN_DATA|runtime[\\/]0\.5\.0|Host Python 3\.10|exactly 15|恰好 15' bin tools/stm32-toolkit/pyproject.toml tools/stm32-monitor/pyproject.toml skills README.md README_zh-CN.md .mcp.json .claude-plugin/plugin.json
rg -n '0\.5\.0' tools/release/run_0502_windows_gates.ps1 tools/stm32-toolkit/tests/test_0502_release_gate_controller.py docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE
```

The first search must have no stale current-contract hit; Claude path substitutions may remain only in
the thin `.mcp.json`/Skills/README mapping, never in generic launcher/setup implementation. The
second search confirms historical 0502 identities were retained rather than rewritten.

Review every changed file against the specification, ensure tests name observable breaks and do
not assert only on mocks, and perform the mutation check for wrong version, wrong Python range,
missing root rejection, launcher fallback, omitted MCP name, omitted Skill, Monitor mismatch, and
unsafe setup promotion.

Commit product, tests, adapters, and bilingual docs together after GREEN evidence:

```powershell
git add -- .claude-plugin/plugin.json .mcp.json bin skills README.md README_zh-CN.md tools/stm32-toolkit tools/stm32-monitor
git commit -m "feat(vs09): converge runtime and agent adapters"
```

Run the exact affected matrix and smoke again if the commit changed any tested bytes after their
last run. Record `git rev-parse HEAD` as the product CodeHead before creating the report.

- [ ] **Step 15: Write the implementation report and reconcile the SDD ledger**

Create the report path named above. It must record:

- module/phase `STM32 Toolkit 0.9 / VS09-A`;
- full accepted base `9a5a132b74638a39b346848cfad0eeb7db9a0539`;
- specification commit `4073ea1e8450bd189d416350bf5742befd222399` and this plan commit;
- sole Luna/max implementer identity and Sol reviewer ownership;
- branch/worktree, no PR, no remote/hardware authority, and no bounded override;
- product CodeHead captured before the report commit, never the report's own SHA;
- exact RED causes, GREEN commands, counts, skips, warnings, elapsed evidence, wheel names/hashes,
  doctor/inventory outputs, and affected regression results;
- PRODUCT/INFRASTRUCTURE/ENVIRONMENT/PLATFORM/HARDWARE/REPORT classification with no invented PASS;
- exact cleaned run roots and retained evidence; and
- tracked/untracked, committed/uncommitted, pushed/unpushed, upstream, and remote state.

Resolve the task's actual starting and returned short commit identities with `git rev-parse --short`
and append the same current facts plus one line in the exact form
`Task 1: complete (commits STARTING_SHORT_SHA..RETURNED_SHORT_SHA, pending Sol complete-diff review)`
to the ignored SDD ledger. Replace both all-caps identity tokens with the values returned by Git;
do not copy the token text into the ledger. Do not claim `ACCEPTED`; only Sol may record that verdict.

Commit only the tracked report:

```powershell
git add -- docs/codex/returns/STM32TK-0901-RUNTIME-AGENT-CONVERGENCE/implementation-report.md
git commit -m "docs(vs09): record runtime convergence implementation"
```

- [ ] **Step 16: Return the bounded implementation for Sol review**

Run final handoff checks:

```powershell
git status --short --branch
git log --oneline 9a5a132b74638a39b346848cfad0eeb7db9a0539..HEAD
git diff --check 9a5a132b74638a39b346848cfad0eeb7db9a0539..HEAD
git branch -vv
git branch -r --contains HEAD
```

Return only status `DONE` or `DONE_WITH_CONCERNS`, product CodeHead, final local report head, the
one-line affected-matrix and fresh-smoke summary, cleanup state, and concerns. Do not push, open or
mutate a PR, merge, tag, release, touch hardware, start VS09-B, or self-accept.

---

## Sol review gate after Task 1

The GPT-5.6-sol primary agent, not the implementer, creates a clean detached review worktree at the
returned head, inspects the complete
`9a5a132b74638a39b346848cfad0eeb7db9a0539..returned-head` diff, verifies the report against Git,
runs only the exact affected matrix and one independent fresh wheel/runtime smoke, cleans its run
artifacts/worktree, and records one repository verdict. Correctable findings return to the same
Luna/max implementer. If the same issue fails two implementation/review rounds, stop local patching
and return to the interface/design. VS09-B cannot begin before an explicit Sol `ACCEPTED` verdict.

---

## Sol review round 1 corrections — 2026-08-25

The independent complete-diff review of returned head
`591a71242bfbcbd29433634cae4cd433fe9e9725` issued `REVISION_REQUIRED`. The same sole
Luna/max implementer owns this bounded correction round. The frozen specification already defines
the behavior; this section corrects plan omissions and does not add a product subsystem.

- [x] **Root cardinality and value safety:** add RED tests showing that CLI workflow, hardware,
  testing, and diagnostic parsers reject a global plus command-local project root, and that CLI
  empty, unresolved-token, relative, or redirected project roots fail before workflow invocation.
  Add MCP parser tests proving duplicate project/data roots fail rather than last-value-wins.
  Implement one shared CLI project-root argument action/type across every existing root helper and
  the equivalent bounded MCP parser guard. Preserve current aliases and all workflow behavior.
- [x] **Managed-runtime health evidence:** make both Check and pre-promotion validation require the
  exact doctor runtime contract (`requiredPython`, `pythonSupported`, Toolkit/Monitor versions and
  compatibility) plus the exact 48 MCP and eight Skill inventories. Missing, false, malformed, or
  mismatched fields make the runtime broken or abort promotion before mutation. Update the setup
  fake package to emit the complete contract and add a negative test for an `ok=true` doctor with
  unsupported/missing runtime evidence.
- [x] **Independent inventory oracle:** keep the production `MCP_TOOL_NAMES` map, but make
  `test_public_inventory.py` contain an independent frozen expected mapping/set copied from the
  specification. Assert the production map and actual server registrations separately against
  that oracle so one typo in the production map cannot update both sides of the test.
- [x] **Monitor/UI identity closure:** align the two root versions in `package-lock.json` and the
  current fake-runtime/bootstrap/main fixtures to `0.9.0`. Extend the Python public-inventory test
  to parse/check these files without introducing a browser or Node release matrix.
- [x] **Executable documentation:** change both bilingual build examples to the existing
  `--preset arm-debug` value and assert that exact example in the focused documentation test.
- [x] **Evidence reconciliation:** run the focused CLI/MCP/public-inventory/doctor/plugin/setup and
  Monitor package/protocol/runtime tests affected by these fixes in an installed CPython 3.12
  environment so isolated fake-CMake children can import the returned candidate. Use package-split
  pytest commands or `--import-mode=importlib` to avoid the two `test_cli.py` basename collision.
  Re-run the fresh local wheel/runtime smoke only if product/package bytes changed, clean every
  new run root, append the correction evidence to both reports/ledger, and commit locally. Do not
  start VS09-B or perform remote/hardware actions.

Sol independently re-reviewed `591a71242bfbcbd29433634cae4cd433fe9e9725..8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`
and the complete accepted-base range
`9a5a132b74638a39b346848cfad0eeb7db9a0539..8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`
in a clean detached worktree. All five findings are addressed, the risk-triggered checks and one
fresh installed-wheel smoke pass, and the VS09-A verdict is `ACCEPTED`. The detailed independent
evidence is in
`docs/codex/returns/STM32TK-0901-RUNTIME-AGENT-CONVERGENCE/review-report.md`.
