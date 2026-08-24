# STM32 Toolkit VS08-A Versioned Scenario Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two versioned, software-only acceptance scenario definitions and one bounded adapter that validates completed existing workflow chains, publishes immutable records in the existing EvidenceStore, and exposes describe/record/show through CLI and MCP.

**Architecture:** A focused `acceptance` package owns closed models and a thin workflow adapter. The adapter reloads Project, Test, and Diagnostic public records, derives all identities and verdicts, and publishes one existing-Evidence root; CLI/MCP only translate arguments. There is no scenario executor, scheduler, mutable checkpoint store, or second Evidence lifecycle.

**Tech Stack:** CPython `>=3.12,<3.13`, dataclasses, existing `OperationResult`, Project/Test/Diagnostic/Evidence APIs, argparse, FastMCP/Pydantic, pytest.

## Global Constraints

- Accepted base is exactly `8f7bcb5c860998bc8459c7b33690d9a297319a6c`.
- GPT-5.6-sol owns specification, plan, risk decisions, complete-diff review, and acceptance.
- This entire slice has exactly one GPT-5.6-luna implementation owner with reasoning effort `max`; internal steps do not create additional implementers, branches, reports, or gates.
- Python support remains exactly `>=3.12,<3.13`; do not edit package/bootstrap/runtime support metadata in this slice.
- The only scenarios are `legacy-keil-migration` version `1` with project origin `keil`, and `new-cubemx-project` version `1` with project origin `cubemx`.
- The only execution profile is `software-replay`; every completed record has `executionSource == "replay"`, `physicalTransportEvidence is false`, and `verdict == "SOFTWARE_PASSED"`.
- Reuse the existing Project model, Test public show workflow, Diagnostic public show/verification workflows, EvidenceStore, RootRecord, CLI, MCP, and OperationResult. Do not add a controller, scheduler, daemon, provider, Evidence store, Probe backend, release gate, CI, or remote runner.
- VS08-A does not implement resume, interruption checkpoints, per-step timeout, lease/target cleanup, source editing, flashing, or human authorization checkpoints; those are VS08-B after this slice is independently accepted.
- Replay/fixture results are software evidence and are never physical PASS.
- Do not install dependencies or tools and do not execute hardware, push, PR, merge, tag, release, close, or remote branch deletion.
- The tracked implementation report records accepted base and product/tests CodeHead before the report commit; it does not record its own final report commit SHA or moving commit totals.

---

### Task 1: Deliver the complete VS08-A vertical slice

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/workflows.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_model.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_cli.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_mcp.py`
- Create: `tools/stm32-toolkit/tests/test_vs08a_scenarios.py`
- Create: `docs/codex/returns/STM32TK-0801-VS08-A/implementation-report.md`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_gc.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `ProjectModel.load`/existing project loader; `TestingWorkflowContext` and `test_show`; `DiagnosticWorkflowContext`, `diagnostic_show`, and `diagnostic_show_verification`; `EvidenceStore`, `EvidenceEnvelope`, `RootRecord`, `put_root`, and `get_root`; existing `OperationResult`.
- Produces: `AcceptanceScenario`, `AcceptanceRecord`, `AcceptanceWorkflowContext`, `describe_acceptance_scenario`, `record_acceptance_scenario`, and `show_acceptance_scenario`; CLI `scenario describe|record|show`; MCP `stm32_acceptance_scenario_describe|record|show`; registered Evidence root type `acceptance-scenario`.

- [ ] **Step 1: Write strict model RED tests.** Add literal, hand-derived expectations. The production mutations these tests must catch are: swapping the scenario origin, accepting an unknown field/version, changing ordered stages, allowing physical evidence, accepting a noncanonical UUID/hash/timestamp, or calculating a digest over the digest field itself.

```python
def test_version_one_definitions_are_closed_digest_bound_and_software_only():
    legacy = acceptance_scenario("legacy-keil-migration", "1")
    cubemx = acceptance_scenario("new-cubemx-project", "1")
    assert legacy.to_dict() == {
        "schema": "stm32-acceptance-scenario/1",
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "projectOrigin": "keil",
        "executionProfile": "software-replay",
        "requiredStages": [
            "project-materialized", "firmware-built-before",
            "target-failure-replayed", "diagnosis-completed",
            "firmware-built-after", "target-fix-verified",
        ],
        "physicalTransportEvidence": False,
    }
    assert cubemx.project_origin == "cubemx"
    assert cubemx.scenario_digest == "5650cf942b41f7e6d281cdd836f5ff7320434557998906065c133830701402b3"


