# POST134 specification D — offline flash failure investigation

Date: 2026-10-28. Offline, documentation-only slice. **No hardware, probe discovery,
connect, flash, reset, halt, resume, installation, network download, package build, test
execution or product change occurred.** No test, hardware or self-acceptance PASS is
claimed.

## Identities and evidence

- Accepted base: `7e578ca1395ffa3b9743bef5a9fe55c40912eed6`.
- Source head this corrected report is written at (pre-report head):
  `ccc5d9994ac93571227d204786f9cefdb4e66e2e`, branch `codex/post134-flash-investigation`.
- Governing scope: [specification](../../../superpowers/specs/2026-10-28-post134-usability.md)
  section D and the [bounded plan](../../../superpowers/plans/2026-10-28-post134-usability.md).
- Procedure reference: [standard test procedure](../../../testing/standard-test-procedure.md).

### Supplied evidence (coordinator-copied read-only snapshots; originals unchanged)

| Snapshot | SHA-256 | Notes |
| --- | --- | --- |
| `C:/work/stm32/fresh-flash-1.json` | `0bba74a47fcfd3c2a451d7366bdc22b7a6ed56f33de357f82dfe5c2c68be6934` | Only log that carries `flashOptions` + `recoverySuggestion` |
| `C:/work/stm32/v130-test/flash-2.json` | `67dff5f35f5561c0e5c29ec58434bcb3e9a065b13c1337a06ccbb14f2bcec2f6` | `programDiagnostic` only; no options, no runtime identity |
| `C:/work/stm32/v130-test/flash-3.json` | `67dff5f35f5561c0e5c29ec58434bcb3e9a065b13c1337a06ccbb14f2bcec2f6` | Byte-identical to `flash-2.json` |

| Source snapshot | SHA-256 |
| --- | --- |
| pyOCD `flash/flash.py` | `2385cdc3f8425baef7cbc75ffd6f74daf374e5185c77bceb56b5b35c66a1b7d7` |
| pyOCD `target_STM32F429xx.py` | `d40d52966ae1744c5e4bcda618ba2b7c5961de8eca696f3f02bb34a7a30c1dc7` |
| pyOCD `METADATA` | `0170c581995cfbfa044f65f4839cfb5d5171a71fd45a080a07bf75181f92a3f1` (declares 0.45.1) |
| pyOCD `coresight_target.py` | `0c46ec4ca6af91f1c5f8617c02a68e05638fa640eb9681f863c83ed94514415a` |
| pyOCD `cortex_m.py` | `b99781362e763f7a3962cd5f70985a66e4ae9c48b9235af0d3a59a49889a9496` |

Hash pinning establishes only which snapshots were read; it does not identify the failing
run's runtime, which remains unrecorded (see the caveat below).

**These snapshots are comparison evidence, not proven failed-runtime identity.** The
failing run's pyOCD distribution/version is unrecorded; a matching message wording is
suggestive of the same code path, not proof of byte-identical runtime code.

## 1. What the diagnostic literally shows

All three logs carry the same failure shape: `code: PROBE_PROGRAM_FAILED`,
`message: "Probe worker operation failed"`, `data: null`, and
`details.programDiagnostic.stage = "program-call"` with one
`pyocd.core.exceptions.FlashFailure` whose message is `target was not halted as expected
after calling flash algorithm routine (IPSR=3)`; `address`, `errno`, `winerror` and
`resultCode` are all `null`.

1. **Stage `program-call`.** Toolkit `probe/pyocd_backend.py:195-211` raises
   `programmer-create` for `FileProgrammer(...)` construction and `program-call` for
   `programmer.program(...)`; `1558-1564` wraps that exception with the failing stage.
   The `FileProgrammer` was therefore constructed and the failure arose inside
   `program()`.
2. **Which pyOCD branch.** In the 0.45.1 snapshot this exact wording is emitted only at
   the non-running/non-halted branch of `wait_for_completion`
   (pyOCD `flash/flash.py:668-672`), reached after a `get_state()` that returned neither
   `RUNNING` nor `HALTED`. It is **not** that function's timeout branch.
3. **Not a timeout symptom.** The wait loop (`648-663`) returns its timeout result from
   the `while`–`else` path; the observed branch requires a `break`, so the loop exited on
   an observed non-RUNNING state rather than by budget exhaustion. (`Timeout.check()`
   semantics were inferred from the loop structure; `pyocd/utility/timeout.py` was not
   in scope.)
