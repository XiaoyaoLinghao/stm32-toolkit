# STM32TK-0404 Typed Debug Implementation Plan

> **Execution owner:** Codex. Use test-driven development for every behavior
> change, independent subagents only on disjoint paths, and
> verification-before-completion before remote delivery.

**Goal:** Add a strictly read-only, firmware-identity-bound typed debug kernel
for DWARF variables, exact SVD registers, finite sampling, and Fault evidence.

**Accepted base:** `35a5326fed7a4810152020c363f3529ebd50c382`
(`master`, merged `STM32TK-0403-FLASH-HANDOFF`).

**Branch:** `codex/STM32TK-0404-TYPED-DEBUG`

**Ownership ledger:** Codex owns specification, implementation, tests, review,
report, push, PR, and ordinary merge under the user's explicit continuation
authorization. OpenClaw remains paused. There is no bounded override from a
different implementer and no active PR at initialization.

**Architecture:** Parse ELF/DWARF and SVD only in the Toolkit client process.
Every target read still goes through the authenticated `ProbeClient`; the
loopback Probe Service remains the sole PyOCD owner. A debug binding validates
the current build/flash evidence, exact physical probe/target, and complete
target segment readback before exposing a bounded immutable catalog. Typed
reads derive address, size, signedness, and structure only from current
DWARF/SVD metadata. Sampling is finite and in-memory; Fault analysis observes
only a core already reported halted and never halts, resumes, resets, or writes.

**Packet boundary:** This packet exposes Python contracts only. It does not add
CLI, MCP, Skills, doctor capability, version changes, Cortex-Debug task wiring,
Monitor groups/history/storage/WebSocket/UI, breakpoints, halt/resume/step/
reset, arbitrary addresses, pointer dereference, target writes, or process
control. CLI/MCP/release integration belongs to 0405; Monitor persistence and
UI belong to 0501/0502.

---

## Task 1: Freeze shared models and current-firmware binding

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`
- Create: `tools/stm32-toolkit/tests/test_debug_firmware.py`

- [x] Write RED tests for frozen JSON-safe models, stable codes, exact caller
  `buildId`/ELF SHA pins, canonical project roots, bounded identifiers, no
  booleans-as-integers, and portable paths.
- [x] Define immutable `DebugBindingRequest`, `DebugFirmwareBinding`, typed
  location/value/read item/report, SVD selection/register evidence, sample
  report, and Fault report contracts. Preserve 64-bit integers losslessly as
  decimal string plus raw hex and bit width; map NaN/Inf to explicit symbolic
  values instead of non-standard JSON numbers.
- [x] Implement `bind_debug_firmware(request, client)`. Reuse the complete
  current build-result/identity/Git/input/ELF/MAP/flash chain from 0403 without
  introducing a weaker mtime rule. The current observation session may differ
  from the flash source session, but workspace/probe/target/build/ELF must
  match and both session IDs are recorded.
- [x] Bind the exact client endpoint before hardware access, attach the exact
  probe/target, read every current file-backed segment, and revalidate disk
  evidence after readback. Changed, missing, redirect, partial, or mismatched
  evidence fails closed and writes nothing.
- [x] Prove binding is read-only by snapshotting project bytes, names, modes,
  mtimes, and Git porcelain.

---

## Task 2: Implement a real DWARF type and location graph

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/types.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py`
- Create: `tools/stm32-toolkit/tests/test_dwarf.py`
- Create: `tools/stm32-toolkit/tests/fixtures/dwarf/typed.c`
- Create: `tools/stm32-toolkit/tests/fixtures/dwarf/typed.elf`

- [x] Write RED tests against a real ELF/DWARF fixture for signed/unsigned
  8/16/32/64-bit integers, bool, IEEE-754 float32/64, enum known/unknown,
  typedef/const/volatile chains, arrays, nested structures, and pointers shown
  as addresses without implicit dereference.
- [x] Implement bounded `DwarfCatalog.from_elf()` using pyelftools DIEs and
  location expressions/lists. `lookup(expression)` accepts only identifiers,
  structure members, and constant in-range array indices; reject calls,
  arithmetic, dynamic indices, casts, and pointer dereference.
- [x] Types come only from current DWARF. Never infer type or signedness from
  byte size, symbol section, address, or variable name.
- [x] Return stable explicit failures for duplicate/ambiguous symbols,
  optimized-out/register-only/unavailable locations, unsupported expressions,
  bitfields, recursive/incomplete types, malformed/no-DWARF ELF, overflow, and
  addresses outside project-readable memory regions.
- [x] Bound ELF size, DIE count/depth, expression length, type size, array
  elements, catalog entries, and decode output before allocation or recursion.

---

