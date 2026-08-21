# STM32 Toolkit 0600 VS-03 Task 2 Explicit Mode Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one diagnostic session durably bind its failed TestRun as Host or Target so missing or corrupt authority is classified without workspace or root guessing.

**Architecture:** `diagnostic_start` receives an explicit closed `failed_run_mode`, defaulting to Host for byte compatibility. A Target binding is stored in `session.created`, reduced into `DiagnosticSession`, and carried across every later event; the common workflow loader routes errors exclusively from that durable value and then independently validates the loaded Evidence. Existing Host events, session dictionaries, calls, and result bytes remain unchanged.

**Tech Stack:** CPython 3.12 only, frozen dataclasses, closed canonical diagnostic events, `DiagnosticStore`, `EvidenceStore`, `TestRunRepository`, pytest.

## Global Constraints

- Accepted product base for complete-diff review: `a854d839ff6dedf3b4ad13d9b41d72e6b00d6777`.
- Correction worktree start: `1509aa1e256a9f1e272537494fd27e379c8e9797`; commits `8ec120bc...` and `0ac69cc1...` remain review candidates, not accepted product bases.
- Approved design authority: `docs/superpowers/specs/2026-08-21-stm32-toolkit-0600-vs03-target-replay-monitor-verification-design.md` at `1509aa1e...`.
- One existing `gpt-5.6-luna` implementer at reasoning effort `max` owns all product and implementation-test edits in this plan; GPT-5.6-sol independently reviews `a854d839...` through the final code head.
- No push, PR mutation, merge, close, remote branch deletion, hardware access, Python 3.10 work, Task 3 operation, Monitor change, CLI change, or MCP change is authorized.
- Preserve the exact legacy Host `session.created` event, `DiagnosticSession.to_dict()`, default call signature behavior, and `OperationResult` bytes.
- A Target caller must explicitly pass `failed_run_mode="target"`; no code may infer mode from root metadata, target-device spelling, or workspace equality.
- One operation may append at most one DiagnosticStore event, and every validation failure must leave diagnostic events and Evidence roots byte-identical.

---

### Task 1: Bind failed-run mode from start through every diagnostic reload

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_model.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_events.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Interfaces:**

- Consumes: existing `DiagnosticEvent`, `DiagnosticSession`, `reduce_event`, `TestRunRepository.load`, `diagnostic_start`, `diagnostic_begin`, and `diagnostic_show`.
- Produces:

```python
diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    failed_test_run_id: str,
    failed_run_mode: Literal["host", "target"] = "host",
    actor: str = "user",
) -> OperationResult[object]
```

- Produces `DiagnosticSession.failed_run_mode: Literal["host", "target"]`, with `host` as the decode default and with the field serialized only when its value is `target`.

- [ ] **Step 1: Freeze legacy Host bytes and Target session round-trip in model tests.** Add focused tests that construct a legacy Host `DiagnosticSession` without the new argument and assert its existing dictionary exactly omits `failed_run_mode`. Construct the same session with `failed_run_mode="target"`, assert the top-level dictionary contains exactly that additional field, and assert `DiagnosticSession.from_value(session.to_dict()) == session`.

```python
host = DiagnosticSession(...existing arguments...)
host_wire = host.to_dict()
assert "failed_run_mode" not in host_wire
assert DiagnosticSession.from_value(host_wire) == host

target = replace(host, failed_run_mode="target")
assert target.to_dict() == {**host_wire, "failed_run_mode": "target"}
assert DiagnosticSession.from_value(target.to_dict()) == target
```

Also assert explicit serialized `failed_run_mode="host"`, an unknown value, and a non-string value are rejected with `DIAGNOSTIC_INVALID_EVENT`; the Host value is represented only by absence so its accepted bytes cannot fork.

- [ ] **Step 2: Freeze event compatibility and durable reduction.** In `test_diagnostic_events.py`, preserve the existing exact Host `session.created` event digest and reduced Host session dictionary. Add a Target `session.created` event whose request is exactly `{failed_test_run_id, failed_run_mode: "target"}`; reduce it and assert the session mode is Target. Append an existing `investigation.started` event and assert the mode remains Target after reduction. Reject explicit Host, unknown, missing-value, and extra-field Target request shapes.

```python
target_created = create_event(
    ...,
    event_type="session.created",
    payload={
        "request": {
            "failed_test_run_id": "vs03-failed-before",
            "failed_run_mode": "target",
        },
        "result": {"failed_evidence_id": evidence_id, "identity": identity.to_dict()},
    },
)
target_session = reduce_event(None, target_created)
assert target_session.failed_run_mode == "target"
assert target_session.to_dict()["failed_run_mode"] == "target"
```

- [ ] **Step 3: Run the model/event RED tests.** Use a new basetemp and confirm the new tests fail because `DiagnosticSession` and `session.created` do not yet carry the mode.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-task2-mode-red `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py `
  -k "failed_run_mode or target_session_created"
