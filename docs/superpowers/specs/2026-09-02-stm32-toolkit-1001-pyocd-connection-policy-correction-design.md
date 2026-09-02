# STM32TK-1001 PyOCD Connection Policy Correction Design

**Module / phase:** `STM32TK-1001 / VS10-A`, bounded hardware-connection correction

**Full accepted base:** `03036f912e16006b1d2030b212962d3704e8a20f`

**Accepted-base tree:** `b7688538514a50f2e083d4bef788030f342daaba`

**Active implementation branch:**
`codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

**Remote baseline:**
`origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl` at
`74ee5f4c7872af1bb612c9068af36319457e087b`; the accepted base is nine local commits ahead and
has not been pushed.

**Specification owner / reviewer:** GPT-5.6-sol primary

**Implementation owner:** exactly one GPT-5.6-luna agent at reasoning effort `max`, after this
specification and its implementation plan are separately approved

**Remote authority:** none. This correction does not authorize push, PR mutation, merge, tag,
release, closure, or remote branch deletion.

## 1. Decision and reason for reopening

The accepted probe-inventory/selection compatibility slice remains accepted. Physical diagnosis
after that acceptance found a separate product defect in the existing single PyOCD backend:

- Toolkit opened the target with `connect_mode="attach"` and
  `pack.debug_sequences.enable=false`.
- The selected `ATK-HS-V3-CMSIS-DAP` probe then failed at 100 kHz SWD with
  `PROBE_ATTACH_FAILED`, caused by a PyOCD `No ACK` transfer failure.
- The same host, probe, board, PyOCD `0.45.1`, CPython `3.12.10`, target
  `STM32F429ZGTx`, and 100 kHz SWD succeeded when opened with `connect_mode="halt"` and Pack
  Debug Sequences enabled. PyOCD discovered one Cortex-M4 core, and an explicit resume returned
  the target to `State.RUNNING`.

The isolated diagnostic evidence is stored outside the repository at
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\backend-option-isolation-20260902-01.json`,
SHA-256 `bf80192281fe7195cd349a855dd122f93cc27d921caa752a3c75cb9ffb5d12ae`.
The user approved replacing the former absolute “observation attach cannot halt” rule with a
bounded transient halt for target discovery and identity validation.

This is a Toolkit `PRODUCT` correction. It is not a probe-selection defect, VS Code extension
dependency, Keil dependency, driver failure, or permission failure.

## 2. Runnable user scenarios

### Scenario 1 — observation connects without leaving the application halted

Given an exact public probe selector, an explicit project target, and an `OBSERVE` Probe Service,
Toolkit opens the selected probe with the pinned PyOCD target, temporarily halts the core while
Pack Debug Sequences perform target/core discovery, proves exactly one valid target identity,
resumes the target, verifies that it is running, and only then returns successful attachment
evidence. Subsequent debug binding, bounded reads, register reads, and Monitor observation use the
same existing public CLI/MCP behavior.

### Scenario 2 — modification remains halted until the existing guarded flash gate passes

Given a `MODIFY` Probe Service and a current exact build identity, Toolkit opens the target through
the same discovery path but keeps it halted after successful identity validation. The existing
flash workflow independently validates the returned probe, requested target, resolved target, and
single-core evidence before it invokes `flash.program`. Programming is therefore impossible until
the connection and firmware gates both pass.

### Scenario 3 — mismatched or unavailable targets produce zero programming

If the resolved target identity is malformed, unavailable, ambiguous, or does not canonically
equal the explicit requested target, attach fails before a successful attach response is published.
Toolkit makes zero flash calls. If Toolkit halted a core, it attempts to resume it before closing
the session. A successful-looking attachment must never be returned after failed restoration or
cleanup.

### Scenario 4 — attach, recovery, cancellation, and cleanup remain fail closed

If Pack Debug Sequence execution, core discovery, attach, resume, state verification, cancellation,
or close fails, Toolkit returns an existing stable Probe error and does not reset, erase, unlock,
program, switch probes, or retry automatically. A cleanup failure never becomes success. The
original failure remains chained as its cause; when Toolkit cannot guarantee safe cleanup, the
existing `PROBE_CLOSE_FAILED` safety error remains authoritative.

## 3. Frozen architecture and ownership

There remains exactly one local runtime, one Probe Service, and one `PyOCDBackend`. This correction
does not add a backend, controller, provider, MCP registration, or Agent-specific path.

The existing internal interface remains:

```python
def open_attach(
    self,
    probe_id: str,
    target: str,
    *,
    halt_on_connect: bool = False,
) -> ProbeAttachmentEvidence: ...
```

The boolean describes the required state at successful return, not the mechanics used during
discovery:

- `False`: transiently halt for discovery and identity validation, then resume and prove running
  before returning.
