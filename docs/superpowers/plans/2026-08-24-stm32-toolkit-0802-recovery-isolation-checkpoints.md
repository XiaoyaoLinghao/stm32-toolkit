# STM32 Toolkit VS08-B Recovery, Isolation, and Human Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded immutable attempt/checkpoint adapter that resumes the two accepted VS08-A software scenarios, enforces stage deadlines and one explicit source-change authorization, isolates workspaces and concurrent writers, and binds completion to the existing acceptance record.

**Architecture:** Extend the focused `acceptance` package with a closed recovery model and thin workflow adapter. Each complete snapshot is an immutable `acceptance-attempt` Evidence root keyed by attempt and bounded revision; show/resume scan and verify at most eight roots. Existing Project/Build/Test/Diagnostic/Acceptance readers remain authoritative. CLI/MCP translate arguments only. No stage execution, mutable head, scheduler, lease owner, or Probe integration is added.

**Tech Stack:** CPython `>=3.12,<3.13`, dataclasses, existing `OperationResult`, Project/Build/Test/Diagnostic/Acceptance/Evidence APIs, argparse, FastMCP/Pydantic, pytest.

## Global constraints

- Accepted base is exactly `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`.
- GPT-5.6-sol owns this specification/plan, risk decisions, complete-diff review, and acceptance.
- This slice has exactly one GPT-5.6-luna implementation owner at reasoning effort `max`. The implementer must not delegate or accept its own diff.
- Preserve VS08-A scenario digests exactly: legacy `e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb`; CubeMX `5650cf942b41f7e6d281cdd836f5ff7320434557998906065c133830701402b3`.
- Preserve the frozen recovery policy digest exactly: `af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c`.
- Reuse the existing EvidenceStore and mutation lock. Add exactly one registered root type, `acceptance-attempt`; do not add a mutable head/index/database/lock.
- Reuse public Project, Build, Test, Diagnostic, and VS08-A readers. Do not execute their actions or trust caller-supplied identity/digests/verdicts.
- Do not add a controller, runner, scheduler, daemon, provider, Evidence store, Probe backend, transport, CI, or remote runner.
- Python support remains `>=3.12,<3.13`. Do not install dependencies or tools.
- Replay/fixtures are software-only and never physical PASS. Do not execute hardware, flash, push, PR, merge, tag, release, close, or remote branch deletion.
- The implementation report records the product/tests CodeHead before the report commit and never its own commit SHA.

---

### Task 1: Deliver the complete VS08-B vertical slice

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_recovery_model.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_recovery_cli.py`
- Create: `tools/stm32-toolkit/tests/test_acceptance_recovery_mcp.py`
- Create: `tools/stm32-toolkit/tests/test_vs08b_scenarios.py`
- Create: `docs/codex/returns/STM32TK-0802-VS08-B/implementation-report.md`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_gc.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_server.py`

**Interfaces:**
- Consume: accepted `acceptance_scenario` and `show_acceptance_scenario`; current project loader; `build_project_context`; `test_show`; `diagnostic_show`; existing EvidenceStore/RootRecord/mutation lock; existing `OperationResult`.
- Produce: `AcceptanceRecoveryPolicy`, `AcceptanceAttempt`, `AcceptanceRecoveryContext`, `begin_acceptance_attempt`, `checkpoint_acceptance_attempt`, `authorize_acceptance_source_change`, `show_acceptance_attempt`, `resume_acceptance_attempt`; five CLI commands and five closed project-bound MCP tools; root type `acceptance-attempt`.

- [ ] **Step 1: Write strict recovery model RED tests.** Use literal hand-derived policy JSON/digest and snapshot payloads. Tests must fail if code changes a timeout, VS08-A digest, stage order, physical flag, checkpoint digest domain, revision range/link, exact prefix/output-null invariant, timestamp ordering, authorization fields, or closed JSON boundary. Include tuple, boolean-as-integer, noncanonical UUID/hash/timestamp, unknown field, revision gap, authorization at the wrong revision, and `COMPLETED` before the final stage.

