# Diagnostic lock contention correction plan

Accepted base: `fa8502e6bf706fcaae26122cf996077678053cc5`.
Governing design: `../specs/2026-09-19-stm32tk-diagnostic-lock-contention-design.md`.
This corrects a demonstrated supported-scenario product/platform failure in the
authorized 1.0 local release goal; no scope or remote authorization is added.

Primary owns specification, decomposition, entry review, integration, evidence
cleanup and final acceptance. One Luna/max implementation owner uses isolated
`D:\codex-tmp\v10b-0918\r10\lk`, branch
`codex/STM32TK-1.0-diagnostic-lock-contention`. Independent review uses a separate
clean checkout at the exact returned head. No recursive delegation.

## Ownership and implementation

The implementation owner owns only:

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`:
  bounded Windows native acquisition, operational busy exception and cleanup.
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`:
  export that operational exception.
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py` and
  `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py`:
  narrow result-adapter handling, forwarding the recognized nested Diagnostic
  Busy failure in `_public_data`, and sanitized availability messages only.
- Existing DiagnosticStore and workflow test modules for this behavior; reuse
  their fixtures. A new post-publication Busy case may be added to
  `test_continuation_monitor.py`; the existing concurrent continuation test
  function must remain byte-for-byte unchanged. No ownership of the four
  public-decode qualification test modules is transferred to this owner.
- One short implementation return under
  `docs/codex/returns/STM32TK-1.0-local-release/diagnostic-lock-contention-report.md`.

Do not modify model schemas, lock users' ordering, other acquisition primitives,
hardware code, release configuration or lockfiles. Do not remove checks to make
the original test pass. Shared contracts and constants are owned by this one
implementation owner; primary alone edits the design/plan.

## Proportionate verification

Reuse `_failed_evidence`, `_created`, the existing store concurrency fixtures and
the public result fixtures. Deterministic native/clock fault injection must enter
through an existing public store/workflow operation, preserve real validation,
and prove timeout, non-contention refusal, no late protected entry and cleanup.
Include direct and nested public Busy results and post-publication revision-1
preservation/exact retry, as specified by the design. Use the existing durable
fixture; no duplicate diagnostic framework or ten-second sleep is required.
Source scopes remain the same except for the explicitly named nested adapter.
A small standard-library native child/descriptor fixture is allowed only for
the actual cross-process exclusion check; use an existing subprocess pattern,
finite waits and owned-child cleanup, not a new runner or lock framework.
The native child fixture uses an explicit ready/release handshake: after ready,
it continues holding the lock until the parent has observed its public Busy
result and sends release. A fixed sleep is not proof of continued ownership.
Both readiness and child release have finite deadlines; unconditional parent
cleanup releases the signal and settles or terminates only its owned child.
Fault injection and close assertions concern the Diagnostic lock descriptor;
public load may also open and close evidence descriptors or acquire other native
locks. Preserve their constants and behavior instead of counting all process
closes as if they belonged to one lock.

First run the affected store module and new adapter cases once with `-x`. Then
run exactly the existing node
`test_continuation_monitor.py::test_persisted_continuation_monitor_diagnostic_and_expired_attempt_reuse`
once with Toolkit branch instrumentation. No other verification child runs
during that second step. Keep its assertions, data and two-worker behavior.
Product imports must point to the implementation tree, NOT frozen verify15b;
the latter remains the immutable failure baseline.

Use `r10/py`, explicit PowerShell 7, and short temp roots under `r10/t/lk` with
all TEMP/TMP/TMPDIR, basetemp and caches bound and actual tempfile checked.
Use short children `t/lk/f/b` and `t/lk/c/b` for focused and continuation basetemp,
respectively; retain the descriptive evidence directory names. Existing Windows
publication fixtures have demonstrated native path-limit failures with longer
derived temporary paths.
Reuse the working bounded child-launch pattern from retention r3; do not add
another generic runner. Set finite child bounds of 180 seconds for focused
store/adapter tests and 240 seconds for the continuation node. Primary reviews
exact command/entry before execution; commit code first. Store raw coverage,
JSON, JUnit, stdout/stderr, source heads, command and real child exit under
`r10/e/diagnostic-lock-contention`. Do not combine failed-run coverage.

Independent complete-diff and result review precedes integration. Correctable
findings stay with this owner/branch. Do not repackage/deploy, benchmark, run a
full suite, access hardware, clean preserved evidence or mutate GitHub in this
slice. Final packaging will need the accepted new runtime bytes; unchanged
hardware behavior is not automatically retested for this offline lock fix.
