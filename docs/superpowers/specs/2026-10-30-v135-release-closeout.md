# v1.3.5 local release closeout

Accepted base: 946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432.
Primary owns design, orchestration, complete-diff review and acceptance; the local
Claude Code CLI using the existing deepseek-v4.1-flash[1m] configuration owns
product/test/documentation implementation and delegated verification.

The user authorizes version closeout, documentation updates, integration regression
and local package acceptance. No hardware, original-firmware changes, replacement
of installed runtime, global settings, push, PR, tag or publication. Firmware-specific
ABI and CCM issues are outside this work; preserve existing diagnostics.

## Public behavior

Align active Toolkit, Monitor, UI root/lock, plugin, launchers, setup, release utility,
policy and release schema to1.3.5. Recognize1.3.4 as an additional legacy managed
runtime and generation producer, preserving every older entry and integrity guard.
Recognition is read-only; explicit existing Repair/configure transactions still
own mutations. Future-version, same-version source mismatch, downgrade, identity,
lease and authorization refusals remain. Do not change dependencies, schemas,
templates, accepted flash behavior or production timeout budgets in this slice.
Preserve pyOCD0.46.0 and the ordinary100kHz default.

Current user documentation describes an unpublished local1.3.5 candidate, with
published1.3.4 clearly separated. Never imply an available1.3.5 GitHub download or
an installed upgrade. Cover preset evidence isolation, field-level flash-region
errors, migration/debug handoff guidance, controlled reset/HALTED gate, attach
progress, dependency repair and preservation of initiating flash diagnostics.
Keep historical release records immutable. One candidate-source/original-pair
ordinary100kHz flash passed; that is neither installed1.3.5 nor release acceptance.

## Gates and evidence ownership

Claude runs bounded existing offline integration/version/setup tests with the
verified direct CPython3.12.14, isolated0.46.0 SDK and existing dependencies.
Primary reviews the full diff in a clean exact-head checkout and independently
verifies material contracts. No new test helper/validator/automation is product scope.
Any product/test correction belongs to a bounded Claude edit task.

Coverage uses native branches and unchanged responsibility rules. The user-approved
v1.3.5 condition is each group's exact ratio >=v1.3.4; see the dated coverage
authorization. Reuse only source/config/dependency-bound evidence, dropping arcs
for changed source. Preserve failures/skips and attribution. Do not label an old
aggregate or a startup message a fresh passing run.

Freeze the reviewed candidate, build twice independently from canonical tracked
bytes with the existing official offline builder, compare all13 outputs and verify
an extracted bundle. Existing wheelhouse/cache inputs must match the current
policy, including0.46.0; resolve missing inputs offline before building. No package
installation is part of this authorization. Final installed VS Code/MCP and any
other mandatory external checks remain explicitly pending with owner/scope.

Completion is one concrete local candidate, package hashes and a reconciled
acceptance report. An unmet comparison or code failure requires revision; missing
external evidence remains pending and is not promoted to release acceptance.