```python
def test_recovery_policy_is_frozen_software_only_and_flash_inapplicable():
    policy = acceptance_recovery_policy()
    assert policy.to_dict() == {
        "schema": "stm32-acceptance-recovery-policy/1",
        "attemptSchema": "stm32-acceptance-attempt/1",
        "stageTimeoutSeconds": {
            "project-materialized": 60,
            "firmware-built-before": 900,
            "target-failure-replayed": 300,
            "diagnosis-completed": 900,
            "firmware-built-after": 900,
            "target-fix-verified": 300,
        },
        "intrusiveActions": {
            "source-change": {
                "applicable": True, "authorization": "explicit-single-use",
                "afterStage": "diagnosis-completed", "beforeStage": "firmware-built-after",
            },
            "flash": {
                "applicable": False, "authorization": "existing-probe-action-digest",
                "reason": "software-replay",
            },
        },
        "physicalTransportEvidence": False,
    }
    assert policy.digest == "af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c"


@pytest.mark.parametrize("mutation", [
    {"revision": True}, {"revision": 8}, {"physicalTransportEvidence": True},
    {"status": "COMPLETED"}, {"extra": None},
])
def test_attempt_rejects_noncontract_mutations(valid_revision_zero, mutation):
    payload = dict(valid_revision_zero)
    payload.update(mutation)
    with pytest.raises(AcceptanceRecoveryValidationError):
        AcceptanceAttempt.from_value(payload)
```

- [ ] **Step 2: Run model RED before production code.**

```powershell
$env:PYTHONPATH=(Resolve-Path '.\src').Path + ';' + (Resolve-Path '..\stm32-monitor\src').Path
py -3.12 -m pytest tests/test_acceptance_recovery_model.py -q --basetemp=C:\tmp\stm32tk-vs08b-red-model
```

Expected: collection/import failure naming the absent recovery module or API, not a dependency/environment failure. Preserve exact RED output.

- [ ] **Step 3: Implement minimal closed models.** Use frozen dataclasses and existing canonical JSON validation patterns. `checkpointId` hashes the canonical snapshot without `checkpointId`. Export the fixed policy and digest. Model exactly revisions 0..7 and the fixed revision/stage mapping: 0 begun; 1..4 first four stages; 5 authorization; 6 after-build; 7 final verification. `stageOutputs` always has the exact fixed key set and nulls for unavailable facts. Reject derived-timeout state in storage; only `ACTIVE` and `COMPLETED` are stored.

- [ ] **Step 4: Run model GREEN with a new absent basetemp.** Expected: all model tests pass with pristine output.

- [ ] **Step 5: Write storage, recovery, concurrency, and timeout RED tests.** Use the real EvidenceStore/root primitives and fake only the server clock and existing public readers where the test is about the adapter algorithm. Include:
  - begin idempotency and same-ID/different-scenario conflict;
  - fresh-context show/resume at every prefix;
  - bounded contiguous revision scan, exact root ID/link verification, corrupt/missing/gapped root/envelope refusal;
  - crash between envelope and root followed by successful retry;
  - exact deadline equality accepted and one microsecond late refused with no new root;
  - identical concurrent retry converges and different concurrent transitions yield one winner plus revision conflict;
  - same `attemptId` in two workspace stores advances independently;
  - copied roots and cross-workspace/project references fail closed;
  - attempt storage creates no lease, endpoint, transport, process, or mutable head/index state.

```python
def test_interrupted_attempt_resumes_latest_verified_prefix(authority):
    begun = authority.begin()
    authority.checkpoint(begun, "project-materialized")
    latest = authority.checkpoint_revision(1, "firmware-built-before")
    fresh = authority.fresh_context()
    resumed = resume_acceptance_attempt(fresh, attempt_id=authority.attempt_id)
    assert resumed.ok is True
    assert resumed.data["attempt"] == latest
    assert resumed.data["nextStage"] == "target-failure-replayed"
    assert resumed.data["authorizationRequired"] is False
    assert resumed.data["timedOut"] is False


def test_two_workspaces_same_attempt_id_are_isolated(workspace_pair):
    left, right = workspace_pair(same_attempt_id=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda item: item.begin(), (left, right)))
    assert all(result.ok for result in results)
    assert results[0].data["attempt"]["workspaceId"] != results[1].data["attempt"]["workspaceId"]
    assert left.show().data["attempt"] == results[0].data["attempt"]
    assert right.show().data["attempt"] == results[1].data["attempt"]
```

- [ ] **Step 6: Run workflow RED.**

```powershell
py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py tests/test_evidence_gc.py::test_registered_typed_roots_are_closed_and_shared_objects_follow_reachability -q --basetemp=C:\tmp\stm32tk-vs08b-red-workflow
```

