# STM32TK-1001: 100 ms continuous Monitor sampling

Status: APPROVED — user authorized implementation on 2026-09-10 after reviewing the governing behavior change.
Accepted product base: `e83ecdde272c68cf22245aceb06928c46c8b7d93`.
Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
Design, dispatch, integration, review and acceptance owner: primary conversation agent, independent of model name.
Implementation and implementation-test owner: one directly assigned `gpt-5.6-luna`, reasoning `max`.
Authority: local implementation and offline verification; no remote, deployment or new hardware operation.

## Problem and preserved results

The e83 replacement-board run `vs10a-task8-e83-observe2-20260910-09` passed typed
testtime, GPIOE.ODR/PE4 transitions and same-batch correlation. Its four batches took
1.078–1.125 seconds each and recorded 43 deadline drops at a configured 100 ms interval.
Every stable batch still loads firmware twice, launches four Git subprocesses, and
revalidates ELF/MAP/SVD content. This is avoidable host work, not evidence of a hardware limit.
Keep this physical PASS, the 54,896-byte replacement-board flash/readback PASS and
attempt 7 historical PASS. Task 9, Task 10 and VS10-A remain outside this acceptance.

## User scenarios

1. Connect to the running board using the existing halt-then-resume connection policy;
   start a 100 ms group containing testtime and GPIOE.ODR. Perform complete admission
   verification once and repeatedly read without halt, reset or resume operations.
2. Pause and resume monitoring. Pause invalidates the old read plan; resume performs
   full admission again and creates a fresh plan. Late results from the old epoch
   cannot reach history or subscribers.
3. Lose the connection/lease, change the active group revision, stop, close or cancel
   during a read. Use the existing terminal/blocked lifecycle and discard stale results;
   do not reconnect, control the core, or retry a hardware session automatically.

## Read-plan and validation contract

- Apply the optimization only to continuous Monitor sampling. Keep public standalone
  reads, catalog operations and their existing complete validation behavior compatible.
- At each start/resume admission, keep the existing full firmware binding and target
  image readback, host evidence checks, DWARF and SVD validation. This runs before the
  timed sampling window and does not add a halt/reset/resume operation.
- Compile the admitted selectors into a private immutable read plan using existing
  expression resolution, region/size checks, SVD readAction/access policy and decoding.
  Cache metadata and read instructions, never sampled target values. Preserve selector
  ordering, duplicates policy and existing per-item unsupported/error behavior.
- Bind a plan to the owning observation/client endpoint, workspace, session, probe,
  lease, firmware binding and exact ordered watch set. The sampler owns its existing
  epoch and group revision; the observation owns its plan identity/invalidation token.
  Neither becomes an independent replacement source of truth for the other.
- Before and after the reads, verify directory/root identity, both client/observation
  endpoints, plan identity and the existing committed logical attachment. Retain the
  same-session attachment check; it must not open a new physical attachment. The
  service continues to enforce lease and read authorization for each request.
- Stable ticks do not load firmware, run Git, read/hash ELF/MAP/SVD/canonical flash
  evidence, or re-resolve expressions. They reuse the plan and existing bounded reads.
  For the two-item scenario retain two physical ranges: SRAM and MMIO must not be
  combined, over-read or widened to reduce transactions.
- A successful report and timestamp are constructed only after the post-read guard.
  Pre-guard failure performs zero reads; post-guard failure publishes no batch. Preserve
  existing Monitor error mappings, item-result rules and cancellation propagation.

### Explicit change from the previous contract

Continuous samples describe the firmware image verified at start/resume admission.
They do not assert that host files or canonical flash evidence were rehashed at each
sample. External file edits or flashing through another tool during RUNNING are not
automatically detected. To observe a changed image, stop and reconnect through the
existing flow with matching evidence; do not silently rebind an active run.
Resume revalidates the existing binding and fails if it has changed. There is no new
public reload endpoint. An external target change without a connection/lease change
is not guaranteed to be detected. Running target readback is not an atomic snapshot.

Do not retrofit sealing flags, retrospective history invalidation, metadata watchers,
TTL/background attestations or new evidence schemas to conceal this contract change.
Stored samples retain the existing exact binding; history is not relabeled as a fresh
per-sample firmware attestation. Public standalone checks remain unchanged.

## Lifecycle and ownership

Prepare a plan only after successful full admission and before admitting RUNNING.
Publish the plan only if that admission still owns its lifecycle generation. Failed or
cancelled preparation leaves no usable plan. Start/resume must invalidate the old
generation before preparing its replacement, not erase a newly installed plan afterward.

