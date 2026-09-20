# Public recovery workflow qualification

Accepted base: `8c819a150f4307564a04e1f92f38ef50ed5cef94`.
Runtime source: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Governing scope: the approved core-public-contract qualification specification
of 2026-09-19. This is an offline, test-only caller qualification. Primary owns
specification, integration, review and acceptance; Luna/max owns test changes.
No remote action, hardware, packaging or deployment is authorized by this plan.
Union20 remains the accepted coverage baseline: Toolkit 11795/13578,
Monitor 2653/2940; mandatory package 90% and preferred core 95% are unchanged.

## User scenarios

1. A caller binds a historical acceptance predecessor, reopens/reuses that
   association, and receives exact refusals for invalid checkpoints while its
   Diagnostic session remains unresolved. Original authorization and persisted
   history must not change when the caller is refused.
2. A caller reopens a completed Diagnostic graph, begins finalization, receives
   invalid-input and deadline refusals without a partial checkpoint, completes
   the valid checkpoint, then shows/resumes/retries the persisted terminal state.

These are two complete caller journeys, with finite variant tables below.
They do not promise that a currently unresolved continuation can be completed
without producing its required real analysis/marker graph.

## Shared contracts and ownership

Use `begin_acceptance_attempt`, `checkpoint_acceptance_attempt`,
`show_acceptance_attempt` and `resume_acceptance_attempt` as behavior entries.
Use existing `prepare_pair` and `PersistedCase` / `_build_synthetic_case` once
per respective journey. The existing firmware-facts seam constructs replay
fixtures only: it is not evidence of physical identity, hardware or actual
firmware loading. Do not add or change a production reader/provider patch.

Public model constructors, public EvidenceStore reads and test-local wrappers
around public workflows are allowed. A test helper's underscore does not make
it private production code. Do not reuse helpers that invoke production
`_typed_root_path`, `_publish_root_locked`, `_finalization_snapshot` or private
readers/decisions. For new assertions resolve a root with public `get_root`, or
the existing test-local canonical public root-key helper. No new corruption,
mutation or diagnostic framework is needed: all new variants are caller inputs
or the supported clock callable. No authority bytes are mutated.

Call results are asserted through `result.to_dict()`; immutable internal
mapping/tuple payloads must not be compared to JSON dict/list payloads.
Refusal oracles include exact operation/code/message/data plus unchanged
persisted roots, envelope/object bytes and Diagnostic event/checkpoint bytes.
Snapshot persistent authority subtrees; do not treat transient locks or test
output files as persisted authority. Read-only calls and exact retries must
not add authoritative resources. Input dictionaries must remain unchanged.

## Scenario 1: pending continuation

File: `tools/stm32-toolkit/tests/test_acceptance_continuation.py`.
Reuse one `prepare_pair` graph, preserving its logical project/workspace and
its original project path. The session is at the real post-declaration prefix;
there is no matching completed FixVerification.

Begin/refusal sequence:

| Caller action | First guard / result | Persistence oracle |
| --- | --- | --- |
| Bind with the predecessor's own attempt UUID | recovery_workflows.py:3226, `ACCEPTANCE_ATTEMPT_CONFLICT` | No change |
| Publicly begin a distinct normal v2 attempt, then bind using that UUID | :3233, `ACCEPTANCE_ATTEMPT_CONFLICT` | Existing v2 root unchanged |
| Bind with a fresh continuation UUID | Public success, revision 0 | Only expected proof and attempt roots |
| Bind the same request with a second fresh UUID | :3176 existing proof path | Same proof identity, no duplicate proof resources |
| Show, resume, and repeat begin with the first UUID | Public success | Same revision 0, no mutation; resume nextStage target-fix-verified, authorizationRequired false, timedOut false |
| Public reuse request with its actual continuationEvidenceId and a fresh UUID | Public success | Same proof; new revision-0 attempt only |

For checkpoint variants keep valid run/session fields from the fixture and a
valid but absent 64-hex fixVerificationId. Change exactly one field per call:

