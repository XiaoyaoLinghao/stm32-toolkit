# STM32TK-1001 Flash Readback Timeout Correction Design

Date: 2026-09-03
Module / phase: STM32TK-1001 / VS10-A H2 physical acceptance correction
Status: FROZEN FOR USER REVIEW
Full accepted base: `d462f0ba868ae3cb980544a5a3c746ee7fc996c2`
Accepted-base tree: `ceeb30c228290bad48dacc2372d7978fe4acc113`
Accepted product code head below the report commits: `35da97e57939636c021e74802f3604dc2da5f914`
Accepted product tree: `9de8bbbeeefad697810c130a3b60f265527786de`
Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
Remote tracking baseline: `origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
at `74ee5f4c7872af1bb612c9068af36319457e087b`; local accepted base is 42 commits
ahead and 0 behind that local tracking reference
Specification owner and final reviewer: GPT-5.6-sol primary
Implementation owner after separate specification and plan approval: exactly one GPT-5.6-luna
agent at reasoning effort `max`
Remote action: none authorized
Hardware action: the prior one-attempt authorization was consumed; no further hardware action is
authorized by this specification

## 1. Trigger and exact failure boundary

The accepted public recovery command was executed once with the exact accepted Toolkit source,
CPython 3.12.10, PyOCD 0.45.1, the fixed 100 kHz SWD / connect-under-reset profile, the accepted
opaque probe selector, and exact build/ELF pins. The command emitted both PyOCD progress bars and
then returned:

```json
{
  "ok": false,
  "operation": "stm32_flash",
  "code": "PROBE_TIMEOUT",
  "message": "Probe backend operation timed out"
}
```

The operation had passed the accepted attach, single-core, target identity, and halted-state gates
before entering `flash.program`. Because programming had begun, the target contents after the
timeout are unknown. Toolkit correctly published no `flash-result.json`, released the probe lease,
left no hardware-owner process, performed no automatic retry, and did not run the planned public
bind/read confirmation.

The retained physical evidence is:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-under-reset-recovery-timeout-20260903-01.json`;
- SHA-256 `34b52662ff2dc07c55a995916327bd94601932431adcc0a60476f0a3822ce3c2`.

The product call chain is deterministic:

1. `FlashRequest.timeout_ms` defaults to 30,000 ms and is already validated within `1..30000`.
2. `flash_firmware()` passes that budget to `program_verified_elf()`.
3. After programming, `_verify_segments()` reads each ELF load segment in chunks of at most
   65,536 bytes.
4. `_verify_segments()` currently calls `ProbeClient.read_memory(address, length)` without a
   deadline argument.
5. `ProbeClient.read_memory()` consequently sends the generic request default of only 5,000 ms.

The first accepted ELF load segment is 51,852 bytes. At 100 kHz, its 414,816 payload bits alone
require about 4.15 seconds before SWD request, ACK, parity, turnaround, address setup, transport,
and Python/PyOCD overhead. Therefore a fixed 5-second deadline cannot reliably contain that
bounded read. The observed total duration and timeout after programming progress are consistent
with the first verification read exhausting this deadline. No additional hardware execution is
needed to establish the missing timeout propagation.

Failure classification: `PRODUCT` — the flash transaction validates and owns a 30-second native
operation budget but fails to propagate it to its required post-program readback. This finding does
not establish that the programmed bytes are correct or incorrect, and it does not change the
previously accepted recovery connection profile.

## 2. Runnable user scenarios

### Scenario 1 - ordinary observation reads retain their accepted deadline

Existing callers of `ProbeClient.read_memory(address, length)` without an explicit timeout continue
to send exactly 5,000 ms. Variable reads, debug binding, register/fault flows, Monitor, and all
other observation paths receive no broader waiting policy and no new public option.

### Scenario 2 - flash verification uses the flash transaction's existing budget

After one authorized normal or recovery flash has completed programming, every existing bounded
load-segment readback request carries the same validated `FlashRequest.timeout_ms` value used by
the program operation. The public workflow continues to construct the default 30,000 ms request.
For the accepted 51,852-byte segment, the service and worker therefore receive 30,000 ms rather
than the generic 5,000 ms observation default.

