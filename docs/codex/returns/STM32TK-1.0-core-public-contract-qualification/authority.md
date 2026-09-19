# Authority public-contract qualification return

Status: IMPLEMENTED; TEST EXECUTION NOT_RUN.

This bounded Luna/max revision starts from accepted base
0a6bf2a6c591e5e89c6451050de3087168b77eb4 on branch
codex/STM32TK-1.0-core-authority. Runtime source remains the accepted
a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d. The revised test-code head before
this report commit is 98ef03426ca802c50f1cadf3ac05c5a1dee30ee0.

The revision keeps the runtime, schemas, configuration, dependencies, shared
fixtures, and coverage configuration unchanged. It corrects the first review
round and extends the same finite public-contract wave with focused checks in
existing tests:

- tools/stm32-toolkit/tests/test_acceptance_model.py
- tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py
- tools/stm32-toolkit/tests/test_acceptance_continuation.py
- tools/stm32-toolkit/tests/test_acceptance_finalization.py
- tools/stm32-toolkit/tests/test_diagnostic_mcp.py
- tools/stm32-toolkit/tests/test_diagnostic_events.py
- tools/stm32-toolkit/tests/test_diagnostic_store.py
- tools/stm32-toolkit/tests/test_fix_verification_model.py

The first review corrections are concrete. The recovery-workflow parameter is
now begin_args, so pytest's reserved request fixture name is not used. The
checkpoint invariant captures each persisted file's relative path and bytes,
and explicitly checks that resume still reports revision zero. The physical
observation selector now uses a re-digested valid fixed-after v2 reference and
asserts the public validate_run_reference succeeds before the selector guard.
Its replay row uses a valid v1 replay reference with the canonical replay
labels and a recomputed digest, so the selector exercises the physical
provenance guard. Duplicate tuple and UUID rows were removed where the
existing model tests already prove those contracts.

The new distinct public checks cover continuation and finalization bind/reuse
request discriminators, diagnostic event actor validation, and diagnostic
store resolver input validation. Each preserves the caller wire or the
published durable revision as applicable.

## Public guard coverage

| Source authority | Public trigger | Expected result and invariant |
| --- | --- | --- |
| acceptance/model.py | AcceptanceScenario.from_value receives unknown/version, short or non-string stages, or a non-boolean transport flag; AcceptanceRecord.from_value receives an object stage container | Exact acceptance input/scenario codes and unchanged caller mapping. Existing tests retain the tuple and UUID cases already covered by the closed-field and canonical-digest tests. |
| acceptance/recovery_workflows.py | begin_acceptance_attempt, checkpoint_acceptance_attempt, and resume_acceptance_attempt receive malformed public references | Exact input/stage codes; begin and resume create no state; checkpoint resume returns the original revision-zero snapshot and identical persisted file bytes. |
| acceptance/continuation.py | ContinuationRequest.from_value receives a boolean diagnostic revision or a reuse-shaped object with bind kind | ContinuationValidationError; each input mapping remains unchanged. The existing valid bind/reuse round-trip and durable graph mutations remain in the same selector. |
| acceptance/finalization.py | FinalizationRequest.from_value receives a boolean diagnostic revision or a reuse-shaped object with bind kind | FinalizationValidationError; each input mapping remains unchanged. Existing finalization workflow tests retain the complete physical graph lifecycle. |
| diagnostics/model.py | ObservationStep.from_value receives invalid physical fact selectors or a valid-but-fixed-after v2/non-physical replay reference; VerificationPlan.from_value receives invalid V2 continuation binding | Exact DIAGNOSTIC_PLAN_INVALID or DIAGNOSTIC_INVALID_EVENT; caller wires are unchanged and valid public references are validated before the intended outer guard. |
| diagnostics/events.py | Public create_event receives an unsupported actor with an otherwise valid empty investigation.started payload | DIAGNOSTIC_INVALID_EVENT; the payload mapping remains unchanged. Existing reducer tests cover lifecycle transition and duplicate-reference guards. |
| diagnostics/store.py | resolve_operation receives an empty event type, empty actor, or non-mapping request after a published operation | DIAGNOSTIC_INVALID_EVENT; the accepted revision remains unchanged. Existing store tests cover exact retry, conflict, append, recovery, and provider-error behavior. |
| diagnostics/model.py V2 verification | Existing V2 plan wire is valid only with continuation evidence and digest identity | Valid V2 round-trip; missing, legacy-schema, and changed-ID forms remain closed without mutation. |

## Exact residual disposition