Pause, stop, block and close synchronously invalidate the plan through the existing
sampler lifecycle before yielding. Reads capture the plan locally and verify it is
still current after awaits. The sampler keeps its existing epoch/state publication
check. A watch-set mismatch is an invalid plan, never a reason to resolve/rebuild on
the hot path. Close rejects future preparation/reads. No cache survives a connection
or observation-session change. Do not add locks, tasks, queues or scheduling deadlines.

## Scope and non-goals

Product scope is limited to Toolkit `debug/read.py`, `monitor_observation.py` and
Monitor `probe_session.py`, `sampler.py`, plus their existing focused tests. The
primary agent owns this design and its plan; the sole Luna/max implementer owns those
product/test files. Any necessary scope increase returns to the primary agent first.

No connection-policy/backend/worker protocol changes, pack changes, SWD frequency
changes, firmware changes, 50 ms target, UI rewrite, generic profiler, new public
schema, sealed history or whole-project verification matrix. Preserve existing
group-revision checking, scheduler/drop accounting, queues, history and export formats.
Connection may halt briefly and resume; continuous reads must not issue core control.

## Precision-wait implementation amendment (2026-09-10)

At accepted implementation base `575d90c0c8b289068d8bd859261782ee9a3eee44`,
QPC measures a real 111.6048ms adjacent-capture P95. A bounded host-only comparison
using the production sampler and identical existing fake stores/16ms fake reads
isolated the wait primitive: default asyncio wait had approximately110.400ms P95,
thread sleep approximately100.863ms. These exploratory nearest-index percentiles
are not the physical nearest-rank acceptance gate and do not upgrade prior evidence.

Refine only the existing sampler wait, preserving its single producer and absolute
QPC next_deadline. For more than50ms remaining, use existing asyncio sleep for the
coarse portion and recheck QPC. In the final at-most50ms, submit one pure wait to
the existing default executor. The worker recomputes remaining time from that
same absolute deadline when it actually starts; queued elapsed time must not be
added again. An expired deadline causes zero sleep. Cap a worker sleep argument
at50ms and recheck afterward. Do not busy-spin, change the event-loop clock/policy,
set global timer resolution, create a new pool, or add a background scheduler.

The producer owns this executor Future until completion, including after repeated
cancellation. Reuse the existing owned-await helper, widening its type from Task
to Future if needed; do not create another asyncio Task. Stop/close invalidate the
epoch as before and cannot finish while this wait Future remains pending. After
cancellation, propagate cancellation before group access or probe reading. No
promise is made about OS scheduling or executor queue latency; only the worker's
requested blocking sleep is capped. Pause/resume and all pre-read/post-read guards
remain unchanged. No wait touches a target, store, binding, lease or read plan.

This is an implementation refinement of the approved sampling scenarios, not a
new public timing/API promise. Physical thresholds and separate authorization
for deployment and a fresh physical run remain unchanged.

## Acceptance

Offline evidence must prove one plan per admission, reuse across multiple ticks,
zero hot-path loaders/Git/source revalidations, two authorized physical reads per
successful two-item batch and zero sampling-induced halt/reset/resume calls. Cover
pre/post guard failure, watch mismatch, failed/cancelled prepare, pause/resume and
epoch/close races without stale publication. Verify frozen address/access restrictions
and affected standalone-read compatibility. Fakes prove these contracts, not 10 Hz.

After separate deployment and hardware authorization, use one fixed 30-second measured
window following successful admission, with the same board/probe/firmware/two watches.
Select all batches captured within [windowStart, windowStart + 30 s); no warm-up trimming
inside that window. Proposed practical 100 ms acceptance, not a hard-real-time promise:

- At least 297 complete valid two-item batches, at least 9.9 valid batches/second.
- P95 actual adjacent-capture interval <=110 ms and P99 <=150 ms, calculated from
  monotonic intervals (existing actualRateHz may be inverted); report maximum too.
- P95 scheduled-to-captured delay <=100 ms, and at most 3 deadline drops in the window.
- No service/history/subscriber drops; all three existing functional criteria pass;
  no core control after admission, no retry, release and runtime cleanup succeed.

Use all measured samples, nearest-rank percentiles and existing status/export fields;
report read latency separately because it excludes the group-store lookup. Record a
wall-clock discontinuity as unusable wall-clock delay evidence, never clamp it into PASS.
If the gate fails, retain actual rate/distribution/drops and classify the bottleneck
offline. Existing seams may record host guard and real-read spans in the authorized
single run; no additional target operations or generic instrumentation framework.
Do not call software completion physical 100 ms acceptance or automatically retry.