The deadline is per existing bounded read chunk, not an unbounded whole-process wait. The chunk
limit remains 65,536 bytes and the accepted `FlashRequest` maximum remains 30 seconds.

### Scenario 3 - a readback timeout still fails closed

If any segment read does not reach a terminal response within the propagated budget, Toolkit
retains the existing `PROBE_TIMEOUT` behavior, publishes no success result, releases the lease and
owned processes through the existing cleanup path, and performs no retry, reconnect, second
programming attempt, reset, or evidence bypass.

### Scenario 4 - only complete exact readback creates trusted evidence

All ELF load-segment bytes must still match before the existing disk/build revalidation and atomic
schema-version-1 `flash-result.json` publication. A successful result remains the sole trust input
for public debug bind/read/Monitor. The timeout correction adds no result field, alternate evidence,
or direct-PyOCD import path.

## 3. Selected architecture

### 3.1 Preserve the generic client default and add one internal explicit budget

`ProbeClient.read_memory()` gains one keyword-only argument whose default preserves all current
callers:

```python
async def read_memory(
    self,
    address: int,
    length: int,
    *,
    timeout_ms: int = 5_000,
) -> bytes:
    data = await self.request(
        "memory.read",
        {"address": address, "length": length},
        timeout_ms=timeout_ms,
    )
```

The existing protocol decoder remains the single authority for the `1..300000` request bound.
There is no CLI/MCP parameter, schema field, environment variable, configuration file, or
recovery-only public API.

### 3.2 Reuse the already validated flash request budget

`_verify_segments()` receives the typed flash request's validated timeout and forwards it on each
existing chunk:

```python
actual = await client.read_memory(
    segment.address + offset,
    length,
    timeout_ms=timeout_ms,
)
```

`flash_firmware()` passes `typed.timeout_ms` to both `program_verified_elf()` and
`_verify_segments()`. The default public transaction therefore uses 30 seconds for programming and
30 seconds for each bounded verification read. The source of truth remains `FlashRequest`; no
parallel timeout constant or recovery flag is introduced in `probe/flash.py`.

### 3.3 Unchanged lifecycle and dependency direction

The change stays inside the existing CLI/MCP -> flash workflow -> ProbeClient -> Probe Service ->
single worker -> PyOCD backend path. The service, worker, backend, recovery connection policy,
protocol schema, flash program call, result format, and consumers remain unchanged.

## 4. Alternatives considered

### Reduce the readback chunk size while retaining 5 seconds

Rejected. A smaller chunk would make the current board more likely to pass but would not express
the actual flash-operation budget, would add more IPC/SWD calls, and would still depend on an
unproven frequency/latency threshold.

### Change every `ProbeClient.read_memory()` call to 30 seconds

Rejected. It would silently broaden unrelated observation, debug, fault, and Monitor behavior.
Those paths did not fail and must retain the accepted 5-second default.

### Add a recovery-specific read timeout or public timeout knob

Rejected. Exact readback is part of both ordinary and recovery flash. A special recovery field
would duplicate state already owned by `FlashRequest`, expand the public compatibility surface,
and make the same transaction behave through two timeout authorities.

### Retry the physical command or trust the apparent programming progress

Rejected. The consumed attempt crossed an irreversible boundary and produced no complete
readback. Progress bars are not trusted evidence, and a second physical attempt requires a new
authorization after software correction and independent acceptance.

## 5. Error, lifecycle, and safety contract

- No public error code or message changes.
- Invalid request deadlines retain the existing protocol/request validation.
- The 5-second default remains exact for callers that omit the new internal keyword.
- Flash verification forwards only the already validated `FlashRequest.timeout_ms`.
- Programming remains at most once per invocation.
- Each verification read remains at most 65,536 bytes and at most 30 seconds for the public flash
  request.
- Timeout, cancellation, partial read, mismatch, disk/build change, cleanup failure, and result
  publication failure retain their accepted precedence and fail-closed behavior.
- No stale or new success result survives an unsuccessful current attempt.
- No automatic retry, reconnect, target fallback, reset, resume, or run action is added.

## 6. Bounded implementation ownership

The sole GPT-5.6-luna/max implementer may change product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.

