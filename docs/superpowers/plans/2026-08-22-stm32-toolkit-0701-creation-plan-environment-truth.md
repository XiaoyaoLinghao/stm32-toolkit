# STM32 Toolkit VS07-A Creation Plan and Environment Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one read-only public workflow that accurately discovers the supported local creation environment and returns a deterministic plan for creating an STM32 project from exactly one MCU, board, or `.ioc` source.

**Architecture:** A focused `tool_support` module owns explicit-path, CubeCLT-metadata, supported-standard-path and PATH discovery without mutating the host. A separate `generation.creation` module validates the caller request and builds immutable plan/action digests; thin workflow, CLI and MCP adapters expose the same result and never invoke CubeMX or write the destination in VS07-A.

**Tech Stack:** CPython `>=3.12,<3.13`, dataclasses, pathlib, existing canonical JSON/SHA-256 helpers, FastMCP, argparse, pytest, STM32CubeCLT 1.22.0 metadata, STM32CubeMX 6.18 version evidence.

## Global Constraints

- Product accepted base: `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`.
- Design source: `fa9a3c4aa349d296f5de9704ecb4300fc420a71f` (`2026-08-22-stm32-toolkit-0.7-1.0-integrated-product-design.md`).
- One GPT-5.6-luna implementer with reasoning effort `max` owns the complete VS07-A product diff; the steps below are sequential checkpoints, not separately dispatched tasks or Gates.
- GPT-5.6-sol independently reviews the full accepted-base-to-final-head diff and accepts or returns the same slice.
- Python support is exactly `>=3.12,<3.13`; do not add Python 3.10/3.11 branches or matrices.
- Planning is read-only: it does not run CubeMX, create staging, write the destination, modify VS Code, install software, access hardware, or mutate Git.
- Discovery order is explicit support profile → CubeCLT metadata/known supported install root → supported standard path → PATH.
- Discovery never recursively searches whole disks, chooses an ambiguous executable, follows redirects, uses ambient credentials, or downloads components.
- CubeCLT 1.22.0 supplies GCC/CMake/Ninja facts; CubeMX 6.18 is a separate required generator.
- PyOCD remains the only Probe backend; this slice does not add flash/debug behavior.
- Public output uses the existing closed `OperationResult` convention and never leaks private host paths in failure text.
- No push, PR, merge, tag, release, remote branch or hardware operation is authorized.

---

### Task 1: Closed tool support facts

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/tool_support.py`
- Create: `tools/stm32-toolkit/tests/test_tool_support.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/doctor.py`
- Modify: `tools/stm32-toolkit/tests/test_doctor.py`

**Interfaces:**
- Produces: `SupportProfileRequest(profile_path: Path | None, data_root: Path | None)` for a trusted local runtime/CLI caller; MCP operations never supply executable roots.
- Produces: `ToolFact(name: str, path: Path, version: str, source: Literal["explicit", "cubeclt-metadata", "standard", "path"], executable_sha256: str)`.
- Produces: `ToolSupportProfile(python_version: str, cubemx: ToolFact | None, cubeclt_root: Path | None, gcc: ToolFact | None, cmake: ToolFact | None, ninja: ToolFact | None, vscode: ToolFact | None, vscode_extensions: tuple[tuple[str, str], ...], issues: tuple[ToolSupportIssue, ...])` with `to_dict() -> dict[str, object]`.
- Produces: `discover_tool_support(request: SupportProfileRequest) -> ToolSupportProfile`.
- Consumes later: Task 2 uses `ToolSupportProfile` as immutable creation-plan input.

- [ ] **Step 1: Write RED model and serialization tests**

Add tests that construct a complete profile and assert stable closed JSON, frozen tuples, exact source values, SHA-256 format, sorted issues and rejection of unsupported Python.

```python
def test_support_profile_is_closed_deterministic_and_python_312_only(tmp_path: Path):
    profile = discover_tool_support(_explicit_profile_fixture(tmp_path))
    payload = profile.to_dict()
    assert payload["pythonVersion"].startswith("3.12.")
    assert payload["gcc"]["source"] == "explicit"
    assert tuple(payload) == (
        "pythonVersion", "cubeMx", "cubeCltRoot", "gcc", "cmake", "ninja",
        "vsCode", "vsCodeExtensions", "issues",
    )
