# STM32 Toolkit 1001 Task 8 post-flash run transition plan

**Goal:** Start the exact newly programmed Target-test firmware after flash/readback and identity
proof, using the existing CONTROL authorization machinery before opening the Target transport.

**Architecture:** The public Target workflow injects its Probe Service CONTROL store into the
physical flash adapter. After the existing runner completes flash/readback and post-flash identity
proof, the adapter derives and consumes one exact `target.resume` authorization through the same
Probe client. The service's existing running-state proof gates transport open. General flash and
debug CONTROL behavior remain unchanged.

**Accepted base:** Toolkit `342447dd6049326e6df439b0adc778657ee548f2` (tree
`c98ae4607514c30a486fae83776dfa0f2bb55521`); project
`4bfcf9f95b1d761c9a82042d6ded751d068c1e06`.

**Ownership:** one GPT-5.6-luna/max implementation owner; GPT-5.6-sol independent reviewer. No
hardware or remote action.

## Task 1 - TDD RED

- Audit exact tracked/untracked and committed/uncommitted state at the docs head.
- Add a physical Target execution regression whose fake backend models MODIFY attach as halted,
  flash/readback as still halted, `resume` as running, and transport open as illegal unless running.
- Prove both normal and recovery execute currently lack the required transition or reach transport
  while halted. Record RED before product code.
- Add the smallest runner/adapter unit case needed to freeze post-flash identity before resume,
  exact CONTROL binding, and one-resume/no-retry behavior.

## Task 2 - bounded GREEN

- Extend `PhysicalTargetFlashAdapter` with the exact CONTROL authorization store and one bounded
  post-flash run-transition method.
- Compose `ControlAuthorizationClient.prepare()` with the same workspace/project/session/revision,
  target, build ID, and ELF SHA from the consumed Target binding, operation `target.resume`, and
  empty arguments; consume that exact digest through the same `ProbeClient`.
- In `TargetTestRunner.run()`, invoke the transition only for the physical adapter, only after the
  existing post-flash identity match, and before `transport.open`.
- In `target_test_execute()`, inject `supervisor.control_authorizations`. Do not expose a second
  store, service, route, protocol field, or public action.
- Preserve the outer absolute deadline, terminal parent authorization, and existing cleanup/error
  precedence.

## Task 3 - negative and order verification

- Prove identity mismatch after flash performs no resume and no transport open.
- Prove flash/readback failure performs no resume; resume failure performs no transport open or
  TestRun publication; no case can program twice or retry.
- Prove successful normal and recovery paths each have one attach, one flash, one CONTROL resume,
  a `running` proof, then one transport open.
- Prove general public flash and standalone CONTROL tests remain unchanged.

## Task 4 - proportionate local verification

- Run exact RED/GREEN nodes first.
- Run complete affected `test_target_runner.py` and the smallest physical-workflow selection that
  covers normal/recovery success and failure ordering.
- Run Probe client/service CONTROL tests only because the adapter now composes that existing public
  contract. Do not run build, package, release, Monitor, hardware, or unrelated suites.
- Run `git diff --check`, `git diff --name-only`, and final status. Clean only exact run-owned
  disposable output after preserving minimum failure evidence.

## Task 5 - independent Sol review

- Create a fresh detached worktree at the returned code head.
- Review the complete accepted-base-to-head diff and verify only the four frozen product/test paths.
- Re-run the exact order, negative, Target runner, and Probe CONTROL risk set under CPython 3.12.
- Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`; do not access hardware or remotes.

## Stop boundary

After software acceptance, update the ignored SDD ledger and stop before physical execution. The
previous action is consumed. A new probe attach, target read, reset/resume, flash, or Target execute
requires a new explicit hardware authorization.

