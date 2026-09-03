# STM32TK-1001 Public Flash Under-Reset Recovery Design

Date: 2026-09-03
Module / phase: STM32TK-1001 / VS10-A H2 hardware closure
Status: FROZEN FOR USER REVIEW
Full accepted base: `f7865ed6e927403b51664705506237f4f69aa21d`
Accepted-base tree: `91bbcfa5314df8e5b7f0b510a7155187428a69b9`
Accepted product code head below the report commit: `f801f41905f8601c30cbe82d6cf07753f704a357`
Accepted product tree: `cf01bca001d0a7566e83374507d6af57ba064d23`
Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
Remote branch baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`
Specification owner and final reviewer: GPT-5.6-sol primary
Implementation owner after separate specification and plan approval: exactly one GPT-5.6-luna
agent at reasoning effort `max`
Remote action: none authorized

## 1. Trigger, evidence, and exact defect boundary

The accepted public flash path was invoked once against the current STM32F429ZGTx campaign
project with explicit authorization, exact build and ELF pins, and the accepted public probe
selector. Identity and build gates passed, programming began, PyOCD emitted programming progress,
and the operation ended with `PROBE_PROGRAM_FAILED`. Toolkit correctly did not publish
`artifacts/migration/flash-result.json`, but the operation had already entered an irreversible
erase/program phase.

A later authorized 100 kHz SWD connect-under-reset diagnostic proved that the selected target was
the expected STM32F429ZGTx and that the first 256 bytes at `0x08000000` were all `0xff`, including
invalid `0xffffffff` initial MSP and reset-vector values. This explains the repeatable LOCKUP after
power cycles. A separately authorized direct recovery using the already-pinned PyOCD 0.45.1
engine, the same exact ELF, 100 kHz SWD, `connect_mode="under-reset"`, `auto_unlock=false`, sector
erase, `trustCrc=false`, and `keepUnwritten=true` completed and exact readback of both non-empty ELF
load segments matched. After a power cycle, the user observed D4 blinking again.

The retained external evidence is:

- failed public flash:
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-guarded-flash-failed-20260903-01.json`,
  SHA-256 `240d21c220864d0cb2ea2a62b293d0b450d335669c5bdfcee04f5ddbfdc664fb`;
- blank-vector diagnostic:
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-under-reset-diagnostic-20260903-01.json`,
  SHA-256 `14fce7c105669bf8cb5a6197409d298eb3160cb52ab8650ae97fe945ed4a8724`;
- successful direct recovery and exact readback:
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-under-reset-guarded-flash-20260903-01.json`,
  SHA-256 `79b85a09bc581a1b5ea680a9b5bf251da581d41df9abfabe37bf79eb49411396`;