@pytest.mark.parametrize("mutation", [
    {"extra": True},
    {"scenarioVersion": "2"},
    {"physicalTransportEvidence": True},
])
def test_scenario_model_rejects_noncontract_input(mutation):
    payload = {
        "schema": "stm32-acceptance-scenario/1",
        "scenarioId": "legacy-keil-migration",
        "scenarioVersion": "1",
        "scenarioDigest": "e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        "projectOrigin": "keil",
        "executionProfile": "software-replay",
        "requiredStages": [
            "project-materialized", "firmware-built-before",
            "target-failure-replayed", "diagnosis-completed",
            "firmware-built-after", "target-fix-verified",
        ],
        "physicalTransportEvidence": False,
    }
    payload.update(mutation)
    with pytest.raises(AcceptanceValidationError):
        AcceptanceScenario.from_value(payload)
```

- [ ] **Step 2: Run the model RED test and confirm it fails because the package and definitions do not exist.**

Run from `tools/stm32-toolkit` with a fresh worktree-external `--basetemp`:

```powershell
$env:PYTHONPATH=(Resolve-Path '.\src').Path + ';' + (Resolve-Path '..\stm32-monitor\src').Path
py -3.12 -m pytest tests/test_acceptance_model.py -q --basetemp=C:\tmp\stm32tk-vs08a-red-model
```

Expected: collection/import failure naming `stm32_toolkit.acceptance`, not a fixture, permission, or dependency error.

- [ ] **Step 3: Implement the minimal closed models and fixed definitions.** Use frozen dataclasses and existing canonical JSON helpers. Keep model JSON names exactly as the specification; internal attributes may be snake_case. Compute `scenarioDigest` as SHA-256 over the canonical object without `scenarioDigest`. `AcceptanceRecord.from_value` must reject tuple JSON containers, unknown/missing fields, noncanonical identifiers, a stage list other than the definition's exact tuple, any source other than `replay`, any physical flag other than `false`, and any verdict other than `SOFTWARE_PASSED`.

```python
SCENARIO_SCHEMA = "stm32-acceptance-scenario/1"
RECORD_SCHEMA = "stm32-acceptance-record/1"
REQUIRED_STAGES = (
    "project-materialized",
    "firmware-built-before",
    "target-failure-replayed",
    "diagnosis-completed",
    "firmware-built-after",
    "target-fix-verified",
)

_DEFINITIONS = {
    ("legacy-keil-migration", "1"): ("keil", REQUIRED_STAGES),
    ("new-cubemx-project", "1"): ("cubemx", REQUIRED_STAGES),
}
```

- [ ] **Step 4: Run model GREEN.** Use a new absent basetemp path. Expected: all model tests pass with pristine output.

- [ ] **Step 5: Write workflow RED tests against real existing stores and readers.** Build test authorities with real `EvidenceStore`, `TestRunPublisher`/replay workflow, and `DiagnosticStore`/diagnostic workflows. Mock only external/native execution if needed; do not mock `test_show`, `diagnostic_show`, `diagnostic_show_verification`, Evidence publication, root publication, or model validation. The production mutations these tests catch are: trusting caller-supplied identity, accepting physical evidence, reversing failed/fixed states, skipping verification binding, crossing workspaces, replacing an existing record, returning an unverified/corrupt root, or creating state during describe failure.

```python
@pytest.mark.parametrize(
    ("scenario_id", "origin"),
    [("legacy-keil-migration", "keil"),
     ("new-cubemx-project", "cubemx")],
)
def test_completed_software_chain_is_published_and_queryable_after_reload(
    scenario_authority, scenario_id, origin
):
    authority = scenario_authority(origin=origin)
    result = record_acceptance_scenario(
        authority.context,
        record_id=authority.record_id,
        scenario_id=scenario_id,
        scenario_version="1",
        failed_before_test_run_id=authority.failed_run_id,
        fixed_after_test_run_id=authority.fixed_run_id,
        diagnostic_session_id=authority.session_id,
    )
    assert result.ok is True
    assert result.data["record"]["executionSource"] == "replay"
    assert result.data["record"]["physicalTransportEvidence"] is False
    assert result.data["record"]["verdict"] == "SOFTWARE_PASSED"
    fresh = AcceptanceWorkflowContext(
        authority.project_root, authority.data_root, authority.runtime_session_id
    )
    shown = show_acceptance_scenario(fresh, record_id=authority.record_id)
    assert shown.ok is True
    assert shown.data == {"authoritative": True, "record": result.data["record"]}


