# Owned precision wait correction

Accepted base: `575d90c0c8b289068d8bd859261782ee9a3eee44`.
Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
Governing contract: precision-wait implementation amendment in the approved
2026-09-10 monitor-100ms-read-plan design. The primary conversation owns design,
integration and independent review; the existing sole Luna/max product agent owns
implementation and implementation tests. No deployment/hardware/remote authority.

Implement only in sampler.py and its existing test_sampler.py. Replace the single
relative await-sleep at the producer deadline with the specified QPC wait helper.
Reuse the default executor and owned-await helper; one Future at a time, no new
Task, pool, lock, queue, system timer configuration, or thread touching product state.
Worker queue time consumes the existing absolute deadline; bound its sleep argument
to50ms. Cancellation must drain the owned Future, then propagate before any next
group/probe work. Long periods retain coarse asynchronous waiting and prompt
cancellation before a precision Future is submitted. Preserve scheduler drop policy.

Required evidence: focused regressions for expired/queued deadline (no restarted
relative sleep), the50ms sleep cap, long-period coarse cancellation, and stop/close
during an active owned precision wait with no later probe read. Reuse existing
fixtures and lifecycle helpers. Keep the precise capture-rate/latency regression;
adjust its clock seam only as required by the changed wait implementation. Run the
full existing sampler module once after focused checks pass; no unrelated matrix.

Then execute one100-batch host-only smoke using the existing local experiment
entry's single-condition function with the new production wait and identical fake
stores/16ms fake read. No baseline replay, new profiler or hardware. Label fake
evidence explicitly. Main independently reviews the complete base-to-CodeHead diff
in a clean D: worktree and checks only the affected deadline/cancellation behavior.
After software acceptance, prepare one reviewable offline candidate; fresh
deployment and a single physical30s run remain pending explicit authorization.

Evidence references: -11 physical result and offline-timing-decomposition.json;
D:\codex-tmp\m100-wakeup-offline-20260910\offline_experiment.py and offline_results.json.
The exploratory experiment uses an approximate percentile estimator and includes
one final canceled sleep in aggregate sleep records; neither is formal acceptance.
Previous functional PASS and Task9/Task10/VS10-A boundaries remain unchanged.
Keep all artifacts on D: and never retry cleanup previously denied by policy.
