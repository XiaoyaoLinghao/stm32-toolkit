# Diagnostic public caller journeys

Accepted base: `569de655ab28fedff5e23d4f26cb604ddc0eecdc`.
Product baseline: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
This finite test-only decision implements the approved core-public-contract
qualification and union20 governance decision. It does not change product
behavior, mandatory Toolkit native branch 90%, or preferred core 95% goals.

## Two caller scenarios

1. A real schema-3 replay project advances Diagnostic investigation through
   declaration, verification plan, start, marker and successful completion.
   Reject invalid caller fields and out-of-order transitions without changing
   authority; exact completion retry and public reload retain the completed
   result. This tests a connected caller journey, not fabricated reducer state.
2. A caller submits source-change or analysis authorities that are structurally
   representable but fail one concrete authority check. Reject each through
   the public declaration/plan function; preserve all pre-call bytes and the
   original valid graph. A final valid operation remains possible.

No hardware, deployment, packaging, platform capability checks, product edits,
new frameworks, private reader replacement, contradictory typed objects or
coverage-denominator changes. Historical PASS and the seven Windows gaps are
unchanged. These scenarios do not promise to close the remaining 426 branches.

## Shared construction and ownership

Only `tools/stm32-toolkit/tests/test_fix_verification_workflows.py` is writable
by one Luna/max implementer. Main owns specification, integration, independent
complete-diff review, serial pytest and cleanup. No helper-file or source edits.
Reuse the existing test-local real project/replay helpers in
`test_vs08b_scenarios` and `test_vs08a_scenarios`. In particular start with
`_prepare_real_diagnostic_before_source`, then reuse the public operations in
`_prepare_completion_graph` rather than the `_install_model` synthetic seam.
Allowed local helpers only organize these two journeys and their exact byte
snapshots/clone copies; no configurable mutation or graph framework.

Use one real graph per journey (at most two constructors for the batch).
Actual Diagnostic revisions are 6 before declaration, 7 FIX_PROPOSED,
8 plan added, 9 VERIFYING, 10 marker attached, 11 RESOLVED. Capture data-root
copies at live prefixes before advancing; never truncate event history to
manufacture earlier state. Clones keep the original project path and logical
workspace identity; only the data-root location changes. Close all public
operations before copying. All files stay below the assigned D task root.

## Journey 1 finite checks

Use the original session argument throughout. New typed objects are created
with their public constructors and digests. Derive successful outputs from
the real persisted public objects and compare public `result.to_dict()`.

| Prefix | Input/operation | First expected outcome |
|---|---|---|
| 6 | Invalid hypothesis/step syntax | argument validation at :315/:321 |
| 6 | Start verification before declaration | INVALID_TRANSITION at :2833 |
| 7 | Different valid declaration, same valid lineage/diff, extra changed path | PLAN_INVALID at :2651 |
| 7 | Plan with a different valid `diagnostic_session_id` field | PLAN_INVALID at :2724; caller session remains real |
| 7 | Plan with existing fixed run but different valid evidence ID | INCOMPATIBLE_IDENTITY at :2751-2754 |
| 7 | Start with absent valid plan ID | PLAN_INVALID at :2840 |
| 8 | Attach valid marker before start | INVALID_TRANSITION at :2900 |
| 9 | Typed marker with unpaired analysis/evidence | PLAN_INVALID at :2922 |
| 10 | Completion executed IDs empty, 65 IDs, duplicates, or cancelled=1 | input guards :276/:279/:285 |
| 10 | Normal completion | PASSED / VERIFICATION_PASSED, revision11 RESOLVED, active plan cleared |
| 11 | Public reload/show and exact completion retry | same result, no mutation |
| 11 | New completion operation; new declaration operation | INVALID_TRANSITION at :910 / :2639 |

These line numbers refer to diagnostic_workflows.py at the product baseline.
For each call assert exact public code/message/data/details, revision/event
head, and no storage mutation on refusal/retry. Successful transitions must
preserve all previous immutable authority bytes and add only the public event,
evidence and root resources appropriate to that transition. Existing accepted
completion fixture oracles may be reused without changing their helper files.
Do not include plan-before-declaration just to reconstruct future plan data.

## Journey 2 finite authority checks

Save the real revision6 and revision7 prefixes. Diff failures use prefix6;
analysis failures use prefix7 after publishing genuine replay/Monitor/analysis
through existing public APIs. Use legacy analysis/1 with native request/1,
not a native analysis/3 or fabricated model. E is EvidenceEnvelope, R the
monitor-analysis RootRecord, A the artifact JSON, P VerificationPlan.

| Variant | Exact construction | First guard |
|---|---|---|
| diff operation, artifact.kind, media_type (3 cases) | Public new E with one changed field, public new declaration references E; original diff artifact retained | :2199-2209 |
| P evidence ID mismatch | Another real evidence ID, P digest recomputed, A/E/R unchanged | :2263-2264 |
| E parents count | First two genuine parents, not three; new E, R manifest, P evidence | :2271-2272 |
| E third parent | Another genuine evidence ID at index2; same count and other fields | :2275-2276 |
| E import workspace metadata | One different valid workspace ID; R metadata agrees; new E/R/P evidence | :2316-2317 |
| canonical non-object A | canonical JSON array, new artifact/E; old analysis identity retained in R/P | :1448-1449 |
| nested A.identity extra key | Recompute unsigned A hash and synchronize analysis ID in E/R/P | :2229-2230 called at :2397 |
| extra A top-level key | Recompute A hash and synchronize E/R/P | :2329-2330 |
| A schema /2 without continuation | Retain field set, recompute A hash, synchronize E/R/P | :2338-2339 |
| A claimed analysis ID mismatch | Change only payload's claimed ID; old identity in E/R/P; new artifact/E/R manifest/P evidence | :2338-2339 |

All return EVIDENCE_INTEGRITY_FAILURE with message
`Target replay evidence failed integrity validation.`, data=null, details={}.
Do not assert a claimed line from code alone: retain native execution evidence
and distinguish earlier rejection if it occurs. Test-local case labels must
appear in failure messages. Canonical array is intentional: the shared decoder
allows a non-object at this entry, then the workflow rejects it. Noncanonical
JSON and same-ref object corruption are excluded because earlier readers
preempt the proposed guards.

When E changes, publicly republish it and update R.manifest_id and P's evidence
ID. If A's content identity changes, update R.root_id, E/R metadata and P's
analysis ID too. `put_root` NEVER overwrites an existing key. For same-root-ID
variants, copy the prefix data while excluding exactly that one analysis root
file, retaining old manifests/artifacts and every other authority. Compute its
filename using the existing test-local canonical public root-key formula.
Publish the replacement R once through public `put_root`. For a new analysis
ID, preserve the old root and publish the distinct new key. This is deliberate
corrupt-input setup on a disposable clone, not a production overwrite API.
Capture the no-mutation snapshot AFTER setup and before the public call. The
original graph must remain byte-for-byte unchanged across all clone variants.

Deferred/excluded: missing/duplicate plans that public reducers cannot create,
store singleton branch :596, preempted analysis identity :2269, deep transcript,
marker or monitor corruption inventories, races, private model seams and
already accepted legacy-guard/completion matrices. Do not widen on the fly.