def test_physical_or_cross_workspace_reference_publishes_no_acceptance_root(
    scenario_authority,
):
    authority = scenario_authority(origin="keil", physical_failed_run=True)
    before = authority.acceptance_root_snapshot()
    result = authority.record(scenario_id="legacy-keil-migration")
    assert result.ok is False
    assert result.code == "ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN"
    assert authority.acceptance_root_snapshot() == before == ()
```

Cover exact codes for unknown ID/version, malformed UUID, wrong origin,
missing/corrupt roots, unresolved session, no passing verification, wrong
failed/fixed state, verification bound to different run IDs, identity mismatch,
idempotent identical retry, conflicting same record ID, and show under a
different bound workspace.

- [ ] **Step 6: Run workflow RED and confirm the new functions/root type are missing.**

```powershell
py -3.12 -m pytest tests/test_acceptance_workflows.py tests/test_evidence_gc.py::test_registered_typed_roots_are_closed_and_shared_objects_follow_reachability -q --basetemp=C:\tmp\stm32tk-vs08a-red-workflow
```

Expected: failures caused by absent acceptance workflow/root behavior. Preserve the exact relevant RED output in the implementation report.

- [ ] **Step 7: Implement the bounded workflow and existing-Evidence publication.** `AcceptanceWorkflowContext` contains only project root, data root, and session ID. `describe_acceptance_scenario` must be state-free. `record_acceptance_scenario` follows the specification's eight-step validation/publication order, derives all record values, and maps validation/integrity errors to the closed acceptance codes without raw paths or exception text. Register exactly `acceptance-scenario` in `REGISTERED_ROOT_TYPES`; update the exact registered-root test count and set. Publish no record until all references validate. Identical retry returns the existing canonical record; conflict never replaces it. `show_acceptance_scenario` verifies root, envelope, metadata, identities, and current workspace binding before returning.

Do not add a new directory below the workspace other than the existing EvidenceStore's normal `manifests/` and `roots/acceptance-scenario/` paths. Do not create an acceptance database, JSON ledger, mutable index, cache, lock, thread, subprocess, timer, or background task.

- [ ] **Step 8: Run workflow GREEN and focused Evidence GC coverage.** Expected: all new workflow tests and the updated registered-root reachability test pass with no warning/error output.

- [ ] **Step 9: Write CLI and MCP RED contract tests.** Tests must invoke the real parser/server boundary and assert returned JSON behavior, not grep source. Require exact argument/property sets, no project/data/command/environment override, strict UUID/string types, client-root binding, helper argument translation, and parity of describe/record/show results.

```python
def test_scenario_record_mcp_schema_is_closed_and_project_bound(tmp_path):
    schema = schemas(tmp_path)["stm32_acceptance_scenario_record"]
    assert set(schema["properties"]) == {
        "recordId", "scenarioId", "scenarioVersion",
        "failedBeforeTestRunId", "fixedAfterTestRunId",
        "diagnosticSessionId",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert not ({"projectRoot", "dataRoot", "command", "environment"}
                & set(schema["properties"]))


def test_cli_record_dispatches_exact_values_once(monkeypatch, capsys):
    seen = []
    record_id = "00000000-0000-4000-8000-000000000001"
    failed_id = "00000000-0000-4000-8000-000000000002"
    fixed_id = "00000000-0000-4000-8000-000000000003"
    session_id = "00000000-0000-4000-8000-000000000004"
    ok = OperationResult.success(
        "acceptance.scenario.record", {"record": {"recordId": record_id}}
    )
    monkeypatch.setattr(cli, "record_acceptance_scenario",
                        lambda context, **kwargs: seen.append((context, kwargs)) or ok)
    assert cli.main([
        "scenario", "record", "--project", "C:/work/project",
        "--data-root", "C:/work/data", "--session-id", "session-a",
        "--record-id", record_id,
        "--scenario-id", "legacy-keil-migration",
        "--scenario-version", "1",
        "--failed-before-test-run-id", failed_id,
        "--fixed-after-test-run-id", fixed_id,
        "--diagnostic-session-id", session_id,
    ]) == 0
    assert seen[0][1] == {
        "record_id": record_id,
        "scenario_id": "legacy-keil-migration",
        "scenario_version": "1",
        "failed_before_test_run_id": failed_id,
        "fixed_after_test_run_id": fixed_id,
        "diagnostic_session_id": session_id,
    }
    assert json.loads(capsys.readouterr().out)["operation"] == "acceptance.scenario.record"
```

- [ ] **Step 10: Run CLI/MCP RED.**

```powershell
py -3.12 -m pytest tests/test_acceptance_cli.py tests/test_acceptance_mcp.py tests/test_mcp_server.py -q --basetemp=C:\tmp\stm32tk-vs08a-red-adapters
```

Expected: new command/tool assertions fail because adapters are absent.

- [ ] **Step 11: Implement thin CLI/MCP projections.** Add one `scenario` CLI group with `describe`, `record`, and `show`. Add exactly three project-bound MCP tools with the names and camelCase inputs from the specification. Reuse client-root verification. Pydantic types must reject coercion and close schemas. Adapters perform no scenario validation beyond input syntax and call the shared workflow exactly once. Update the current authoritative MCP inventory test; do not edit the retained historical `test_mcp_migration_build.py` fifteen-tool inventory test.

- [ ] **Step 12: Run CLI/MCP GREEN and current inventory tests.** Expected: new adapter tests and `tests/test_mcp_server.py` pass with pristine output.

- [ ] **Step 13: Write the two-scenario vertical RED integration test.** Parameterize both project origins but execute real existing replay publication and diagnostic completion components. The test must create distinct project/data roots, complete failed-before -> diagnosis -> source declaration -> fixed-after -> passing verification, finalize the correct version-1 acceptance record, discard all in-memory authorities, reconstruct fresh contexts, and query the immutable record. Assert no physical success vocabulary or `true` physical flag appears anywhere in the returned record. Add a separate mismatch case proving a Keil definition cannot finalize a CubeMX project.

- [ ] **Step 14: Run vertical RED, then make only the minimal integration corrections needed for GREEN.** Do not add orchestration behavior to make the test convenient. If the adapter cannot consume the real existing public results, correct the adapter/model seam, not the Test, Diagnostic, Evidence, or Monitor lifecycle.

```powershell
py -3.12 -m pytest tests/test_vs08a_scenarios.py -q --basetemp=C:\tmp\stm32tk-vs08a-vertical
```

Expected GREEN: both software scenario parameters and the negative origin case pass; fixtures/replay remain explicitly non-physical.

- [ ] **Step 15: Run the proportionate affected slice suite once.** Use a new absent basetemp path and local source paths; do not install anything.

```powershell
$env:PYTHONPATH=(Resolve-Path '.\src').Path + ';' + (Resolve-Path '..\stm32-monitor\src').Path
py -3.12 -m pytest \
  tests/test_acceptance_model.py tests/test_acceptance_workflows.py \
  tests/test_acceptance_cli.py tests/test_acceptance_mcp.py \
  tests/test_vs08a_scenarios.py tests/test_evidence_gc.py \
  tests/test_vs03_end_to_end.py tests/test_creation_workflows.py \
  tests/test_workflows.py tests/test_mcp_server.py \
  tests/test_testing_mcp.py tests/test_diagnostic_mcp.py \
  tests/test_testing_cli.py tests/test_diagnostic_cli.py \
  -q --basetemp=C:\tmp\stm32tk-vs08a-green
py -3.12 -m compileall -q src tests
git diff --check 8f7bcb5c860998bc8459c7b33690d9a297319a6c..HEAD
```

PowerShell does not use backslash line continuation: execute the pytest command as one line or replace each displayed `\` with PowerShell backtick continuation. Required result: zero failures/errors; any existing platform skip is named and is not physical PASS. Do not run the full release, install, browser, performance, or hardware matrices.

- [ ] **Step 16: Self-review the complete accepted-base diff.** Check every specification acceptance criterion, exact public field and error code, no duplicate copied Evidence payloads, no physical-success path, no mutable acceptance store/index, no background execution, and no unrelated refactor. Mentally mutate origin selection, physical flag, failed/fixed state, verification binding, workspace comparison, root conflict, and show-time integrity; confirm a named test would fail for each mutation.

- [ ] **Step 17: Commit product and tests, then write and commit the tracked report.** First commit all product/tests changes (including this plan/spec only if they are not already committed) with a subject such as `feat(acceptance): add versioned software scenarios`. Record that full product/tests CodeHead in the report. The report must include accepted base, specification/plan paths, single implementer identity, branch/worktree, TDD RED/GREEN commands and outputs, exact test results, complete file list, non-physical classification, blockers by PRODUCT/INFRASTRUCTURE/ENVIRONMENT/PLATFORM/HARDWARE/REPORT, local/unpushed/no-upstream state, and confirmation that no prohibited action occurred. Commit the report separately with `docs(acceptance): record VS08-A implementation` and do not write the report commit's own SHA inside the report.

- [ ] **Step 18: Return the short implementation contract.** Return only status, created commits, one-line test summary, concerns, and the SDD report-file path. Leave the branch clean, local, unpushed, and without upstream.
