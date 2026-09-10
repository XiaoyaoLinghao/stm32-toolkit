# Monitor 100 ms read-plan software review

Verdict: SOFTWARE_COMPLETE_HARDWARE_PENDING.
Accepted product base: `e83ecdde272c68cf22245aceb06928c46c8b7d93`.
Approved design handoff: `adb2d68f497e6b71eb2f193a69fd281883c0a8d5`.
Reviewed CodeHead: `a8ee77cf4f35204c018d7a0cb067b19391b4e809`.
Implementation/test owner: existing Luna/max implementer, directly dispatched by the primary conversation.
Independent reviewer: primary conversation agent.
Review worktree: `D:\codex-tmp\m100-review-20260910`, clean at CodeHead.
No remote, deployment or hardware action occurred in this review.

## Behavior and complete-diff assessment

Reviewed the full accepted-base-to-CodeHead diff: approved design/plan and role-policy
updates, four permitted product files and three existing focused test files.
The continuous path prepares immutable resolved metadata once per successful full
admission, reads live target values each tick into a fresh result buffer, and preserves
two bounded SRAM/MMIO reads. Stable ticks omit firmware loading, Git subprocesses and
DWARF/SVD content revalidation. Pre/post directory, endpoint, committed attachment and
plan identity checks remain, followed by the sampler epoch/state publication check.

Preparation requires a valid admission token. Failure/cancellation and lifecycle
invalidation discard the affected plan without invalidating a newer generation.
An early review finding (successful catalog revalidation invalidated an active plan)
was corrected before CodeHead; the final regression proves plan preservation when
catalog identity remains unchanged. Standalone reads retain their full checks.

No connection-policy, backend, worker, firmware or control code changed. The retained
committed OBSERVE attachment check returns cached attachment evidence at
`probe/service.py:955-962`; it does not repeat physical open while that session is
committed. Continuous sampling does not introduce halt/reset/resume calls. This is
code/offline evidence, not a new physical non-interference measurement.

The approved guarantee is admission-bound imaging, not per-sample disk/flash-content
attestation. External edits or external flashing require stop/reconnect validation.
Samples and history retain their original binding; no sealing or rollback schema was added.

## Verification

Luna RED at the handoff: the new production-shaped stable-plan test failed because
`MonitorObservationSession._prepare_read_plan` did not exist (1 failure). Final Luna
run covered `test_debug_read.py`, `test_sampling.py`, `test_monitor_observation.py`,
`test_probe_session.py` and `test_sampler.py`: 195 passed, 1 skipped in 145.79 s,
exit 0. The only unconditional Windows skip in this set is
`test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state`
(`Windows directory handles deny rename`); this platform restriction is unchanged.
Luna also reported four-file compileall and diff whitespace checks passing.

The primary reviewer independently ran these CodeHead tests using Python 3.12, with
both Toolkit/Monitor source directories on PYTHONPATH and all temporary paths on D:.
`pytest -q -o addopts=''` selected the three new Toolkit functions for stable-plan
reuse, successful catalog revalidation and parameterized guard drift, plus the entire
existing `test_probe_session.py`, `test_sampler.py` and `test_debug_read.py` files.
Result: **115 passed in 95.47 s**, exit 0. Full-range `git diff --check` passed.
Review log: `D:\codex-tmp\m100-review-env\pytest-review.log`.
Log SHA-256: `e775b517b13708004e7e48727d56cb8187c35c99e83dc637056763577d378e29`.

These results verify host call reduction and affected correctness/compatibility;
they do not establish actual 100 ms target throughput. No wall-time fake was counted
as hardware evidence. The existing e83 three-observation PASS, replacement-board
54,896-byte flash/readback PASS and attempt 7 historical PASS are retained.

## Remaining work and artifacts

Prepare one offline candidate, then separately obtain deployment and one 30-second
physical measurement authorization under the approved timing/drop criteria. Until
that gate passes, actual 100 ms performance and the full goal remain unproven.
Task 9, Task 10 and VS10-A overall acceptance remain incomplete.

Cleanup of `D:\codex-tmp\m100-review-b1` and `m100-review-c1` was rejected before
process launch by automatic approval review (`blocked by policy`). Neither deletion
ran; no alternative deletion was attempted. The review log and the implementation
test roots are retained. No previous refused cleanup path was retried.
