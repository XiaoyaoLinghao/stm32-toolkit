# Legacy analysis input qualification

Accepted base: `59b74f05e06556e9a99c7652f7c9d97d6af7bdda`.
This is test-only work within the approved public-contract qualification and
existing analysis/1 compatibility. Runtime remains
`465249dba5560f7c08b1172794fec8fedd9b8d96`. Primary owns design/review/acceptance;
Luna/max owns implementation. No remote, hardware, deployment or schema change.

## Three caller scenarios

1. A valid legacy analysis graph can be used to add a verification plan. Reuse
   _prepared_checkpoint_for_plan with its default arguments: the None mutation
   branch of _verification_checkpoint_inputs ingests real Monitor replay and
   calls compare_monitor_runs with request/1. Verify the analysis uses actual
   Monitor run_ref_sha256 values, quality VALID and changed true. The public
   plan call advances revision4/FIX_PROPOSED to revision5 with the expected plan.
2. A persisted legacy INVALID analysis has contradictory conclusion/statistics,
   out-of-range counts, or inconsistent counts. The public plan call rejects
   all three with EVIDENCE_INTEGRITY_FAILURE before publishing an event.
3. A legacy completed analysis has unknown quality, non-boolean changed, too few
   pairs, inconsistent exclusions, or a nonnumeric scalar. The same public
   plan call rejects all five with EVIDENCE_INTEGRITY_FAILURE and preserves
   Diagnostic revision4, event/checkpoint/root and all pre-call authority bytes.

For INVALID cases start with quality INVALID, conclusion INCONCLUSIVE,
reason INSUFFICIENT_VALID_PAIRS, changed None, every scalar/delta None, counts
1/0/1. Change respectively conclusion to COMPLETED, one count to 2049, or
counts to 1/1/1. For completed cases retain the valid baseline and change
respectively quality to UNKNOWN, changed to None, counts to 1/1/0 with reason
VALUES_CHANGED, counts to 2/2/1 with reason VALUES_CHANGED_WITH_EXCLUSIONS,
or before_first to None. Preserve unrelated fields, identities and transcripts.

## Boundaries

Build the valid graph once and clone data per variant, keeping the original
project path/workspace identity. Extend the existing test-local persisted
analysis mutation helper only for these eight named inputs. Recompute the
analysis digest, envelope/root and public VerificationPlan references with the
existing canonical/public APIs. Use only cloned fixture files; do not modify
runtime readers or substitute their return values. Snapshot authority after
deliberate input mutation, then compare before/after the public call; original
baseline bytes remain unchanged. Public reload confirms refusal state.

Eight candidate pairs are 2426->2439, 2443->2449, 2450->2456, 2458->2459,
2460->2461, 2493->2498, 2499->2504 and 2511->2514 in diagnostic_workflows.py.
The strict allow_nonpassing=false edge 2473->2488 is excluded. Native analysis/3
statistic mutations are rejected earlier by native recomputation and are not
substitutes. Completion need not be repeated: these refusals belong at plan
addition. Static candidates are not coverage or physical PASS claims.

Keep existing tests, dependencies, schemas, coverage exclusions/denominators and
source bytes unchanged. No generic mutation/diagnostic framework. Acceptance
requires the valid prefix, exact public errors/state preservation, complete
native data and independent full-diff review. The overall90/core95 targets and
remaining release gates retain their existing meaning.