- public read stopped before hardware by the missing trusted flash result:
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-read-1mhz-20260903-01.json`,
  SHA-256 `613a9de53e55943b418a29de384e2036c1ef95c2cf6b3f2d7b218241b7e6d5d3`.

The product defect is a missing Toolkit-owned recovery transition: an out-of-band recovery can
restore the board but cannot create trusted Toolkit flash evidence, while the public flash command
has no explicit way to select the already-proven under-reset/100 kHz recovery connection policy.
Consequently the public read/debug/Monitor path correctly remains closed with
`DEBUG_FLASH_REQUIRED` even after the physical board has been recovered.

The exact low-level cause of the original PyOCD programming failure remains unresolved. Existing
evidence does not isolate 1 MHz from connection mode as the necessary discriminator. This design
therefore does not claim that either setting alone caused the failure and does not change the
normal default policy.

Failure classification: `PRODUCT` for the missing public recovery transition. The earlier
programming exception itself remains `UNRESOLVED_AT_PYOCD_PROGRAM_BOUNDARY`.

## 2. Runnable user scenarios

### Scenario 1 - ordinary public flash remains byte-for-behavior compatible

A caller that invokes the existing CLI or MCP flash operation without recovery selection receives
the current 1 MHz, normal halt-connect policy and all existing authorization, identity, sector
programming, readback, publication, error, and cleanup behavior. No new retry, reset, fallback, or
success evidence is introduced into the default path.

### Scenario 2 - explicit recovery flash uses one proven bounded profile

For a board that cannot boot normally after an interrupted or failed programming attempt, the
caller explicitly selects under-reset recovery in addition to the existing exact flash
authorization and build/ELF/probe pins. Toolkit starts its existing single Probe Service and
single PyOCD worker with exactly this recovery profile:

- SWD at exactly `100000` Hz;
- PyOCD `connect_mode="under-reset"`;
- `auto_unlock=false`;
- `resume_on_disconnect=false`;
- the existing explicit target override, Pack Debug Sequences, `no_config=true`, primary core,
  null user script, and selector gate;
- the existing sector-only programming options `trustCrc=false` and `keepUnwritten=true`.

The target remains halted throughout identity validation, programming, and readback. Recovery is
one explicitly selected attempt, not a retry. Toolkit never first runs a normal programming
attempt and then falls back automatically.

### Scenario 3 - recovery identity mismatch performs zero programming

Before `flash.program`, Toolkit must still prove the exact selected probe, requested target,
resolved part number, single core, current build ID, current ELF hash, and model-selected target.
Malformed, unavailable, ambiguous, or mismatched target identity returns the existing stable
error, closes/restores according to the accepted connection policy, performs zero erase/program
calls, and publishes no `flash-result.json`.

### Scenario 4 - verified recovery creates ordinary trusted flash evidence

After a matching recovery attachment, Toolkit programs the exact identity-bound ELF once, reads
back every expected load-segment byte through the existing bounded read protocol, revalidates the
current disk/build evidence, and only then atomically publishes the existing schema-version-1
`flash-result.json`. The document is the same trusted public flash result consumed by debug bind,
register reads, Fault, handoff, and Monitor. Consumers do not receive a bypass, import the direct
recovery evidence, or learn a second trust format.

If programming, readback, revalidation, cleanup, timeout, or cancellation fails, no success result
is published. Toolkit does not retry automatically. A later public read continues to fail with the
existing flash-evidence error until a Toolkit-owned flash succeeds.

## 3. Selected architecture

### 3.1 One optional public recovery selector

The CLI adds one flash-only flag:

```text
stm32-toolkit flash ... --authorized --recovery-under-reset
```

The MCP `stm32_flash` tool adds one optional strict boolean:

```text
recoveryUnderReset: StrictBool = False
```

Omission or exact `false` means the accepted normal policy. Exact `true` selects the bounded
recovery profile. Strings, integers, null, duplicate CLI flags, and recovery selection without
the existing authorization fail before service creation or hardware access. The CLI and MCP remain
thin Agent-neutral adapters over the same `FlashWorkflowRequest` and `flash_workflow()` behavior.

The request model appends one defaulted field so existing positional and keyword callers retain
their current behavior:

```python
@dataclass(frozen=True)
class FlashWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    authorized: object
    recovery_under_reset: object = False