The residual source map is
D:\codex-tmp\v10b-0918\r10\e\python-final\core-public-contract-owner-residuals.json
(SHA-256
AD9CEF74C2D3E33821CE0040E682AC5DAC6C6AEA2CFD3BE9DB07E31E29A27961). It
assigns 941 missing arcs to these ten Authority source files. The counts below
are source-map counts before this test-only revision; they are recorded as
disposition evidence, not as a promise to hit every defensive conjunct.

| Authority source file | Residual arcs and concrete guards | Disposition and remaining barrier |
| --- | --- | --- |
| acceptance/continuation.py | 75 total. PhysicalContinuationAttempt.__post_init__ (lines 394-441, 14 function arcs) checks schema/revision predecessor, frozen scenario and provenance, revision state, time window, and checkpoint digest. validate_continuation_reference (lines 965-1059, 13) checks the after identity, marker parent, analysis envelope shape/canonical bytes/digest, lineage, and native request/statistics. _load_v2_chain_prefix (11) and _continuation_monitor_reference (7) validate the persisted seven-revision physical predecessor and immutable Monitor transcript/reference roots. | The new request parser variants exercise public shape discrimination. Existing test_continuation_bind_reuse_show_resume_preserves_v2_authorization, test_authenticated_continuation_rejects_tampered_parent_run_and_context, test_continuation_parent_order_swap_is_rejected_after_rehashing_envelope_and_root, test_continuation_rejects_readable_after_run_binding_variants, and test_continuation_rejects_readable_replay_after_test_run provide the valid graph and public mutation entrypoints. The remaining arcs are alternate persisted-root/artifact/lineage predicates that all terminate in the same closed continuation validation or identity result; reaching each separately requires duplicating an existing graph mutation while no new public code is exposed. |
| acceptance/finalization.py | 31 total. PhysicalFinalizationAttempt.__post_init__ (lines 382-437, 13) checks schema/revision/predecessor, frozen scenario/provenance/status/stage, deadline and checkpoint. PhysicalFinalizationProof.__post_init__ (lines 169-197, 6) checks expanded intent and distinct before/after evidence. FinalizationRequest.from_value has 5 residual parser branches; its bind/reuse discriminator is now covered by the new test. | test_finalization_persisted_round_trip_and_exact_explicit_retry, test_b_authority_graph_rejections_use_persisted_proof_and_context, test_persisted_attempt_binding_mutations_are_rejected, and the final deadline tests construct the valid seven-revision B graph and mutate its persisted authority. Remaining constructor/proof arcs are alternate closed-field, state, time, or digest mutations with the same FinalizationValidationError result; a separate row for every conjunction would duplicate the existing physical lifecycle assertions. |
| acceptance/model.py | 17 total. Residual guards are _definition_key/scenario construction, scalar and UTC normalization, and record source/stage/digest identity (lines 83-327). | test_scenario_model_rejects_noncontract_input, test_scenario_model_rejects_tuple_json_and_digest_mutation, test_record_model_rejects_physical_source_wrong_stage_and_noncanonical_scalars, and test_record_model_requires_exact_closed_fields_and_canonical_digest already reach these public constructors. The revised parameter wave keeps only distinct short/non-string/object cases; removed tuple and UUID rows were duplicate evidence. Remaining arcs are alternate malformed scalar or digest forms with the same public code. |
| acceptance/recovery.py | 78 total. AcceptanceAttempt.__post_init__ (lines 570-640, 15) and PhysicalAcceptanceAttempt.__post_init__ (lines 1078-1168, 18) enforce revision prefixes, stage-output availability, physical provenance, intent expansion, authorization and checkpoint identity. Additional residuals are policy/from-value, authorization, stage-output, and source-intent guards. | test_revision_zero_has_exact_stage_output_nulls_and_fixed_prefix, test_v1_attempt_decode_rejects_stage_outputs_outside_exact_prefix, test_physical_attempt_rejects_unexpanded_or_misbound_before_intent, test_physical_attempt_decode_rejects_partial_intent_and_unavailable_outputs, and the source-intent mutation tests already use the public wire factories and exact errors. Remaining authorization and later-revision arcs require a valid durable physical chain plus a diagnostic declaration/authorization graph; the existing finalization/continuation fixtures are the sole approved graph factories, and their workflow tests exercise the reachable persisted mutations. |
| acceptance/recovery_workflows.py | 292 total. _build_transition (lines 857-1043, 17) dispatches the six replay stages and output validators. _validate_physical_chain_semantics (1668-1732, 16) checks physical root/envelope revision monotonicity and model/session identity. _load_finalization_graph_locked (3669-3978, 15) authenticates the complete predecessor, diagnostic, TestRun, declaration, analysis, marker, verification, and proof graph. Other residuals are physical checkpoint/authorization and finalization checkpoint branches. | The revised begin/checkpoint/resume tests cover the public input boundary and no-mutation behavior. Existing test_chain_gap_and_corrupt_root_fail_closed, test_current_project_origin_drift_fails_closed_on_public_resume_and_show, test_b_authority_graph_rejections_use_persisted_proof_and_context, test_finalization_persisted_round_trip_and_exact_explicit_retry, and deadline/identity mutation tests cover the valid durable entrypoints. Every remaining guard needs a seven-revision physical chain with a specific persisted authority mutation or deadline; those guards share the same integrity, identity, authorization, timeout, or output result classes already asserted by the existing fixtures. |
| acceptance/workflows.py | 45 total. Residual functions are _load_diagnostic_chain (383-), _public_test_projection_matches (295-), _reader_failure_code (216-), _record_acceptance (591-), _read_acceptance (515-), and context/root failure mapping. | test_describe_is_state_free_and_returns_the_fixed_definition, test_describe_rejects_unknown_definition_without_state, test_record_rejects_malformed_uuid_before_loading_project, test_show_missing_root_is_typed_and_does_not_create_state, and test_actual_diagnostic_reader_failures_map_to_closed_acceptance_codes reach the public adapters. Remaining arcs require a published acceptance record plus a complete diagnostic chain or a reader/provider exception; malformed inputs stop at the earlier public wire validator, and provider variants preserve the same closed reader code. |
| diagnostic_workflows.py | 169 total. _validate_analysis (2234-2536, 30) checks analysis envelope/evidence IDs, parent lineage, schema/digest, native request/statistics, quality/conclusion/reason, counts, numeric bounds, and recomputed deltas. _read_physical_transcript_parent (1673-1960, 23) and _read_monitor_reference_authority (1962-2189, 16) check the immutable physical transcript/reference graph, canonical bytes, run identity, batch sequence, and projected digests. | Existing workflow tests cover replay analysis failure, changed evidence identity, malformed analysis, provider failures, plan limits, and marker/verification lifecycle. The continuation/finalization durable fixtures provide the only valid persisted physical transcript/reference graph; their public mutation tests already cover wrong identity, root, artifact, and replay/physical provenance outcomes. A bare selector cannot reach these nested readers because ObservationStep.from_value and the physical target authority checks reject it first. The remaining source branches are persisted graph conjuncts with existing terminal codes (EVIDENCE_INTEGRITY_FAILURE, INCOMPATIBLE_IDENTITY, or ENVIRONMENT_FAILURE), not new public result families. |
| diagnostics/events.py | 25 total. Residual reducer guards include _require_chain and _require_state (lines 135-165), duplicate or mismatched source-change/plan/marker/fix references, and verification completion links. | The new create_event actor case covers a public event-construction boundary. test_diagnostic_events.py covers canonical payloads, chain sequence/transition links, missing/duplicate hypotheses, plan execution, evidence relation, and result digest; test_fix_verification_events.py covers marker, plan, verification, retry, and terminal-state reducers. Remaining arcs require a valid preceding session and then one alternate event/reference mutation; they all close through the existing invalid-event, invalid-transition, or plan-invalid codes. |
| diagnostics/model.py | 126 total. DiagnosticSession.__post_init__ (lines 796-970, 25) checks lifecycle tuple types/limits, model identity, duplicate IDs, result-to-plan evidence, declaration/plan/marker/fix links, active plan state, and terminal-state requirements. Residual _selector, lifecycle payload, plan, assessment, marker, and hash-tuple branches remain. | test_diagnostic_model.py covers session wire collections, extended lifecycle shape, target mode, selector closure, ID/limit bounds, plan/result evidence, and canonical round-trips. test_fix_verification_model.py and test_fix_verification_events.py cover later declaration/plan/marker/fix links; the MCP selector test now proves valid v2/replay references before the intended physical guard. Remaining alternatives require fully typed lifecycle objects and are the same DIAGNOSTIC_INVALID_EVENT, DIAGNOSTIC_PLAN_INVALID, or limit outcomes already asserted by those public models. |
| diagnostics/store.py | 83 total. _load_chain_locked (524-, 4) and _validate_referenced_evidence (801-, 7) validate persisted event layout and linked evidence. create (1161-, 3), append (1189-, 4), and resolve_operation (1229-, 4) validate public event/session/revision/request inputs. _store_lock and load_creation_intent retain platform/layout branches. | The new resolver test covers empty event type, empty actor, and non-mapping request while proving the accepted revision remains 2. Existing store tests cover create/append type and revision gates, retries/conflicts, interrupted publication, root/layout contradictions, missing evidence, provider OSError, limits, lock contention, and creation-intent reads. Remaining _load_chain_locked and evidence branches require a specific persisted event/root/artifact corruption and already terminate as chain-corrupt or evidence-missing. Windows lock paths are existing platform-specific tests; no new environment assumption is introduced. |

