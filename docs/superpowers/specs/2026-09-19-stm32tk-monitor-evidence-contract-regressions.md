# Monitor evidence-contract release regressions

Accepted integration base: `bab6c8e8d698aa3bddd88a0d20e94a7864980633`.
Frozen product/artifact CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.
The user's ongoing local-release goal authorizes necessary bounded test work.
Primary owns design, integration and acceptance; each test slice has one
Luna/max implementer and an independent non-implementing reviewer.

## Evidence and scope

The existing Monitor suite passed 732 tests. Cross-package instrumentation
completed with 230 passes and two separately diagnosed Toolkit failures.
Combining it with the independently accepted public-lifecycle regressions yields
2394/2936 actual Monitor branches (81.5395%), below the unchanged 90% gate.
Remaining missing branches include replay 167, analysis 77 and analysis workflows
80. Coverage is a locator, not permission to manufacture impossible states.
The two Diagnostic failures retain their original evidence and are outside this
test-only implementation scope until their contract diagnosis is complete.

## Four runnable caller scenarios

1. A caller imports a closed replay document or constructs/parses a public run
   reference. Invalid identity, schema, ordering, window, scalar or digest data
   must be refused through the existing public model/parser contract before
   history or evidence publication. Valid canonical round trips remain usable.
2. A caller reloads or retries an existing replay/physical publication after
   an upstream root/artifact is absent, contradictory or unreadable, or a bounded
   provider failure left a valid publication prefix. Public operations must
   distinguish integrity, intent conflict and environment failures, preserve
   durable authority and support only the existing idempotent retry contract.
   These are offline fixture tests, never physical acceptance claims.
3. A caller submits or reloads an analysis request/result with incompatible
   replay/physical reference families, native alignment fields, statistical
   counts, quality/conclusion, lineage or request/result identity. Public model
   constructors/parsers and analysis entry points must retain their published
   closed contracts, reject contradictions and preserve valid results.
4. Analysis comparison/export receives malformed paged history, incompatible
   source/run/window authority, a contradictory publication or provider failure.
   It must refuse without derived publication or classify a recoverable valid
   prefix according to the existing contract. CLI adapters must preserve the
   public error category without leaking exception text or paths.

## Frozen contracts and ownership

All public model shapes, error mappings, mutation ordering, source identities,
retry/lifecycle rules and provider boundaries come from the current approved
specifications and product15b implementation. This slice does not redesign them.
A contradiction between code and authoritative contract is a product finding to
return to primary, not permission to change an expected value to match code.

Replay slice owns only existing Monitor `tests/test_replay.py` and
`tests/test_physical_publication.py`. Analysis slice owns only existing
`tests/test_analysis.py`, `tests/test_analysis_workflows.py` and
`tests/test_analysis_cli.py`. Each has a distinct implementation report. Existing
shared fixture helper signatures and default behavior are frozen; reuse them
without changing the other slice's test inputs. Worktrees and run roots are
separate. Production modules, schemas, dependency/lock files, shared configuration
and the separately failing Toolkit test module are read-only for both slices.

Use public parsers/constructors/workflows and existing fixture/provider seams.
Parameterization may express distinct malformed external inputs and invariant
classes; it must not merely enumerate private conditionals. Do not mutate frozen
typed objects to create states no caller/provider can supply, add a generic
framework, lower coverage thresholds/exclusions, or change product code. Add no
new transport, hardware run, deployment or package build. New real product defects
require a primary classification and bounded contract amendment before repair.

## Verification and acceptance

Each owner runs only its affected modules against the unchanged final product
source in `r10/verify`, with all temporary and coverage paths under its short D
run root. Keep source/test commit identities separate and retain exact environment,
command, stdout, stderr, JUnit and binary branch coverage. Slice coverage is
informational; it does not replace the per-package release gate. Report statement,
branch and combined ratios separately. Preserve initial failures.

Independent review covers the complete accepted-base-to-final diff, meaningful
scenario assertions, unchanged product source and source-path attribution.
Primary integrates accepted test-only changes. Standard coverage combination
reuses valid prior execution; no second full suite or packaging for test/report
changes. If remaining unmeasured paths are not meaningful reachable scenarios,
report that fact and return to primary rather than gaming the gate. Whole-release
acceptance remains pending all mandatory gates, including the two actual failures.