## Task 3: Implement exact, side-effect-aware SVD parsing

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/svd.py`
- Create: `tools/stm32-toolkit/tests/test_svd.py`
- Create: `tools/stm32-toolkit/tests/fixtures/svd/STM32F429-exact.svd`

- [x] Write RED tests for exact device match, zero/ambiguous/family-only
  rejection, project-relative containment, junction/reparse/permission/size
  failures, and UTF-8/BOM/UTF-16 DTD/ENTITY rejection before XML parsing.
- [x] `select_svd(target_device, candidates)` accepts only an explicit bounded
  candidate tuple. It performs no ambient pack/network search and never falls
  back to a family-prefix guess. Zero or multiple exact matches return
  `SVD_SELECTION_REQUIRED`.
- [x] Parse bounded peripherals, clusters, register arrays, fields,
  `derivedFrom`, access, `readAction`, reset metadata, masks, and address
  arithmetic. Reject inheritance cycles, duplicate paths, malformed widths,
  overflow, and addresses outside project-readable regions.
- [x] Classify reads: write-only is always denied; read-clear/read-set/modify
  and unknown side effects require strict
  `acknowledge_access_risk is True` for a single requested read and are never
  eligible for sampling.
- [x] Prove all public paths are portable project-relative strings and all
  errors exclude raw exceptions and absolute roots.

---

## Task 4: Implement batched typed reads and finite sampling

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/sampling.py`
- Create: `tools/stm32-toolkit/tests/test_debug_read.py`
- Create: `tools/stm32-toolkit/tests/test_sampling.py`

- [x] Write RED tests for bounded variable/register expression counts, adjacent
  range merge, no cross-region merge, exact-length checks, split retry after a
  merged block failure, item-scoped errors, and complete binding evidence.
- [x] Implement `read_variables()` and `read_registers()` using only catalog
  locations or exact SVD addresses. Callers cannot provide raw address/size.
  Merge adjacent reads up to the protocol limit without crossing a memory
  region; if a merged block fails, retry original items independently.
- [x] Implement finite `sample_variables()` with applied interval 100–5000 ms,
  bounded sample count/duration/output, monotonic deadline scheduling, no
  catch-up storm, item isolation, and cancellation propagation with no orphan
  task or thread.
- [x] Report requested/applied interval, scheduled/actual timestamps, latency,
  actual rate, deadline misses, dropped samples, and per-item status. Stop on a
  changed firmware binding or lost lease.
- [x] Sampling creates no group, database, history file, WebSocket, background
  daemon, or persistent subscription; those are 0501 responsibilities.

---

## Task 5: Implement read-only Fault evidence

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/fault.py`
- Create: `tools/stm32-toolkit/tests/test_fault.py`

- [x] Write RED tests proving running/sleeping/reset targets return
  `FAULT_TARGET_NOT_HALTED` with no halt call. Test already-halted Cortex-M
  register capture, EXC_RETURN MSP/PSP and basic/extended frame selection,
  stack alignment, and partial/unavailable reads.
- [x] Read only a fixed allowlist of core and SCB registers/addresses. Decode
  CFSR/HFSR/DFSR/SHCSR and MMFAR/BFAR validity; reject arbitrary caller
  addresses and stack frames outside readable memory.
- [x] Symbolize PC/LR against the exact bound ELF. Symbolization failure keeps
  raw register/fault evidence rather than discarding it or guessing.
- [x] Bind the report to workspace, current observation session, flash source
  session, lease, probe, target, logical project, build ID, ELF SHA, confirmed
  time, and audit operation. Never resume, reset, write, or mutate project
  files.

---

## Task 6: Integrate, package, review, and merge

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/__init__.py`
- Modify: `docs/superpowers/plans/2026-08-07-stm32-toolkit-codex-continuation.md`
- Modify: `docs/superpowers/plans/2026-08-07-stm32tk-0403-flash-handoff.md`
- Create: `docs/codex/returns/STM32TK-0404-TYPED-DEBUG/implementation-report.md`
- Modify: this plan's checkboxes

- [x] Export public Python contracts without importing PyOCD during ordinary
  package import. Do not add protocol operations unless measured evidence shows
  repeated authenticated reads cannot satisfy the bounded sampling contract.
- [x] Run focused tests, full Toolkit pytest with branch coverage at least 90%,
  every new debug module at least 90%, compileall, `git diff --check`,
  changed-file inventory, no-suppression scan, credential/path leak scan, and
  forbidden write/control/process/network/XML API scan.
- [x] Build/install the wheel in a fresh external environment and load the
  typed debug contracts plus real DWARF/SVD fixtures outside the repository.
- [x] Run Windows NTFS path/cancellation/read-only gates. Defer Linux and any
  available real-board non-halting variable/register/Fault smoke honestly to
  0405; fake evidence never closes a physical gate.
- [ ] Commit product/tests before a separate report commit. Push a Ready PR,
  verify local/remote/PR identity, review the full accepted-base diff in a clean
  detached worktree, merge without deleting the remote branch only after all
  non-deferred gates pass.
