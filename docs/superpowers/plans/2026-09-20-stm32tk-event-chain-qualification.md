# Event and predecessor-chain qualification plan

Accepted base: `dcd92a6377e240306de02603027bc6c4f1deb53e`.
Governing specification is the adjacent event-chain qualification document,
within the already approved core public-contract scope. Independent construction
review: r10/e/n95/diagnostic-model-store-design-review.md. Its Store finding is
resolved by exclusion; model and predecessor construction corrections are frozen.

Commit the plan, then create a clean c104e worktree at that exact plan head.
One gpt-5.6-luna/max owner changes only these existing Toolkit test files:
test_diagnostic_events.py, test_fix_verification_events.py and
test_acceptance_continuation.py. It is not alone; preserve others' edits.
Append the nine event variants and one predecessor matrix with one unchanged
positive clone and ten corruption variants. Reuse existing factories; do not
move shared fixtures or build a new mutation framework. No recursive delegation,
pytest/collection/product imports, build, cleanup, hardware or remote action.
The other implementation owner has disjoint probe test files.

All generated paths stay under D:/codex-tmp/v10b-0918/r10: candidate c104e,
detached review r104e, evidence e/n95/event-chain, disposable t/ec1. Primary is
the only pytest executor and cleanup owner. The owner returns a committed
candidate, complete selector list, source/guard/oracle mapping and AST/diff
checks. Do not publish an implementation PASS before actual execution.

Primary reviews the full base-to-candidate diff in r104e, including every public
constructor, hash update, positive graph prefix and first guard. Correctable
findings stay with the same implementer; two nonconvergent rounds require a
construction/design decision. Never replace a failed target with an easier guard.

Reuse the existing bounded launcher and native two-package coverage config.
Bind TEMP/TMP/TMPDIR, basetemp, cache and raw coverage to the assigned roots.
Run only the new event selectors and predecessor matrix with first-failure stop
and a 300-second wall budget after the probe run is terminal. The graph is built
once and cloned; retained prepare_pair executions establish tens-of-seconds
setup, so per-case full rebuilding is outside this budget. If this assumption
fails, classify before a changed retry and preserve completed evidence.

Retain command/environment/log/JUnit/raw/process evidence. Prove unchanged
runtime bytes, reconcile only complete PASS raw data with the current accepted
native union and obtain independent review. No unrelated suite, packaging,
deployment, hardware repeat or cleanup of previously rejected roots. Report
corrections alone never trigger reruns.
