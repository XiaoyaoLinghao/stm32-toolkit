# Risk-layered qualification implementation plan

Accepted base: `4bb612beabfdaf1ab4c845b966061832add38482`.
Specification: [risk-layered qualification v2](../../superpowers/specs/2026-09-20-stm32tk-risk-layered-qualification.md).
Primary owns dispatch/integration, shared test configuration, evidence aggregation
and cleanup. Luna/max agents implement tests in disjoint clean worktrees. No
product source, shared fixture, lockfile or coverage configuration changes are
delegated. Product findings return to primary for a bounded design decision.

## Execution waves

1. Run the existing generic-recovery remainder as one finite current-source group
   (21 functions; parametrized case count comes from JUnit), excluding the three
   already current-source PASS functions/13 cases. Existing launcher with fresh
   evidence/temp roots, 600-second budget, first failure stops. Then qualify the
   four existing continuation and five software physical-protocol selectors as
   one 300-second group if their current fixture prerequisites are valid.
   Exclude the routing-only dispatch mock and the CubeMX profile test whose
   SimpleNamespace project factory has no current-source qualification. Retain
   their historical scope; neither establishes a real identity-chain PASS.
   These checks do not depend on changing the coverage denominator.
2. Independently review the frozen v2 scope. Three Luna/max owners may then
   supplement distinct test families in parallel. First return a compact case
   matrix (entry, valid factory, supported variation, first guard, observable
   invariant, owner, and retained/new/uncovered disposition); main
   resolves overlap/contract ambiguity before implementation. Reuse accepted
   tests and identify true remaining behaviors, not a test per uncovered arc.
3. Review each complete accepted-base-to-test-head diff. Integrate accepted test
   commits locally. Run new coherent selector groups once with isolated roots;
   timing, process-global/shared-state and integration checks run serially.
   Combine complete passing native databases once per coherent wave, with
   current-source identity checks and an independent data review.
4. Report measured gaps and remaining critical behaviors. Test counts or document
   changes are not product progress. Release remains unaccepted until mandatory
   gates and named native/artifact evidence are complete.

## Disjoint implementation ownership

| Owner | Worktree | Test-only file scope | Behavior |
| --- | --- | --- | --- |
| Luna/max A | `r10/v2a` | `test_risk_recovery_contracts.py` in Toolkit tests | Diagnostic/recovery persisted integrity, supported availability failures, idempotency/CAS |
| Luna/max P | `r10/v2p` | `test_risk_project_probe_contracts.py` in Toolkit tests | Project rollback/write ownership and probe provider lifecycle/settlement |
| Luna/max M | `r10/v2m` | `test_risk_monitor_contracts.py` in Monitor tests | Analysis/replay authority, history/export and lifecycle |

Test files may import existing reusable factories without changing them. If an
existing module must instead be extended, primary reassigns its entire ownership
before edits. No agent changes conftest or generic infrastructure. Each returns
one coherent diff and exact selectors, source pin and evidence; it cannot accept
its own work. Main reviews all diffs; independent reviewer handles risk/contract
questions and native data. Subagents do not recursively delegate.

All roots above are children of `D:\codex-tmp\v10b-0918`. Test temp/cache roots
are `r10/t/v2a`, `r10/t/v2p`, `r10/t/v2m`; evidence roots are
`r10/e/risk-v2/a`, `/p`, `/m`. Set TEMP/TMP/TMPDIR, pytest basetemp/cache and native
coverage paths before Python starts. Main is sole cleanup owner. Retain raw
evidence and minimum failures; never retry previously policy-denied deletion.

## Acceptance and reuse

Required for each batch: meaningful assertions, no hardware access, complete
terminal PASS, exact source/candidate/command, diff review and source-qualified
native coverage. Targeted lint only on changed tests. No whole-release rerun for
test/report changes. An environment/platform barrier is recorded, not repaired
by weakening an assertion or faking capability.

