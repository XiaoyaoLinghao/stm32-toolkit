# Owned precision wait review

Accepted base: `575d90c0c8b289068d8bd859261782ee9a3eee44`.
CodeHead: `06ea5e90cdfaf34ddb0004c028d08b7b2a811ecb`.
Verdict: SOFTWARE_COMPLETE_HARDWARE_PENDING.

Main reviewed the complete base-to-CodeHead diff in clean
`D:\codex-tmp\m100-owned-wait-review-20260910`. The amended specification and plan
freeze the change from timer-based asyncio waiting to an owned precision Future
for the last50ms of the existing QPC deadline. Worker queue time consumes that
deadline. Expired workers do not sleep. Cancellation drains the Future before
propagating, and the producer checks lifecycle before group/probe operations.
No new pool, Task, lock, global timer setting, probe read or core control was added.

Luna/max reports four focused checks and43 full sampler tests passing (14.96s).
Main independently verified worker cap/expiry, coarse-wait cancellation,
stop/close with repeated cancellation and no later read, and existing slow-tick
drop accounting: five checks passed in2.62s. Complete-range diff check passed.
Log: `D:\codex-tmp\stm32tk-owned-wait-candidate-20260910\independent-review-pytest.log`.

The implementer ran one100-batch production-wait host smoke using existing fake
stores/16ms fake reads: approximate capture P95 100.753ms, maximum101.048ms,
zero deadline drops and successful stop. Evidence:
`D:\codex-tmp\m100-wakeup-offline-20260910\production_wait_results.json`.
The exploratory entry uses nearest-index percentiles, not formal nearest-rank
physical acceptance, and canceled sleep records are not successful wakeups.

Physical -11 remains300 complete batches/10Hz/zero drops, with QPC P95
111.6048ms and FAIL_P95_INTERVAL. This software result cannot replace that evidence.
The installed runtime remains575d90c0. A candidate and fresh -12 entry are prepared
offline; deployment and one physical30s window require new explicit authorization.
Attempt7 historical PASS and all previous functional evidence are preserved.
Task9, Task10, VS10-A and complete100ms physical acceptance remain incomplete.
