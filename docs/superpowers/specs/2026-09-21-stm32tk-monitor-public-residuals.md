# Monitor public boundary residual qualification

Accepted base: d8e134ce803c8b6f70fd8960ee7c117c903f51d1.
Main owns design, dispatch, integration and acceptance. Existing Monitor owner
`/root/physical_reference_impl` (Luna/max) implements tests; the existing independent
reviewer reviews the complete diff and native evidence. This is an offline test
slice within the unchanged 1.0 goal, not product development or a new release gate.

The residual audit DF74A08C and earlier physical-export audit 94B44890 identify
eight candidate native arcs in unchanged Monitor source. U38 still measures the
same Monitor coverage. A previous test of a neighboring outcome does not cover
these exact missing branches. Conversely, an arc estimate is not execution PASS.

## Public scenarios and the corrected reachability boundary

1. Reject malformed public AnalysisPublication component types and malformed
   AnalysisBundleRef construction/wire shape. Reuse valid published objects and
   existing round-trip fixtures; after each refusal require unchanged original
   objects/store bytes and successful public parsing/reuse of the valid input.
   Candidate arcs in analysis_workflows.py:171->172,173->174,175->176,177->178,
   211->213,224->225. No private object fields or authority substitution.
2. **Withdrawn from this executable batch after the complete guard review.**
   A SampleValue can retain a non-NFC typed-value string, but this does not prove
   that public analysis can reach analysis.py:1208->1209. The public
   analyze_monitor_windows entry first calls _validate_window: each batch is
   canonicalized at analysis.py:1157-1168. Shared monitor_replay_contract.py:193-198
   rejects non-NFC string values, not only keys; the physical canonicalizer does
   the same at332-336. Thus the real code points U+0065,U+0301 in the type value
   are rejected before _trusted_sample. Neighboring control-character/extra-key
   tests do not establish this path. This corrects the main's proposed scenario,
   not product behavior. Do not bypass this guard or claim this branch covered.
   Keep the branch in the frozen denominator and the unfulfilled 95% target.
3. Export an accepted physical-shaped analysis using a different, independently
   valid publicly published TestRun ID. Prove the positive export first; the
   mismatch must reach analysis_workflows.py:1336->1347 with the exact TestRun
   identity error, preserve evidence/history, and succeed with the original ID
   restored. The extra run is a software fixture and is never a physical PASS.

## Boundaries

Only a new test file `tools/stm32-monitor/tests/test_risk_monitor_public_residuals.py`
is owned. Reuse existing public constructors, publishers, stores, analysis/export
entries and test fixture helpers. Return any needed helper-file expansion to
main; do not duplicate the graph or add a framework. No product source, schema,
dependency, private cache/state, validator, source range or denominator change.
Do not add private error-return/OS/provider replacements to force other branches.
Do not reopen accepted Sampler/Diagnostic fixes or repeat their regression suites.

Eight is an estimate, not a minimum imposed on the implementation. Verify exact
native branch reachability and subtract the retained U38 execution data. Retain
valid behavior if measurement finds fewer new branches; classify first failures
before choosing a correction. No attempt to reach a numeric gate by weakening an
oracle. This bounded batch completes the new public-model candidates in the
residual audit; another low-yield batch requires a fresh cost/reachability decision.
