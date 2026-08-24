# STM32 Toolkit 0.8 VS08-B implementation report

## Handoff

- Slice: VS08-B recovery, isolation, and human checkpoints, Task 1.
- Accepted base: `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`.
- Specification/plan head: `79f6317d8fb7899bc2b24171ef4d516acbd837af`.
- Product/tests CodeHead: `b78870ac` (`feat(acceptance): add recoverable isolated attempts`).
- Branch/worktree: `codex/STM32TK-0802-VS08-B` / `C:\tmp\stm32tk-0802-vs08b`.
- Implementer: sole `gpt-5.6-luna`, max reasoning; independent acceptance remains with GPT-5.6-sol.
- Remote state: no upstream, unpushed, no PR or other remote action.

## Scope delivered

Implemented the closed immutable `AcceptanceAttempt` model and frozen recovery policy, the project-bound append-only recovery adapter, bounded revision-chain loading, existing Evidence mutation-lock publication, retry/concurrency conflict handling, deadline/resume projections, explicit single-use source-change authorization, and the five CLI/MCP projections. The adapter only reads the existing Project, Build, Test, Diagnostic, Acceptance, and Evidence authorities; it does not execute stages or add a controller, runner, scheduler, daemon, provider, transport, Probe backend, Python support, mutable head/index/database/lock, or a new Evidence store. `acceptance-attempt` is the sole new typed root and uses the existing EvidenceStore.

Replay/fixture data is required to carry `executionSource: replay` and `physicalTransportEvidence: false`; no physical PASS is claimed. Hardware evidence remains deferred external evidence.

## TDD evidence

The original RED output was preserved before the host interruption and is reported exactly as evidence, without reconstruction:

1. `py -3.12 -m pytest tests/test_acceptance_recovery_model.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-red-model-correct` failed collection with `ModuleNotFoundError: No module named 'stm32_toolkit.acceptance.recovery'`.
2. `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-red-workflow` failed collection with `ModuleNotFoundError: No module named 'stm32_toolkit.acceptance.recovery_workflows'`.
3. CLI RED failed three tests because `begin_acceptance_attempt`, `checkpoint_acceptance_attempt`, and `show_acceptance_attempt` were absent from the CLI module.
4. MCP RED failed two tests because the five attempt tools and the MCP module's `begin_acceptance_attempt` symbol were absent.

After production changes, focused recovery/adapter tests completed with exit 0; the VS08-B vertical suite completed with exit 0; the VS08-A scenario suite completed with exit 0; the four existing boundary tests completed with exit 0. The exact affected regression matrix from the plan completed with exit 0 and one existing platform-capability skip. The first post-resume VS08-A collection attempt used an incorrect relative monitor `PYTHONPATH` and was classified as an environment invocation error; the corrected absolute-path run passed. No product failure was deferred.

## Verification commands

- `py -3.12 -m compileall -q src tests` — exit 0.
- `git diff --cached --check` before the product/tests commit — exit 0.
- Focused recovery, CLI, MCP, GC, and VS08-B suites with an isolated basetemp — exit 0.
- `tests/test_vs08a_scenarios.py` with corrected absolute toolkit/monitor `PYTHONPATH` — exit 0.
- Existing hardware/probe/target boundary tests named by the plan — exit 0; no hardware was executed.
- Plan’s full affected matrix, with corrected absolute toolkit/monitor `PYTHONPATH` and `C:\tmp\stm32tk-0802-vs08b-green-final` — exit 0; one existing platform-capability skip.

The report commit is intentionally not named here. The CodeHead above is the product/tests commit required for independent review.
