# STM32TK-1001 Public Bind Observation Compatibility Design

Date: 2026-09-03

Module / phase: `STM32TK-1001 / VS10-A H2`, bounded public bind/read correction

Status: FROZEN FOR USER REVIEW

Full accepted base: `52392e4910aea3a152b0d2dd4d3c4b7d61f8a410`

Accepted-base tree: `28b94cb6d9f61df09adf593caedaee4226dc742f`

Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

Remote branch baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`; the accepted base is 59 local
commits ahead and has not been pushed.

Specification owner and final reviewer: GPT-5.6-sol primary

Implementation owner after separate specification and plan approval: exactly one GPT-5.6-luna
agent at reasoning effort `max`

Remote action: none authorized

Hardware action: none remains authorized; this specification and its implementation are
software-only

## 1. Trigger, classification, and exact defect boundary

After one separately authorized public under-reset recovery flash succeeded and published the
ordinary trusted `flash-result.json`, the next separately authorized public register-read attempt
failed during debug binding with `DEBUG_TARGET_MISMATCH`. It did not enter register read and did
not retry. The retained external evidence is:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-under-reset-recovery-success-bind-mismatch-20260903-03.json`;
- SHA-256 `03d5ca496d4184b6c555ee06173436d9e6f32592ac5f20a70f21d50097e2e407`.

Source inspection proves that this public result is not reliable evidence of a physical target
identity mismatch. `bind_debug_firmware()` currently catches every exception raised by its initial
and final `client.attach()` calls and rewrites it as `DEBUG_TARGET_MISMATCH`. The later debug-read
attachment guard has the same behavior. A backend attach failure, unavailable service, invalid
protocol response, cleanup failure, or other structured Probe error can therefore be falsely
reported as a target mismatch.

