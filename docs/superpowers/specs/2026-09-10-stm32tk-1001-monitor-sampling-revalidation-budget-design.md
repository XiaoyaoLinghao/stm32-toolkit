# STM32TK-1001 Monitor Sampling Revalidation Budget Design

**Status:** approved by the user on 2026-09-10; implemented and independently accepted  
**Accepted base:** `7f1a5215c291aa6b805bd4c3b7215bbc49540f50`  
**Specification owner / reviewer:** GPT-5.6-sol  
**Implementation owner after approval:** one GPT-5.6-luna agent at reasoning effort `max`  
**Branch:** `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`  
**Remote authority:** none

## Problem and evidence boundary

The replacement-board OBSERVE run `vs10a-task8-7f1-observe1-20260910-05` started one
100 ms group for `testtime` and `GPIOE.ODR`, waited five seconds, and stopped cleanly,
but its exact run ID has zero SQLite history batches and values. The query used the same
session/run/group IDs and a one-second time margin. `sampling.stop` awaits the producer and
history writer before returning, so this is not a history pagination, filter, pump, or flush race.

The current first sampling cycle calls `ProbeSession.revalidate()`, which calls
`MonitorObservationSession.revalidate()`, which calls `bind_debug_firmware()` and reads back every
ELF load-segment byte. The current image has 54,896 verified bytes and OBSERVE uses 100 kHz. The
two catalog calls immediately before sampling also each revalidated through this bind path and
together occupied approximately 15.996 seconds between the binding confirmation and group creation.
This proves a product contract/performance defect: the advertised 100 ms–5 s sampling lifecycle
cannot make useful progress while every tick performs a full-image readback.

The physical run did not preserve a status snapshot before stop. Stop clears the blocked code,
run ID, and sequence. Therefore the exact physical branch that produced zero batches remains
unproved; this design fixes the independently demonstrated per-tick full-readback defect and does
not relabel it as the unique hardware-run root cause.

## Runnable scenarios

1. **Start one sampling epoch.** `sampling.start` performs one full firmware binding revalidation,
   including complete target segment readback, before it publishes a run ID or creates producer
   tasks. If that admission fails, the sampler remains IDLE and returns operation
   `sampling.start`, the revalidation's already-mapped code, fixed message
   `sampling cannot be started`, and empty details; no run or read is started.
2. **Sample inside the admitted epoch.** Each tick revalidates disk firmware/flash evidence,
   endpoint, lease, probe/target identity, root guard, and DWARF/SVD provenance through the same
   service/session, but performs zero complete firmware-segment readbacks. Existing before/after
   guards around the requested variable/register memory reads remain. A changed guard blocks the
   run before publishing that tick.
3. **Invalidate and re-admit.** Stop, release, service close, lease loss, reconnect, a new session,
   or a new run invalidates the epoch. Resume from pause performs a new full revalidation before
   returning to RUNNING. If resume admission fails, state becomes PAUSED_BLOCKED and the response
   is operation `sampling.resume`, the mapped revalidation code, fixed message
   `sampling cannot be resumed`, and empty details. Disk build/ELF/flash changes and
   probe/target/session mismatches continue to fail closed. No cached evidence crosses an
   observation-session lifetime.

## Security and identity contract

### Protected facts

- Initial open still performs the existing full-image readback and final binding checks.
- Every `sampling.start` and `sampling.resume` performs a fresh full-image revalidation before any
  new sample can be published.
- Every tick reloads and compares current project/build/ELF/flash evidence, verifies the guarded
  data root and exact endpoint/session/lease/probe/target, and revalidates DWARF/SVD provenance.
- Existing debug reads retain their before/read/after endpoint, current-firmware, logical attach,
  region, size, and decoding guards. The same-service logical attach must use only committed
  attachment evidence; no new physical attach, reset, resume, retry, or hardware operation is
  introduced.
