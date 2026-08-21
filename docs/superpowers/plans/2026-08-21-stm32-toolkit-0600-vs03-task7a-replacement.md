# STM32 Toolkit VS-03 Task 7A Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this
> plan task-by-task. One user-authorized `gpt-5.6-luna` agent at reasoning effort `max` owns all
> product and implementation-test edits; GPT-5.6-sol independently reviews the complete diff.

**Goal:** Produce one durable replay verification checkpoint that starts from an authoritative
failed Target replay, crosses the existing diagnostic lifecycle, binds a source change and plan,
attaches a genuine Monitor marker, and reloads as `VERIFYING`.

**Architecture:** Toolkit remains independent of the Monitor package and validates Monitor products
as closed canonical JSON Evidence. Host sessions retain local-workspace identity; Target replay
sessions retain origin identity and prove the current import workspace by reloading their bound
TestRun root on every operation. One DiagnosticStore append occurs only after all inputs validate.

**Tech Stack:** CPython 3.12, frozen dataclasses, canonical JSON/SHA-256, EvidenceStore,
TestRunRepository, DiagnosticStore, OperationResult, pytest.

## Global Constraints

- Initial accepted product base: `9ff0f727f5997cf0ffd92c7272ffeb4e1153fccb`.
- Task 2 accepted product head: `76e68b1fa7a747bbda502cca496c9c996345155d`.
- The Task 3 implementation dispatch base is the clean plan-amendment commit recorded with its full
  SHA in the generated SDD brief and ledger before Luna starts.
- Approved design includes explicit durable `failed_run_mode`; Target diagnostic start calls pass
  `failed_run_mode="target"` and later operations consume the stored session value.
- Replacement branch/worktree: `codex/STM32TK-0600-VS03-VERIFY-REWRITE2` at
  `C:\tmp\stm32tk-vs03-task7-rewrite2`.
- Replacement implementer: `/root/vs03_task7a_replacement`, user-authorized
  `gpt-5.6-luna` at reasoning effort `max` for Tasks 1-3.
- Previous implementer owns only the preserved rejected heads `efc26e81294977a64a710038a7a62b76e2fc6f4e`
  and `d3413df297bbb61344cdbe72931e078a6a2b7ca8`; neither is an implementation base.
- No push, PR mutation, merge, close, remote branch operation, physical hardware action, Python
  3.10 work, packaging, release matrix, CI or new dispatch automation.
- Task 3 may modify only `diagnostic_workflows.py` and
  `test_fix_verification_workflows.py`. Tasks 1-2 and the explicit-mode correction are accepted
  dependencies and must not be rewritten. If another product file is required, stop and return
  the exact interface blocker.

---

### Task 1: Freeze paired analysis/evidence identity

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_model.py`

**Interfaces:**

- Consumes: `VerificationPlan.new/from_value` and `FixVerification.new/from_value`.
- Produces: both parallel tuples sorted by analysis ID while preserving each original pair.

- [ ] **Step 1: Write the failing pair tests.** Add production-object tests, not private-helper
  tests. Construct two pairs in reverse analysis-ID order:

```python
analysis_ids = ("f" * 64, "e" * 64)
evidence_ids = ("1" * 64, "2" * 64)
plan = VerificationPlan.new(
    verification_plan_id=PLAN_ID,
    diagnostic_session_id=SESSION_ID,
    failed_before_run_id="failed-before",
    failed_before_evidence_id="3" * 64,
    source_change_declaration_id=declaration.declaration_id,
    fixed_after_run_id="fixed-after",
    fixed_after_evidence_id="4" * 64,
    required_analysis_ids=analysis_ids,
    required_analysis_evidence_ids=evidence_ids,
    required_monitor_quality="VALID",
    expected_changed=True,
)
assert tuple(zip(plan.required_analysis_ids, plan.required_analysis_evidence_ids)) == (
    ("e" * 64, "2" * 64),
    ("f" * 64, "1" * 64),
)
assert VerificationPlan.from_value(plan.to_dict()) == plan
```

  Repeat the pairing assertion through `FixVerification.new()` and `from_value()`.

- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-7a-pairs-red `
  tools/stm32-toolkit/tests/test_fix_verification_model.py -k paired