Already accepted VS10-A/B, attempt7, UI, unchanged product verification and
current-source finalization7/Diagnostic2/generic13 remain valid within their
original bounds. Seven native Windows checks, final artifact/deployment and
release acceptance remain pending. No package, deployment, hardware or remote
action belongs to this offline wave.

## Critical behaviors retained in this wave

Evidence owner for this table is primary; A/P/M are maintenance owners, not
attribution of the original run. `e/python-final/{toolkit,monitor}/junit.xml`
records the named PASS cases at `87699308535bd36431c2e44be8bf131e245d460d`.
The context, migration, DWARF, auth, service and runtime product files below
are byte-identical in Git at the accepted base. Test additions since that run
do not delete or alter the named existing tests. These are retained module
conclusions, not a rerun or a claim that every later cross-module combination
passed. Changed recovery/replay/configuration/environment evidence stays under
its separately accepted current-source qualification.

| Owner / status | Public entry and legal setup | Variation / first guard | Observable assertion / existing selector |
| --- | --- | --- | --- |
| P / retained | `build_project_context`; `prepare_project` plus successful build | Change persisted buildId; `_evidence_fresh` manifest/identity match | `elfFresh` false; `test_context_stale_after_identity_tampered` |
| P / retained | `plan_keil_conversion` then `apply_keil_conversion`; `build_repo` with real C source | Unsupported pragma; `scan_sources` produces blocker and apply refuses | `MIGRATION_BLOCKED`, exact blocker codes, full tree unchanged; `test_apply_blocked_plan_refuses_without_writes` |
| P / retained | Same plan/apply path; valid `standard_repo` plan | Alter proposed bytes with recomputed plan ID; apply patch digest validation | `MIGRATION_PLAN_INVALID`, `patchDigest`, tree unchanged; `test_apply_forged_after_bytes_with_consistent_plan_id` |
| P / retained | `DwarfCatalog.from_binding/revalidate`; real ELF fixture and valid binding | Append ELF bytes; bound file size/digest guard | `DWARF_INPUT_CHANGED` then `DWARF_PROVENANCE_MISMATCH`; `test_catalog_construction_and_revalidation_reject_changed_evidence` |
| P / retained | Valid catalog and binding | Different binding; exact binding guard | `DWARF_PROVENANCE_MISMATCH`; `test_revalidation_requires_the_exact_binding` |
| P / existing assertion mapped | `DwarfCatalog.from_elf().lookup`; fixture with limited readable regions | Symbol outside allowed region; final address-range guard | `DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY`, no hardware provider involved; `test_address_must_be_inside_explicit_readable_regions` |
| M / retained | `MonitorAuth.authorize`; valid loopback auth fixture | Wrong token/origin; auth boundary | Authorization refusal; `test_bearer_auth_accepts_exact_loopback_origin_and_rejects_wrong_token` |
| M / retained | Real HTTP `MonitorService`; `_with_service` valid fixture | Bad Host/Origin or target override; request authentication/closed body guard | HTTP 403/403/400 and runtime calls empty; `test_host_origin_and_forbidden_identity_overrides_fail_closed` |
| M / retained | `MonitorRuntime.start/stop`; supported controlled service dependency | Repeated cancellation during stop; owned shutdown settlement | stop once, runtime record absent, replacement can acquire lock and stop; `test_repeated_cancellation_cannot_interrupt_owned_shutdown` |

The remaining A/P/M matrices add only distinct valid contract scenarios; they
must be frozen for each independent line before its test implementation. A scenario with no new valid
case may return “retained/no new test” instead of manufacturing a branch target.

### M line frozen supplement