- `True`: transiently halt for discovery and identity validation, prove halted, and return while
  halted for the guarded modification path.

`ProbeService` owns the mapping from its already-frozen lease operation level to this internal
boolean:

- `OperationLevel.MODIFY` maps to `halt_on_connect=True`.
- `OperationLevel.OBSERVE` and `OperationLevel.CONTROL` map to
  `halt_on_connect=False`. Explicit control operations continue to use their existing
  single-use authorization path after attachment.

`ProbeService` also owns the final canonical requested/resolved-target comparison before it
publishes a successful attach response. It uses the existing flash target-canonicalization rule.
On mismatch it resumes a modification attachment, verifies running state, closes the backend, and
raises the existing `PROBE_IDENTITY_MISMATCH`. This keeps the backend adapter independent of the
flash workflow while ensuring that a mismatched internal candidate session is never exposed as a
successful public attachment.

The client request schema, Probe protocol version, attachment response fields, lease model,
authorization schema, CLI arguments, MCP tools, and error-code inventory do not change.

## 4. Pinned PyOCD session policy

Every production PyOCD target session created by `open_attach()` uses this closed policy:

```python
{
    "auto_unlock": False,
    "connect_mode": "halt",
    "dap_protocol": "swd",
    "frequency": configured_frequency_hz,
    "no_config": True,
    "pack.debug_sequences.enable": True,
    "primary_core": 0,
    "project_dir": os.getcwd(),
    "resume_on_disconnect": False,
    "target_override": explicit_target,
    "user_script": os.devnull,
}
```

Only `connect_mode` and `pack.debug_sequences.enable` change from the accepted-base policy. The
frequency remains the existing explicit backend setting; this specification does not change its
default or add transport auto-negotiation. `auto_unlock=false`, exact fresh probe selection,
`no_config=true`, the explicit target override, and the null user script remain safety boundaries.

Pack Debug Sequences are those supplied by the already pinned PyOCD/CMSIS-Pack runtime. Toolkit
does not read VS Code or Keil settings at runtime and does not admit a project-local PyOCD config or
user script.

## 5. Target identity, state, and publication order

The backend performs these steps in order:

1. Validate the public probe selector and explicit target before enumeration.
2. Freshly resolve exactly one physical probe through the accepted selector adapter.
3. Close any prior owned backend session.
4. Create and open one PyOCD session with the frozen policy.
5. Require one target object and exactly one core.
6. Read and validate a portable resolved part number.
7. If `halt_on_connect=False`, resume and verify the target reports running. If
   `halt_on_connect=True`, verify it reports halted.
8. Only after all preceding checks succeed, publish the session, target, selected probe, selector
   hash, requested target, and resolved part number into backend-owned state and return candidate
   `ProbeAttachmentEvidence` to `ProbeService`.
9. Before encoding any successful response, `ProbeService` requires canonical equality between the
   resolved part number and requested target. Canonical equality is case-insensitive and ignores
   punctuation only; it does not use prefix, substring, family fallback, or a vendor table. On
   mismatch the service restores running state when necessary, verifies restoration, closes the
   backend, and fails with `PROBE_IDENTITY_MISMATCH`.

Failures before step 8 operate only on local candidate objects. A failure at step 9 closes the
backend-owned candidate before returning a response. Cleanup must not publish a partial or
mismatched public attachment. A modification caller receives no attachment evidence and therefore
cannot reach the existing programming request when identity or state validation fails.

## 6. Error semantics and cleanup

No new public error code is introduced.

- Invalid selector and target input retain `PROBE_SELECTION_REQUIRED` and
  `PROBE_TARGET_INVALID`.
- Missing target, ambiguous cores, and unavailable/malformed identity retain the existing target
  error codes.
- A resolved target that does not canonically match the explicit requested target fails at the
  Probe Service attach boundary with the existing `PROBE_IDENTITY_MISMATCH` code, after bounded
  resume and close. The
  public flash workflow converts only this attach failure back to its already-established
  `FIRMWARE_IDENTITY_MISMATCH`; other attach failures retain their own codes.
- PyOCD open, Pack sequence, resume, and state-transition failures are normalized through the
  existing `PROBE_ATTACH_FAILED` or existing target-state/backend error boundary, without exposing
  raw host paths or hardware identifiers.
- Cleanup that cannot close the session/probe safely retains `PROBE_CLOSE_FAILED`; the initiating
  error is chained as the cause where applicable.
- Upper flash identity rejection retains `FIRMWARE_IDENTITY_MISMATCH` and must observe zero calls to
  `flash_elf` / `flash.program`.
- Cancellation remains cancellation after bounded recovery and cleanup; it is not converted to
  success or an automatic retry.

