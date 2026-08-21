# STM32 Toolkit 0.6 VS-03 Task7B Completion Plan

## Ledger and ownership

- Module/phase: `0600 / VS-03 / Task7B`, complete and reload replay verification.
- Accepted base: `85b259fb6d9d41b09733e9401b8b6f4db8c40508`.
- Specification/plan owner and final reviewer: GPT-5.6-sol primary agent.
- Implementer: one GPT-5.6-luna subagent at reasoning effort `max`.
- Local branch: `codex/STM32TK-0600-VS03-VERIFY-REWRITE2`.
- Remote authority: none. No push, PR mutation, merge, close, or remote branch operation.
- Python authority: CPython 3.12 only; Python 3.10 remains frozen.

## Product slice

A caller with an active replay verification supplies only the executed operation IDs and an
optional cancellation flag. Toolkit reloads the authoritative checkpoint, derives one
deterministic `FixVerification`, appends it once, transitions the session, and can show the full
verification history from a fresh context. The caller never selects status, reason, timestamp,
plan, declaration, analysis, or marker.

This remains one vertical slice. Do not split status cases into separate implementation tasks or
add adapter, release, hardware, packaging, Task8, Task9, VS-04, or Python 3.10 work.

## Frozen public contract

Implement the two signatures and exact operation names from design section 3.7:

- `diagnostic_complete_verification(... executed_operation_ids: list[str], cancelled=False, actor="tool")`
  -> `diagnostic.verification.complete` and data `{session, fix_verification}`.
- `diagnostic_show_verification(... diagnostic_session_id)`
  -> `diagnostic.verification.show` and data
  `{session, fix_verifications, authoritative: true}`.

Completion event payload remains exactly:

```text
request {fix_verification}
result  {fix_verification_id,status,reason_code}
```

The accepted event timestamp is not completion authority. `completed_at_utc` is always the
authoritative fixed-after TestRun `ended_at_utc`.

## Authority and deterministic priority

For a fresh operation, perform these steps in order:

1. Normalize operation/session/revision/actor, require a real list of 1..64 unique safe executed
   operation IDs, and require an exact bool cancellation flag.
2. Load the durable bound session. Resolve an already accepted completion operation before state
   and Evidence preflight. Exact public intent means the same actor, executed operation IDs in the
   same canonical order, and the same cancellation flag. It returns the original accepted
   `FixVerification` plus the current authoritative session with zero mutation. A changed event,
   actor, operations, or cancellation flag is `DIAGNOSTIC_OPERATION_CONFLICT`.
3. A new operation must match current revision, state `VERIFYING`, and one active stored plan and
   declaration. Otherwise fail without Evidence or event mutation.
4. Reload failed-before and fixed-after TestRuns through `TestRunRepository`; both must remain
   Target/replay/non-physical and match their exact planned evidence IDs and frozen identity bridge.
   Failed-before must be failed. Fixed-after may be passed or failed: Task7B corrects the Task7A
   plan-add preflight so a trustworthy failed fixed-after run can reach
   `FAILED/FIXED_TEST_FAILED` instead of being rejected earlier.
5. A provider/filesystem failure is `ENVIRONMENT_FAILURE`; an identity contradiction is
   `INCOMPATIBLE_IDENTITY`. If either core TestRun or the declaration/diff authority cannot be
   loaded well enough to establish identity and the fixed completion timestamp, append nothing.
   This is a core-authority failure, not a fabricated inconclusive record.
6. After core authority is established, derive exactly one outcome with this priority:
   - caller cancellation -> `CANCELLED/CALLER_CANCELLED`;
   - fixed-after state failed -> `FAILED/FIXED_TEST_FAILED`;
   - missing required analysis or attached marker ->
     `INCONCLUSIVE/MANDATORY_EVIDENCE_MISSING`;
   - corrupt/noncanonical required analysis or marker ->
     `INCONCLUSIVE/MANDATORY_EVIDENCE_CORRUPT`;
   - any required analysis not `quality=VALID` and `conclusion=COMPLETED` ->
     `INCONCLUSIVE/ANALYSIS_NOT_VALID`;
   - any valid analysis whose `changed` differs from `plan.expected_changed` ->
     `FAILED/ANALYSIS_CONTRADICTED`;
   - otherwise -> `PASSED/VERIFICATION_PASSED`.
7. Non-cancelled, passed fixed-after evaluation reloads every required analysis and its already
   attached marker using the closed Task7A shared authority. Analysis IDs/evidence IDs stay paired
   and canonical. One genuine attached marker must cover every required pair. Do not import
   `stm32_monitor` and do not consume a bundle.
8. `executed_operation_ids` are caller-recorded execution facts. The frozen plan has no required
   operation-ID field or external operation root, so Toolkit validates their closed shape and
   uniqueness but must not invent an unverifiable existence lookup.
9. Append once through `DiagnosticStore`. `PASSED` yields `RESOLVED`; every other status returns to
   `INVESTIGATING`; active plan clears. Append-time lookup remains the race authority.

## Idempotency support

The completion event stores a derived `FixVerification`, not the public completion request. Add a
read-only locked store lookup that returns the current full session and original accepted event for
`session_id + operation_id`, while checking event type and actor. The completion workflow then
compares the accepted `FixVerification.executed_operation_ids` and whether its status is
`CANCELLED` against normalized public input. This is necessary for exact retry after the active
plan has been cleared or Evidence has later become unavailable. It must not weaken the existing
canonical-request `resolve_operation()` used by Task7A.

## Allowed files

Product:

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`

Tests:

- `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`
- `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- only if an existing Host regression needs an assertion:
  `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`

Do not change the frozen model/event schemas unless RED proves an internal contradiction and Sol
first amends this plan.

## TDD and proportionate verification

RED must cover one runnable public completion matrix, not separate micro-Gates:

- passed -> resolved, show and fresh reload;
- trustworthy fixed failure -> failed/investigating;
- cancelled -> cancelled/investigating;
- missing/corrupt mandatory analysis or marker -> named inconclusive/investigating;
- invalid analysis and valid contradiction -> named outcomes;
- incompatible identity/environment -> no FixVerification and zero mutation;
- exact advanced-state retry -> original value/current session/zero mutation;
- changed actor/operations/cancelled -> operation conflict;
- fresh stale revision -> revision conflict before Evidence preflight.

Run during implementation:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_fix_verification_workflows.py

py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-toolkit/tests/test_fix_verification_workflows.py tools/stm32-toolkit/tests/test_diagnostic_workflows.py tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

Also run `py_compile` for changed product files and
`git diff --check 85b259fb6d9d41b09733e9401b8b6f4db8c40508..HEAD`.

## Sol acceptance

Review the complete Task7B base-to-head diff in a new clean detached worktree. Run only the focused
completion/store tests, the affected three-file regression, one public completion-to-fresh-show
probe, and diff-check. Release matrices, adapters, packaging, hardware, and remote operations remain
deferred to their named layers.
