# Current-version public firmware fixture for finalization qualification

Accepted base: `d8e134ce803c8b6f70fd8960ee7c117c903f51d1`.
Primary owns this design, integration and acceptance. The existing Recovery
Luna/max owner implements the test-only change; independent review is required.
The user-authorized 1.0 qualification goal and all frozen coverage gates remain.

The retained historical project correctly fails the current firmware loader:
its build identity says0.9.0 while current Toolkit is1.0.0. Preserve that failure,
the historical project/data, all physical PASS and the unchanged version guard.
The existing default synthetic fixture bypasses the private firmware-fact alias;
its behavior results remain valid within their previous scope but do not qualify
native authority coverage. Neither route may be relabeled as a new physical PASS.

## Runnable scenarios and boundary

1. In one disposable copy of the complete retained project, use existing public
   configure/build entry points to produce before and after firmware facts. Both
   phases must pass the unmodified public fresh-firmware loader. The actual source
   change, project/Git/snapshot/build/ELF identities and artifact hashes must be
   derived from those public results, never rewritten or replaced with constants.
2. Reuse the existing finalization journey to authenticate a complete fixture
   graph and exercise begin/checkpoint/refusals/deadlines/terminal retry. The
   active after-build files must remain fresh through all public authority checks.
3. Reuse the real fresh-show subprocess to authenticate persisted state after
   publication. Capture its native data independently from the parent process.

These are offline software scenarios. Replay TestRun/Monitor/physical-shaped
records remain explicitly test fixtures even when bound to real build facts.
Use existing public stores, constructors and workflow entry points; do not patch
private facts, readers, validators, factories, clocks beyond the existing public
context injection, or identity generators on the qualified path. No product code,
schemas, authorization rules, hardware, release artifacts or installer changes.

Keep the default portable test behavior and explicit historical-input branch.
Add one explicit opt-in current-project seed setting for this qualification;
reject ambiguous simultaneous legacy/current fixture selection. Record the mode
and seed identity. No implicit fallback may qualify native data. Reuse the shared
fixture graph construction; do not clone the journey or create a fixture framework.

Implementation ownership is limited to
`tools/stm32-toolkit/tests/test_acceptance_finalization.py`. If existing helpers
cannot accept actual build identities without changes elsewhere, return the
concrete dependency to primary before expanding ownership. Current product bytes
must remain unchanged. All copies, build outputs and raw evidence stay in the
assigned D:\codex-tmp roots; original retained projects/evidence are read-only.

## Main-owned identity design return after run1

This is a test-fixture contract correction, not a product change. The complete
identity audit is `r10/e/risk-v2/finalization-current/identity-design-input.md`,
SHA256 `A3B6FE56EF16B3764AE7CB628218B029D22785FD1AE3A816735C16943C32A73E`.
Run1 reached the public `firmware-built-after` checkpoint at revision 6 before
Monitor publication refused a binding whose debug target was `board:t10` instead
of the public project's `stm32f429zgtx`. Preserve that failed run and its phase
correction. Diagnostic's public 32-hex identity is valid; do not convert it.

Freeze two target domains across the whole graph: fresh firmware facts and
`model.target.device` supply the semantic target device in EvidenceIdentity,
TargetRun and Recovery; `model.debug.target` supplies Monitor physical_target.
Both before and after Monitor bindings use the copied project's public debug
target. Probe raw-label/digest, flash/lease, run/case and signal fixture identities
retain their existing separate roles and published cross-references. The current
memory-mailbox project uses the existing mailbox physical-publication mapping.
Do not rewrite the project, substitute private authority or relax any reader.

Extend ownership only to the `_append_physical_monitor_history` helper in
`tools/stm32-toolkit/tests/test_acceptance_physical_recovery.py`, in addition to
the already owned finalization test. Add a keyword physical_target argument with
the existing `board:t10` default so untouched callers keep their behavior. The
finalization graph explicitly supplies its own public model's debug target in
both current and portable branches. Assert the current graph's separate target
domains and provenance relationships using existing public objects. No other
helper contract, production file or test framework is in scope.