On every failed candidate session that may have halted the target, cleanup attempts one bounded
resume before session/probe close. It must not reset, erase, mass-unlock, or reopen the target. If
resume is impossible because no target was discovered, cleanup closes only the resources that were
successfully acquired.

## 7. TDD implementation boundary

The sole Luna/max implementer may change only the minimum product paths needed for this correction:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`

Applicable tests may be added or changed only in:

- `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`
- `tools/stm32-toolkit/tests/test_probe_service.py`
- `tools/stm32-toolkit/tests/test_flash.py`
- `tools/stm32-toolkit/tests/test_debug_firmware.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_monitor_observation.py`

If TDD demonstrates that a product path outside the three named files is necessary to satisfy the
frozen public behavior, implementation stops and returns the exact conflict to Sol. The implementer
must not widen scope, weaken existing assertions, or modify runtime-installation code in this
slice.

Required RED evidence proves:

- the exact frozen PyOCD options;
- observation resumes and verifies running before attachment publication;
- modification stays halted and verifies halted before attachment publication;
- resolved-target mismatch, malformed identity, ambiguous cores, attach failure, resume failure,
  close failure, cancellation, and timeout do not publish a usable session;
- the mismatch path produces zero `flash_elf` / `flash.program` calls; and
- debug binding, read workflows, and Monitor observe only after the successful running-state
  observation attachment.

The implementer commits failing tests before product code, then the minimum product implementation,
then an implementation report in a separate commit. It must not accept its own diff.

## 8. Proportionate verification and evidence ownership

### Slice verification — Luna/max

Run the smallest focused CPython 3.12 matrix covering the changed backend/service behavior and the
six named test files. Use a fresh external run-owned basetemp and no pytest cache. Record the exact
command, interpreter, commit, counts, and cleanup result. Do not run hardware, the full Python
suite, packaging, release, coverage, UI E2E, other Python versions, or unrelated migration tests.

### Independent review — Sol

From a clean detached worktree at the returned implementation-report commit, inspect the complete
`03036f912e16006b1d2030b212962d3704e8a20f..CODE_HEAD` diff and the report-only delta. Re-run the
same focused matrix with a fresh external basetemp. Review option values, identity/state ordering,
zero-programming proof, cancellation, cleanup, unchanged public schema, and scope. Only Sol may
issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`.

### Physical smoke — Sol after software acceptance

Only after the software diff is accepted, and only under existing hardware authority, run one
real 100 kHz SWD observation attach against the exact public probe selector and
`STM32F429ZGTx`. Required physical evidence is: successful one-core identity, transient halt,
explicit return to running, no flash/reset/erase/unlock, no residual process/port, and exact
evidence hash. A guarded flash is not part of this correction's default verification and requires
its own explicit operation authorization.

After every test, clean only the exact run-owned basetemp and disposable logs once their minimum
result evidence is preserved. Never delete tracked tests, fixtures, baselines, existing campaign
evidence, user files, shared caches, or unrelated protected residuals.

## 9. Explicit non-goals

This correction does not:

- special-case `ATK 20210914`, ATK probes, STM32F429, a USB serial, or a board model;
- parse, copy, depend on, or rewrite VS Code, Cortex-Debug, Keil, OpenOCD, or project-local PyOCD
  configuration;
- add transport negotiation, automatic fallback, retry, auto-selection, unlock, reset, erase, or
  recovery programming;
- change the accepted probe selector/fingerprint behavior;
- add or change a public CLI/MCP command, schema, protocol version, authorization, lease, runtime,
  backend, provider, controller, or Agent adapter;
- repair the Windows console-launcher relocation defect; that defect is a separate sequential
  correction slice with its own accepted base, specification, plan, implementer, and review; or
- push, mutate a PR, merge, tag, release, close, or delete any remote branch.

## 10. Acceptance conditions

The correction is accepted only when all of the following are true:

- all four scenarios have direct tests and the focused matrix passes on CPython 3.12;
- the production session options exactly match the frozen policy;
- observation returns only after running-state restoration, while modification returns only while
  halted;
- every identity/state/attach failure proves zero programming and no partial published session;
- mismatch and failure cleanup cannot reset, erase, unlock, auto-retry, or silently leave success;
- public CLI/MCP, protocol, attachment evidence, selectors, authorizations, leases, runtime, and
  Agent-neutral architecture remain unchanged;
- the complete accepted-base-to-code-head diff has no unresolved product, safety, compatibility,
  test, or scope defect under independent Sol review;
- the implementation report accurately records the accepted base, RED/GREEN lineage, code head,
  verification, cleanup, hardware boundary, and remote state; and
- the candidate worktree and reviewer worktree are clean, with remote state stated explicitly.

Acceptance of this correction does not accept the runtime-launcher correction, guarded flash,
VS10-A hardware completion, VS10-B, a release, or any remote action.