```

### 3.2 One worker and one backend with a closed connection policy

`ProbeWorkerConfig` and `PyOCDBackend` gain one internal closed connection-policy value with
exactly two admitted states:

- `normal`: existing frequency and `connect_mode="halt"` behavior;
- `under-reset-recovery`: exactly 100 kHz and `connect_mode="under-reset"`.

The recovery state is constructed only by `flash_workflow()` for an authorized recovery request.
Probe list, observation, debug binding, Monitor, handoff, target tests, and ordinary flash continue
to use `normal`. Invalid combinations fail during configuration before a child process or hardware
session is created. The worker process topology, IPC method allowlist, service endpoint, lease,
backend type, and PyOCD driver remain unchanged.

`PyOCDBackend.open_attach()` continues to receive the existing `halt_on_connect` argument. The
configured connection policy controls only the PyOCD session's connection mechanics; the existing
operation-level state contract still controls the required state at successful return. Recovery is
admitted only for the MODIFY flash workflow, so it must return halted after exact identity and
single-core validation.

### 3.3 Existing flash result remains the sole trust source

No field is added to `flash-result.json`. Its proof is exact target/build/ELF binding plus complete
load-segment readback, not the particular connection mechanics used to reach the target. Keeping
the document byte-schema compatible avoids changes to handoff, debug bind, Fault, read, and Monitor
consumers and prevents a second recovery-evidence authority.

The external physical evidence records the chosen command/profile for acceptance auditing. It is
not consumed as product state.

## 4. Alternatives considered

### Make all flash operations use under-reset at 100 kHz

Rejected. It would silently change every supported board's normal behavior, could break setups
without a connected reset line, and would treat one proven recovery profile as a universal default.

### Automatically retry under reset after a normal failure

Rejected. A failed normal program may already have erased or partially programmed flash. A hidden
second attempt would cross a new irreversible boundary without a new explicit choice and would
violate the existing no-automatic-retry safety rule.

### Expose arbitrary frequency and PyOCD connect-mode knobs

Rejected. It would create a general configuration surface with many unverified combinations,
weaken reproducibility, and expand compatibility scope beyond the single demonstrated recovery
scenario. The named profile admits only the exact settings already proven on the current hardware.

### Import the direct recovery evidence or manually create `flash-result.json`

Rejected. Out-of-band evidence did not run through the public Toolkit transaction and must not be
relabelled as a Toolkit flash PASS. Manually forging the trust commit point would defeat the
existing binder safety boundary.

## 5. Error, lifecycle, and safety contract

No new public error code is required.

- Invalid recovery input returns the existing hardware input/authorization failure before service
  creation or hardware access.
- Attach, identity, state, programming, verification, timeout, cancellation, and cleanup retain
  their accepted stable errors and sanitization.
- Recovery does not alter the precedence of `PROBE_CLOSE_FAILED` or cleanup failures.
- A recovery attach that does not prove the exact target and halted state cannot reach
  `flash.program`.
- The stale success result is removed only at the existing post-identity commit boundary.
- A failed recovery never publishes or preserves a success result for the current attempt.
- One invocation performs at most one attach and one programming call. There is no normal-first
  probe attempt, automatic retry, probe fallback, target fallback, unlock, mass erase, chip erase,
  arbitrary memory write, reset-after-program, or automatic run.
- Successful recovery closes the service and worker through the existing cleanup path. The target
  may remain halted until the user explicitly power-cycles it or a later accepted operation resumes
  it; the success result proves programmed bytes, not application execution.

## 6. Bounded implementation ownership

The sole GPT-5.6-luna/max implementer may change product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`.

The implementer may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_worker.py`;
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`;
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`;
- `tools/stm32-toolkit/tests/test_cli_hardware.py`;
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`;
- `tools/stm32-toolkit/tests/test_flash.py`;
- `tools/stm32-toolkit/tests/test_debug_firmware.py`.

`probe/flash.py`, `probe/service.py`, `probe/protocol.py`, `probe/client.py`, schemas, flash-result
consumers, package/runtime code, Skills, README, and Monitor product code are frozen. If TDD proves
that a frozen product file must change, the implementer stops and reports the exact contract
conflict instead of widening scope.

Tests must be committed RED before product code and must prove:

- default CLI, MCP, request, worker, backend options, and flash behavior are unchanged;
- explicit CLI and MCP recovery values select exactly one under-reset/100 kHz worker;
- invalid values and missing authorization produce no service, attach, erase, or program event;
- normal config cannot accidentally select under-reset and recovery config cannot use another
  frequency or operation;
- recovery session options retain every accepted security setting;
- matching identity allows one program call, existing full segment readback, and ordinary trusted
  flash-result publication;
