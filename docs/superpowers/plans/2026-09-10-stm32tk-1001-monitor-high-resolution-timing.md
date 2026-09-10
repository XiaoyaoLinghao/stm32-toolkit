# Bounded high-resolution timing correction

Accepted base: `6b7046f4fee7c356ac6bd723909bdabaa5bd8d31`.
Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
The primary conversation owns this amendment, integration and independent review;
one Luna/max owner implements product code/tests, a separate Luna/max owner owns
the run-local measurement entry. No remote action is authorized.

This amends the approved 2026-09-10 monitor-100ms-read-plan design only in clock
selection and measurement precision. The user requested continued testing after
the identified timing correction. No new public API, error, state or hardware
operation is introduced. Existing 100ms performance thresholds remain unchanged.

Scenarios: (1) sample the existing two watches using one high-resolution monotonic
clock for deadlines, latency and actual intervals; (2) preserve pause/stop and
slow-read missed-deadline behavior; (3) distinguish wall-clock quantization from a
detectable discontinuity when reviewing one fresh physical window.

Evidence: run `vs10a-task8-6b7046f4-observe1-20260910-10` obtained 300 complete
mixed batches in 30 seconds with no drops. The runner's 5ms clock discrepancy
threshold was below the deployed Python 3.12 clocks' advertised 15.625ms
resolution. That run remains unmodified, with functional PASS and incomplete
precise performance acceptance. QPC-backed `perf_counter` on that runtime reports
100ns resolution. Old timestamps cannot be reconstructed as QPC measurements.

Product ownership is limited to `tools/stm32-monitor/src/stm32_monitor/sampler.py`
and `tools/stm32-monitor/tests/test_sampler.py`. Replace all six sampler
`time.monotonic_ns()` uses with `time.perf_counter_ns()` so all sampler monotonic
arithmetic uses one domain. Keep relative asyncio sleeps, deadline policy,
wall-clock Unix fields, lifecycle, reads, guards and public schemas unchanged.
Do not mix old and new clock epochs or patch process-global time functions in tests.

Use one production-shaped deterministic regression for precise sub-tick latency
and adjacent-capture rate with a distinct clock origin; verify deadline accounting
and existing lifecycle through the full existing sampler test module. No Toolkit
or release matrix rerun is required. Main agent reviews the complete base-to-code
diff in a clean D: worktree and independently checks the focused regression plus
existing slow-tick behavior. Preserve existing valid read-plan evidence.

The run-local entry reuses -10 as a fresh -11 runner, with new single-use identity
and final candidate/runtime pins supplied after deployment. Use perf_counter_ns
for window elapsed time, record deployed time/perf_counter clock info, and reject
insufficient monotonic precision. Compare adjacent wall/monotonic intervals in
sequence order using an explicit resolution envelope: twice the sum of advertised
wall and perf-counter resolutions plus 5ms host-call skew allowance. Apply the
same envelope to window clock consistency. Report both raw scheduled-to-captured
P95 and its conservative upper bound (raw P95 plus that envelope); require the
upper bound <=100ms. Do not change interval P95<=110ms/P99<=150ms, >=297 complete
mixed batches, all drop gates, or functional criteria. Missing evidence cannot PASS.
Use only a few pure-function examples for valid/slow/missing/clock-jump evidence;
no generic instrumentation or diagnostics framework, extra target calls or repeats.

After software review, build and deploy one exact candidate using the existing
offline wheelhouse and official entry, archive the prior runtime for rollback,
then run one newly authorized 30-second OBSERVE. Connection may halt/resume as
already approved; sampling must not halt/reset/resume. No flash, automatic retry,
frequency/pack changes or second session. A terminal failure ends hardware work.
Root owns deployment and physical evidence. Attempt 7 PASS, Task9/Task10/VS10-A
boundaries remain unchanged. All disposable output remains on D:.