```

- [ ] **Step 2: Run the focused RED test**

Run:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py -q
```

Expected: collection fails only because `stm32_toolkit.tool_support` does not exist.

- [ ] **Step 3: Implement immutable closed models and bounded helpers**

Implement exact dataclasses and `to_dict()` methods. Reuse the existing bounded process pattern from `doctor.py`; do not import `doctor` from `tool_support`, and do not retain raw stdout/stderr or absolute paths in issue messages.

```python
@dataclass(frozen=True, slots=True)
class ToolSupportIssue:
    code: str
    component: str
    remediation: str

@dataclass(frozen=True, slots=True)
class ToolFact:
    name: str
    path: Path
    version: str
    source: Literal["explicit", "cubeclt-metadata", "standard", "path"]
    executable_sha256: str
```

- [ ] **Step 4: Write RED discovery-order and local-layout tests**

Cover explicit paths winning over metadata/PATH, parsing `STM32CubeCLT_metadata.bat -j` output through a bounded injected seam, the exact current `C:\ST\STM32CubeCLT_1.22.0` layout, separate missing CubeMX, VS Code installed without `code` on PATH, redirect/non-file rejection, duplicate/ambiguous candidates, timeout and nonzero version probes.

```python
def test_cubeclt_metadata_discovers_build_tools_but_not_cubemx(fake_clt: Path):
    profile_file = _write_support_profile(fake_clt.parent, cubeclt_root=fake_clt)
    profile = discover_tool_support(SupportProfileRequest(profile_path=profile_file, data_root=fake_clt.parent))
    assert profile.gcc is not None
    assert profile.cmake is not None
    assert profile.ninja is not None
    assert profile.cubemx is None
    assert [issue.code for issue in profile.issues] == ["CUBEMX_MISSING"]
```

- [ ] **Step 5: Implement discovery and adapt doctor**

Keep public `run_doctor()` shape compatible while sourcing creation-related facts from `discover_tool_support()`. Add a distinct `creationSupport` object and retain legacy `tools` fields until VS09-A version convergence.

```python
support = discover_tool_support(SupportProfileRequest())
return OperationResult.success(
    "doctor",
    {**legacy_evidence, "creationSupport": support.to_dict(), "mutated": False},
)
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py -q
```

Expected: all collected tests pass; existing doctor keys remain compatible; no files outside pytest temp roots change.

- [ ] **Step 7: Commit the coherent discovery component**

This is an internal checkpoint on the same VS07-A branch, not a separate agent or Gate.

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/tool_support.py tools/stm32-toolkit/src/stm32_toolkit/doctor.py tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py
git commit -m "feat(project): discover supported creation tools"
```

### Task 2: Read-only creation request and deterministic plan

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/generation/creation.py`
- Create: `tools/stm32-toolkit/tests/test_creation_plan.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/__init__.py`

**Interfaces:**
- Consumes: `ToolSupportProfile` from Task 1.
- Produces: `CreationSource(kind: Literal["mcu", "board", "ioc"], value: str, sha256: str | None)`.
- Produces: `CreationRequest(source: CreationSource, destination: str, framework: Literal["hal", "ll"], language: Literal["c", "cpp"], overwrite: Literal["refuse"])` plus `from_ioc(ioc: str, destination: str, *, framework: str, language: str) -> CreationRequest`, `from_mcu(...)`, and `from_board(...)` constructors.
- Produces: `CreationPlan(schema_version: Literal[1], plan_id: str, action_digest: str, expires_at: str, request: CreationRequest, tool_profile_digest: str, destination_inventory_digest: str, blockers: tuple[CreationBlocker, ...])` with `to_dict() -> dict[str, object]`.
- Produces: `plan_project_creation(workspace_root: Path, request: CreationRequest, tools: ToolSupportProfile, *, now: datetime) -> CreationPlan`.

- [ ] **Step 1: Write RED request validation tests**

Test exactly one source kind, canonical MCU/board strings, project-relative portable `.ioc` and destination paths, `.ioc` size/hash/readability, destination absence/empty-inventory behavior, refusal of absolute/traversal/redirect/NUL/control paths and any overwrite policy other than `refuse`.