- target mismatch, attach failure, program failure, readback mismatch, cancellation, and timeout
  produce zero or at most the already-entered single program call as appropriate, no retry, and no
  success result;
- a genuine recovery-produced flash result is accepted by the existing debug-binding consumer,
  while an absent/failed result still returns `DEBUG_FLASH_REQUIRED` before hardware access.

No test may manually forge a recovery-only success schema or weaken an existing default-path,
identity, no-write, readback, cleanup, or exact-field assertion.

## 7. Proportionate verification and evidence owners

### Slice verification - Luna/max implementation owner

Use CPython 3.12, source/test `PYTHONPATH`, `-p no:cacheprovider`, and a fresh external run-owned
basetemp. Run the affected worker/backend/workflow/CLI/MCP/flash/bind test files only. Expand to a
downstream file only when a changed contract or focused failure provides a concrete risk trigger.
Run `git diff --check`, inspect the exact changed-path list, preserve minimum failure evidence, and
clean only the exact run-owned temporary output.

### Independent review - Sol primary

Create a fresh detached clean worktree at the returned report head. Review the complete
`f7865ed6e927403b51664705506237f4f69aa21d..CODE_HEAD` product/test diff and the report-only commit
separately. Re-run the same focused matrix with a new Sol-owned external basetemp. Acceptance
requires exact default compatibility, strict public input, one worker/backend, correct PyOCD
options, identity-before-program ordering, one-attempt behavior, full readback before publication,
unchanged flash-result schema, accurate report lineage, and clean status.

### Physical acceptance - Sol plus user/hardware owner after software acceptance

Hardware is not run by the implementer. After software acceptance, a real recovery flash requires
a separate explicit authorization for that one irreversible attempt. The physical run must use the
exact accepted Toolkit public CLI or MCP entry point and record:

- report/code head and runtime versions;
- exact public recovery selection, 100 kHz SWD, and under-reset connection;
- selected probe and resolved STM32F429ZGTx identity;
- one programming attempt only;
- exact ELF and complete segment readback;
- a Toolkit-owned `flash-result.json` accepted by one subsequent public read/bind;
- cleanup, remaining process/lease state, and the user's separately reported D4 observation after
  an explicit power cycle or run action.

The direct recovery evidence remains historical physical evidence and is never relabelled as the
public Toolkit acceptance run.

## 8. Explicit non-goals

- No second runtime, Probe Service, worker type, backend, provider, controller, or MCP registration.
- No Agent-specific product path or VS Code/Keil runtime dependency.
- No automatic retry, transport negotiation, frequency probing, probe fallback, or target fallback.
- No arbitrary public PyOCD options, project-local PyOCD config, or user script.
- No unlock, mass erase, chip erase, Option Bytes, arbitrary memory write, or reset/run automation.
- No flash-result schema/version change and no alternate trusted recovery evidence.
- No change to public read/debug/Monitor evidence gates.
- No new Python, OS, probe-family, target-family, or board support claim.
- No full suite, coverage, package/install, UI, release, CI, or collaboration-automation work.
- No hardware execution before software acceptance and separate one-attempt authorization.
- No push, PR mutation, merge, tag, release, close, or remote branch deletion.

## 9. Acceptance and stop boundary

This correction is accepted only when all four scenarios are directly proven, the focused
CPython 3.12 matrix passes, the full accepted-base-to-code-head diff has no unresolved product,
safety, compatibility, or scope defect, the implementation report is accurate, run-owned
temporary artifacts are cleaned or explicitly classified, and the implementation and review
worktrees are clean with remote state stated.

Software acceptance authorizes neither a physical flash nor remote publication. After software
acceptance the next step is one separately authorized public recovery flash and one read-only
public bind/read confirmation. If that physical attempt fails, preserve the minimum evidence and
stop without retry. Do not enter VS10-B, release, or any remote operation automatically.