Expected: absent recovery functions/root registration cause the failures.

- [ ] **Step 7: Implement immutable publication, loading, show, and resume.** Add `acceptance-attempt` to the exact registered root set. Revision roots use `<uuid>.<eight digits>`. Scan only 0..7 and reject gaps/later roots. Use the existing Evidence mutation lock around reload/compare/publish. Validate all current workspace/project identities before returning authoritative data. Implement stable retry comparison over request-derived transition facts so a stored server timestamp does not break identical retry. Resume computes but never persists `timedOut`, `nextStage`, `authorizationRequired`, and `actionDigest`. Do not create a timer, thread, subprocess, lock, head file, index, cache, database, lease, endpoint, or transport file.

- [ ] **Step 8: Run workflow/GC GREEN.** Expected: recovery algorithm and updated exact root inventory tests pass without warnings.

- [ ] **Step 9: Write authoritative stage-transition RED tests.** Use real Project, `build_project_context`, Test/Evidence, DiagnosticStore/show, and VS08-A show/root readers; mock only native/external execution already outside this adapter. For both origins build a real software chain and assert:
  - project origin and canonical project digest are derived;
  - before build is fresh Debug and failed Target run is replay/nonphysical and binds it;
  - diagnosis is `INVESTIGATING`, binds the failed run, and has no source declaration at checkpoint;
  - after diagnosis, resume returns the literal deterministic source-change digest;
  - false/wrong/stale authorization publishes nothing;
  - exact authorization creates revision 5 and cannot be reused;
  - after-build before authorization returns `ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED`;
  - after-build requires a different fresh build and one source-change declaration added after the authorized revision with exact before/after lineage;
  - final stage requires the exact VS08-A `SOFTWARE_PASSED`, replay, nonphysical record and sets revision 7 `COMPLETED`;
  - stale/mismatched/corrupt authorities and cross-workspace references return exact codes without rewriting prior roots.

- [ ] **Step 10: Run stage RED, implement minimal authority adapters, then run GREEN.**

```powershell
py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py -q --basetemp=C:\tmp\stm32tk-vs08b-stage
```

The adapter may import lower-level public readers. Do not change their lifecycle or add convenient orchestration. Do not accept caller build hashes, workspace/project IDs, diagnostic revision, physical flag, declaration ID, or verdict.

- [ ] **Step 11: Write CLI/MCP RED contract tests.** Invoke the real parser/server boundary. Require five operations; exact camelCase property sets; strict integer/boolean/UUID/digest types without coercion; all optional checkpoint reference properties present but nullable; no project/data/root/path/command/environment/transport override in MCP; client-root binding; and exact CLI/workflow argument translation. Confirm existing three VS08-A tools are unchanged.

```python
def test_attempt_checkpoint_mcp_schema_is_closed_and_project_bound(tmp_path):
    schema = schemas(tmp_path)["stm32_acceptance_attempt_checkpoint"]
    assert set(schema["properties"]) == {
        "attemptId", "expectedRevision", "stage", "testRunId",
        "diagnosticSessionId", "acceptanceRecordId",
    }
    assert schema["additionalProperties"] is False
    assert not ({"projectRoot", "dataRoot", "command", "environment", "transport"}
                & set(schema["properties"]))
```

- [ ] **Step 12: Run adapter RED, implement thin projections, then run GREEN.**

```powershell
py -3.12 -m pytest tests/test_acceptance_recovery_cli.py tests/test_acceptance_recovery_mcp.py tests/test_mcp_server.py -q --basetemp=C:\tmp\stm32tk-vs08b-adapters
```

Update only the current authoritative MCP inventory. Do not rewrite historical inventory tests. CLI/MCP call shared workflows exactly once and add no validation/state lifecycle beyond syntax/root binding.

- [ ] **Step 13: Write the two-scenario vertical RED test.** Parameterize Keil and CubeMX. In distinct workspace/data roots use real existing software authorities to begin, checkpoint through diagnosis, destroy/recreate the recovery context, require and record the authorization, add the real diagnostic source-change declaration, checkpoint the after-build, finalize/query the VS08-A record, complete the attempt, destroy all in-memory state, and resume/show the completed attempt. Assert the exact stage prefix, linkage, recovery-policy digest, same lineage, `executionSource == replay`, `physicalTransportEvidence is False`, and no physical PASS vocabulary.