```python
def test_creation_request_accepts_exactly_one_ioc_and_hashes_it(tmp_path: Path):
    ioc = tmp_path / "board.ioc"
    ioc.write_text("Mcu.Name=STM32F429ZI\n", encoding="utf-8")
    plan = plan_project_creation(
        tmp_path,
        CreationRequest.from_ioc("board.ioc", "generated", framework="hal", language="c"),
        _supported_tools(tmp_path),
        now=_NOW,
    )
    assert plan.request.source.kind == "ioc"
    assert plan.request.source.sha256 == hashlib.sha256(ioc.read_bytes()).hexdigest()
```

- [ ] **Step 2: Run request RED tests**

Run:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py -q
```

Expected: collection fails because `generation.creation` is absent.

- [ ] **Step 3: Implement closed creation request models and safe inspection**

Use immutable dataclasses, portable forward-slash paths, exact UTF-8 and byte limits, `lstat`/reparse rejection and existing canonical JSON/SHA-256 conventions. Planning may inspect only the declared source, destination chain and tool facts.

- [ ] **Step 4: Write RED digest, expiry and blocker tests**

Assert deterministic `planId` and `actionDigest`, one-hour UTC expiry, blocker ordering, current destination inventory binding, tool-profile binding, distinct digests for any normalized input change, `CUBEMX_MISSING` on the current environment and zero filesystem mutation before/after every outcome.

```python
def test_missing_cubemx_returns_stable_blocker_without_writes(tmp_path: Path):
    before = _tree_snapshot(tmp_path)
    plan = plan_project_creation(tmp_path, _mcu_request(), _tools_without_cubemx(tmp_path), now=_NOW)
    assert [item.code for item in plan.blockers] == ["CUBEMX_MISSING"]
    assert _tree_snapshot(tmp_path) == before
```

- [ ] **Step 5: Implement deterministic planning**

Canonicalize request/profile/inventory, derive `plan_id` from all read-only inputs and `action_digest` from the future apply action. Do not serialize raw host roots; bind their canonical identity through digests.

```python
plan_id = sha256_hex(canonical_json_bytes(plan_inputs))
action_digest = sha256_hex(canonical_json_bytes({"operation": "project-create", "planId": plan_id}))
```

- [ ] **Step 6: Run Task 2 tests and existing generation regression**

Run:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_generation.py -q
```

Expected: all tests pass; existing managed Keil/GCC generation behavior remains unchanged.

- [ ] **Step 7: Commit the coherent plan domain**

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/generation/creation.py tools/stm32-toolkit/src/stm32_toolkit/generation/__init__.py tools/stm32-toolkit/tests/test_creation_plan.py
git commit -m "feat(project): plan CubeMX project creation"
```

### Task 3: One public workflow with CLI and MCP adapters

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_creation_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_creation_cli.py`
- Create: `tools/stm32-toolkit/tests/test_creation_mcp.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`

**Interfaces:**
- Consumes: Task 1 tool support and Task 2 creation plan interfaces.
- Produces: `CreationPlanWorkflowRequest(project_root: Path, data_root: Path, session_id: str, source_kind: str, source_value: str, destination: str, framework: str, language: str, support_profile_path: Path | None)`; the MCP wrapper supplies the runtime-pinned profile rather than accepting it from a tool request.
- Produces: `plan_creation_workflow(request: CreationPlanWorkflowRequest) -> OperationResult[dict[str, object]]`.
- Produces CLI: `stm32-toolkit project create-plan --source-kind {mcu,board,ioc} --source VALUE --destination PATH --framework {hal,ll} --language {c,cpp}` plus an optional trusted local `--support-profile` file.
- Produces MCP: `stm32_project_create_plan(sourceKind, source, destination, framework, language)`; it accepts no root, executable, command, environment or support-profile override.

- [ ] **Step 1: Write RED workflow result tests**

Assert a plan with blockers remains a valid read-only result, malformed input maps to closed `CREATION_INPUT_INVALID`, discovery failure maps to `CREATION_ENVIRONMENT_INVALID`, output contains no exception text, and no path calls a CubeMX execution seam.