4. **IPSR=3.** After the branch, pyOCD calls `halt()` and reads `ipsr` (`669-670`);
   `cortex_m.CORE_EXCEPTION[3]` is HardFault. Under this source model that is a captured
   HardFault context. It is **not** a root cause, and it does not prove that the SWD link
   cannot be involved.
5. **`resultCode: null`** is consistent with the `668-672` raise, which carries no
   `result_code`. It is not a general exclusion: `Flash.init()` (`flash.py:255-265`) can
   raise `FlashFailure` with a result code, so `FlashFailure` as a type does not by itself
   rule out an algorithm-error path. Only the message text narrows the branch.

## 2. Where the failure sits in the Toolkit pipeline

Managed path (`stm32_flash`) only, all three logs. Toolkit sources: `probe/flash.py`,
`probe/pyocd_backend.py`, `probe/worker.py`, `probe/service.py`, `hardware_workflows.py`.

1. `flash_firmware` (`probe/flash.py:840-953`) reloads and re-admits the firmware, then
   attaches; a modify-level attach requires the target to end up halted
   (`service.py:1018-1021`, `probe/pyocd_backend.py:1041-1048`). **This attach/halt step is
   a source-model inference, not a log fact:** it assumes the supplied current Toolkit
   source matches the code that actually ran. The log establishes only that execution
   reached the program call (stage `program-call`), not that this source identity produced
   it. Under that assumption a failed attach would have reported `PROBE_ATTACH_FAILED`
   with an `attachDiagnostic` instead, so the reaching of the program call is consistent
   with attach/halt having succeeded first.
2. `_validate_attachment` (`probe/flash.py:790-802`) requires the resolved part number to
   match and `core_count == 1`.
3. `_remove_stale_result` (`probe/flash.py:832-837`, called at `870`) deletes
   `artifacts/migration/flash-result.json` **before** programming. A failed attempt
   therefore destroys the previous known-good receipt; evidence must be copied first.
4. `program_verified_elf` → `service.py:1144-1158` → `PyOCDBackend.flash_elf`
   (`probe/pyocd_backend.py:1539-1568`) with `chipErase="sector"`, `trustCrc=False`,
   `keepUnwritten=True`, `fileFormat="elf"`.
5. Post-program verification, the identity re-read and the success receipt
   (`probe/flash.py:805-829`, `879-889`) are never reached on failure; `data: null` is
   the expected consequence.

**Cleanup on this path (corrected).** `ProbeBackendWorker.call` invokes
`abort_owned_execution()` (`worker.py:524`) and `worker.py:567-581` terminates that exact
worker. `hardware_workflows.py:1248` then runs `_cleanup` over the clients/service and
may promote a cleanup failure into the result. The supplied JSON contains **no detailed
cleanup fragment** for this program-failure path, so the raw logs do not establish the
final physical state (clean close, target left halted/locked up, or reset). They do not
show that cleanup was skipped or unchecked.

## 3. Normal versus recovery policy (source-level, not observed behaviour)

Both policies use the same backend; they differ in session options at
`probe/pyocd_backend.py:980-996`: `connect_mode` `halt` vs `under-reset`, frequency
(default or explicit vs forced 100 kHz at `worker.py:129-135`), and pyOCD init-sequence
reset handling (`coresight_target.py:227-230`, `243-248`, `258-271`).

- Under-reset forces 100 kHz (`worker.py:92-97`, `probe/pyocd_backend.py:421-426`,
  `hardware_workflows.py:1008-1021`), so under-reset and 100 kHz cannot be separated by
  that entry point: an under-reset attempt at 100 kHz changes two variables at once.
- Normal policy with explicit `frequencyHz=100000` is accepted (`worker.py:84-99`,
  `hardware_workflows.py:1035-1043`).
- The `recoverySuggestion` is emitted for every program failure under the normal policy
  without inspecting the diagnostic (`hardware_workflows.py:1113-1120`), so its presence
  in `fresh-flash-1.json` says nothing about cause.
- `flash-2.json`/`flash-3.json` carry no options or runtime identity. Their difference
  from the fresh log is consistent with predating the FLASH-FREQUENCY slice, but the
  logs themselves establish **nothing** about the frequency, connect mode, Toolkit
  version or board revision used. Those attributions come only from the user's report,
  recorded here as report, not as proven log fact.

