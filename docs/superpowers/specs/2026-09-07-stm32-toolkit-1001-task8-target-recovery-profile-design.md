# STM32TK-1001 Task 8 Target Recovery Profile Design

Date: 2026-09-07

Module / phase: STM32TK-1001 / VS10-A H2 Task 8 physical closure

Status: FROZEN UNDER THE USER'S STANDING AUTONOMOUS-REPAIR AUTHORIZATION

Full accepted product base: `9d51b841a150d50a4323432d4fd118c8399efa4f`

Accepted-base tree: `764458944b24b0a5cbdc9503346ffc0c3781d1af`

Specification owner and independent reviewer: GPT-5.6-sol primary

Implementation owner after this freeze: the existing Task 8 GPT-5.6-luna agent at reasoning effort `max`

Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

Remote action: none authorized

Hardware action: no further flash is authorized by this design

## 1. Trigger and exact defect boundary

The accepted RAM-profile correction was installed in a uniquely active 0.9.0 runtime bound to
`9d51b841`. Public probe discovery found the expected opaque selector, and public
`test target prepare` succeeded for STM32F429ZGTx and `d4-heartbeat`, proving the sorted support
profile, exact project/build/ELF identity, protocol v2, and case inventory. The one user-authorized
`test target execute` then entered programming and returned `TEST_FLASH_FAILED`; the one-time
authorization record was consumed and no TestRun was published.

This reproduces the already established physical split: ordinary 1 MHz/halt programming fails on
this board/probe path, while the existing explicit public flash recovery profile at exactly
100 kHz SWD plus connect-under-reset has completed programming and exact readback. The current
Target two-phase API cannot bind or select that existing profile. `_target_supervisor()` always
constructs a default `ProbeWorkerConfig`, including for MODIFY execute.

Classification: `PRODUCT`. The RAM-profile correction remains accepted. This is a separate,
bounded missing selection in the Target testing orchestration; it does not justify a new backend,
retry, arbitrary connection settings, or a silent default change.

## 2. Runnable scenarios

### Scenario 1 - default Target prepare/execute remains compatible

Without recovery selection, public CLI, MCP, and Python callers retain the accepted normal Target
behavior. Prepare binds `recovery_under_reset=false`; execute derives the normal worker profile
from the consumed authorization. Existing error codes, inventory digests, result schemas, and
publication behavior remain unchanged.

### Scenario 2 - prepare binds one exact recovery intent

CLI `test target prepare` accepts one duplicate-rejecting `--recovery-under-reset` flag. MCP
`stm32_test_target_prepare` accepts one optional strict boolean `recoveryUnderReset=false`.
Python `target_test_prepare()` accepts keyword-only `recovery_under_reset: object = False` and
requires its exact type to be `bool` before service creation or hardware access.

The exact boolean is stored in the existing prepared authorization binding and therefore covered
by the existing action digest. Prepare itself remains OBSERVE and performs no programming.

### Scenario 3 - execute derives recovery solely from the consumed action

The public execute shape is unchanged: probe selector plus action digest. Execute does not accept
a second connection choice. After loading and consuming the exact prepared record, it requires an
exact boolean binding. `false` constructs the current normal worker. `true` derives the existing
`ProbeWorkerConfig.for_under_reset_recovery()` and therefore uses exactly 100 kHz SWD and
connect-under-reset for the one MODIFY attachment and programming attempt.

Missing, malformed, stale, or contradictory binding data fails closed before service creation.
There is no normal-first attempt, retry, fallback, or arbitrary frequency/mode input.

### Scenario 4 - existing Target safety and evidence gates remain authoritative

Recovery selection changes only connection construction. Execute must still revalidate probe,
workspace/project/session, source revision and dirty state, input snapshot, build ID, ELF path/hash,
transport, support profile, inventory and case digests before starting the service. It must prove
the same target identity before programming, perform the existing single flash/readback flow,
decode the existing output-only transport, and publish the unchanged physical TestRun only after
all checks pass. Any failure publishes no PASS.

## 3. Frozen architecture and state ownership