```

  Expected: the accepted implementation rejects the unsorted IDs or associates an Evidence ID with
  the wrong analysis.

- [ ] **Step 3: Correct pair normalization.** Validate both input tuples without sorting, reject
  duplicate/invalid/boundary values, zip them, sort pairs by `analysis_id`, then unzip. Apply the
  identical rule to tuple and wire paths.

- [ ] **Step 4: Run GREEN.** Repeat Step 2; expected all selected tests pass.

### Task 2: Establish Target replay session authority

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Interfaces:**

- Consumes: `target_replay_run`, `TestRunRepository.load`, existing `diagnostic_start`,
  `diagnostic_begin`, `diagnostic_add_hypothesis`, and `diagnostic_show`.
- Produces: existing Host behavior plus Target replay sessions whose origin/import identities remain
  distinct and revalidated on every operation.

- [ ] **Step 1: Write the real replay authority test.** Use
  `tests/fixtures/vs03/target/failed-before.json` and `.hex`, call `target_replay_run`, then call
  `diagnostic_start`, `diagnostic_begin`, `diagnostic_add_hypothesis`, discard the context/store
  objects, and call `diagnostic_show` with fresh objects. Assert:

```python
assert replay.ok is True
assert started.ok is True and started.data["session"]["state"] == "OPEN"
assert begun.ok is True and begun.data["session"]["state"] == "INVESTIGATING"
assert shown.ok is True
assert shown.data["session"]["identity"]["workspace_id"] == origin_workspace_id
assert origin_workspace_id != WorkspacePaths.from_roots(project, data).workspace_id
```

  Snapshot DiagnosticStore events/roots before each negative. Parameterize a foreign manifest
  identity, physical flag, non-replay transport, wrong origin metadata and wrong current import
  metadata; each returns a stable failure and leaves the snapshot identical.

- [ ] **Step 2: Run RED.** Run the new test against `baf1d0fd...`; expected failure is
  `DIAGNOSTIC_IDENTITY_MISMATCH` from the Host-only bound-session check after start.

- [ ] **Step 3: Implement the common authority loader.** Reload `session.failed_test_run_id` through
  `TestRunRepository`. For Host, preserve the exact existing local identity rule. For Target, require
  manifest mode/state/transport `target/failed/replay`, exact manifest/session EvidenceIdentity,
  root metadata `mode=target`, `state=failed`, `execution_source=replay`,
  `physical_transport_evidence=false`, `origin_workspace_id=session.identity.workspace_id`, and
  `import_workspace_id=current WorkspacePaths.workspace_id`. Map identity contradiction to
  `INCOMPATIBLE_IDENTITY`, provider I/O to `ENVIRONMENT_FAILURE`, and corrupt/absent immutable
  Evidence to `EVIDENCE_INTEGRITY_FAILURE` without altering existing VS-02 result bytes.

- [ ] **Step 4: Run GREEN and Host regression.**

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-7a-authority `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

### Task 3: Prepare and reload the genuine verification checkpoint

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Interfaces:**

- Produces exactly `diagnostic_declare_source_change`, `diagnostic_add_verification_plan`,
  `diagnostic_start_verification`, and `diagnostic_attach_marker` with the signatures and operation
  names in design section 3.7.

- [ ] **Step 1: Write one complete failing public-path test.** After Task 2, create a real diff
  ArtifactRef/envelope and `SourceChangeDeclaration`, publish closed analysis and marker Evidence,
  start the Target diagnostic with `failed_run_mode="target"`, then call the four new operations.
  Construct producer IDs by these exact equations:

```python
analysis_id = sha256(canonical_json_bytes({k: v for k, v in analysis.items()
                                           if k != "analysis_id"})).hexdigest()
analysis["analysis_id"] = analysis_id
marker_id = sha256(canonical_json_bytes({k: v for k, v in marker.items()
                                         if k != "marker_id"})).hexdigest()
marker["marker_id"] = marker_id
```

  Ingest the complete canonical bytes and use that separate artifact SHA. Marker payload schema is
  `stm32-diagnostic-marker/1`; DiagnosticMarkerRef schema is
  `stm32-diagnostic-marker-ref/1`. After attach, discard objects and reload with
  `diagnostic_show`; assert state `VERIFYING`, exact declaration/plan/marker ref, ordered parents,
  unchanged input Evidence tree, and exact retry idempotency.

- [ ] **Step 2: Add fail-closed negatives.** Mutate one dimension at a time before calling attach:
  payload/ref schema conflation, extra payload field, wrong unsigned marker ID, wrong marker
  envelope ID, wrong analysis parent, wrong operation/kind/media, corrupt/noncanonical artifact,
  absent analysis root, wrong analysis unsigned ID, foreign analysis identity, or declaration/run
  lineage mismatch. Assert the named public failure and byte-identical session revision/events/roots.

- [ ] **Step 3: Run RED.** At dispatch base
  `76e68b1fa7a747bbda502cca496c9c996345155d`, expected failures are the missing four public
  operations. Do not run or copy either rejected branch.

- [ ] **Step 4: Implement preflight and one-append workflows.** Toolkit must not import Monitor.
  Reload root, envelope and sole artifact for analysis/marker; require exact closed field sets,
  canonical bytes, full artifact digest, unsigned producer-ID equations, envelope identity,
  metadata and parents. Compare marker payload/ref only across marker ID and the eight shared fields;
  never compare their unequal schema values or ref-only `marker_evidence_id`. Complete all checks
  before the one DiagnosticStore append.

- [ ] **Step 5: Run the complete slice suite.**

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest -q --basetemp C:/tmp/pytest-vs03-7a-final `
  tools/stm32-toolkit/tests/test_fix_verification_model.py `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_target_replay_workflows.py
git diff --check 76e68b1fa7a747bbda502cca496c9c996345155d..HEAD
```

  Expected: all tests pass. Use the full implementation dispatch-base SHA from the SDD brief to
  confirm only the two Task 3 authorized files differ; no `.superpowers`, model, event, adapter,
  Monitor, release or remote change exists.

- [ ] **Step 6: Commit once.**

```powershell
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py
git commit -m "feat(diagnostics): prepare replay fix verification"
```

## Sol Acceptance

Sol reviews `9ff0f727f5997cf0ffd92c7272ffeb4e1153fccb..final-head` in a new detached clean
worktree, runs the complete Task 7A suite plus an independent public replay probe, and returns
`ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. The implementer cannot approve its own diff.
Task 7B, adapters, VS-04, release matrices, hardware and remote operations remain out of scope.
