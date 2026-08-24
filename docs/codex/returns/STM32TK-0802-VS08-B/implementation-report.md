# STM32 Toolkit 0.8 VS08-B implementation report

## Handoff

- Slice: VS08-B recovery, isolation, and human checkpoints, Task 1.
- Accepted base: `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`.
- Specification/plan head: `79f6317d8fb7899bc2b24171ef4d516acbd837af`.
- Product/tests CodeHead: `38972842729f944359a58b3d696752f44d9fd6d5` (`fix(acceptance): close replay authority and begin races`).
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

## Correction round 2

Independent review round 2 identified a canonical revision-chain semantic gap. The preserved RED reproduction was a public Keil revision-0 attempt followed by a canonical CubeMX revision-1 snapshot; public resume returned `True OK new-cubemx-project`. The correction validates immutable attempt/scenario/version/digest/policy/workspace/project/origin/execution/physical/opened fields, prior output and authorization continuity, timestamp/deadline policy, exact envelope parents/artifacts/produced time, and current project-origin binding on begin/show/resume/authorize/advance. Focused GREEN coverage includes scenario switch, prior-output rewrite, opened/deadline rewrite, authorization rewrite on an intact 0–6 chain, wrong/missing parent, artifact, produced-time mismatch, and public origin drift; all fail closed without publishing a new root. The round-2 affected matrix completed with exit 0; compileall and diff-check completed with exit 0. No hardware or remote action was performed.

## Correction round 3

Independent review round 3 was `REVISION_REQUIRED` for three bounded authority/concurrency gaps. The original RED output was not retained as a raw transcript; the following are result summaries from the exact focused commands, with no transcript reconstructed:

- `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py::test_failed_replay_target_only_mismatch_fails_closed -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-red-target` — RED, `1 failed` (`DID NOT RAISE`), PRODUCT: failed replay did not compare the published target device.
- `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py::test_source_declaration_before_authorization_fails_closed tests/test_acceptance_recovery_workflows.py::test_stale_diagnostic_revision_or_head_fails_closed_before_authorization -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-red-diagnostic` — RED, `2 failed` (both returned `OK`), PRODUCT: authorization did not reload Diagnostic authority.
- `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py::test_concurrent_identical_begin_returns_one_exact_revision_zero -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-red-concurrent` — RED, `1 failed`: one of two identical callers returned `ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED`, PRODUCT: publication race did not converge.

The correction adds the authoritative current-target comparison, reloads and validates the exact Diagnostic session/revision/event head/state/source-declaration set immediately before revision 5, and returns the exact existing revision-0 snapshot for identical requests serialized by the existing Evidence mutation lock. Distinct scenario/origin requests remain conflicts. The source-declaration and stale-authority tests now construct valid public Diagnostic snapshots rather than mocking the reader failure.

GREEN evidence:

- `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py::test_failed_replay_target_only_mismatch_fails_closed tests/test_acceptance_recovery_workflows.py::test_source_declaration_before_authorization_fails_closed tests/test_acceptance_recovery_workflows.py::test_stale_diagnostic_revision_or_head_fails_closed_before_authorization tests/test_acceptance_recovery_workflows.py::test_concurrent_identical_begin_returns_one_exact_revision_zero -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-green-final` — `4 passed`.
- `py -3.12 -m pytest tests/test_acceptance_recovery_workflows.py tests/test_vs08b_scenarios.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-focused` — exit 0; recovery workflow and both real Keil/CubeMX revision-7 verticals passed.
- `py -3.12 -m pytest tests/test_acceptance_recovery_model.py tests/test_acceptance_recovery_workflows.py tests/test_acceptance_recovery_mcp.py tests/test_acceptance_recovery_cli.py tests/test_acceptance_workflows.py tests/test_diagnostic_workflows.py tests/test_vs08a_scenarios.py tests/test_vs08b_scenarios.py -q --basetemp=C:\tmp\stm32tk-0802-vs08b-r3-matrix` — exit 0; `169` tests collected, no failure output.
- `py -3.12 -m compileall -q src` and `git diff --check` — exit 0.

No hardware, install, or remote action was performed. Product/tests CodeHead for this correction is the commit recorded in Handoff; the report commit is intentionally not named here.

## Verification commands

- `py -3.12 -m compileall -q src tests` — exit 0.
- `git diff --cached --check` before the product/tests commit — exit 0.
- Focused recovery, CLI, MCP, GC, and VS08-B suites with an isolated basetemp — exit 0.
- `tests/test_vs08a_scenarios.py` with corrected absolute toolkit/monitor `PYTHONPATH` — exit 0.
- Existing hardware/probe/target boundary tests named by the plan — exit 0; no hardware was executed.
- Plan’s full affected matrix, with corrected absolute toolkit/monitor `PYTHONPATH` and `C:\tmp\stm32tk-0802-vs08b-green-final` — exit 0; one existing platform-capability skip.

The report commit is intentionally not named here. The CodeHead above is the product/tests commit required for independent review; this report was written after that commit and will be committed separately.

## Independent GPT-5.6-sol acceptance

- Verdict: `ACCEPTED`.
- Accepted base: `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`.
- Product/tests CodeHead: `38972842729f944359a58b3d696752f44d9fd6d5`.
- Implementer report head reviewed: `5d9fea6d52de4fd5245315e0b19c2763a0b23812`.
- Reviewer: GPT-5.6-sol primary agent, independent of the sole Luna/max implementer.
- Review isolation: detached clean worktree at the exact report head; complete
  accepted-base-to-report diff reviewed. All round-1, round-2, and round-3
  product findings are resolved; no unresolved product defect remains.
- Independent focused recovery/CLI/MCP/VS08-B/Evidence-GC/MCP-server matrix:
  200 collected tests, exit 0.
- Independent Acceptance/Diagnostic/VS08-A/VS08-B integration matrix: 169
  collected tests, exit 0. Both Keil and CubeMX revision-7 software verticals
  passed from real existing authorities and fresh recovery contexts.
- Independent concurrent-begin probe: two results were `(True, OK)`, their
  stored attempts were exact-equal, and both were revision 0.
- Independent canonical scenario-switch corruption probe failed closed with
  `ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED` and published no later root.
- `py -3.12 -m compileall -q src tests`, complete diff check, frozen scenario
  and recovery-policy digest checks, prohibited-surface scan, credential scan,
  branch/upstream/remote audit, and report self-SHA check all passed.
- Verification generated no physical evidence and made no hardware, install,
  push, PR, merge, tag, release, or other remote action. Replay/fixture evidence
  remains software-only and is not physical PASS.
- Run-scoped basetemps, bytecode caches, and detached review worktrees were
  removed after evidence reconciliation. The implementation branch remained
  clean, local, unpushed, and without an upstream before this acceptance-only
  report update.

This acceptance section intentionally does not name its own commit. The
product/tests CodeHead above remains the immutable product review boundary.
