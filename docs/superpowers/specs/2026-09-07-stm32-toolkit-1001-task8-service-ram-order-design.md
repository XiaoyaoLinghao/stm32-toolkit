# STM32 Toolkit 1001 Task 8 Probe Service RAM-order correction design

## Ledger

- Module/phase: `STM32TK-1001`, Task 8 physical Step 4 post-flash transport correction.
- Accepted Toolkit product base: `215bfe13ee556509cca907bde5a00b8132982149` (tree
  `4ae441a7e2f33bd72c95c653335f0e9e98f75a14`).
- Specification start/docs head: `7fbfed05690fc30b71cfe145d5592adeb53882bd` (tree
  `7d79e604173007a80a7f651664ed27d586486c29`).
- Accepted project head: `4bfcf9f95b1d761c9a82042d6ded751d068c1e06` (tree
  `a73fc32019989ef7ffa44619eefe767c5da3dab3`).
- Specification/plan owner and independent reviewer: GPT-5.6-sol primary.
- Implementation owner: one GPT-5.6-luna agent at reasoning effort `max`.
- Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Remote action: none authorized.
- Hardware action: none authorized during implementation or review. Action
  `45b4cdb359ddc0d276fd5d91cdd705d067d935bd16b652667ef8056f05c3940e` is consumed and must
  never be retried.

## Trigger and exact defect

The one authorized 60-second recovery execute reached exact 100 kHz SWD/connect-under-reset,
proved the expected STM32F429ZGTx identity, programmed the accepted ELF, completed exact segment
readback, and wrote a successful `flash-result.json`: 54896 verified bytes from
`2026-09-07T08:52:03.654105Z` through `2026-09-07T08:52:19.779543Z`. It then returned
`TEST_TRANSPORT_UNAVAILABLE` before publishing a TestRun.

The accepted Task 8 RAM-profile correction sorts the support profile passed into the production
worker. At transport open, however, `ProbeService._effective_target_transport_config()` rebuilds
the writable RAM list directly from `model.memory.regions` without sorting. This project's valid
manifest order is `IROM1, IRAM1, MAILBOX, IRAM2`, so the rebuilt writable list is
`IRAM1, MAILBOX, IRAM2` rather than ascending address order `IRAM2, IRAM1, MAILBOX`.
`MailboxTransport.open()` calls the shared fail-closed `ram_regions()` validator, which rejects
unsorted RAM before any mailbox read. The backend maps that failure to `PROBE_BACKEND_ERROR`, and
the public workflow maps it to `TEST_TRANSPORT_UNAVAILABLE`.

Classification: `PRODUCT / integration normalization`. The successful flash remains valid. This
is not a timeout, hardware, probe-name, PyOCD programming, firmware, or mailbox-data failure.

## Runnable scenarios

### Scenario 1 - valid project order produces canonical runtime RAM

Given a Project v3 model whose writable regions are valid but not in ascending address order, the
Probe Service rebuilds target transport configuration with the same complete writable regions
sorted by numeric `(origin, length)`. For the accepted project the exact result is IRAM2
`0x10000000+0x10000`, IRAM1 `0x20000000+0x2EFF0`, MAILBOX
`0x2002EFF0+0x1010`.

### Scenario 2 - production mailbox open accepts the rebuilt configuration

Through the real Probe Service transport-config boundary and the admitted production mailbox
adapter with a fake already-attached target, `target.transport.open` succeeds for the accepted
model order. It returns the unchanged closed mailbox identity. No target memory read or write is
needed merely to open the transport.

### Scenario 3 - invalid maps and drift remain fail-closed

Overlapping, out-of-range, malformed, mismatched project/support, wrong target/probe, changed
project transport, and unsupported provider inputs continue to fail with existing codes and before
mailbox reads. Sorting must not silently repair overlap, drop regions, merge regions, or change
addresses/sizes.

### Scenario 4 - recovery, flash, deadline, and publication remain unchanged

Static recovery prepare, terminal authorization consumption, one recovery worker, identity before
program, flash/readback, absolute run deadline, mailbox protocol, TestRun publication, and all
normal profiles remain byte-for-byte unchanged. The correction only canonicalizes the Service's
runtime copy of writable RAM before the existing validators consume it.

## Frozen implementation boundary

Allowed product file:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`: deterministically sort the complete
  writable-region projection before composing target transport configuration.

Allowed test files:

- `tools/stm32-toolkit/tests/test_probe_service.py` for the Service projection and closed failures;
- `tools/stm32-toolkit/tests/test_physical_target_workflows.py` only if needed for a public
  production-composition regression using the accepted four-region model.

The implementer must first commit a RED that exercises the real unsorted Project v3 order and
proves no hardware access. GREEN may change only the Service projection. Do not modify the earlier
support-profile normalizer, project model/schema, transport validator, worker/backend, recovery
profile, timeout, flash, firmware, CLI, MCP, runtime inventory, or error mapping.

## Evidence and acceptance

The Luna/max owner runs only exact RED/GREEN nodes, the complete affected Service/physical
workflow tests, and the smallest risk-triggered Target transport/backend regression set. It records
`git diff --check`, changed paths, final status, and leaves acceptance to Sol.

The Sol reviewer uses a fresh detached worktree and reviews the complete
`215bfe13ee556509cca907bde5a00b8132982149..CODE_HEAD` diff, reconciling all intervening frozen
documents. Acceptance requires deterministic full-region preservation, ascending runtime order,
production mailbox-open success through a fake target, unchanged closed failures and public
surfaces, all focused tests passing, and no hardware or remote operation.

## Non-goals

- No target retry, fallback, new attach, new flash, reset, halt, resume, memory read, or physical
  acceptance during software work.
- No second normalizer authority exposed publicly; the Service owns only its existing runtime
  reconstruction boundary.
- No firmware/project/linker/mailbox protocol, schema, backend/provider/controller, runtime/MCP
  registration, Agent-specific behavior, Python range, package, release, CI, or collaboration
  automation change.
- No push, PR mutation, merge, tag, release, or remote branch action.