## 4. Hypotheses (unranked; none established)

| # | Hypothesis | Discriminating evidence not available |
| --- | --- | --- |
| H1 | Firmware-established processor state at halt (MPU, clocks, VTOR, live interrupts) is hostile to the RAM-resident algorithm | No MPU/clock/vector evidence; pyOCD `Flash.init` has configurable `reset=False` and halt/reset preparation, and the actual call sequence for this run is not established |
| H2 | Target/algorithm selection (wrong part, `F429xG` vs `F429xI`, protection/option bytes) | No recorded target identity; `data: null`; no option-byte or protection read |
| H3 | Flash algorithm execution faulted (phase-specific init/erase/program failure, stack use) | No trace phase; no fault-cause registers; the algorithm has no `end_stack`, so pyOCD's stack-canary check is skipped — that means no canary detection, not that overflow is proven or that it must cause this message |
| H4 | SWD link reliability at 1 MHz produced a wrong non-halted state read | No link-quality or DHCSR evidence; IPSR=3 is consistent with, but does not separate, H1–H4 |

The `analyzer_address` == `page_buffers[1]` overlap in the supplied target snapshot may be
intentional; nothing here establishes a defect. The logs do not support causal
elimination between H1–H4, and a single later success would not do so either.

## 5. Known facts and explicit unknowns

Established: the failure occurred inside `FileProgrammer.program()`; its message matches
pyOCD's non-running/non-halted branch, not the timeout branch; one log (`fresh-flash-1`)
records a normal-policy attempt with explicit `flashOptions`; the historical pair is
byte-identical and records neither options nor runtime; the recovery suggestion is
actionable recovery guidance but does not identify the root cause; no supplied evidence
shows any recovery attempt, successful or otherwise.

Unknown, and not answerable from the supplied data: which algorithm call failed; which of
`RESET`/`LOCKUP`/`SLEEPING` was observed; `CFSR`/`HFSR`/`DFSR`/`MMFAR`/`BFAR`/`SHCSR`/
`VTOR`/`DHCSR` values; MPU and clock configuration at halt; connected part and flash size;
Toolkit and pyOCD identities of the failing run; pyOCD trace logging; session timeout
options; whether this target ever flashed successfully and with which firmware; the
`SoCTarget` indirection used by `Flash`; and the exact `FileProgrammer`/`FlashLoader`
erase-program-verify order (both `pyocd/core/soc_target.py` and
`pyocd/flash/file_programmer.py`/`loader.py` were outside the supplied read scope).

## 6. Future investigation (separately authorized hypotheses only)

Not an execution plan, and not authorized by this report. The current user instruction
expressly forbids hardware access; any hardware step additionally requires a filled
execution card per the standard test procedure.

1. **Offline reconciliation first:** pin the source, runtime, probe and target identity
   behind `fresh-flash-1.json`, and establish the target's previous known state. Without
   that, no comparison of these logs is interpretable.
2. **If hardware is later authorized:** a bounded comparison of a normal-policy 100 kHz
   attempt against a controlled normal-policy 1 MHz attempt started from the same initial
   state, which separates frequency from connection policy; phase and fault diagnostics
   captured inside that same authorized owned operation. The existing normal 1 MHz log
   (`fresh-flash-1.json`) records the normal configured 1 MHz attempt, but the runtime that
   produced it and the controlled initial physical state are unrecorded, so it is not a
   controlled baseline; the historical pair (`flash-2.json`/`flash-3.json`) records no
   options at all.
3. An under-reset 100 kHz attempt changes two variables at once and cannot attribute a
   result to frequency.
4. No automatic reattach after a failure and no sequence of attempts; first failure stops.

## 7. Invocation limitations and limits of this report

- The first draft run performed one `src`-root search outside its declared `read_scope`
  and was rejected as an invocation; that violation is not retroactively accepted. This
  report is a separately bounded correction pass over the existing file only: no new
  discovery, no source reads, no searches, no scope expansion.
- Purely static and offline. No probe enumeration, connect, halt, reset, flash, readback,
  installation or test ran in either pass; no test or hardware PASS is claimed.
- The snapshots are comparison evidence only; byte-identity with the failing runtime is
  unestablished.
- Conclusions depending on `SoCTarget` indirection or the programmer/loader order remain
  open.
- This report is submitted for primary review; it does not accept itself, change product
  behaviour, or grant hardware authority.
