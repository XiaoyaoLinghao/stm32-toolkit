# Historical release fixture portability

Accepted integration base: `47988d34725f97075d3ea69a43a65cb5b2144189`.
Shipped product remains `15b1a70e9bd684285da5557104deff529f537e49`.
Primary owns this contract, integration and acceptance; one Luna/max owner
implements and tests it, followed by independent complete-diff review.
This is necessary local-release work under the active user-authorized goal.

## Runnable scenarios

1. Historical 0502 controller tests execute against the historical 0.5.0 launcher
   contract even when current launchers target 1.0.0. Store two small, immutable
   launcher fixtures under `tools/stm32-toolkit/tests/release/fixtures/0502/`,
   extracted exactly from local commit
   `eae54be02cd28a707488f15f58b8f58e66db1a2c`. Record original blob identifiers
   `43be14c9c2b1c5fc0fa34cb7b6e85751be2e366b` and
   `ad7eaa864a53dd7e6d871f152587eba1de80d56d` in the fixture attribution.
   Tests consume these tracked bytes without requiring Git ancestry at runtime.
   Existing controller expectations and final product launchers stay unchanged.
2. 0600 unit contracts execute with their required environment: no coverage
   injection for no-coverage gates, existing pinned Node dependencies, and a
   verified fake support profile below the approved D drive run root. The
   17-file support manifest and final 435-package dependency graph remain the
   input authorities. Do not copy the old UI package metadata over final files.
3. The hardware contract self-test uses only its existing FakeBackend and can
   receive test-owned temp/profile paths in its child process. A private seam
   accepts `STM32TK_TEST_0600_TEMP_ROOT` and
   `STM32TK_TEST_0600_SUPPORT_PROFILE` only with `PYTEST_CURRENT_TEST` present.
   Require canonical absolute existing appropriate directory/file inputs; partial
   overrides or use outside pytest fail before creating output. This host binds
   both paths below `D:\codex-tmp`; do not hardcode that host path into the helper.
   When absent, historical public defaults remain unchanged. No new public CLI,
   hardware backend or general path framework is introduced.
4. Two stale public-contract tests use the approved current contract: GC's closed
   registry contains `physical-continuation` (12 root kinds), and regeneration
   CLI tests supply an absolute project root. Preserve all reachability,
   refusal and no-mutation assertions; do not change product behavior.

## Boundaries and evidence

Allowed implementation files: `test_0502_release_gate_controller.py`,
`tests/release/test_gate_controller_0600.py`,
`tests/release/test_release_verifier_0600.py`, `test_evidence_gc.py`,
`test_regeneration_cli.py` (all under `tools/stm32-toolkit/tests`), the two
historical fixtures and their attribution, and only the private self-test seam
in `tools/release/run_0600_gates.py`. Report in the existing release return tree.
No source package, launcher, schema, dependency lock, thresholds or physical
authorization changes. No hardware, remote operation or repeated packaging.

Independent clean-checkout review found Git's Windows line-ending conversion
changes the two fixture files' raw hashes, although their Git blobs are correct.
The same fixture owner additionally owns a directory-local `.gitattributes` in
`tests/release/fixtures/0502/` with exactly the two launcher filenames marked
`-text`. This preserves the authoritative historical bytes in a fresh checkout;
do not change global Git configuration, active launchers or root attributes.

Original full-suite failures remain evidence. Correct only their known causes,
then run the exact 51 no-coverage, 2 Node, 16 support and 10 historical launcher
nodes, plus the one GC and one CLI node. Add narrowly focused seam guard checks
for partial overrides and non-pytest callers. This evidence is a test-contract
correction, not a new hardware or historical release acceptance.