```python
def test_plan_workflow_reports_missing_cubemx_as_plan_blocker(tmp_path: Path):
    result = plan_creation_workflow(_workflow_request(tmp_path, source_kind="mcu"))
    assert result.ok is True
    assert result.data["blockers"][0]["code"] == "CUBEMX_MISSING"
    assert result.data["mutated"] is False
```

- [ ] **Step 2: Implement the thin workflow**

Construct support and creation requests, call the two domain functions once, and translate only named domain exceptions. Do not place CubeMX argv, path scanning or digest logic in the workflow.

- [ ] **Step 3: Write RED CLI and MCP parity tests**

Test all three source kinds, exact choices, project-root containment, a trusted CLI support profile, rejection of any MCP executable/profile override, malformed/duplicate inputs, MCP client-root enforcement and equality of normalized CLI/MCP payloads.

```python
def test_cli_and_mcp_creation_plan_payloads_match(tmp_path: Path):
    cli_payload = _run_cli_plan(tmp_path, "mcu", "STM32F429ZITx")
    mcp_payload = _run_mcp_plan(tmp_path, "mcu", "STM32F429ZITx")
    assert cli_payload == mcp_payload
```

- [ ] **Step 4: Add the public adapters**

Add only `project create-plan` and `stm32_project_create_plan`. Do not expose apply/authorized flags in VS07-A and do not modify existing Keil or hardware semantics.

- [ ] **Step 5: Run Task 3 tests and public adapter regression**

Run:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q
```

Expected: all tests pass with no new skip/xfail and no change to existing command/tool behavior.

- [ ] **Step 6: Commit the public vertical behavior**

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py
git commit -m "feat(project): expose read-only creation plans"
```

### Task 4: Slice acceptance, documentation and return ledger

**Files:**
- Modify: `README.md`
- Modify: `README_zh-CN.md`
- Create: `docs/codex/returns/STM32TK-0701-CREATION-PLAN/implementation-report.md`
- Test: all Task 1–3 tests plus the affected regression command below

**Interfaces:**
- Consumes: final `stm32_project_create_plan` and CLI `project create-plan` behavior.
- Produces: one user-facing environment/plan example and one report recording accepted base and code head before the report commit.

- [ ] **Step 1: Add concise user documentation**

Document the CubeMX/CubeCLT distinction, read-only command, Windows/Python 3.12 support, missing-CubeMX remediation, and that VS07-A cannot generate or mutate a project.

- [ ] **Step 2: Run the complete VS07-A slice verification**

Run from the clean implementation worktree with the candidate package imported from that worktree:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q
```

Expected: exit 0 with no new skip/xfail. This is a slice check, not a full release/coverage/package/browser/hardware matrix.

- [ ] **Step 3: Run real read-only environment observations**

Run doctor and one create-plan against a disposable workspace. Before CubeMX installation, require CubeCLT 1.22.0 facts plus `CUBEMX_MISSING`; after user-authorized CubeMX installation, require CubeMX 6.18 facts and a blocker-free plan. Snapshot the disposable workspace before/after and require identical bytes and names.

- [ ] **Step 4: Inspect the complete implementation diff**

The Luna implementer records, but does not approve:

```powershell
git diff --check d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58..HEAD
git diff --stat d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58..HEAD
git status --short
```

Expected: only VS07-A product/tests/docs/report paths plus inherited governance commits; no package version, hardware backend, release controller or remote automation change.

- [ ] **Step 5: Write the bounded implementation report**

Record product accepted base, specification/plan source, implementer, code head before report commit, exact test commands/exits, real environment observations, blockers classified by domain and tracked/untracked/committed/pushed state. Do not put the report's own final SHA or moving commit counts inside the report.

- [ ] **Step 6: Commit docs and report**

```powershell
git add -- README.md README_zh-CN.md docs/codex/returns/STM32TK-0701-CREATION-PLAN/implementation-report.md
git commit -m "docs(project): record VS07-A creation planning"
```

## Independent Sol review

The primary reviewer creates a clean review worktree at the returned final local head, confirms the imported package path, reviews the complete accepted-base-to-head diff, runs the exact Task 4 slice command and the two real read-only observations, then issues one `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` verdict. No full release matrix, push, PR, merge, tag or hardware action is part of this review.