This map is based on the accepted native toolkit coverage input
D:\codex-tmp\v10b-0918\r10\e\python-final\toolkit-reconciled-r1\coverage.json
(SHA-256
C5A698B58B91A9510597A5EE06525080212DE3088207A5A31A2B6B57F92D65BB) and
the monitor input
D:\codex-tmp\v10b-0918\r10\e\python-final\monitor-reconciled-r1\execution\coverage.json
(SHA-256
BDE30A21C94D061CAFD163EDC447FE9BF1E8D19CF0876623EC4C58B0C9AAD5E2). No
new coverage claim is made before the primary-owned serial run.

## Exact selected functions

The primary-owned launcher can select these functions without guessed
parameter IDs:

    tools/stm32-toolkit/tests/test_acceptance_model.py::test_scenario_wire_guards_preserve_input_and_exact_error_codes
    tools/stm32-toolkit/tests/test_acceptance_model.py::test_record_wire_container_guards_preserve_input
    tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_begin_public_input_rejection_publishes_no_state
    tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_checkpoint_public_input_rejection_preserves_revision_zero
    tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_resume_public_attempt_id_rejection_creates_no_state
    tools/stm32-toolkit/tests/test_acceptance_continuation.py::test_continuation_request_accepts_mapping_and_is_closed
    tools/stm32-toolkit/tests/test_acceptance_finalization.py::test_finalization_request_wire_guards_preserve_input
    tools/stm32-toolkit/tests/test_diagnostic_mcp.py::test_physical_observation_step_wire_guards_fail_closed_without_mutation
    tools/stm32-toolkit/tests/test_diagnostic_events.py::test_create_event_rejects_invalid_public_actor_without_mutating_payload
    tools/stm32-toolkit/tests/test_diagnostic_store.py::test_resolve_operation_returns_current_session_for_exact_intent_and_conflicts_changes
    tools/stm32-toolkit/tests/test_fix_verification_model.py::test_v2_verification_plan_requires_and_binds_continuation_evidence

