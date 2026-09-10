# STM32TK-1001 Monitor Batch Revalidation Design

**Status:** approved by the user on 2026-09-10; implemented and independently accepted
**Accepted base:** `4db09f65067e6cacbbe88c1c4c2e1f8dd19bd451`
**Specification owner / reviewer:** GPT-5.6-sol
**Implementation owner:** one GPT-5.6-luna agent at reasoning effort `max`
**Branch:** `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
**Remote authority:** none

## Problem and evidence boundary

The accepted admission change removed the complete target-image readback from stable sampling ticks,
but a stable two-item Monitor batch still repeats the same host and attachment guards around each
typed read. The replacement-board run `vs10a-task8-4db-observe2-20260910-07` published one batch in
five seconds with `latencyNs=3984000000` and `deadlineDrops=44`. Offline call tracing against the
accepted code proved that one variable plus one register currently causes nine
`_load_fresh_firmware` calls, eighteen Git subprocesses, five DWARF ELF revalidations, five SVD
revalidations, five same-session attachment IPC checks, and two actual memory-read IPC calls.

This proves avoidable repeated host validation in the batch path. It does not prove that host
validation is the only latency source and it does not prove that the 100 ms interval is attainable
after this slice. The user approved changing the private Monitor sampling path from per-read guards
to one guard before and one guard after the complete batch, with whole-batch discard on drift.

## Runnable scenarios

1. **Stable mixed batch.** One admitted RUNNING tick resolves and authorizes its variable and
   register requests, performs one same-session guard, executes the existing bounded reads in the
   existing variable-then-register order, performs one final same-session guard, and only then
   returns values to the sampler for persistence and broadcast.
2. **Identity drift inside a batch.** If disk firmware/flash evidence, endpoint, lease, committed
   attachment, DWARF, or SVD provenance fails before the reads, no memory read occurs. If any of
   those checks fails after one or more reads, every value from that tick is discarded, the sampler
   enters its existing blocked state, and neither history nor subscribers receive the batch.
3. **Cancellation or stale lifecycle.** Cancellation propagates without publication. Pause, stop,
   close, blocked state, or an epoch change while the batch is in flight makes the sampler discard
   the completed batch through its existing epoch/state check. No extra guard, hardware call, or
   wait is added to recover diagnostics after cancellation.

## Frozen batch contract

### Private entry and read policy

- The optimization is reachable only through the private Monitor sampling composition. Public
  standalone `read_variables`, `read_registers`, `sample_variables`, and `sample_registers` keep
  their existing request, guard, result, item-error, and cancellation behavior.
- Before the first memory read, the private batch path validates tuple shape and limits, resolves
  each DWARF expression and SVD path, checks address, byte size, and readable region, and applies
  the existing sampling-only SVD `readAction` rule with `acknowledge_access_risk=False`.
- The batch uses the existing read grouping, maximum-read-size, variable-first/register-second
  order, decoding, partial-read, fallback, and per-item error semantics. It does not permit a raw
  address, a wider region, a larger transfer, a register access acknowledgement, or a new read.
- The pre- and post-batch guards each verify the existing endpoint/session/lease binding, reload
  and compare current firmware and canonical flash evidence, revalidate both DWARF and selected
  SVD sources, and check the existing committed logical attachment. These checks use the same
  observation session and client; they do not create an attachment candidate or physical session.
- A successful result may be returned only after the post-batch guard succeeds. A pre-guard failure
  performs zero memory reads. A post-guard failure may follow already-completed reads but returns no
  values. Existing Monitor code mapping and fixed public messages remain unchanged and expose no
  private path or raw backend details.

### Lifecycle and publication

- Full target-image revalidation remains at initial Monitor open and each `sampling.start` and
  `sampling.resume` admission. No admitted epoch, binding, source result, or batch guard is cached
  across ticks.
- The sampler's current group-revision check runs before the private batch. After the batch returns,
  the existing epoch and RUNNING-state checks occur before a `SampleBatch` is built, queued, or
  broadcast.
- Cancellation from resolution, a guard, or a read is re-raised. The cancelled tick is never
  published. Cancellation does not trigger a compensating read, attach, reset, resume, retry, or
  extended deadline.
- Existing scheduling deadlines, missed-slot accounting, queues, history writer, locks, pause,
  stop, release, close, and error states are unchanged. No new lock, queue, task, deadline, TTL, or
  background cache is permitted.

### Exact stable two-item call budget

For the production-shaped batch containing one variable and one register, after `sampling.start`
admission and excluding the sampler's group-store lookup, the accepted implementation must reduce:

| Call | Accepted 4db tick | Required tick |
|---|---:|---:|
| `_load_fresh_firmware` | 9 | 2 |
| Git subprocesses attributable to those loads | 18 | 4 while one load still invokes two |
| DWARF/ELF source revalidation | 5 | 2 |
| SVD source revalidation | 5 | 2 |
| committed attachment IPC | 5 | 2 |
| memory-read IPC | 2 | 2 |

The counts are per completed stable tick. A guard failure may stop earlier. The Git count records the
current loader implementation rather than a new public promise. Even two loader calls can exceed
100 ms on the measured project, so this slice claims removal of same-batch duplication only. It
does not claim a strict 100 ms sampling rate or authorize a TTL, cross-batch cache, background
attestation, or relaxed drop accounting.

## Minimal scope and ownership

The single Luna/max implementer owns:

- `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`: extract only the private prepared/raw-read
  primitive needed to reuse existing grouping, fallback, decoding, and item-error behavior while a
  caller owns the two outer guards. Public entry points remain behavior-compatible.
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`: add the private mixed Monitor batch
  entry and own combined pre/post guard ordering and whole-batch discard.
- `tools/stm32-monitor/src/stm32_monitor/probe_session.py`: adapt the private batch result to the
  existing ordered `ProbeReadOutcome` and existing blocking/error mapping.
- `tools/stm32-monitor/src/stm32_monitor/sampler.py`: use the private guarded batch as the stable
  tick validation/read unit and remove the now-duplicate standalone lightweight call from that
  tick only.
- Focused tests in existing `test_monitor_observation.py`, `test_probe_session.py`, and
  `test_sampler.py`, plus existing debug-read tests only where the internal extraction needs a
  direct compatibility check.

`debug/sampling.py` remains unchanged: its existing sampling-only SVD resolver may be reused as a
private dependency. If preserving existing behavior requires another product file, implementation
stops and Sol amends the design before the file is touched.

## Non-goals

- No public read/API/schema/error change and no batching across ticks, groups, sessions, or probes.
- No removal of start/resume full target-image admission or weakening of disk, flash, endpoint,
  lease, target, region, access-risk, DWARF, or SVD checks.
- No new synchronization, cache, profiler, generic diagnostics, hardware operation, package,
  deployment, runtime, pack, remote action, or historical-evidence mutation.
- No claim that this alone makes 100 ms sampling achievable or that the prior physical run has
  been completed. The historical attempt 7 PASS remains separate; Task 9, Task 10, and VS10-A stay
  incomplete.

## Acceptance

Luna must first demonstrate the accepted nine-load/five-source/five-attachment behavior with the
existing production seam, then prove the required two/two/two/two/two counts on at least two
stable ticks. Focused failures must show zero reads on pre-drift; reads but zero publication on
post-drift; and zero publication on cancellation, pause, or epoch change. Existing public
standalone-read tests, region/access-risk tests, error mapping, deadline-drop accounting, and
start/resume admission tests must remain green. GPT-5.6-sol reviews the complete accepted-base to
CodeHead diff in a separate clean D: worktree and accepts only evidence from the returned commit.