Primary reviewed M-01/02/03/05 against the real implementation; M-04 reuses the
existing export-authorization conclusion and does not add a duplicate test.
The independent scope review confirmed Monitor's unchanged whole-file scope.
These tests do not depend on a new denominator and may proceed while A/P finish
preparing their disjoint matrices. No v2 acceptance is implied.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| M-01 / M / new | `analyze_monitor_windows`; canonical two-position windows rebuilt through public SampleBatch/reference factories | Empty scalar type; `_trusted_sample` type length guard (non-NFC input is blocked earlier by replay canonicalization and is not targeted) | INVALID/INCONCLUSIVE/INSUFFICIENT_VALID_PAIRS, one aligned and one excluded position; inputs unchanged |
| M-02 / M / new | Same entry and valid windows | Wrong request type; `type(request) is AnalysisRequest` guard | ANALYSIS_REQUEST_INVALID and exact message; inputs unchanged |
| M-03 / M / new | Valid `AnalysisBundleRef.to_dict` payload passed to `from_value` | Nested artifact None/list; ArtifactRef decoder then public exception translation | ANALYSIS_WORKFLOW_INVALID, exact public message, input unchanged; no claim of reaching the later constructor guard |
| M-05 / M / new | `ProbeSession.revalidate/prepare_read_plan/read`; supported observation factory and real admission | `_read_prepared` provider raises CancelledError; cancellation handler invalidates current plan | Cancellation propagated, plan/admission cleared exactly once, no retry/fallback or stale-plan reuse |

### P line frozen supplement

Primary reviewed P-01/03/04/05 against the actual apply/ProbeService guards and
nearest retained tests. P-02 (read-only missing-manifest conversion) is prepared
but not selected. The scenarios operate independently of core reclassification.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| P-01 / P / new | `apply_project_configuration`; existing real project/plan factory | Directory fsync fails after a real destination replacement; `_FsyncError` to fsync phase | GENERATION_APPLY_FAILED/phase=fsync; prove mutation preceded failure, complete bytes/modes restored and owned temporary/staging paths absent |
| P-03 / P / new | `ProbeService.start`; canonical service/backend inventory | Provider capability preflight raises RuntimeError; pre-lease preflight mapping | PROBE_BACKEND_ERROR, exact message, one preflight, zero attach/lease/endpoint |
| P-04 / P / new | start, client attach, debug_handoff_metadata; canonical supported provider | Metadata mapping lacks boardId; DebugHandoffMetadata decoder | PROBE_BACKEND_ERROR, attachment cleared, tasks settled, service still usable; final stop releases owned endpoint/lease |
| P-05 / P / new | `ProbeService.start/stop`; canonical backend | Backend closes then raises TimeoutError; cleanup classification plus lease finalizer | PROBE_CLOSE_FAILED, exact failed-close/successful-release fragments, endpoint removed, released lease and successful successor acquisition |

### A line frozen supplement

Primary accepted R1/R2/R3 from A's matrix, using the union24 residuals. Existing
CAS/idempotency/lock scenarios retain their source-qualified 36+10 PASS and are
not repeated. Constructor-unreachable conjunctions remain visible, unclaimed.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| R1 / A / new | `DiagnosticStore.load_creation_intent`, `load_durable`, `load`; existing created-target/failed-evidence factory | Missing diagnostic root, regular-file root, or missing referenced evidence in clone; root-shape or evidence resolution guard | NOT_FOUND / CHAIN_CORRUPT; durable read still returns exact persisted session while resolving read gives EVIDENCE_MISSING; sentinel and caller input graph unchanged |
| R2 / A / new | `diagnostic_show_verification`; real `_prepare_completion_graph`, clone data root | Remove only published analysis root; analysis authority lookup/conversion | Exact DIAGNOSTIC_CHAIN_CORRUPT wire; no new envelope/root/event/checkpoint; clone unchanged by caller, original project/data graph unchanged |
| R3 / A / new | `show_acceptance_attempt`, `resume_acceptance_attempt`; real public physical-protocol rev0/1 graph, clone data root | Public EvidenceStore publishes same envelope metadata with unknown attempt schema and root points to it; wrapper schema dispatch | Exact ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED show/resume wire; read-only rejection and both source and modified clone unchanged by callers |

Clone-only fixture corruption is an explicit test input, not authorization for a
production caller to overwrite authority. Each row compares the post-corruption,
pre-call clone snapshot to its post-call snapshot, and separately preserves the
unmodified source graph. No private production reader or mocked decision is used.