The public observation workflow also constructs the normal default worker at 1 MHz. In contrast,
the same host, opaque probe selector, board, target, PyOCD 0.45.1, and CPython 3.12.10 previously
completed a physical observation attachment at exactly 100 kHz SWD with normal
`connect_mode="halt"`, Pack Debug Sequences enabled, one Cortex-M4 core, and a verified return to
running. That evidence is:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-physical-observation-attach-20260903-01.json`;
- SHA-256 `81c6ca89af42be25902379ae9e413c3bdb20e8779645013ff426b280288eed87`.

The latest failed public bind does not prove that 1 MHz itself failed because the error-collapse
defect hid the original Probe error. The bounded compatibility decision is nevertheless to use
the only physically proven observation frequency for existing public observation workflows while
making every attachment failure truthful. A later physical run is required to prove that the
combined product correction restores public bind/read.

Failure classification: `PRODUCT`. This is not a VS Code extension, Keil, USB-discovery, trusted
flash-evidence, probe-selection, or SVD-selection defect.

## 2. Runnable user scenarios

### Scenario 1 - public observation uses the proven non-resetting profile

Given an exact public probe selector, current trusted flash evidence, and an existing public
observation operation, Toolkit starts its existing single Probe Service and single PyOCD worker
with exactly 100 kHz SWD and the accepted normal halt-connect policy. It temporarily halts for
discovery and identity validation, resumes and proves running before publishing observation
attachment evidence, and performs no reset, erase, unlock, programming, fallback, or automatic
retry.

The profile applies consistently to existing public `OBSERVE` workflows constructed by
`hardware_workflows`, including debug bind/read consumers, and to Monitor observation. It does not
create a new public mode or configuration surface.

### Scenario 2 - a genuine target mismatch remains a debug target mismatch

If `client.attach()` returns attachment evidence whose probe, requested target, resolved target,
or single-core facts do not exactly satisfy the existing debug-binding contract, debug binding or
the later read guard returns `DEBUG_TARGET_MISMATCH`. If the Probe Service itself rejects exact
identity with `PROBE_IDENTITY_MISMATCH`, the debug layer also maps that one exact code to
`DEBUG_TARGET_MISMATCH`.

No memory read, register read, successful binding, or Monitor session is published after a target
mismatch.

### Scenario 3 - structured Probe failures retain their real cause

If an initial bind attachment, the final bind attachment, or a later debug-read reattachment raises
a structured `ProbeClientError` other than `PROBE_IDENTITY_MISMATCH`, the enclosing public
operation returns its exact stable Probe code, message, and JSON-safe details. Examples include
`PROBE_ATTACH_FAILED`, `PROBE_SERVICE_UNAVAILABLE`, `PROBE_RESPONSE_INVALID`,
`PROBE_PROTOCOL_INVALID`, `PROBE_TIMEOUT`, and `PROBE_CLOSE_FAILED` when emitted by the owned
client boundary.

The operation performs no subsequent memory/register read after such an attachment failure.
Cancellation remains cancellation. An unstructured exception retains the existing safe
`DEBUG_INTERNAL_ERROR` boundary and does not expose raw exception text.

### Scenario 4 - modification and recovery behavior remain unchanged

Ordinary modification workflows continue to use their accepted normal 1 MHz profile. Explicit
guarded recovery flash continues to use exactly 100 kHz under reset. Neither path is silently
converted to the observation profile. Existing programming authorization, identity-before-write,
readback, result publication, and cleanup behavior remain byte-for-behavior compatible outside
the worker configuration value intentionally selected for `OBSERVE`.

## 3. Selected architecture

### 3.1 One internal observation profile

`ProbeWorkerConfig` gains one pure derivation method:

```python
def for_observation(self) -> "ProbeWorkerConfig": ...
```

It returns a new closed worker configuration with:

- `frequency_hz=100_000`;
- the caller's exact target profile;
- the caller's existing `transport_provider`;
- `connection_policy="normal"`.

It does not mutate the source configuration and cannot preserve or select
`under-reset-recovery`. The existing `for_under_reset_recovery()` remains unchanged.

`hardware_workflows._make_supervisor()` selects `seams.worker_config.for_observation()` only when
the requested operation level is exactly `OperationLevel.OBSERVE`. `MODIFY` and `CONTROL` retain
the provided base configuration. A test backend factory remains a test seam and is not replaced or
wrapped by a production worker configuration.

Monitor observation is always `OperationLevel.OBSERVE`, so it passes
`_seams.worker_config.for_observation()` to its existing supervisor. This selection occurs before
the worker is created; it does not add another worker, backend, service, process, or attach attempt.

The accepted PyOCD session policy remains normal halt-connect with Pack Debug Sequences enabled,
`auto_unlock=false`, `resume_on_disconnect=false`, exact target override, `no_config=true`, primary
core zero, and null user script. This correction changes only the internally selected frequency
for observation construction.

### 3.2 One truthful attachment error boundary

`bind_debug_firmware()` separates these operations instead of placing them under one broad catch:

1. await the client's attach call;
2. classify an exception from the client boundary;
3. validate the returned attachment evidence.

The same classification is used for both the initial attachment and final trust revalidation:

- `asyncio.CancelledError`: re-raise unchanged;
- `ProbeClientError(code="PROBE_IDENTITY_MISMATCH", ...)`: return
  `DEBUG_TARGET_MISMATCH` with the existing sanitized debug message;
- any other `ProbeClientError`: return its exact code, message, and details through the existing
  debug-bind `OperationResult`;
- returned evidence that fails `_validate_attachment()`: return `DEBUG_TARGET_MISMATCH`;
- any other exception: return `DEBUG_INTERNAL_ERROR` through the existing outer boundary.

`debug.read._attach()` uses the same rule for every before/after memory-read attachment guard.
Its internal read failure carrier may be extended to retain JSON-safe details so the final
`OperationResult` can preserve the structured Probe failure without changing the public result
schema. A failed reattachment stops the read; it is not converted into an item-level successful or
partial result.

The two successful bind attachments and the debug read's before/after guards are existing
freshness and identity revalidations. They are not automatic retries. This correction neither
removes them nor adds another attach call.

## 4. Public contracts and lifecycle

No CLI flag, MCP field, project model, schema, protocol version, result model, error-code inventory,
probe selector, authorization, lease, runtime, or Agent adapter changes.

The lifecycle remains:

1. validate project, trusted flash evidence, SVD/DWARF provenance, and request facts at their
   accepted boundaries;
2. create one observation service with the internal 100 kHz normal profile;
3. attach and validate exact target identity;
4. verify current firmware bytes and evidence;
5. reattach for final bind trust confirmation;
6. publish a binding only after all checks pass;
7. for a requested read, run the existing before/after attachment and provenance guards around the
   bounded memory read;
8. close the one client/service/worker through the existing cleanup path.

An attach failure stops at its current lifecycle point. It cannot enter a later memory read,
register read, Monitor sampling, programming operation, reset, or fallback path.

## 5. Alternatives considered

### Change every normal worker to 100 kHz

Rejected. It would slow and alter ordinary modification/control behavior without evidence that
those paths need the compatibility setting. The proven need is observation construction.

### Add a project or CLI/MCP frequency setting

Rejected. It would expand the public schema and compatibility matrix and admit unverified
combinations when the smallest real supported scenario needs one closed internal profile.

### Make observation use 100 kHz under reset

Rejected. Under-reset actively changes target execution and boot state. It belongs only to the
explicit authorized recovery flash workflow and violates observation semantics.

### Try 1 MHz and automatically fall back to 100 kHz

Rejected. It adds an implicit second hardware attempt and can hide the first failure. Existing
observation policy forbids automatic retry and transport negotiation.

### Fix only the error mapping

Rejected as incomplete. It would restore diagnostic truth but retain a public observation profile
that has not passed the available physical compatibility proof. Error truthfulness and the
bounded observation profile are one connected public-bind correction.

## 6. Bounded implementation ownership

The sole GPT-5.6-luna/max implementer may change product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`.

