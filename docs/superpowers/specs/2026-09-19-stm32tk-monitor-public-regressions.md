# Monitor public refusal and lifecycle regression evidence

Accepted product base and frozen release candidate:
`15b1a70e9bd684285da5557104deff529f537e49`.
The user's active local-release goal authorizes this necessary bounded test work.
Primary owns this contract and acceptance; Luna/max implements tests; a separate
reviewer examines the full base-to-final diff. No product changes are authorized.

The final Monitor suite passed 732 cases, but measured only 2359/2936 branches.
Cross-package instrumentation is being supplemented separately. A read-only audit
also confirmed distinct public gaps in CLI, ProbeSession and MonitorSampler that
the Toolkit tests do not call. These caller-visible refusals and lifecycle states
can be verified independently of the aggregate result; raw coverage percentages
alone do not justify private-helper or impossible-state tests.

## Four scenarios

1. A public replay/physical/analysis CLI adapter receives an absent or invalid
   project context. It returns the documented sanitized protocol refusal and
   exit status before calling a workflow or opening a device. Reuse existing
   CLI temporary-project fixtures and production error mappings.
2. A connected caller requests a variable/register catalog with an invalid query,
   or its observation provider fails. ProbeSession preserves the public request
   versus provenance error distinction, exposes no raw exception/path, and does
   not fabricate catalog data. Use the existing FakeObservation and typed
   OperationResult boundary.
3. An admitted caller prepares a read plan and then changes its watches. Invalid
   preparation is refused; a changed watch set cannot reuse the original plan
   or perform a backend read. Use existing public revalidate, prepare_read_plan
   and read methods and the existing observation fixture.
4. Sampling starts or resumes after admission succeeds but plan preparation
   fails. The public lifecycle remains IDLE or PAUSED_BLOCKED as specified and
   creates no sampling work. More than 256 active watches are refused, and a
   delivery subscription made after close terminates promptly. Reuse the
   existing group, observation, sampler and lifecycle fixtures.

## Boundaries

Only the three existing Monitor test modules `test_cli.py`,
`test_probe_session.py` and `test_sampler.py` may change. Reuse existing fixtures
and public methods; do not add a general harness or new test framework. Do not
edit product modules, dependencies, schemas, coverage exclusions or thresholds.
Do not mutate frozen release, physical evidence or the running verification
checkout. No hardware, packaging, deployment or remote action is needed.

Assertions must prove observable error/state and relevant absence of side
effects. Do not mutate internal immutable objects merely to hit defensive
branches, count impossible states as scenarios, add sleeps to make timing pass,
or mirror every private conditional. A discovered product failure returns to
primary with its exact reproduction; this test-only scope does not authorize a
product fix. Existing valid evidence remains intact.

## Evidence and candidate identity

Implementation runs only these affected modules in the isolated test checkout.
Temporary, cache and coverage output is under `D:\codex-tmp\v10b-0918\r10`.
The existing final-source full suites continue unchanged. Record the test commit
separately from product CodeHead: the shipped product remains 15b1a70e and the
supplement must prove product-source equality before contributing coverage.
Independent review and primary acceptance are required before any supplement is
counted. Test-only changes do not trigger rebuilding or re-running the release
matrix. Use normal coverage append/combine with explicit source mapping when the
verification owner reconciles measurements; do not duplicate source paths in
the coverage denominator. The whole-release gate remains actual per-package
branch coverage >=90%, plus all other approved release gates.
