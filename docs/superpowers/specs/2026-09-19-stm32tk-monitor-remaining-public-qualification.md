# Monitor remaining public-contract qualification

This schedules remaining evidence within the approved 1.0 release scope. It
does not change product behavior, the 90% branch gate, supported hardware, or
the accepted A/B results. The full implementation baseline is
87699308535bd36431c2e44be8bf131e245d460d; this is a frozen software candidate,
not an accepted 1.0 release. Primary owns this specification and acceptance.
Luna/max owns implementation and implementation tests; review is independent.

The final Monitor package run passed 838 tests, with 2472/2936 branches. The
earlier compatible Monitor aggregate has 2491/2936. Required coverage is 2643
branches. Neither one scenario nor a static branch map proves the remaining
gain. Authority is roadmap line 87 and the existing local-release plan, not a
new threshold created for these tests. Evidence and feasibility are under
D:\codex-tmp\v10b-0918\r10\e\python-final\monitor.

## Three runnable caller scenarios

1. A caller reloads or reuses a persisted Monitor reference after a stored
   root, envelope, artifact or transcript contradicts its authenticated
   identity. Reach residual canonical-byte, metadata and provider-authority
   variants through ingest_monitor_replay, publish_physical_monitor_run or
   load_monitor_run_reference and existing real EvidenceStore fixtures. The
   caller receives the existing MonitorReplayError classification and cannot
   adopt contradictory authority or mutate history. Existing happy paths,
   retry/cursor/race cases and already covered variants are retained.
2. A caller supplies a malformed Analysis request, computation or result
   through its public constructor/from_value/new interface. Qualify residual
   native/v1 field and reference-family rules, count/state/statistic consistency,
   finite scalar arithmetic, request threshold, digest and lineage binding.
   The public refusal remains AnalysisError with ANALYSIS_REQUEST_INVALID;
   valid input values and earlier accepted cases remain unchanged. Finite
   inputs whose arithmetic overflows are legitimate scalar boundaries; fake
   numeric subclasses, bypassed dataclass validation and impossible serializer
   objects are not. Window/continuation cases require existing authenticated
   fixtures and must not duplicate Replay-owned validation.
3. A caller compares authenticated runs or exports a published Analysis bundle
   when derived root/envelope/artifact authority is missing, contradictory, or
   fails at its provider boundary. Reach residual preflight, publication reload
   and export validation variants through compare_monitor_runs and
   export_analysis_bundle. Preserve existing classification: conflicting
   canonical intent is OPERATION_CONFLICT; corrupted persisted authority is
   EVIDENCE_INTEGRITY_FAILURE; actual provider I/O is ENVIRONMENT_FAILURE;
   incompatible run/continuation identity is INCOMPATIBLE_IDENTITY. Earlier
   immutable publication is not promised to roll back after a later failure.

## Frozen shared contract and state ownership

All production code, schemas, error sets, limits, dependencies, and lifecycle
transitions remain at the baseline. Replay owns transcript/reference authority;
Analysis owns derived models and computation; Analysis workflows consume those
authorities and own derived publication. Tests use existing public stores and
provider seams without adding a backend, shared fixture framework or dispatcher.

Each new variant must identify a currently missing branch and a caller-visible
contract. Verify it is absent from the accepted tests before adding it. Refusal
assertions cover the public error and relevant state preservation, not merely
line traversal. Snapshot after intentional corruption/provider setup and before
the operation, so the injection itself is not counted as product mutation.
Do not bypass constructors, mutate frozen typed objects, call production
private helpers, invent cyclic objects or manufacture race outcomes for coverage.
Do not duplicate already passing tests or add exclusions/no-cover directives.

Unexpected product behavior returns to primary with evidence. No runtime fix
belongs to these test-only slices. A repeated non-converging finding requires
design reconsideration, not successive private-state patches. Numeric coverage
gain is reported only from retained native data after execution.

## Evidence and acceptance

Use isolated D-drive worktrees. Keep the running qv candidate untouched. No
new pytest process may compete with the current Toolkit release matrix.
Preparation is source/test implementation plus syntax inspection only; primary
will schedule each owner's bounded selected-node execution after that matrix
settles and the actual entry has been reviewed. Use existing pytest/launcher
patterns, short IDs and paths, all three temp variables, explicit branch
instrumentation and durable raw/JSON/JUnit/actual-child evidence. No new generic
diagnostic framework is authorized.

Independently review each complete baseline-to-return diff and reconcile exact
test outcomes. Merge only accepted slices. Test-only changes do not invalidate
the unchanged runtime's existing valid evidence or trigger another complete
suite. Aggregate matching-source raw coverage once after the selected checks;
the 1.0 gate remains unmet until both required package ratios actually pass.
There is no hardware, packaging, deployment, cleanup or remote action here.

## Bounded transcript publication error correction

Accepted runtime base: `87699308535bd36431c2e44be8bf131e245d460d`.
Regression/implementation starting head: `e4ce6d7d5e0737a9dc05cd7dd924e67a7b28ca4c` (q1).
The terminal replay run1 has seven PASS and one genuine product failure: a valid but contradictory ArtifactRef is detected by `_publish_transcript`, then its EvidenceValidationError is incorrectly wrapped as ENVIRONMENT_FAILURE. The approved 2026-08-22 Task7a authority amendment requires corrupt immutable evidence to map to EVIDENCE_INTEGRITY_FAILURE, while provider I/O maps to ENVIRONMENT_FAILURE.

The primary owns this bounded design and independent acceptance; a Luna/max owner implements only `tools/stm32-monitor/src/stm32_monitor/replay.py` and relevant public regression cases in `tools/stm32-monitor/tests/test_replay.py`. One existing slice return report may record actual results. The prior test-only boundary is overridden only for this proven error-mapping defect under the user's active local-release goal.

Runnable scenarios:
1. Ingesting a replay whose provider returns a valid ArtifactRef with a contradictory digest raises EVIDENCE_INTEGRITY_FAILURE, preserving EvidenceValidationError as its cause; neither transcript/reference root nor History is published.
2. Real direct or nested non-missing provider OSError failures remain ENVIRONMENT_FAILURE and publish no root/History. Reuse the existing `_has_non_missing_os_error` rule and reference-publication classification; do not invent new codes or a new exception framework.
3. Valid replay and physical transcript publication retain their current behavior and authority checks.

Only the transcript-publication exception classification may change. Do not alter ArtifactRef construction, storage schemas, sampling, probe/hardware logic, publication order, root rollback, reference publication, or any public success shape. The failed immutable-identity expectation must remain unchanged. The actual first run did not reach its post-error invariant assertions; subsequent genuine PASS is required.
