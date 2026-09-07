# STM32 Toolkit 1001 Task 8 Probe Service RAM-order correction plan

**Goal:** Preserve all valid writable Project v3 regions while presenting them in canonical
ascending address order at the existing Probe Service target-transport boundary.

**Architecture:** The Service remains the owner of fresh project-to-runtime transport
reconstruction. It sorts only its complete local writable-region projection before passing it to
the existing backend and transport validators. Every validator, error, worker, recovery, flash,
deadline, protocol, and public surface remains unchanged.

**Accepted base:** Toolkit product `215bfe13ee556509cca907bde5a00b8132982149`; docs start
`7fbfed05690fc30b71cfe145d5592adeb53882bd`. Project
`4bfcf9f95b1d761c9a82042d6ded751d068c1e06`.

**Ownership:** one GPT-5.6-luna/max implementation owner; GPT-5.6-sol independent reviewer. No
hardware or remote action.

## Task 1 - TDD RED

- Audit tracked/untracked and committed/uncommitted state at the exact docs head.
- Add a Service-level regression with the accepted manifest order
  `IROM1, IRAM1, MAILBOX, IRAM2` and a fake already-attached production boundary.
- Assert the exact backend runtime RAM configuration must be
  `IRAM2, IRAM1, MAILBOX`, every region is retained once, and transport open performs no memory
  read/write.
- Retain existing invalid/mismatch assertions. Commit RED before product code.

## Task 2 - bounded GREEN

- In `ProbeService._effective_target_transport_config()`, sort the projected writable regions by
  numeric origin and length before composing mailbox/RTT runtime configurations.
- Do not change region filtering, sizes, target/probe identity, error mapping, validators, or any
  other product file.
- Run the exact RED node and commit GREEN separately.

## Task 3 - proportionate verification

- Run complete `test_probe_service.py` and `test_physical_target_workflows.py`.
- Run only the directly affected mailbox transport and PyOCD backend tests required by the shared
  boundary.
- Run `git diff --check`, `git diff --name-only`, and final status. Remove only exact run-owned
  disposable test output when policy permits.
- Do not build/install a runtime and do not access hardware.

## Task 4 - independent Sol review

- Create a fresh clean detached worktree at the returned code head.
- Review complete `215bfe13ee556509cca907bde5a00b8132982149..CODE_HEAD`, including frozen documents.
- Re-run the exact Service/physical/mailbox/backend risk set under CPython 3.12 with an external
  run-owned basetemp.
- Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`; perform no hardware or remote
  action.

## Stop boundary

After software acceptance, update the local SDD and stop. The completed flash is preserved as
successful flash evidence, but Task 8 physical TestRun remains unproven. Any later target action,
including a read-only mailbox run or another flash, requires its own explicit user authorization.