## Verification status

AST-only syntax inspection passed for all eight changed test files. It used the
approved D-drive temporary root with TEMP, TMP, and TMPDIR bound before Python:

    D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -c "import ast, pathlib; paths=[pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_model.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_diagnostic_mcp.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_fix_verification_model.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_continuation.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_finalization.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_diagnostic_events.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_diagnostic_store.py')]; [ast.parse(p.read_text(encoding='utf-8')) for p in paths]; print('AST_OK', *paths, sep='\\n')"
    AST_OK
    tools\stm32-toolkit\tests\test_acceptance_model.py
    tools\stm32-toolkit\tests\test_acceptance_recovery_workflows.py
    tools\stm32-toolkit\tests\test_diagnostic_mcp.py
    tools\stm32-toolkit\tests\test_fix_verification_model.py
    tools\stm32-toolkit\tests\test_acceptance_continuation.py
    tools\stm32-toolkit\tests\test_acceptance_finalization.py
    tools\stm32-toolkit\tests\test_diagnostic_events.py
    tools\stm32-toolkit\tests\test_diagnostic_store.py
    exit code 0

git diff --check passed before the test-code commit. Pytest, collect-only,
package imports, builds, installers, hardware, remote operations, and cleanup
were not performed in this implementation wave. The tests remain NOT_RUN
pending the primary's independent complete-diff review and serial selected-node
execution. Native coverage aggregation remains primary-owned.

## Primary integration disposition

The primary independently reviewed the complete accepted-base-to-test-head diff
and executed the bounded selected functions. Run1 at5819 recorded12PASS and a
test-only missing deepcopy import failure. Test headf74a91cba9adc1c274f24f8e7a310d9300ad17e5 corrects two missing imports; run2 executed only the failed and unrun functions:15PASS,exit0,zero skips,14.379secondsJUnit,no timeout,and childreaped. The twelve unchanged passing items are retained, for27distinct selected passes. Historical failure evidence remains in r10/e/core95/authority/run1; current reconciliation is in run2/primary-result-review.json.

Verdict: ACCEPTED for this bounded test change. Runtime source remains equal to
a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d. No coverage threshold, remaining
source-family barrier exemption, physical result, or1.0 release acceptance is
implied. Native coverage aggregation remains pending the four-owner wave.
