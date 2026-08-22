# SDD ledger — plan: docs/superpowers/plans/2026-08-22-stm32-toolkit-0701-creation-plan-environment-truth.md

- Module/phase: STM32 Toolkit 0.7 / VS07-A implementation.
- Product accepted base: d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58.
- Implementation branch base: 6007fafc33ee801b8bda64540dcefa50eef8b26a.
- Specification/plan owner: GPT-5.6-sol primary agent.
- Implementer: `/root/vs07a_implementer`, one GPT-5.6-luna subagent, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch: codex/STM32TK-0701-CREATION-PLAN.
- Worktree: C:/tmp/stm32tk-0701-creation-plan.
- Remote authority: none; no push, PR, merge, tag, release, close, or remote branch mutation.
- Hardware/install authority: none in this slice; planning remains read-only.
- Bounded ownership exception: none.

- 2026-08-23 dispatch: implementation started at clean `6007fafc33ee801b8bda64540dcefa50eef8b26a`; Tasks 1-4 are sequential checkpoints owned by the same implementer.

- Task 1 RED: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py -q` failed at collection with the expected missing `stm32_toolkit.tool_support` module.
- Task 1 GREEN: implemented immutable ToolSupportProfile discovery and doctor `creationSupport`; `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py -q` passed (`32 passed`, exit 0; PYTHONPATH pointed at this worktree and TEMP used a disposable worktree directory due host temp ACL).
- Environment note: CubeMX is installed outside the standard C: candidates at the Windows App Paths registration `D:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe`, observed by the primary agent as `6.18.1-RC2`; product discovery includes the bounded App Paths lookup and does not execute CubeMX.
- Task 2 RED: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py -q` failed at collection with the expected missing `generation.creation` module.
- Task 2 GREEN: implemented immutable CreationRequest/CreationPlan and read-only inventory/digest binding; `py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_generation.py -q` passed (exit 0; 296 tests in this command, no skips/xfails).
- Task 3 RED: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_workflows.py ... -q` failed at collection with the expected missing `creation_workflows` module.
- Task 3 GREEN: added one read-only workflow plus CLI `project create-plan` and MCP `stm32_project_create_plan`; focused adapter/regression command passed (exit 0, 58 passed, one pre-existing warning; no skips/xfails). Updated the stale MCP registration expectation to include already-registered target/diagnostic tools and the new creation-plan tool.
- Task 4 GREEN: README/README_zh-CN and implementation report prepared. Exact complete slice command passed exit 0 with no skips/xfails (one existing runpy warning). Real doctor and create-plan both exited 0 against `C:\tmp\stm32tk-0701-observe-20260823`; CubeMX `6.18.1-RC2` via bounded App Paths, CubeCLT root `C:\ST\STM32CubeCLT_1.22.0`, GCC `14.3.1`, CMake `4.3.1`, Ninja `1.13.2`, plan blockers empty, mutated false, workspace snapshot unchanged. Doctor issue `VSCODE_MISSING` is recorded as ENVIRONMENT; test fixtures retain CUBEMX_MISSING coverage.
- Sol review round 1: F1–F5 PRODUCT findings received and corrected in `30382b0bbd89f0db04a933bf3cd8626a90df2e57`; focused and complete slice tests pass exit 0 with no skips/xfails. Fresh real observations remain doctor/create-plan exit 0, CubeMX `6.18.1-RC2`, native CubeCLT facts, empty blockers, `mutated=false`, unchanged workspace snapshot. Report CodeHead updated to this correction head before its next report commit.
- Sol review round 2: `REWRITE_REQUIRED`; F1/F2/F4 did not converge (fail-open invalid profile content, possible CubeMX process fallback, wrong tier order, missing ambiguity/version/timeout semantics, and non-proving parity/root tests). Local patching stopped. Replacement discovery boundary frozen in `docs/superpowers/specs/2026-08-23-stm32-toolkit-0701-discovery-boundary-rewrite-design.md` with execution plan `docs/superpowers/plans/2026-08-23-stm32-toolkit-0701-discovery-boundary-rewrite.md`; the same Luna/max implementer retains the slice.
- Replacement Task 1: implemented the coherent discovery-boundary rewrite with fail-closed support profiles, bounded metadata/native probes, static CubeMX/VS Code facts, explicit priority and ambiguity handling; commit `a35c1caf`.
- Replacement Task 2: restored the exact creation request contract, keyword-only frozen support dependency, CLI trusted-profile binding, and MCP runtime-pinned support reuse for doctor/create-plan; commit `2eb09e18`.
- Replacement verification: focused discovery/adapter tests and the exact complete slice command exited 0 with no skips/xfails; one pre-existing runpy warning. Real read-only doctor/create-plan observations remain unchanged: CubeMX `6.18.1-RC2` via registered App Paths, CubeCLT `1.22.0` native facts GCC `14.3.1`, CMake `4.3.1`, Ninja `1.13.2`, `VSCODE_MISSING` environment issue, empty plan blockers, `mutated=false`, and unchanged observation workspace snapshot.
- Replacement Task 3: implementation report and this ledger updated before report commit; report records code head `a8e6851f` and intentionally does not record its own final SHA.
- Static PE fact correction: CubeMX discovery now reads the registered executable's PE version metadata without enabling any process probe; focused tests and the complete slice were rerun successfully. CodeHead before report commit is `a8e6851f`.
- Replacement review round 1: Sol identified R1–R5 contract gaps. Final bounded revision added tier ordering/ambiguity handling, safe parent-chain enforcement, strict native evidence and creation blockers, production-parser metadata seam coverage, and CLI duplicate rejection. Product revision commit: `763c7698`; report records this code head before its report commit.
