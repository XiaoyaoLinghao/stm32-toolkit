# STM32TK-0403 Flash and Cortex-Debug Handoff Implementation Plan

> **Execution owner:** Codex. Use test-driven development for every behavior
> change and verification-before-completion before remote delivery.

**Goal:** Add one identity-bound, sector-only firmware programming path and a
crash-safe, one-time Cortex-Debug ownership handoff on top of the accepted
Probe Service.

**Accepted base:** `4424b5f45b38bb032e30ba7dc3b7bb37130fc8cd`
(`master`, merged `STM32TK-0402-PYOCD-BACKEND`).

**Branch:** `codex/STM32TK-0403-FLASH-HANDOFF`

**Ownership ledger:** Codex owns specification, implementation, tests, review,
report, push, PR, and ordinary merge under the user's explicit continuation
authorization. OpenClaw remains paused. There is no bounded override from a
different implementer and no active PR at initialization.

**Architecture:** The high-level flash gate validates the current debug build
and the caller-confirmed identity before it invokes the authenticated
loopback-only Probe Service. The service independently revalidates the exact
project-relative ELF size and SHA-256 inside the serialized backend section,
then passes those same bounded in-memory bytes to PyOCD for sector-only
programming. Success requires exact readback of
every file-backed load segment and is committed last in `flash-result.json`.
The handoff coordinator persists a workspace/session/probe-bound one-time
ticket, stops only its own Probe Service, releases the lease, and reacquires and
revalidates the same firmware before restoring only the originating
workspace's opaque monitor selection.

**Packet boundary:** This packet exposes Python contracts and protocol support.
It does not add CLI, MCP, Skills, version changes, Monitor behavior, GDB process
management, breakpoints, typed reads, SVD, sampling, or Fault analysis. Those
belong to 0404, 0405, and 0501. It never runs or kills Cortex-Debug/PyOCD
processes and never performs chip erase, Option Bytes, arbitrary writes, or an
implicit reset.

---

## Task 1: Freeze flash evidence and protocol contracts

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`
- Create: `tools/stm32-toolkit/tests/test_flash.py`
- Modify: `schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_protocol.py`

- [x] Write RED tests for frozen JSON-safe `FlashRequest`, `FlashReport`, and
  bounded ELF load-segment evidence. Require exact boolean authorization,
  caller-confirmed 64-hex `buildId` and `elfSha256`, exact probe/target IDs,
  canonical project roots, and deterministic portable result paths.
- [x] Extend protocol version 1 compatibly with exactly one modify operation,
  `flash.program`, whose data is a portable project-relative `.elf` path,
  expected SHA-256, and expected byte size. Reject absolute/backslash/dot-dot,
  NUL/control characters, unknown fields, booleans-as-integers, overflow, and
  non-modify operation levels before backend execution.
- [x] Make backend programming telemetry honest: nullable backend-reported
  programmed byte/sector counts are allowed because PyOCD 0.45.1 does not
  expose reliable post-commit counts. The high-level report separately records
  exact verified readback bytes.
- [x] Preserve root/packaged schema byte identity.

**RED command:**

`python -m pytest tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_probe_protocol.py -q`

---

## Task 2: Validate one current debug-build identity and its flash image

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`
- Modify: `tools/stm32-toolkit/tests/test_flash.py`

- [x] Write RED tests that reject missing/failed/oversize/malformed build
  result or identity documents, invalid identity schema/recomputed build ID,
  non-debug presets, project/identity/result disagreement, changed Git HEAD or
  input snapshot, current ELF/MAP byte changes, unsafe redirects/reparse points,
  unsupported target configuration, no file-backed ELF load segments,
  overlapping/out-of-range segments, and aggregate image size above 64 MiB.
- [x] Reuse the existing project model, build identity schema, current input
  snapshot, Git evidence, ELF32 little-endian ARM validation, and bounded file
  readers. Do not duplicate a weaker mtime-based freshness rule.
- [x] Compare the request's expected build ID and ELF SHA before opening a
  probe. A stale UI/AI confirmation returns `FLASH_PLAN_CHANGED` and invokes no
  backend operation.
- [x] Extract deterministic non-overlapping file-backed `PT_LOAD` bytes at
  their physical load addresses for later target readback; never infer active
  firmware from a timestamp or filename.

---

## Task 3: Add service-side digest guard and sector-only PyOCD programming

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/tests/fakes/fake_probe.py`
- Modify: `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_service.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_client.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_supervisor.py`
- Modify: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

- [x] Write RED tests proving observe/control leases cannot program, service
  without an exact project root cannot program, path escape/reparse/non-regular
  files fail before the backend call, a size/hash race returns
  `FIRMWARE_INPUT_CHANGED`, request timeout/cancellation does not start a
  queued flash, and raw filesystem/PyOCD errors are never serialized.
- [x] Extend supervisor/service configuration with an optional canonical
  project root. Resolve only portable project-relative paths under that root
  and lstat every component. Read, hash, and size-check the ELF immediately
  inside the serialized backend operation, then pass those exact bytes to
  `flash_elf` so a path replacement cannot change what PyOCD programs.
- [x] Bind endpoint evidence to the exact probe ID and granted operation level.
  Map `flash.program` to a server-owned `MODIFY` minimum regardless of the
  client's claim. Once a modify call enters the backend critical section,
  timeout/cancellation/shutdown waits for its explicit completion before close
  or lease release; a queued call can still be cancelled before entry.
- [x] Add a strict client `program_verified_elf()` method that always requests
  `OperationLevel.MODIFY` and validates the complete response shape.
- [x] Implement the PyOCD driver seam with `FileProgrammer` forced to
  `chip_erase="sector"`, `trust_crc=False`, `keep_unwritten=True`, no progress
  output, and ELF format. Do not pass PyOCD 0.45.1's deprecated/ignored
  `no_reset` parameter. Do not call reset, unlock, chip erase, mass erase, or
  target writes outside PyOCD's verified file programmer.
- [x] Test exact programmer options and that a PyOCD failure yields a stable
  code while leaving no success evidence.

---

## Task 4: Orchestrate flash, verify target bytes, and commit evidence last

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py`
- Modify: `tools/stm32-toolkit/tests/test_flash.py`