```

- [ ] **Step 4: Add the minimal durable session field.** Add the defaulted field after existing defaulted session fields so old constructors remain valid:

```python
failed_run_mode: Literal["host", "target"] = "host"
```

Validate it in `__post_init__`. In `from_value`, accept only the existing legacy/extended key sets or those exact sets plus `failed_run_mode`; when present, require the value to be exactly `target`, otherwise decode the absent value as Host. In `to_dict`, add `failed_run_mode` only for Target. Update `_advance` to carry `session.failed_run_mode` unchanged.

For `session.created`, accept exactly these request shapes and no others:

```python
{"failed_test_run_id": run_id}
{"failed_test_run_id": run_id, "failed_run_mode": "target"}
```

The reducer uses `request.get("failed_run_mode", "host")`. Do not add the Host default to a legacy event or its digest.

- [ ] **Step 5: Run the complete model/event regression.** Both files must pass, not only the new selected tests.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-task2-mode-model-green `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py
```

- [ ] **Step 6: Freeze public workflow routing with real authority failures.** Update every Target call in `test_fix_verification_workflows.py` to pass `failed_run_mode="target"`. Add the following public-path regressions and snapshot DiagnosticStore events plus Evidence roots before the operation under test:

1. Delete the actual published Target `test-run` root before `diagnostic_start(..., failed_run_mode="target")`; expect `EVIDENCE_INTEGRITY_FAILURE` and zero DiagnosticStore mutation.
2. Make the Target repository raise a non-`FileNotFoundError` `OSError` at start; expect `ENVIRONMENT_FAILURE` without needing a readable root hint.
3. Create a legal origin/import alias Target session, delete its actual `test-run` root, then call a fresh `diagnostic_show`; expect `EVIDENCE_INTEGRITY_FAILURE` and zero mutation, proving the durable session mode is used.
4. Make the default Host repository raise `EvidenceValidationError(EVIDENCE_CORRUPT, "corrupt")`; assert `ok is False`, code `DIAGNOSTIC_EVIDENCE_MISSING`, message `required TestRun evidence is absent or damaged`, and empty details, matching the existing VS-02 tests.
5. Pass an invalid mode; pass Target mode for a Host record; and pass default Host mode for a Target record. Assert respectively `DIAGNOSTIC_INVALID_EVENT`, `EVIDENCE_INTEGRITY_FAILURE`, and the existing `DIAGNOSTIC_INVALID_EVENT`, all with zero mutation.
6. Retain the foreign logical-project, physical flag, transport, origin/import metadata, and legal alias success tests from review round 1.

The real-root deletion must resolve only the isolated test's exact `roots/test-run/*.json` file and call `Path.unlink()` inside `tmp_path`; do not monkeypatch a root hint and do not delete outside that test workspace.

```python
target_roots = tuple(
    (workspace.workspace_root / "evidence" / "roots" / "test-run").glob("*.json")
)
assert len(target_roots) == 1
target_roots[0].unlink()
result = diagnostic_start(
    fresh_context,
    operation_id="diagnostic.start.target-missing",
    failed_test_run_id="vs03-failed-before",
    failed_run_mode="target",
)
assert result.ok is False
assert result.code == "EVIDENCE_INTEGRITY_FAILURE"
```

- [ ] **Step 7: Run workflow RED.** Confirm the new tests fail because the public signature lacks the explicit mode and bound reload still guesses from workspace identity.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-task2-mode-workflow-red `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py
```

- [ ] **Step 8: Replace every hint with explicit routing.** Remove `get_root`, `_target_run_root_hint`, optional `target_hint`, and every workspace-equality mode inference. Add:

```python
from typing import Literal, cast

def _validate_failed_run_mode(value: object) -> Literal["host", "target"]:
    if not isinstance(value, str) or value not in {"host", "target"}:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return cast(Literal["host", "target"], value)
```

Pass the validated mode into `_load_authoritative_run`. The loader selects `target_hint = failed_run_mode == "target"` before repository access. Its Target path validates Target/replay/failed/non-physical authority and current logical project; its default Host path remains the accepted Host implementation. A declared Target that loads Host maps to `EVIDENCE_INTEGRITY_FAILURE`; default Host that loads Target retains `DIAGNOSTIC_INVALID_EVENT`.

For Target `diagnostic_start`, add `failed_run_mode="target"` to the `session.created` request; omit it for Host. `_load_bound_session` and `_load_bound_failed_run` pass `session.failed_run_mode` and never inspect workspace equality to choose semantics.

- [ ] **Step 9: Run GREEN and the proportionate affected regression.** Run only the model, events, Task 2 workflow, existing diagnostic workflow, and Target replay files.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-task2-mode-final `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

Expected: exit `0`. Do not add CLI, MCP, packaging, platform, hardware, coverage, or full-repository gates.

- [ ] **Step 10: Self-review, report, and commit.** Confirm no mode inference remains and only the six authorized files changed.

```powershell
rg -n "_target_run_root_hint|target_hint|workspace_id !=|workspace_id ==" `
  tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py
git diff --check
git diff --stat 1509aa1e256a9f1e272537494fd27e379c8e9797
```

The first command must find no mode-routing implementation. Update the uncommitted SDD report with RED, GREEN, exact test count, and the code head before the report. Commit only the six authorized product/test files:

```powershell
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py `
  tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py `
  tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py
git commit -m "fix(diagnostics): bind failed run mode"
```

Return `STATUS`, full commit SHA, exact RED/GREEN results, changed-file list, and concerns. Do not push.

## Independent Review Gate

GPT-5.6-sol reviews the complete accepted product base `a854d839ff6dedf3b4ad13d9b41d72e6b00d6777` through the returned final code head, not only the correction commit. It independently reruns the five-file command from Step 9, verifies exact Host bytes and all Target failure probes, checks the uncommitted report, and issues `ACCEPTED` or `REVISION_REQUIRED`. Task 3 starts only after this gate is `ACCEPTED`.