The implementer may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_worker.py`;
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`;
- `tools/stm32-toolkit/tests/test_monitor_observation.py`;
- `tools/stm32-toolkit/tests/test_debug_firmware.py`;
- `tools/stm32-toolkit/tests/test_debug_read.py`.

Tests must be committed RED before product code and must directly prove:

- `for_observation()` produces exactly 100 kHz normal policy while preserving target profile and
  provider;
- the source config, ordinary modification config, and under-reset recovery config remain
  unchanged;
- every production `OperationLevel.OBSERVE` supervisor in `hardware_workflows` receives the
  observation config, while MODIFY/CONTROL do not;
- Monitor receives the same observation config;
- initial and final bind attach failures preserve each representative structured Probe error;
- only exact service identity mismatch and invalid returned attachment evidence map to
  `DEBUG_TARGET_MISMATCH`;
- every debug-read attachment guard has the same structured-error and mismatch behavior;
- cancellation remains cancellation, unknown exceptions remain `DEBUG_INTERNAL_ERROR`, and
  failed attachment performs no later memory/register read;
- the public request/result schemas, attach counts, one worker/backend topology, no-reset,
  no-retry, and no-programming assertions remain unchanged.

If TDD proves that a product or test path outside these exact lists must change, implementation
stops and reports the contract conflict. The implementer must not weaken or delete existing tests
to satisfy the slice.

## 7. Proportionate verification and evidence ownership

### Slice verification - Luna/max implementation owner

Use CPython 3.12, source/test `PYTHONPATH`, `-p no:cacheprovider`, and a fresh external run-owned
basetemp. Run only the five named affected test files. Expand to a downstream file only when a
changed contract or focused failure provides a written risk trigger. Run `git diff --check`, inspect
the exact changed-path list, preserve minimum failure evidence, and clean only the exact run-owned
temporary output.

The implementer does not run hardware, a full suite, coverage, packaging, installation, release,
UI, another Python version, or unrelated migration checks. It commits the implementation report
separately from code/tests and does not accept its own diff.

### Independent review - Sol primary

Create a fresh detached clean worktree at the returned report head. Review the complete
`52392e4910aea3a152b0d2dd4d3c4b7d61f8a410..CODE_HEAD` product/test diff and the report-only commit
separately. Re-run the same focused matrix with a new Sol-owned external basetemp. Acceptance
requires exact observation configuration, truthful error propagation, mismatch-only mapping,
unchanged attach counts, no reset/retry/programming, unchanged public contracts, accurate report
lineage, and clean status.

### Physical confirmation - Sol plus user/hardware owner after software acceptance

Hardware is not run by the implementer or reviewer as part of software acceptance. After the
software diff is accepted, one read-only public bind and `GPIOE.ODR` register read may be run only
after a new explicit hardware authorization. It must use the exact accepted code/runtime/project,
opaque selected probe, STM32F429ZGTx, 100 kHz SWD, and normal halt-connect. Required evidence is:

- one worker/backend and one public operation attempt;
- no reset, erase, unlock, program, fallback, or automatic retry;
- exact selected and resolved target identity;
- truthful stable failure if attach does not succeed;
- successful bind and exact bounded register read if it does succeed;
- target returned to running, released lease, stopped worker/service, no residual hardware process,
  and an exact evidence hash.

No flash is required for this confirmation because the current trusted public flash result already
exists. A failed physical confirmation stops without retry.

## 8. Explicit non-goals

- No special case for `ATK 20210914`, ATK, a USB serial, STM32F429, or one board model.
- No VS Code, Cortex-Debug, Keil, OpenOCD, or project-local PyOCD runtime dependency.
- No second runtime, Probe Service, worker type, backend, provider, controller, or MCP registration.
- No public frequency/configuration option and no project/schema/protocol migration.
- No under-reset observation, automatic retry, frequency probing, transport negotiation, probe
  fallback, target fallback, reset, unlock, erase, programming, or arbitrary memory write.
- No change to normal flash, explicit under-reset recovery, trusted flash-result schema, SVD/DWARF
  selection, register authorization, or Monitor data schema.
- No new Python, OS, probe-family, target-family, or board support claim.
- No full suite, coverage, package/install, release, CI, or collaboration automation.
- No hardware action before software acceptance and a new explicit one-attempt authorization.
- No push, PR mutation, merge, tag, release, close, or remote branch deletion.

## 9. Acceptance and stop boundary

This correction is accepted only when all four scenarios have direct tests, the focused CPython
3.12 matrix passes, the complete accepted-base-to-code-head diff has no unresolved product,
safety, compatibility, test, or scope defect, the implementation report accurately records the
accepted base and RED/GREEN lineage, disposable run-owned artifacts are cleaned or classified, and
the implementation and review worktrees are clean with remote state stated.

Software acceptance does not prove physical public bind/read success and does not authorize a
hardware attempt or remote publication. After software acceptance, stop and request the one
read-only physical confirmation authorization. Do not enter another VS10 slice, VS10-B, release,
or any remote action automatically.
