# STM32TK-1001 Monitor probe descriptor bridge correction plan

**Accepted base:** `b464d9573ba0cba71bee2f600b4ab73d1de70460` (tree
`c922fae99665ad71ea25d4a95f6b14ee09522762`)

**Ownership:** GPT-5.6-sol owns this plan and independent acceptance; one GPT-5.6-luna/max owner
implements product code and implementation tests. Local commits are authorized. Hardware, runtime,
candidate, firmware/project, and remote actions are excluded.

## Task 1 - freeze and prove RED

In the clean D-drive detached implementation worktree, audit HEAD/status and read the companion
design. Modify only `tools/stm32-monitor/tests/test_runtime.py` to add a focused production-contract
seam using real `probe_list_workflow` with an injected fake backend that returns a normal
`ProbeDescriptor`.

Prove at accepted behavior that the workflow succeeds with a six-field descriptor but Monitor maps
it to `MONITOR_PROBE_ENUMERATION_FAILED`. Preserve the exact node ID and output under a run-owned
evidence directory in `D:\codex-tmp`. The fake must record create/list/close and must make any real
worker/PyOCD construction fail the test. Do not start a real service or touch hardware.

## Task 2 - implement the bounded bridge

Modify only `tools/stm32-monitor/src/stm32_monitor/runtime.py`.

1. Recognize only a homogenous exact four-field or exact six-field descriptor tuple.
2. Keep the existing four-field path unchanged for constructor-seam compatibility.
3. For six fields, use the public Toolkit `ProbeDescriptor` contract to validate hardware ID,
   public selector, and fingerprint consistency, while applying existing Monitor display-text rules.
4. Build a fresh four-field projection, sort/deduplicate by public selector, and discard raw identity
   values before the Monitor result is created.
5. Preserve the existing stable error code/message/empty-details behavior and all lifecycle paths.

Do not change Toolkit files, protocols, schemas, runtime state, or historical evidence.

## Task 3 - complete focused implementation tests

Within `tools/stm32-monitor/tests/test_runtime.py`, cover:

- production six-field list and connect success through the real workflow seam;
- public output contains exactly four fields and no raw ID/fingerprint;
- missing/extra fields and mixed four/six listings;
- invalid hardware ID, selector mismatch, fingerprint mismatch, invalid display metadata, and
  duplicate selectors;
- existing exact four-field seam behavior.

Run only the new nodes first, then affected probe discovery/connect tests in `test_runtime.py`.
Use the D runtime CPython 3.12.10 with isolated import paths and D-only `--basetemp`/cache/evidence.
Do not run hardware, package, release, build, firmware, launcher, or full-repository matrices.

Commit product/test changes as one local CodeHead after focused GREEN, `git diff --check`, allowed
file audit, exact HEAD/tree capture, and a clean worktree. Return the CodeHead and evidence paths to
Sol; do not accept the diff or update the continuation branch.

## Task 4 - independent Sol review

Sol creates a second clean detached D-drive review worktree at CodeHead and reviews the complete
`b464d9573ba0cba71bee2f600b4ab73d1de70460..CodeHead` diff, including this design and plan. Sol
independently reruns the production seam, invalid identity/privacy checks, existing four-field
compatibility, and affected discovery/connect regression nodes with D-only basetemp/cache.

Any product finding returns to a Luna/max correction round on the same local attempt. If accepted,
Sol writes the tracked implementation report on top of CodeHead. The report records the accepted
base and CodeHead before its own commit and does not include its own final SHA or moving commit
counts.

After report commit, Sol verifies the original continuation worktree is still clean and still at
accepted base, then fast-forwards that sole local branch to ReportHead. No push, PR mutation, merge,
tag, release, runtime replacement, candidate packaging, hardware action, or master update occurs.