| Field / value | First guard | Exact code suffix |
| --- | --- | --- |
| expected_revision = 1; separately True | :3303 | REVISION_CONFLICT |
| stage = verification-pending | :3305 | STAGE_INVALID |
| acceptance_record_id = non-null; separately source_change_intent = non-null | :3305 | STAGE_INVALID |
| test_run_id = the existing failed-before run | :3313 | IDENTITY_MISMATCH |
| diagnostic_session_id = a different valid 32-hex ID | :3313 | IDENTITY_MISMATCH |
| All checkpoint fields otherwise valid, absent fix ID | :3276 | OUTPUT_INVALID |

All suffixes use `ACCEPTANCE_ATTEMPT_`. Every refusal leaves revision 0 and all
authority bytes unchanged. Finish by public show/resume to prove that the
pending association is still readable and resumable. Do not claim completion.

## Scenario 2: finalization

File: `tools/stm32-toolkit/tests/test_acceptance_finalization.py`.
Use the portable synthetic `PersistedCase` graph, never externally configured
VS10B data. Public begin at existing SAFE_TIME creates revision 0. Obtain the
proof with public EvidenceStore reads and PhysicalFinalizationProof.from_value.

Use a valid baseline checkpoint with expected_revision=0,
stage=target-fix-verified, actual fixed-after run, actual Diagnostic ID and
actual fixVerificationId. Before success change one caller field per refusal:

| Field / value | First guard | Code suffix |
| --- | --- | --- |
| expected_revision = 1; separately True | :4518 | REVISION_CONFLICT |
| stage = verification-pending | :4520 | STAGE_INVALID |
| acceptance_record_id = non-null; separately source_change_intent = non-null | :4520 | STAGE_INVALID |
| diagnostic_session_id = not-a-diagnostic-id | :4528 | INPUT_INVALID |
| test_run_id = the real failed-before run | :4560 | IDENTITY_MISMATCH |
| diagnostic_session_id = a different valid 32-hex ID | :4560 | IDENTITY_MISMATCH |
| fix_verification_id = a different valid 64-hex ID | :4560 | IDENTITY_MISMATCH |
| Repeat begin for the existing attempt with a different valid bind diagnosticEventHead | :4383 | CONFLICT |

Use the same `ACCEPTANCE_ATTEMPT_` prefix. No refused call writes authority.

Two deadline variants use only `AcceptanceRecoveryContext.clock`, an explicit
nondecreasing iterator that records calls and fails on unexpected consumption.
Let S be SAFE_TIME, after the actual predecessor deadline and before the new
attempt deadline; let L be strictly after the actual new attempt deadline.
Assert these inequalities using public persisted values before each variant.
The complete checkpoint clock path is:

1. :3721 during initial `_authenticate_finalization_locked` graph validation;
2. :4579 initial checkpoint time;
3. :4604 locked current-attempt time;
4. :4137 predecessor recheck;
5. :4617 candidate publication time;
6. :4641 post-envelope check (not reached in these refusal variants).

`[S,S,L]` must refuse at :4604; `[S,S,S,S,L]` must refuse at :4618.
Both return TIMED_OUT and write no revision-1 envelope, root or object; revision
0 and Diagnostic history remain byte-identical. Constant-late behavior is
already qualified and is not rerun for additional coverage. Do not use clock
callbacks to mutate state or replace production recheck functions.

Finally use constant S for a valid checkpoint: revision 1, COMPLETED and
target-fix-verified. Public show/resume must authenticate that exact state;
resume nextStage is null, authorizationRequired false and timedOut false.
Exact checkpoint and begin retries return the persisted attempt without new
roots/events/objects. Assert public policy fields, never manufactured authority.

## Deliberate exclusions

The exploratory recovery matrix is not implementation authority. Exclude
stale Diagnostic bind :3182 until a matching public plan graph is constructed;
completed continuation retry :3317; missing/duplicate plan contradictions;
typed-impossible states; opaque corruption arc inventories; races; and
post-envelope orphan cases :3266/:4301. The primary corrected the exploration's
missing clock read at :3721. No orphan-resource claim is made.
Do not change runtime, schemas, shared fixtures, dependencies or denominators.
Do not repeat accepted legacy, event, probe or physical batches. Static guards
are candidate scope, never a promised native coverage gain.
