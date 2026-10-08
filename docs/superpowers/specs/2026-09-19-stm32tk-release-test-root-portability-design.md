# Release-test temporary-root portability

Status: authorized under the user's 1.0 local-release goal; bounded fixture and test-seam fix.
Accepted base: `1df30a0f4070805488687a67f907dbaa1867d681`.
Primary owns design/integration/acceptance; one Luna/max owner changes fixtures and
runs their tests; a separate reviewer accepts the complete diff. No remote action.

## Scenarios and scope

1. The complete Python release suite runs with TEMP/TMP/TMPDIR and pytest basetemp
   under the approved D-drive run root; legacy fixtures also create files there.
2. Native Windows path/lock/coverage fixtures retain their real filesystem checks
   using the owned temporary tree, without opening or creating a `C:\tmp` tree.
3. Fixture cleanup targets only the paths created by that fixture, preserving
   sibling user data and retained release evidence.

Non-goals: no public product/runtime behavior, release version, assertion relaxation,
generic fixture framework, new dependency, hardware, or remote change. Literal
Windows path strings used only as parser/negative-test input are not filesystem
operations and retain their test meaning.

The concrete blocker is `tempfile.mkdtemp(..., dir=r"C:\tmp")` in ten legacy
test modules. It overrides all environment variables. Replace actual fixture
allocation and coupled parent/sibling/lock accesses with the standard resolved
temporary root or fixture-owned parent. Reuse `tempfile`/pytest facilities; do
not add a second path-policy mechanism. Preserve short directory names needed by
Windows generated-project staging. All three environment variables remain a
preflight requirement; the suite must not infer an external authorized root.

Owned files: `tools/stm32-toolkit/tests/test_diagnostic_store.py`,
`test_diagnostic_workflows.py`, `test_evidence_catalog.py`, `test_evidence_gc.py`,
`test_evidence_store.py`, `test_host_testing.py`, `test_testing_publication.py`,
and `tests/release/test_release_verifier_0600.py`, `test_gate_controller_0600.py`,
`test_acceptance_feasibility_0600.py` under the same Toolkit test root.
Any newly discovered actual external-write site is reported with its call path
before expanding this list. Release-version tests have separate ownership.

## Coverage-controller seam amendment

The first retained Windows coverage-sibling run failed before its runner because
`run_dev_coverage` validates and locks a fixed `C:\tmp` parent. Moving only the
fixture cannot exercise that real lock/pipe contract in the approved D-drive root.
The same controller already supports a private, pytest-only temporary-root
argument for `run_wrapper_contract`; reuse that pattern for `run_dev_coverage`.

The fixture owner additionally owns only the coverage-root seam in
`tools/release/run_0600_gates.py`: a private keyword argument, defaulting to the
unchanged legacy root, passed consistently to location validation and directory
locking. A non-default override must be rejected without `PYTEST_CURRENT_TEST`,
before directory creation or runner invocation. There is no new CLI switch or
ambient environment root selection. Keep the frozen basetemp parser token
unchanged; actual runtime basetemp remains within the locked evidence root.
Canonical direct-child, new-path, outside-repository, no-reparse, sentinel,
native handle identity and post-lock revalidation checks all remain effective.

Use the fixture-owned existing parent explicitly at affected test calls; do not
patch validation or locking to succeed. Verify the retained failing raw-pipe
publication case, real native locking, rejection without pytest context, and
wrong-parent/existing-path/refusal behavior. This corrects a release-test
environment boundary, not the accepted hardware/runtime contracts. The initial
coverage failure remains retained and is not deferred or called PASS.

Acceptance requires unchanged test assertions, no live hardcoded external temp
operation in this scope, successful representative native/fixture checks, and
independent full-diff review. The final release matrix runs after integration;
do not duplicate it for this fixture-only change.
