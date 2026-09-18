# VS10-B completed-evidence offline finalization plan

Status: DRAFT / USER_APPROVAL_PENDING. Governing proposal: [offline finalization design](../specs/2026-09-18-stm32tk-vs10b-offline-finalization-design.md). Full accepted local base is `abdc2fb5dbde2b6643e26d42e29c7ad6db72f921`; deployed software remains `12df4fe0569104d6f0e7a827496341d999e1f3ea`. Neither draft approves implementation or claims VS10-B acceptance.

## Ownership and exact scope

Primary owns specification, plan, integration, complete-diff review and final acceptance. One new bounded Luna/max implementation owner owns the entire product slice and its implementation tests; no substitute lead or recursive delegation. An independent read-only reviewer checks the design and returned full diff. Primary remains the only canonical evidence-application and cleanup owner. No ownership exception or remote action.

Root for all new output: `D:\codex-tmp\v10b-0918\fin`; short test/cache/temp children remain under it. Implementation worktree `fin\impl`, clean review worktree `fin\review`, candidate offline data copy `fin\data-copy`, retained evidence `fin\e`. Implementation branch: `codex/STM32TK-1002-offline-finalization`. Original project `p\b`, canonical `data`, both Monitor role markers and card05 evidence remain preserved.

Product files, owned together by the one implementer:

- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/finalization.py`: bounded B completed-evidence proof/request/attempt/policy model and authenticated reader, if separation from the A implementation is the smallest coherent change.
- `acceptance/continuation.py`: only reuse/extraction of the smallest pure common authority checks; old /1 and /3 canonical behavior preserved. No generic registry or configurable profile engine.
- `acceptance/recovery_workflows.py`: exact request/attempt schema routing and immutable bind/begin/checkpoint/show/resume publication for the new closed profile.
- `acceptance/__init__.py`: required exports only.
- `mcp_server.py`: closed request /2 bind/reuse union; existing tool signatures and operation inventory remain.
- Existing `cli.py` only if its existing generic continuation-file dispatch actually requires a narrow change; no new command or flags.

Tests: reuse `test_acceptance_continuation.py`, `test_continuation_adapters.py`, `test_acceptance_physical_recovery.py`; a focused B-finalization test module may separate the new persisted cases if otherwise those modules become less clear. No product edits in Probe, Monitor, Diagnostic, CubeMX, firmware, release packaging or UI. If a validator cannot be reused without changing those contracts, return the exact blocker to primary before expanding scope.

## Execution waves

1. **Contract first.** Independent design review resolves schema routing, authority closure, lock order, error classification and byte compatibility before user approval and implementation. Check that /5, proof/request/policy /2 have no production namespace owner. Freeze the whole public offline call sequence and every dynamic ID source before any timed finalization begins.
2. **Single implementation.** Luna/max branches from the approved design commit, retains the above full product base, implements the bounded adapter and runs focused persisted tests. Tests exercise real EvidenceStore/TestRun/Diagnostic records and existing public functions. All subprocesses use the recorded interpreter and TEMP/TMP/TMPDIR; test basetemp/cache stay under the new root. No hardware, deployment or canonical data mutation.
3. **Independent acceptance.** Primary reviews the full accepted-base-to-returned-CodeHead diff in a clean detached review worktree; independently checks only changed behavior and relevant regressions. Findings return to the same owner/branch. Two nonconverging rounds trigger design reconsideration. Preserve unchanged release/hardware qualification.
4. **Real evidence rehearsal and application.** After software acceptance and user-approved offline application scope, use an isolated copy of actual card05 evidence with the exact current project/source facts. Existing public functions/CLI own all binding and completion; no manually authored accepted envelopes. Verify the canonical original graph was unchanged. Then perform one canonical offline bind/begin, final checkpoint and fresh read using the reviewed candidate code. Record candidate runtime/source identity explicitly; do not call it an installed deployment. No package/deployment or hardware step is required for this offline-only acceptance adapter unless an actual runtime dependency gap is found.
5. **VS10-B final review.** Link the new completed /5 record to the unchanged timed-out /4 predecessor and the already passed physical/Diagnostic results. Reconcile creation, NORMAL/IDE/CLI/MCP, both physical windows, source authorization, fixed result and archive identities against the original B acceptance criteria. Only then decide VS10-B ACCEPTED; missing evidence stays explicit. Local commits are distinct from unauthorized GitHub synchronization.

## Proportionate required validation

- Positive persisted B chain: expired /4 revision6, same-session physical failed/passed Target pair, exact intent/declaration, RESOLVED Diagnostic and PASSED FixVerification/1 → bind /2 → new attempt /5 → new-process read → checkpoint → new-process completed read. Actual card05 is the later offline real-evidence rehearsal, not a unit fixture labeled physical execution.
- No authority expansion: backend/service/supervisor creation, firmware mutation/build and Monitor/Diagnostic writes are forbidden by test seams. Old /4 roots, deadlines and physical artifacts remain unchanged.
- Reject incomplete/unresolved/non-PASSED evidence, mixed profiles/schemas, replay or cross-session inputs, swapped/foreign run/firmware/probe/target/mailbox/intent/declaration, unavailable/tampered artifact/envelope/parent/root, and inconsistent selected FixVerification/analysis.
- Publication boundaries: predecessor or Diagnostic head changes, current firmware drift, new deadline passes, or concurrent/conflicting UUID publish → no invalid accepted root. Identical retry returns the published result; expired new attempt can be followed by a fresh UUID reusing the same authenticated proof.
- Compatibility: selected existing A continuation happy/error paths and physical/replay routing/canonical-byte regressions, plus MCP strict request parsing and CLI public path. Broad release/packaging or repeated hardware tests are excluded.

Retain exact commands, source head, stdout/stderr and exit codes for required checks. Use small targeted output projections; keep full authoritative JSON on disk so nanosecond integers and graph hashes cannot be rounded or truncated through JavaScript. Failures are classified before product edits; reporting mistakes do not revoke physical PASS.

## Approval and current stop

The original B specification explicitly excluded A-only continuation, so this is an additional product contract requiring approval under AGENTS.md delivery workflow. The user's latest “继续” is being used to prepare and review this concrete proposal, not treated as approval of schema fields they had not yet seen. Once approved, implement and complete the bounded offline application without requesting per-command confirmation. This plan requests no hardware or remote authorization.