- The prepared authorization binding is the sole authority for the Target recovery choice.
- `TargetTestRunner` remains the strict canonical authorization-record owner. Its closed field
  sets admit `recovery_under_reset` only as one optional exact boolean so existing lower-level
  callers remain compatible; both prepare-time and loaded-record validation reject every other
  value and every unknown field.
- Public `target_test_prepare()` always writes the exact boolean into that existing canonical
  binding.
- `target_test_execute()` reads that bound boolean and chooses between the existing normal worker
  and the existing `for_under_reset_recovery()` derivation.
- The CLI and MCP remain thin adapters. Execute receives no new flag or MCP field.
- Probe worker, PyOCD backend, connection-policy constants, service, lease, flash adapter, protocol,
  schemas, and TestRun publication stay unchanged.
- The action digest and existing consumed-record lifecycle prevent a caller from changing the
  connection choice between prepare and execute.

## 4. Errors and lifecycle

- Non-boolean Python input and non-strict MCP input return the existing closed Target request
  failure before service creation; CLI duplicates or value syntax fail during parsing.
- A prepared record missing an exact boolean is invalid after this version change and cannot
  execute. Ephemeral pre-upgrade authorizations are deliberately fail-closed.
- Identity mismatch remains before programming and performs zero program calls.
- One execute performs at most one attach and one program call. Failure never retries and never
  publishes a physical PASS.
- Cleanup and stable public error sanitization remain unchanged.

## 5. Bounded ownership

Product changes are allowed only in:

- `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`.

Tests are allowed only in:

- `tools/stm32-toolkit/tests/test_target_runner.py`;
- `tools/stm32-toolkit/tests/test_physical_target_workflows.py`;
- `tools/stm32-toolkit/tests/test_testing_cli.py`;
- `tools/stm32-toolkit/tests/test_testing_mcp.py`;
- `tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py` when a real public adapter path needs
  coverage not expressible in the narrower files.

The same Task 8 Luna/max owner must commit RED before GREEN. The implementer does not accept the
diff. Sol reviews the complete accepted-base-to-final-code-head diff in a fresh detached worktree.

## 6. Required evidence

Tests must prove:

- default prepare binds exact false and default execute uses unchanged normal worker configuration;
- the strict runner accepts optional exact false/true in canonical prepared records, preserves
  legacy low-level bindings without the field, and rejects non-boolean values at prepare and load;
- recovery prepare binds exact true into the action digest, while prepare itself performs no write;
- recovery execute derives exactly 100 kHz/under-reset from the binding before service start;
- execute has no independent recovery input and cannot contradict the prepared action;
- invalid Python/MCP/CLI values and malformed/missing authorization fields fail before service,
  attach, or program;
- identity mismatch still performs zero programming;
- matching recovery flow performs one program call, existing readback/transport validation, and
  unchanged physical TestRun publication;
- no retry/fallback and no schema or MCP inventory-count change.

Use CPython 3.12, source `PYTHONPATH`, `-p no:cacheprovider`, `-o addopts=''`, and a short unique
external basetemp to avoid the independently classified Windows path-length condition. Run only
the affected Target workflow/CLI/MCP public tests unless a concrete failure identifies another
contract. Clean only run-owned temporary output; classify protected residue.

## 7. Explicit non-goals

- No automatic use of recovery and no change to ordinary Target defaults.
- No arbitrary frequency, connect mode, retry, transport negotiation, probe/target fallback,
  unlock, mass erase, chip erase, Option Bytes, or reset/run automation.
- No second runtime, service, worker, backend, provider, controller, MCP registration, or evidence
  authority.
- No Agent-, VS Code-, or Keil-specific product behavior.
- No project firmware, schema, protocol, TestRun, flash-result, Monitor, packaging, release, Python
  range, CI, or collaboration automation change.
- No additional physical attempt, push, PR mutation, merge, tag, release, or remote branch action.

## 8. Acceptance and stop boundary

Software acceptance requires all required focused tests, clean diff/status, an accurate local SDD
record, and an independent Sol complete-diff verdict with no unresolved product, safety,
compatibility, or scope defect. It does not authorize another hardware flash. After acceptance,
physical retry remains stopped until the user supplies a new one-attempt authorization.