- [x] Write RED tests for exact authorization (`True` only), current identity,
  attach to the exact project-selected probe/target, modify-level programming,
  chunked readback at no more than 65,536 bytes, partial/mismatched readback,
  disconnects, and cancellation.
- [x] Sequence: validate current identity -> attach exact probe/target -> invoke
  service-side guarded programming -> read every expected load-segment byte ->
  revalidate current disk identity -> atomically publish result. Any failure
  returns stable evidence, performs no reset, and never claims the firmware is
  active.
- [x] Publish `artifacts/migration/flash-result.json` with schema version,
  status/code, Toolkit version, workspace/session/probe, target device and
  debug target, build ID, ELF path/SHA/size, Git HEAD/dirty state, input
  snapshot, verified byte count, backend telemetry, start/finish timestamps,
  and authorization/operation-level audit facts. The result document is the
  commit point and is written only after successful readback.
- [x] Inject disk-change and atomic-write failures and prove stale success is
  never retained. Keep all public paths project-relative and all messages free
  of raw exception text/token/absolute-root leakage.

---

## Task 5: Implement persistent one-time Cortex-Debug handoff

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/handoff.py`
- Create: `tools/stm32-toolkit/tests/test_debug_handoff.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py`

- [x] Write RED tests for states `observing`, `paused-for-debug`,
  `externally-owned`, and `reacquiring`; exact boolean authorization; current
  successful flash identity; supervisor stop before external ownership; lease
  release; restart/reacquire; target readback after return; one-time ticket
  replay; forged/wrong workspace/session/probe/build tickets; corrupted state;
  begin/end races; cancellation; startup/stop failure; and process restart.
- [x] Persist a bounded, user-only, atomic state record below the exact session
  root. The ticket binds ticket ID, workspace/session/probe, target, build ID,
  ELF SHA, prior opaque watch-selection tuple, issue time, state, and schema/
  Toolkit version. Never persist an endpoint token.
- [x] Begin validates the current flash result and target readback, writes the
  paused transition, stops only the supplied supervisor, proves its lease is
  released, and then records external ownership. It never starts, signals, or
  kills Cortex-Debug/PyOCD/GDB.
- [x] End accepts only the active ticket, marks reacquiring, starts the owning
  supervisor, reattaches the exact probe/target, revalidates disk identity and
  complete target readback, consumes the ticket, and returns only the original
  workspace's prior watch selection. Transient reacquire failure remains
  retryable; success is not replayable.
- [x] Define a data-only Cortex-Debug contract for 0405 that requires
  `servertype=pyocd`, exact target/executable, and attach-only behavior. This
  packet does not edit generated tasks or expose public CLI/MCP commands.

**Focused command:**

`python -m pytest tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_debug_handoff.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_probe_supervisor.py tools/stm32-toolkit/tests/test_pyocd_backend.py -q`

---

## Task 6: Package, verify, review, and integrate

**Files:**

- Create: `docs/codex/returns/STM32TK-0403-FLASH-HANDOFF/implementation-report.md`
- Modify: `docs/superpowers/plans/2026-08-07-stm32-toolkit-codex-continuation.md`
- Modify: this plan's checkboxes

- [ ] Run focused tests, full Toolkit pytest with branch coverage at least 90%,
  compileall, `git diff --check`, schema byte identity, changed-file inventory,
  no-suppression scan, credential/token/absolute-path scan, and forbidden API
  scan for process termination, shell strings, chip erase, mass erase, Option
  Bytes, arbitrary memory writes, or implicit reset.
- [ ] Build a wheel and install `[probe]` into a fresh external environment.
  Prove ordinary package import stays PyOCD-lazy and the new contracts load.
- [ ] Run Windows real-NTFS state/path/atomicity/cancellation gates. Run Linux
  equivalents in 0405. If no selected physical probe is present, label actual
  sector programming/readback/handoff `DEFERRED_TO_AVAILABLE_REAL_PROBE`; fake
  evidence never closes that release gate.
- [ ] Commit product/tests first and the reconciled report last. The report
  records this accepted base and the code head before its own commit and never
  records its own final SHA.
- [ ] Push, create a ready PR targeting `master`, verify local/remote/PR head
  identity, review the full accepted-base-to-final-head diff in a clean detached
  worktree, correct findings on the same branch, and merge without deleting the
  remote branch only after all non-deferred gates pass.