Add independent negative cases for concurrent different workspaces, copied reference/root rejection, timeout non-mutation, source-change-before-authorization refusal, and final AcceptanceRecord lineage mismatch.

- [ ] **Step 14: Run vertical RED and make only minimal seam corrections for GREEN.**

```powershell
py -3.12 -m pytest tests/test_vs08b_scenarios.py -q --basetemp=C:\tmp\stm32tk-vs08b-vertical
```

If a real authority cannot be consumed, correct the recovery adapter/model seam. Do not modify Test, Diagnostic, Evidence, AcceptanceRecord, Probe, or hardware lifecycle to make the scenario convenient.

- [ ] **Step 15: Rerun focused existing cleanup and authorization contracts.** These checks prove the adapter did not take ownership; they are software/fake evidence only:

```powershell
py -3.12 -m pytest tests/test_hardware_workflows.py::test_flash_derives_target_and_workspace_and_uses_modify_with_exact_pins tests/test_hardware_workflows.py::test_raw_operation_exception_is_sanitized_and_cleanup_runs tests/test_probe_lease.py::test_release_allows_a_successor_and_old_release_is_idempotent tests/test_target_runner.py::test_control_authorization_cross_process_consume_has_one_winner -q --basetemp=C:\tmp\stm32tk-vs08b-existing-boundaries
```

No hardware is invoked. If a platform-only process test skips, report it exactly and do not relabel it PASS.

- [ ] **Step 16: Run the proportionate affected slice suite once.** Use a new external basetemp and source paths; do not install anything.

```powershell
$env:PYTHONPATH=(Resolve-Path '.\src').Path + ';' + (Resolve-Path '..\stm32-monitor\src').Path
py -3.12 -m pytest tests/test_acceptance_recovery_model.py tests/test_acceptance_recovery_workflows.py tests/test_acceptance_recovery_cli.py tests/test_acceptance_recovery_mcp.py tests/test_vs08b_scenarios.py tests/test_acceptance_model.py tests/test_acceptance_workflows.py tests/test_acceptance_cli.py tests/test_acceptance_mcp.py tests/test_vs08a_scenarios.py tests/test_evidence_gc.py tests/test_identity.py tests/test_paths.py tests/test_workflows.py tests/test_diagnostic_workflows.py tests/test_mcp_server.py tests/test_testing_mcp.py tests/test_diagnostic_mcp.py tests/test_testing_cli.py tests/test_diagnostic_cli.py tests/test_hardware_workflows.py::test_flash_derives_target_and_workspace_and_uses_modify_with_exact_pins tests/test_hardware_workflows.py::test_raw_operation_exception_is_sanitized_and_cleanup_runs tests/test_probe_lease.py::test_release_allows_a_successor_and_old_release_is_idempotent tests/test_target_runner.py::test_control_authorization_cross_process_consume_has_one_winner -q --basetemp=C:\tmp\stm32tk-vs08b-green
py -3.12 -m compileall -q src tests
git diff --check eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2..HEAD
```

Required: zero failures/errors. Name any genuine platform skip. Do not run release, package/install, browser, performance, or hardware matrices.

- [ ] **Step 17: Self-review the complete accepted-base diff.** Verify all acceptance criteria and mentally mutate: policy timeout/digest, root revision/link, stage order, deadline comparison, retry equivalence, workspace binding, replay/physical flag, authorization ordering/digest, diagnostic revision, source declaration lineage, and final AcceptanceRecord lineage. Name a test that fails for every mutation. Scan for prohibited controller/scheduler/provider/store/Probe/backend/Python-support changes and mutable attempt state.

- [ ] **Step 18: Commit product/tests, then report separately.** Commit product and tests with `feat(acceptance): add recoverable isolated attempts`. Record the exact product/tests CodeHead in `docs/codex/returns/STM32TK-0802-VS08-B/implementation-report.md`, including accepted base, spec/plan, single implementer identity, branch/worktree, exact RED/GREEN outputs, tests, file list, software/nonphysical classification, timeout/isolation/concurrency evidence, existing cleanup/auth boundary evidence, failure classification, clean local/no-upstream/unpushed state, and prohibited-action confirmation. Commit the report as `docs(acceptance): record VS08-B implementation`. Never write the report commit SHA into the report.

- [ ] **Step 19: Return the implementation contract.** Return only status, commits, one-line test summary, concerns, and SDD report path. Leave the branch clean, local, unpushed, and with no upstream.
