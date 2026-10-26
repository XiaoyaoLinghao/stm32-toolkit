# Diagnostic snapshot consumers — candidate, revision required

Date: 2026-10-27. Verdict: **REVISION_REQUIRED**. This is retained local work, not software acceptance or a release qualification.

## Ownership and source ledger

- Accepted base: `59464807250cdb0cf58c7d7d19f8a9ba47cdde44` (B2b2A).
- Governing contract: `docs/superpowers/specs/2026-10-26-gcc-delivery-contract.md`.
- Bounded plan: second edit in `docs/superpowers/plans/2026-10-26-gcc-monitor-consumers.md`.
- Primary Codex owns specification, dispatch, complete-diff review and acceptance; local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` route owns implementation/test changes.
- Branch: `codex/gcc-monitor-consumers`; no PR or remote action authorized for this slice.
- Product candidate: `752ac797c0df917a94bf6accaf45893357772a7b`.
- CodeHead before this report: `462815e52ad7b6ffb1769d128c8f5605673dae1a`, including opt-in test fixture extensions.
- Independent review checkout: `C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit`, clean and detached at the CodeHead. Primary reviewed the complete six-file accepted-base-to-CodeHead diff; `git diff --check` passed. Both implementation/review checkouts were clean before this report.
- Boundary: disposable software fixtures only; no original firmware projects, installed runtime changes, hardware, global permission/model/auth changes, version changes or remote publication.

## Retained implementation

Claude added complete source-baseline/Git-evidence comparison to Diagnostic replay/physical transcript and reference consumers, and to continuation Monitor transcript/reference checks. Existing identity, scope, target, probe, session, lease and evidence-authority checks remain.

The MCP Monitor reference candidate accepts the validated snapshot pair and nullable Git fields while attempting to preserve legacy serialization. It has the unresolved R1 finding below and is not accepted.

Three existing software fixtures now support the complete pair: `prepare_pair` has an opt-in `snapshot_provenance=False` parameter, and both Monitor history builders forward the pair. Default legacy behavior remains. No new regression test file was completed.

## CLI health and retained failures

All invocations used the global dispatcher at `C:/Users/zhy76/.codex/tools/claude-dispatch/dispatch.py`. Actual native initialization metadata was inspected, not inferred from exit codes or model claims.

| Run under `D:/codex-tmp/gcc26/` | Native evidence and outcome |
| --- | --- |
| `diagnostic-health-20261027` | PowerShell inventory matched; real harmless smoke and exact in-scope plan-heading read succeeded. This was not a product test. |
| `diagnostic-core-20261027` | Session `90044073-3afb-4b46-b509-4b2def81bda4`; correct file-tool inventory, 17 successful edits. Then attempted unavailable Bash with `echo "no shell available"`. Native result proves it did not execute; dispatcher stopped. Partial edits were independently reviewed and preserved in the product candidate. |
| `diagnostic-tests-20261027` | Session `4f2e2a37-8539-4674-855a-301fca2bea24`; correct file-tool inventory, no scope violation. Reached the 100-turn limit after extensive reading and one constants edit. Tests were neither completed nor executed. Work/logs retained; remaining work was split into smaller tasks. |
| `diagnostic-fixtures` | Session `f5b8c5de-3918-4555-a0cc-012c2267446f`; correct file-tool inventory, fixture edits completed, no scope violation. One intermediate Edit string was not found and was corrected; the strict dispatcher retained a nonzero outcome, while native edit completion and normal CLI completion are separately recorded. No tests ran. |
| `diagnostic-mcp-r1` | Session `46cddfd7-ab3d-4eb6-989a-a8ec2ec27bdb`; correct file-tool inventory. After five reads/searches it attempted unavailable Bash `true`; native result proves no execution and dispatcher stopped. No edit was produced. |

The absent Bash calls were no-op shell attempts, not read/search operations. The global one-shot recovery rule therefore did not apply. No recovery, permission expansion, interpreter substitution or automatic restart of those failed operations was performed. Repeated unavailable-tool behavior means successful startup is not proof of reliable implementation completion.

Native shell results without numeric status retain `numeric_exit_code=null`. Test subprocess exit codes below come from the independent execution record, not an inferred tool exit status. Previous provider refusal logs also remain preserved.

## Primary verification performed

1. `D:/codex-tmp/gcc26/dgp/execution.json`: primary independent run at product candidate `752ac797c0df917a94bf6accaf45893357772a7b`, using `run_checks.py` group `diagnostic-content-core`. **106 passed, 0 failed, 0 errors, 0 skipped**; subprocess exit 0 and source unchanged. Files: `test_diagnostic_workflows.py`, `test_diagnostic_input_integrity_boundaries.py`, `test_diagnostic_end_to_end.py`. One existing Pydantic settings forward-reference warning was emitted. This precedes the fixture commit and is not claimed as a final-head full rerun or Claude-owned testing.
2. At CodeHead `462815e52ad7b6ffb1769d128c8f5605673dae1a`, primary executed an isolated producer/readback check in `D:/codex-tmp/gcc26/dgo`: `prepare_pair(..., snapshot_provenance=True)` → `_monitor_baseline` → `authenticate_continuation` → `validate_continuation_reference`. Native subprocess exit 0. Output in `dgo-primary.txt`: baseline `input-snapshot-v1`, both Git commits null, analysis readback `VALID`. This uses real persisted synthetic TestRun/Diagnostic/continuation/Monitor evidence and the normal evidence readers. It does not constitute a physical target test or the missing regression matrix.
3. R1 independently reproduced in the clean review checkout at the product candidate. Details retained in `D:/codex-tmp/gcc26/diagnostic-primary-findings.txt`.

No delegated test execution occurred in this slice. No coverage or release threshold is claimed.

## Open finding R1

Path: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`, `DiagnosticMonitorRunRef._serialize_reference` and existing-instance validation.

Reproduction: validate the legacy `test_diagnostic_mcp.PHYSICAL_MONITOR_REF`, then `model_copy(update={"source_baseline": None})`. The copied object's `model_fields_set` records the explicit null, but `model_dump(by_alias=True)` erases it, and `DiagnosticMonitorRunRef.model_validate(copy)` accepts that same object. Observed output: `explicit-null declared True`, `explicit-null survives dump False`, `revalidated object accepted True`.

Expected: omit only absent default pair keys; reject explicitly-null, partial, mixed or mutated provenance before dispatch/effects. Preserve valid legacy and snapshot model-instance roundtrips and required nullable `svd_sha256`. The shared replay validator must remain authoritative; broad null stripping is not acceptable.

The correction and corresponding tests were assigned to Claude in `diagnostic-mcp-r1.task.json`, but that invocation stopped without edits. This remains an actual uncorrected code finding.

## Work required before acceptance

1. Claude implements R1 and actual registered MCP schema/roundtrip/refusal regression tests, updating only affected legacy schema expectations.
2. Claude completes `test_content_monitor_diagnostics.py`: snapshot replay and physical-shaped persisted readback, continuation/verification, self-consistent provenance substitution refusals and no-effect assertions. A bounded task is prepared in `diagnostic-backend-tests.task.json` but was not launched.
3. Claude runs designated focused/affected checks through native PowerShell; primary reviews the final complete diff in the clean exact-head checkout and independently verifies representative paths. Existing partial evidence must remain attributed to its actual source head and owner.

The broader GCC delivery integration and source-preparation fixture remain separate unfinished work. No version or release status changes follow from this candidate.