- Any failed full or lightweight revalidation blocks before that tick is persisted or broadcast.
  Existing tick-failure status, sampler stop/cleanup behavior, and all pre-existing public
  codes/messages remain unchanged. The two fixed admission messages above are the only new public
  failure branches; they disclose no backend details.

### Epoch ownership and invalidation

The `MonitorSampler` owns one in-memory admitted epoch. It is created only after successful full
revalidation in `start`, retained across an uninterrupted RUNNING interval, invalidated on pause,
stop, blocked state, close, release, or service teardown, and recreated only by a successful full
`start` or `resume` admission. No timestamp/TTL cache, persisted token, global cache, new lock, new
queue, or new deadline is permitted.

A Toolkit reset, flash, or other control/modify workflow requires a different service/lease and
therefore cannot share the admitted OBSERVE epoch. It must stop/release OBSERVE first; a later
Monitor connection or run performs full admission again.

### Required user risk decision

The present implementation attempts, before every sample, to read and compare all ELF load-segment
bytes with the locked ELF. A successful comparison proves only that the returned load-segment bytes
matched at the moments they were read. It is not atomic with the later sample, does not prove the
bytes remain unchanged between the scan and that sample, and does not detect a reset that leaves
those bytes unchanged.

The recommended contract moves that complete load-segment comparison to each
`start`/`resume`/reconnect admission point. During the admitted RUNNING interval, another debugger,
another probe, or target self-programming could change load-segment bytes without a complete scan
on every tick. Toolkit's own lease and lifecycle prevent a second Toolkit operation, but cannot
exclude those external writers. An ordinary read may fail, and the next full admission may detect
changed load-segment bytes, but neither outcome is guaranteed for the current tick. Reset state,
non-load memory, and the non-atomic interval after a successful scan were already outside the
existing full-readback proof and are not newly weakened by this design.

Implementation requires explicit acceptance of that residual delta. If the existing per-tick
attempt to compare every ELF load-segment byte must remain, this slice must not proceed: the 100 ms
contract cannot be met with the current generic full-image comparison, and a separate attestation
design would be required.

## Minimal product scope

- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`: add one private lightweight
  same-session revalidation seam by reusing the existing debug-read current-firmware and logical
  attachment guards; retain the existing full `revalidate()` path.
- `tools/stm32-monitor/src/stm32_monitor/probe_session.py`: expose the private lightweight method
  only to the sampler and preserve existing result/code mapping.
- `tools/stm32-monitor/src/stm32_monitor/sampler.py`: make full revalidation an admission step for
  start/resume, use lightweight revalidation per tick, and invalidate the epoch at existing
  lifecycle transitions.
- Focused tests only in `test_monitor_observation.py`, `test_probe_session.py`, and
  `test_sampler.py`; use `test_runtime.py` only if the existing production-composition seam cannot
  prove the public start path.

`debug/firmware.py`, Probe Service/client/worker/backend, wire schemas, SQLite, CLI/MCP, runtime,
pack selection, flash evidence, and hardware behavior are out of scope. Importing the already-owned
private disk and attachment guards avoids duplicating their authority; if implementation proves
that reuse impossible without editing `debug/firmware.py`, Sol must amend this scope before code.

## Non-goals

- No claim that this was the unique physical reason for the zero-batch run.
- No blind TTL cache, skipped disk/lease/endpoint checks, or reuse across run/session boundaries.
- No per-tick full-image scan, background attestation task, new synchronization primitive, or
  hardware-specific checksum protocol.
- No public schema or error change and no change to stop-state reporting in this slice.
- No package, deployment, runtime, pack, hardware, remote, or historical-evidence mutation.

## Acceptance

The slice may enter implementation only after the residual-risk decision above is approved. Luna
must prove by call counts that open and each start/resume retain full verification, each stable tick
performs zero full segment readbacks, drift blocks without publishing a sample, and lifecycle
invalidation cannot reuse an epoch. Sol reviews the complete accepted-base-to-code-head diff and
runs only these focused offline checks.
