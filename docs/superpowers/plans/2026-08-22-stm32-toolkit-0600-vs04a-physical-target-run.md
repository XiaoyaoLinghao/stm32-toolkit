# STM32 Toolkit 0.6 VS04-A Physical Target Run Plan

## Ledger and boundary

- Module/phase: `0600 / VS04-A`, authorized physical Target result.
- Accepted base: `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.
- Specification: `docs/superpowers/specs/2026-08-22-stm32-toolkit-0600-vs04-physical-integration-design.md`.
- Specification/plan owner and reviewer: GPT-5.6-sol primary.
- Implementer/test owner: one GPT-5.6-luna agent, reasoning effort `max`.
- Implementation branch: `codex/STM32TK-0600-VS04A-PHYSICAL-TARGET` in one clean worktree.
- Remote authority: none. Physical hardware authority: none. CPython 3.12 only.

The slice is complete when a caller can prepare one exact physical Target action, inspect its
closed digest, execute that persisted digest through one fake production Probe Service lease, and
freshly reload the resulting physical TestRun through `test.show`. It does not publish Monitor
runs, compare analysis, access real hardware, or implement VS04-B/C.

## Allowed implementation surface

Expected product files:

- `tools/stm32-toolkit/src/stm32_toolkit/execution_provenance.py` (new unique policy authority);
- `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/testing/publication.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`;
- package exports only if required by an existing public pattern.

Tests:

- create `tools/stm32-toolkit/tests/test_physical_target_workflows.py`;
- modify existing `test_target_runner.py`, `test_target_replay_publication.py`,
  `test_testing_cli.py`, and `test_testing_mcp.py` only for directly affected compatibility.

If correct single-lease production composition requires a narrow helper in an existing Probe module,
stop and report the exact file/symbol to Sol before editing it. No Monitor or Diagnostic file is in
scope.

## Implementation tasks

### 1. Freeze provenance and request/result models with failing tests

Add the closed replay/physical policy exactly as the specification table defines. Add immutable
prepare/execute request types and public result shapes. Callers may select probe, transport, cases,
and timeout; identity/build/inventory/path values are derived from current public project/build and
read-only discovery boundaries.

Tests first prove:

- replay policy remains byte-compatible;
- physical requires true flag, current origin/import workspace/session, and non-replay labels;
- unknown/mixed values fail closed;
- prepare performs no MODIFY/flash/test call and returns only bounded public fields;
- persisted intent is closed, canonical, <=5-minute, and contains a portable project-relative ELF
  path plus the complete derived binding.

### 2. Make authorization process-independent and single-use

Keep `TargetTestRunner.prepare()` as the authority for nonce, expiry, canonical digest, and create-new
record. Add the minimum public reload/execute-by-digest path needed for a later CLI process; do not
trust a caller-reconstructed `PreparedTargetRun`.

Tests prove wrong, expired, missing, corrupt, reused, drifted revision/inventory/build/ELF/probe, and
changed case/transport intent all fail before side effects. After any execute attempt the digest is
consumed and retry requires a new prepare.

### 3. Compose one MODIFY lease for flash and Target execution

Create one application-owned Probe supervisor/client boundary. Target identity, guarded flash,
post-flash identity, transport execution, Evidence collection, and cleanup all use that one lease.
The flash adapter calls the existing `flash_firmware` behavior with the already-bound client; it
must not call `flash_workflow`, start another supervisor, or acquire another lease.

Tests with production-shaped fakes prove exactly one start/acquire/release, no nested flash workflow,
one flash, one selected transport, exact cases, busy owner preservation, cancellation/timeout
cleanup, and no process kill/lease steal.

### 4. Publish and reload the physical TestRun

Publish the runner's terminal manifest/raw artifacts as operation `target-test-physical`, with a
closed envelope/root carrying physical provenance, current workspace IDs, real hardware labels,
firmware identity, action digest, and deterministic intent digest. Publication must be idempotent
for identical bytes and conflict on changed intent.

Extend `TestRunRepository.load()` and `test.show` to validate and return Host, Target replay, and
Target physical variants. Existing replay serialization and error behavior must remain unchanged.

### 5. Expose thin CLI and MCP adapters

Add:

- `test target prepare`;
- `test target execute --authorized-action-digest <64hex>`;
- MCP `stm32_test_target_prepare`;
- MCP `stm32_test_target_execute`.

Adapters bind runtime project/data/session roots, use closed schemas, call one workflow once, and
return its OperationResult unchanged. They expose no endpoint, token, raw probe serial in durable
output, absolute ELF path, or caller-controlled identity field.

## Slice verification

The Luna implementer runs, with exact worktree source roots and a fresh bounded basetemp:

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_physical_target_workflows.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_target_replay_publication.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_hardware_workflows.py
py -3.12 -m py_compile <changed Python files>
git diff --check 5d6e06845a2c1d991181c5ff84a9194dfcc49c8c..HEAD
git status --short
```

No complete Probe, Monitor, release, coverage, packaging, Python 3.10, or physical hardware matrix
is allowed. The Sol reviewer independently inspects the complete accepted-base-to-head diff in a
clean detached worktree and reruns only this slice and the named affected regressions.

Expected commit subject: `feat(testing): publish authorized physical target runs`.