The implementer may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_client.py`;
- `tools/stm32-toolkit/tests/test_flash.py`;
- `tools/stm32-toolkit/tests/test_debug_firmware.py` only if the genuine producer-to-binder test
  seam must accept the new keyword-only argument.

The implementation report, when required, is limited to:

- `docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md`.

`hardware_workflows.py`, CLI, MCP, Probe Service, worker, PyOCD backend, schemas, connection
profiles, flash-result consumers, runtime, dependencies, packaging, README, Skills, Monitor, and
all other product files are frozen. If TDD proves another product file must change, the implementer
stops and reports the exact conflict.

## 7. Required TDD evidence

Tests must be committed RED before product code and directly prove:

- omitted `ProbeClient.read_memory()` timeout still forwards exactly 5,000 ms;
- an explicit 30,000 ms read forwards exactly 30,000 ms without changing address/length or
  operation level;
- `flash_firmware()` forwards its exact validated `FlashRequest.timeout_ms` to programming and
  every verification chunk;
- the accepted 51,852-byte first segment is not silently split, skipped, or accepted without exact
  byte comparison;
- every readback chunk remains bounded to 65,536 bytes;
- a read timeout/failure after one program call produces no retry and no `flash-result.json`;
- a mismatch still removes/withholds success evidence;
- complete matching readback still publishes the unchanged exact flash-result field set;
- the genuine produced result remains consumable by the existing binder, while a missing result
  still blocks before hardware access.

Tests must not sleep for physical durations, forge a recovery-only result, weaken existing exact
field assertions, delete the prior recovery tests, or change unrelated product behavior to make a
fixture pass.

## 8. Proportionate verification and evidence owners

### Slice verification - Luna/max implementation owner

Use the accepted CPython 3.12 runtime, candidate source/test `PYTHONPATH`, `-p no:cacheprovider`, and
a fresh external run-owned basetemp. Run only the affected client, flash, and genuine binder tests.
Add a specific protocol/service test only if RED demonstrates that the existing decoder does not
accept the already-supported 30,000 ms value. Do not run the prior seven-file recovery suite,
full suite, coverage, package, UI, release, or hardware checks without a concrete new risk trigger.

Run `git diff --check`, inspect exact changed paths, preserve minimum failure evidence, and clean
only exact run-owned temporary output.

### Independent review - Sol primary

Create a fresh detached clean worktree at the returned report head. Review the complete
`d462f0ba868ae3cb980544a5a3c746ee7fc996c2..CODE_HEAD` product/test diff and the separate report
commit. Re-run the same focused matrix with a new Sol-owned external basetemp. Acceptance requires
default 5-second compatibility, exact flash-timeout propagation, unchanged one-program/no-retry
behavior, complete readback-before-publication, unchanged trust schema, accurate report lineage,
and clean status.

### Physical acceptance - new explicit authorization after software acceptance

The implementer runs no hardware. Software acceptance does not reuse the consumed authorization.
A new one-attempt public recovery flash requires a new explicit user authorization. On success,
run one read-only public bind/read confirmation; on failure, preserve minimum evidence and stop
without retry.

## 9. Explicit non-goals

- No second service, worker, runtime, backend, controller, provider, or MCP registration.
- No change to 100 kHz SWD / connect-under-reset or ordinary 1 MHz / halt policies.
- No public timeout, frequency, PyOCD option, retry, or recovery-evidence parameter.
- No global change to observation/read/debug/Monitor timeouts.
- No chunk-size, program-option, target gate, result-schema, or consumer change.
- No Agent-specific, VS Code-specific, or Keil-specific product logic.
- No new Python, OS, probe, target, or board support claim.
- No install, package, release, CI, collaboration automation, push, PR mutation, merge, tag, close,
  or remote branch deletion.
- No hardware operation before independent software acceptance and a new authorization.

## 10. Acceptance and stop boundary

The correction is accepted only when all four scenarios are directly proven, the focused CPython
3.12 matrix passes, the full accepted-base-to-code-head diff has no unresolved product, safety,
compatibility, or scope defect, the implementation report is accurate, and implementation/review
worktrees and run-owned artifacts are clean or explicitly classified.

After software acceptance, stop. Do not reuse the consumed hardware authorization, automatically
run another recovery attempt, enter VS10-B, or publish remotely.
