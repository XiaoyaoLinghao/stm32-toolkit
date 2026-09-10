# STM32TK-1001 Monitor Batch Revalidation Plan

**Status:** approved by the user on 2026-09-10; implementation completed and independently accepted
**Accepted base:** `4db09f65067e6cacbbe88c1c4c2e1f8dd19bd451`
**Specification:** `docs/superpowers/specs/2026-09-10-stm32tk-1001-monitor-batch-revalidation-design.md`
**Specification owner / reviewer:** GPT-5.6-sol
**Implementation owner:** one GPT-5.6-luna agent at reasoning effort `max`

## Boundaries and lessons

The implementation changes only the private Monitor stable-tick path from repeated per-read guards
to one pre-batch and one post-batch guard. Public standalone debug reads retain their existing
behavior. `STM32TK-EL-001` keeps the existing absolute deadline and prevents late work after an
expired request; `STM32TK-EL-002` permits only committed same-session attachment evidence; and
`STM32TK-EL-003` prohibits introducing a new lock, queue, task-admission point, or timeout boundary.
This slice introduces none. No package, deployment, runtime, pack, hardware, remote, or evidence
operation is authorized.

## Implementation and verification

1. **Isolate and RED.** Commit the approved design and plan, then create one clean detached D:
   worktree. Preserve the already-recorded `-07` baseline instead of repeating profiling. In the
   existing production-shaped observation/ProbeSession/sampler seams, add failing expectations for
   the required two-load/two-DWARF/two-SVD/two-attachment/two-read result and whole-batch discard.
2. **Extract the private prepared-read seam.** In `debug/read.py`, reuse the current resolver,
   grouping, bounded-transfer, fallback, decode, and item-error machinery with a caller-supplied
   raw memory reader. Keep every public entry on its existing per-read `_memory_read` guard path.
   Do not change `debug/sampling.py`; reuse its existing private sampling register resolver.
3. **Compose one guarded Monitor batch.** In `monitor_observation.py`, resolve and authorize all
   requested variable/register items before reads, run the combined existing guard, execute the
   existing variable-first/register-second reads, and run the same combined guard after them.
   Return no value if either guard fails. Cancellation propagates without a compensating operation.
4. **Connect the private path.** In `probe_session.py`, require and call only the private batch
   method for sampler reads, preserve input ordering and item errors, and map malformed or failed
   results through the existing safe Monitor outcome. In `sampler.py`, remove the separate stable
   tick `_revalidate_lightweight()` call because the private batch now owns both guards. Retain the
   group check, post-await epoch/state check, blocked transition, timing boundaries, queues, and
   drop accounting.
5. **Focused GREEN.** Prove the exact two-load/two-DWARF/two-SVD/two-attachment/two-read completed
   tick budget over at least two ticks. Prove pre-drift makes zero reads, post-drift publishes no
   history/subscriber batch, and cancellation/pause/epoch changes publish nothing. Verify unchanged
   public standalone read guards, SVD sampling access rules, binding/error mapping, start/resume
   full admission, and scheduling/drop behavior. Run only the existing affected test modules or
   focused nodes; do not run a release matrix.
6. **Independent review and integration.** GPT-5.6-sol reviews
   `4db09f65067e6cacbbe88c1c4c2e1f8dd19bd451..CodeHead` from a separate clean D: worktree. Review
   rejects hidden caches, new synchronization/deadlines, public behavior drift, guard calls outside
   the two batch boundaries, relaxed address/region/access checks, or publication before post-guard.
   Correctable findings return to the same Luna owner. After ACCEPTED, fast-forward only the
   existing local implementation branch and add a tracked report that records accepted base and
   pre-report CodeHead. No push is permitted.

## Required evidence

| Claim | Focused evidence |
|---|---|
| Stable batch deduplicates guards | production-shaped two-tick call-order and exact call counts |
| Access remains bounded | existing variable region/grouping and SVD sampling readAction tests |
| Drift is atomic at publication | pre- and post-guard drift with memory/history/broadcast counts |
| Lifecycle stays closed | cancellation and in-flight pause/stop/epoch-change tests |
| Compatibility is retained | public standalone debug-read tests and unchanged Monitor errors |

Performance acceptance is the deterministic call-budget reduction. Wall-clock speed and a later
physical 100 ms observation are integration evidence and are not software-slice acceptance gates.
