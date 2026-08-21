# VS-03 Task 7A-R1 Monitor Run Reference Authority Plan

> **Implementation owner:** the existing `gpt-5.6-luna` / `max` Task 7A implementer. The
> GPT-5.6-sol primary owns this plan and independently reviews the complete diff.

**Goal:** Make a complete MonitorRunRef reloadable and independently verifiable from real replay
ingestion through Monitor comparison and Toolkit diagnostic plan preparation.

**Dispatch base:** the local docs commit created from
`d9e3e1d6b8af8d4193c3a4268eae76fd20657f95`; record its full SHA in the SDD ledger before edits.

**Boundaries:** no diagnostic mode/error or operation-retry changes; no adapters, hardware,
packaging, Python 3.10, release Gate, or remote operation.

## Task 1: Publish and repair canonical run-reference Evidence

**Product files:**

- `tools/stm32-monitor/src/stm32_monitor/replay.py`
- `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`

**Tests:**

- `tools/stm32-monitor/tests/test_replay.py`
- `tools/stm32-toolkit/tests/test_evidence_gc.py`

1. Write RED tests for a new `monitor-run-ref/<operation_id>` root, its closed envelope, sole
   canonical ref artifact, transcript parent, metadata, identity, and static GC registration.
2. Test exact re-ingestion, interrupted publication repair, legacy transcript/root plus complete
   History repair, conflicting ref/root, corrupt ref artifact, and provider failure. Assert no
   partial History adoption or rewrite.
3. Implement canonical reference publication only after the existing transcript/root and any
   existing History are proven compatible. Do not mutate the old root.
4. Run the two focused files on CPython 3.12 and commit only after GREEN.

## Task 2: Consume the same authority on both sides of the module boundary

**Product files:**

- `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`

**Tests:**

- `tools/stm32-monitor/tests/test_analysis_workflows.py`
- `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

1. Write RED Monitor tests proving comparison rejects an absent, corrupt, or contradictory full
   ref authority before History analysis.
2. Write RED Toolkit tests using real `ingest_monitor_replay` and `compare_monitor_runs`, then prove
   analysis before/after IDs equal the authoritative ref digests. Replace arbitrary fake run IDs in
   positive helpers. Add negatives for a digest-only root, swapped refs, and one mutation in each
   binding/window/group/batch-digest class.
3. Implement one closed ref loader/validator per package. Toolkit must not import Monitor; it parses
   the specified canonical JSON contract and independently reconstructs the transcript projection.
4. Run focused Monitor replay/analysis and Toolkit fix-verification tests on CPython 3.12. Commit
   the bounded task, then report full SHAs, diff, and exact commands to Sol.

## Sol review checkpoint

Review dispatch-base-to-head in a fresh detached worktree. Required evidence is the four focused
test files plus `git diff --check`. Do not run a release matrix. A finding returns to the same Luna
owner; no remote action is authorized.

