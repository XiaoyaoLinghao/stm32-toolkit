# STM32TK-1001 Monitor Sampling Revalidation Budget Plan

**Status:** approved by the user on 2026-09-10; implementation completed and independently accepted  
**Accepted base:** `7f1a5215c291aa6b805bd4c3b7215bbc49540f50`  
**Specification:** `docs/superpowers/specs/2026-09-10-stm32tk-1001-monitor-sampling-revalidation-budget-design.md`

## Ownership and boundaries

One GPT-5.6-luna/max implementer owns the bounded product and focused tests in a clean detached D:
worktree. GPT-5.6-sol owns contract decisions, complete-diff review, focused independent
verification, and acceptance. No product work starts until the user accepts that the existing
per-tick attempt to compare all ELF load-segment bytes moves to full `start`/`resume` admission.
During RUNNING, changed load-segment bytes from an external writer are no longer fully scanned on
every tick. The existing comparison was already non-atomic with the following sample and did not
prove reset state or detect resets that left those bytes unchanged. No remote, package, deployment,
runtime, pack, hardware, or evidence action is authorized by this plan.

Applicable lessons: `STM32TK-EL-001` keeps one existing request deadline across any admission work;
`STM32TK-EL-002` forbids reuse of uncommitted or abandoned attachment evidence; and
`STM32TK-EL-003` forbids adding a lock, queue, task-admission point, or timeout boundary without a
design amendment. This slice adds none of those primitives.

## Implementation steps

1. **RED: freeze the two revalidation modes.** In existing fake seams, prove that current
   `sampling.start` permits the producer to enter full binding per tick. Add focused failing tests
   requiring exactly one full admission before a run, lightweight calls on ticks, and no history
   publication when either admission or lightweight validation fails.
2. **Implement the private lightweight path.** In `monitor_observation.py`, reuse the existing
   debug-read current-firmware/flash and logical-attachment guards, plus current root, endpoint,
   DWARF, and SVD guards. Return the existing mapped Monitor errors and no new details. Keep the
   existing full `revalidate()` byte-for-byte in behavior.
3. **Bind the sampler lifecycle.** In `probe_session.py`, adapt the new private method with the
   existing binding equality and error mapping. In `sampler.py`, await full revalidation before
   publishing start/resume success, then use only lightweight validation in `_produce`. Preserve
   the existing absolute deadlines, task/queue construction, drop accounting, pause/blocked/stop
   states, cleanup order, and pre-existing public response shapes. A failed start admission remains
   IDLE and returns `sampling.start` / mapped code / `sampling cannot be started` / `{}`. A failed
   resume admission enters PAUSED_BLOCKED and returns `sampling.resume` / mapped code /
   `sampling cannot be resumed` / `{}`. Cancellation before admission completion creates no run or
   producer/history task and retains the pre-call IDLE or PAUSED state.
4. **GREEN: focused contract checks.** Prove:
   - initial open and each start/resume call full verification once;
   - multiple ticks cause zero additional full-segment readbacks;
   - stable 100 ms fake sampling produces and persists batches;
   - build/ELF/flash, endpoint/session/lease, probe/target, root, DWARF, or SVD drift blocks before
     publication;
   - stop/release/close/new run cannot reuse the prior epoch;
   - admission failure creates no producer/history task and lightweight failure publishes no batch;
   - existing cancellation, queue draining, error codes/messages, and same-service committed attach
     reuse remain unchanged.
5. **Independent review.** Sol reviews the complete
   `7f1a5215c291aa6b805bd4c3b7215bbc49540f50..CodeHead` diff in a separate clean D: worktree,
   checks for hidden TTLs, skipped identity checks, new locks/queues/deadlines, public-schema drift,
   or extra hardware calls, and reruns only the affected focused nodes. Correctable findings return
   to the same Luna owner; two non-converging rounds stop for redesign.
6. **Local integration and report.** After ACCEPTED, fast-forward only the existing local
   `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl` branch and record accepted base and
   pre-report CodeHead in the tracked return report. Do not package, deploy, or claim physical PASS.

## Evidence mapping

| Claim | Required offline evidence |
| --- | --- |
| Full target proof remains at admission | production-seam call order and full-readback call count for open/start/resume |
| Per-tick full readback is removed | at least two produced ticks with full-readback count unchanged after admission |
| Identity remains fail closed | one focused parameterized drift test covering disk, endpoint/lease, attachment, DWARF/SVD classes |
| Lifecycle cannot leak an epoch | stop/new start, pause/resume, blocked, close/release call-order tests |
| Public behavior is compatible | unchanged success/error shapes and existing cancellation/cleanup tests |

No hardware result is part of software acceptance. A later candidate/deployment and one newly
authorized physical observation are separate integration gates.
