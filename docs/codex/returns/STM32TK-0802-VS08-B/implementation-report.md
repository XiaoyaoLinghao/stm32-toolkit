# STM32 Toolkit 0.8 VS08-B implementation report

## Handoff

- Slice: VS08-B recovery, isolation, and human checkpoints, Task 1.
- Accepted base: `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`.
- Specification/plan head: `79f6317d8fb7899bc2b24171ef4d516acbd837af`.
- Product/tests CodeHead: `fc83263304d5d949191ac1ba49d8405a196670fa` (`fix(acceptance): close VS08-B retry and lineage gaps`).
- Branch/worktree: `codex/STM32TK-0802-VS08-B` / `C:\tmp\stm32tk-0802-vs08b`.
- Implementer: sole `gpt-5.6-luna`, max reasoning; independent acceptance remains with GPT-5.6-sol.
- Remote state: no upstream, unpushed, no PR or other remote action.

## Scope delivered

Implemented the closed immutable `AcceptanceAttempt` model and frozen recovery policy, the project-bound append-only recovery adapter, bounded revision-chain loading, existing Evidence mutation-lock publication, retry/concurrency conflict handling, deadline/resume projections, explicit single-use source-change authorization, and the five CLI/MCP projections. The adapter only reads the existing Project, Build, Test, Diagnostic, Acceptance, and Evidence authorities; it does not execute stages or add a controller, runner, scheduler, daemon, provider, transport, Probe backend, Python support, mutable head/index/database/lock, or a new Evidence store. `acceptance-attempt` is the sole new typed root and uses the existing EvidenceStore.

Replay/fixture data is required to carry `executionSource: replay` and `physicalTransportEvidence: false`; no physical PASS is claimed. Hardware evidence remains deferred external evidence.

## TDD evidence

The original RED output was not retained as a raw transcript across the host interruption. The following result summaries are the preserved/original evidence; no exact transcript is claimed or reconstructed:

1. `py -3.12 -m pytest tests/test_acceptance_recovery_model.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-red-model-correct` failed collection with `ModuleNotFoundError: No module named 'stm32_toolkit.acceptance.recovery'`.
2. `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-red-workflow` failed collection with `ModuleNotFoundError: No module named 'stm32_toolkit.acceptance.recovery_workflows'`.
3. CLI RED failed three tests because `begin_acceptance_attempt`, `checkpoint_acceptance_attempt`, and `show_acceptance_attempt` were absent from the CLI module.
4. MCP RED failed two tests because the five attempt tools and the MCP module's `begin_acceptance_attempt` symbol were absent.

After the correction round, the focused recovery suite completed `15 passed`; the real Keil/CubeMX VS08-B vertical completed `2 passed`; and the affected recovery/model/CLI/MCP/VS08-A regression command completed with exit 0. The plan matrix completed with exit 0 and one existing platform-capability skip. The first post-resume vertical invocation used an incorrect relative monitor `PYTHONPATH` and was classified as ENVIRONMENT; the subsequent absolute-path invocation passed. The first temporary monitor-fixture rewrite omitted its required fixture digest and was classified as TEST_FIXTURE; redigesting the rewritten software fixture passed. No product failure was deferred.

## Correction round 1

Independent review round 1 was `REVISION_REQUIRED`. New RED summaries were captured before correction: the identical project checkpoint retry command returned `1 failed` with `ACCEPTANCE_ATTEMPT_REVISION_CONFLICT`; the seven-case diagnostic lineage command returned `7 failed` because the production validator had no `expected_session_id` contract; and the real vertical returned `2 failed` at monitor-fixture ingestion until the rewritten fixture digest was repaired. The final-completion vertical then exposed `2 failed` with `ACCEPTANCE_ATTEMPT_INPUT_INVALID` from the UUID/hash mismatch in `acceptanceRecordId` validation. These are result summaries, not retained raw transcripts.

The correction adds exact immutable retries for all checkpoint stages and source authorization, identity-bound diagnostic sessions and source hashes, fail-closed chain/root/orphan/copy isolation checks, exact-deadline coverage, one-workspace concurrent publication, and real reader-chain vertical coverage through revision 7 for both origins. Verification: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py tools/stm32-toolkit/tests/test_vs08b_scenarios.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r1-affected-1` — `15 passed` in the focused recovery portion and `2 passed` vertical origins; `py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` — exit 0; `git diff --check` — exit 0.

## Verification commands

- `py -3.12 -m compileall -q src tests` — exit 0.
- `git diff --cached --check` before the product/tests commit — exit 0.
- Focused recovery, CLI, MCP, GC, and VS08-B suites with an isolated basetemp — exit 0.
- `tests/test_vs08a_scenarios.py` with corrected absolute toolkit/monitor `PYTHONPATH` — exit 0.
- Existing hardware/probe/target boundary tests named by the plan — exit 0; no hardware was executed.
- Plan’s full affected matrix, with corrected absolute toolkit/monitor `PYTHONPATH` and `C:\tmp\stm32tk-0802-vs08b-green-final` — exit 0; one existing platform-capability skip.

The report commit is intentionally not named here. The CodeHead above is the product/tests commit required for independent review; this report was written after that commit and will be committed separately.
