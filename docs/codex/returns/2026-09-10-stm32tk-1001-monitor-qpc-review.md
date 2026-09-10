# High-resolution sampler clock review

Accepted base: `6b7046f4fee7c356ac6bd723909bdabaa5bd8d31`.
CodeHead: `ee9c7f4f5f095ff5c022bada944e21eb652796e5`.
Verdict: SOFTWARE_COMPLETE_HARDWARE_PENDING.

The primary conversation independently reviewed the complete base-to-CodeHead
diff in clean `D:\codex-tmp\m100-qpc-review-20260910`. Product scope is six
sampler clock calls, now consistently perf_counter_ns, and one behavior regression.
Relative sleep/deadline policy, Unix fields, lifecycle and hardware reads are unchanged.

Luna/max implementation evidence: focused regression 1 passed; full sampler module
39 passed in 14.63s; compileall and diff check exited zero. The primary independently
ran the new precise-clock regression and existing slow-tick deadline test at CodeHead:
2 passed in 2.28s, exit zero. Log:
`D:\codex-tmp\stm32tk-qpc-candidate-20260910\independent-review-pytest.log`.
Complete-range `git diff --check` also passed. No unrelated module matrix was rerun.

The fresh -11 entry retains one connection, a fixed 30-second capture window, no
flash/retry and terminal cleanup. It uses QPC window timing, recorded clock precision,
resolution-aware clock consistency and a conservative upper bound for wall-time
scheduled-to-captured delay. Existing frequency/interval/drop limits remain intact.
Runner owner reports pure-function valid/slow/few/missing/100ms clock-jump checks
passing; its product/runtime pins remain NOT_READY until deployment.

Prior -10 evidence remains 300 functional batches/zero drops, with precise timing
acceptance incomplete. This review does not relabel it, accept Task9/Task10/VS10-A,
or supply hardware evidence. The user's current continued-testing request authorizes
the next bounded physical run described by the timing correction plan.
