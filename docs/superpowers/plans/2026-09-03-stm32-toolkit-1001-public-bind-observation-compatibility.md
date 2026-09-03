# STM32TK-1001 Public Bind Observation Compatibility Implementation Plan

> **For the implementation owner:** Use `subagent-driven-development` or `executing-plans`,
> `test-driven-development`, and `verification-before-completion`. Complete the checkbox steps in
> order. The sole implementation owner is GPT-5.6-luna at reasoning effort `max`; that owner must
> not review or accept its own diff.

**Goal:** Make public observation binding use the physically proven 100 kHz normal halt-connect
profile and preserve the real stable Probe failure whenever attach fails, without adding reset,
retry, fallback, public configuration, or another runtime/backend.

**Architecture:** Derive one closed observation-only `ProbeWorkerConfig` before the existing
single worker is created. Existing hardware OBSERVE workflows and Monitor use that derived config;
MODIFY, CONTROL, and explicit under-reset recovery keep their current profiles. Debug bind and
debug read separate client transport/service failures from validation of returned attachment
evidence: only exact identity mismatch maps to `DEBUG_TARGET_MISMATCH`, while all other structured
`ProbeClientError` values cross the existing `OperationResult` boundary unchanged.

**Tech stack:** CPython 3.12, pytest, asyncio, frozen dataclasses, existing Probe Service/client,
PyOCD 0.45.1, Git.

## Global constraints

- Full accepted base: `52392e4910aea3a152b0d2dd4d3c4b7d61f8a410`; tree
  `28b94cb6d9f61df09adf593caedaee4226dc742f`.
- Approved specification commit: `4d42c09b7d3b5cbcf100696328241590ecc7f8ba`;
  specification:
  `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-public-bind-observation-compatibility-design.md`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; remote baseline
  `74ee5f4c7872af1bb612c9068af36319457e087b`; no remote action is authorized.
- Exactly one GPT-5.6-luna/max implementation owner makes all product/test/report changes. Sol owns
  the complete accepted-base review and final verdict.
- Commit all failing tests before changing product code. Do not remove or weaken an existing
  assertion to make the new behavior pass.
- OBSERVE is exactly 100 kHz with the existing normal halt-connect policy. It may transiently halt,
  must resume and prove running before successful attachment publication, and must not reset.
- Ordinary MODIFY remains its existing normal 1 MHz profile. Explicit recovery remains exactly
  100 kHz under reset. CONTROL retains the provided base config.
- No automatic retry, 1 MHz-to-100 kHz fallback, transport negotiation, probe/target fallback,
  reset, unlock, erase, programming, or arbitrary memory write is added.
- Product files are limited to `probe/worker.py`, `hardware_workflows.py`,
  `monitor_observation.py`, `debug/firmware.py`, and `debug/read.py`.
- Test files are limited to `test_probe_worker.py`, `test_hardware_workflows.py`,
  `test_monitor_observation.py`, `test_debug_firmware.py`, and `test_debug_read.py`.
- CLI, MCP, request/result models, project schemas, Probe protocol, PyOCD backend options other than
  the already-configurable frequency, selector behavior, trusted flash result, SVD/DWARF, runtime,
  package, Skills, and README are frozen.
- Implementation verification is software-only. Do not access hardware, run the full suite,
  coverage, packaging, installation, UI, another Python version, release checks, or remote actions.

## File ownership map

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`: sole source of the closed derived
  observation worker configuration.
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`: selects that config only for
  existing production `OperationLevel.OBSERVE` supervisors.
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`: selects the same config for its
  always-observe production supervisor.
- `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`: owns truthful initial/final debug-bind
  attachment classification.
- `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`: owns the same classification for every
  before/after debug-read guard.
- The five named test files own direct RED/GREEN proof.
- `docs/codex/returns/STM32TK-1001-PUBLIC-BIND-OBSERVATION-COMPATIBILITY/implementation-report.md`:
  report evidence only, added after the final code head.

## Frozen interfaces

`ProbeWorkerConfig` gains exactly one pure internal method:

```python
def for_observation(self) -> "ProbeWorkerConfig":
    return ProbeWorkerConfig(
        frequency_hz=100_000,
        target_profile=self.target_profile(),
        transport_provider=self.transport_provider,
        connection_policy=NORMAL_CONNECTION_POLICY,
    )
```

No constructor field or public schema is added. The existing normal and
`for_under_reset_recovery()` contracts remain unchanged.

Attachment classification is exact:

```text
CancelledError                              -> re-raise
ProbeClientError(PROBE_IDENTITY_MISMATCH)   -> DEBUG_TARGET_MISMATCH
other ProbeClientError                      -> exact code/message/details
returned attachment evidence mismatch       -> DEBUG_TARGET_MISMATCH
other exception                             -> DEBUG_INTERNAL_ERROR
```

No successful bind/read result is emitted after any failed attachment.

---

### Task 1: Commit observation-profile RED contracts

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_probe_worker.py`
- Modify: `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_monitor_observation.py`

**Produces:** Failing tests for the exact 100 kHz normal observation derivation and its two
production construction points, without changing product code.

- [ ] **Step 1: Add the exact worker derivation test**

Next to the existing under-reset derivation test, construct a base config with a non-empty target
profile and the accepted provider. Call `for_observation()` and assert:

```python
assert observation.frequency_hz == 100_000
assert observation.connection_policy == NORMAL_CONNECTION_POLICY
assert observation.target_profile() == base.target_profile()
assert observation.transport_provider == base.transport_provider
assert base == ProbeWorkerConfig(target_profile=profile)
assert base.frequency_hz == 1_000_000
assert base.for_under_reset_recovery().connection_policy == (
    UNDER_RESET_RECOVERY_CONNECTION_POLICY
)
```

Also construct a recovery config first and require `recovery.for_observation()` to return normal
100 kHz rather than preserving under-reset. This proves observation can never inherit recovery
mechanics.

- [ ] **Step 2: Add hardware-workflow production selection tests**

Use the existing capturing supervisor seam with `_test_backend_factory=None`. Call
`_make_supervisor()` separately for OBSERVE, MODIFY, and CONTROL with one non-default base config.
Assert:

- OBSERVE receives a `ProbeWorkerConfig` at exactly 100 kHz and normal policy;
- target profile and provider are preserved;
- MODIFY and CONTROL receive the original base config unchanged;
- each call constructs only one supervisor contract;
- the test-backend-factory branch still receives the existing factory rather than a worker config.

Update only existing assertions that currently expect `ProbeWorkerConfig()` for an OBSERVE
production supervisor; keep all service level, endpoint, attach-count, no-reset, and no-program
assertions.

- [ ] **Step 3: Add Monitor production selection tests**

Use `MonitorObservationSeams` with `_test_backend_factory=None` and a capturing supervisor factory.
Invoke the existing Monitor observation construction far enough to capture its backend contract.
Require exactly one `ProbeWorkerConfig` with 100 kHz, normal policy, and preserved profile/provider.

Keep a separate seam test proving `_test_backend_factory` is still passed through and is not
wrapped or replaced. Do not start a real service or access hardware.

- [ ] **Step 4: Run the three-file RED proof**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-public-bind-red-profile' `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py -q
```

Expected: only new/updated observation assertions fail because `for_observation()` does not exist
and production still receives the base 1 MHz config. Existing recovery and non-observation tests
remain green. If another existing contract fails independently, classify it and stop instead of
changing unrelated product behavior.

Inspect the exact basetemp, preserve the concise RED summary, and remove only that resolved
run-owned path after it is no longer needed.

- [ ] **Step 5: Commit profile RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py
git commit -m "test(vs10a): define public observation profile"
```

The commit contains no product or report path.

---

### Task 2: Commit truthful bind/read error RED contracts

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_debug_firmware.py`
- Modify: `tools/stm32-toolkit/tests/test_debug_read.py`

**Produces:** Failing tests that distinguish service/backend attachment failures from actual
attachment identity mismatch at every bind/read revalidation point.

- [ ] **Step 1: Add initial bind attachment error tests**

Using the existing valid project, flash result, endpoint, and binding client fixtures, parameterize
representative `ProbeClientError` values:

```python
(
    ("PROBE_ATTACH_FAILED", "Probe attach failed", {"stage": "open"}),
    ("PROBE_SERVICE_UNAVAILABLE", "Probe Service request failed", {}),
    ("PROBE_RESPONSE_INVALID", "Probe Service response is invalid", {}),
    ("PROBE_CLOSE_FAILED", "Probe cleanup failed", {"stage": "close"}),
)
```

Make the first `attach()` raise each error. Require the returned debug-bind result to preserve its
exact code, message, and details; require zero memory-read calls and no second attach.

Add separate cases proving:

- `ProbeClientError("PROBE_IDENTITY_MISMATCH", ...)` becomes `DEBUG_TARGET_MISMATCH`;
- returned wrong probe/target/resolved part/core evidence becomes `DEBUG_TARGET_MISMATCH`;
- a raw `RuntimeError` becomes `DEBUG_INTERNAL_ERROR` without raw text/details;
- `CancelledError` is re-raised.

- [ ] **Step 2: Add final bind attachment error tests**

Let the first attach and firmware segment readback succeed, then make the existing final attach
raise each representative structured Probe error. Require exact code/message/details, no binding
publication, and no third attach or later read. Retain the existing final returned-evidence
mismatch test and require `DEBUG_TARGET_MISMATCH`.

- [ ] **Step 3: Add every debug-read guard error test**

In `test_debug_read.py`, use a genuine valid binding and the existing recording client. Inject a
structured attach failure before the first memory read and after a successful memory read. For both
variable and register entry points where existing parameterization permits, require:

- the operation-level result preserves exact Probe code/message/details;
- no memory read occurs when the first guard fails;
- no success report is returned when the post-read guard fails;
- `PROBE_IDENTITY_MISMATCH` and invalid returned evidence become
  `DEBUG_TARGET_MISMATCH`;
- a raw exception becomes `DEBUG_INTERNAL_ERROR`;
- cancellation remains cancellation;
- existing successful-path attach counts remain unchanged.

Do not turn a guard-level attachment failure into an item-level partial success.

- [ ] **Step 4: Run the two-file RED proof**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-public-bind-red-errors' `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py -q
```

Expected: structured-error tests fail because current broad catches rewrite failures to
`DEBUG_TARGET_MISMATCH`; unknown-error tests expose any current divergence. Existing genuine
mismatch and successful bind/read tests remain green. If a new test cannot isolate the attachment
stage from an earlier accepted gate, stop and report the test-design conflict rather than weakening
the gate.

Inspect and clean only the exact resolved basetemp after retaining the RED summary.

- [ ] **Step 5: Commit error RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py
git commit -m "test(vs10a): distinguish public bind failures"
```

At this checkpoint both RED commits exist and no product file has changed.

---

### Task 3: Implement the observation-only worker profile

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`

**Produces:** Exact 100 kHz normal construction for existing observation workflows with no public
or backend contract change.

- [ ] **Step 1: Implement `ProbeWorkerConfig.for_observation()`**

Add the frozen method exactly as shown in the frozen interfaces. It must reconstruct from
`target_profile()` and preserve only the admitted provider while explicitly selecting
`NORMAL_CONNECTION_POLICY`. Do not add a third policy string or loosen constructor validation.

- [ ] **Step 2: Select the profile in hardware workflows**

In `_make_supervisor()`, retain the test factory precedence. For the production worker-contract
branch only, derive the observation config when `level is OperationLevel.OBSERVE`; otherwise pass
the original config. Do not alter `ProbeServiceConfig`, lifecycle ordering, `_one_shot()`, service
start/stop, client construction, or operation callbacks.

- [ ] **Step 3: Select the profile in Monitor**

At the existing production backend-contract selection point, pass
`_seams.worker_config.for_observation()`. Preserve the test factory path, root guard, supervisor
count, service/client/bind order, SVD preflight/revalidation, Monitor error mapping, and cleanup.

- [ ] **Step 4: Run and commit profile GREEN**

Run the same three files with fresh basetemp
`C:\tmp\stm32tk-1001-public-bind-green-profile`. Expected: all three pass. Inspect and clean that
exact run-owned path.

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py `
  tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py `
  tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py
git commit -m "fix(vs10a): use proven public observation profile"
```

Before committing, require that no test, debug, backend, public adapter, or report file is
uncommitted.

---

### Task 4: Implement truthful attachment error propagation

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`

**Produces:** Mismatch-only debug mapping and exact structured Probe failures at initial/final bind
and every read guard.

- [ ] **Step 1: Correct debug binding**

Import `ProbeClientError` from the existing client module. Separate each awaited attach call from
returned-evidence validation. Catch only cancellation and `ProbeClientError` locally:

- re-raise cancellation;
- convert exact `PROBE_IDENTITY_MISMATCH` to the existing sanitized
  `DEBUG_TARGET_MISMATCH` failure;
- convert every other `ProbeClientError` to `_BindingFailure` with its exact code, message, and
  details.

Run `_validate_attachment()` outside the attach exception catch and keep its existing
`DEBUG_TARGET_MISMATCH` behavior. Let raw exceptions reach the existing safe
`DEBUG_INTERNAL_ERROR` outer boundary. Apply this to both existing attach sites without adding or
removing an attach/read.

- [ ] **Step 2: Correct debug-read guards**

Import `ProbeClientError`. Extend `_ReadFailure` and `_fail()` with optional mapping/details while
preserving existing callers. In `_attach()` apply the same exact classification as binding and
validate returned evidence separately. In `_execute()` and request validation paths, return the
stored details rather than replacing them with `{}`.

Do not catch structured guard failures in `_one()` or `_group()` as item errors. They must continue
to reach `_execute()` and fail the whole public read operation.

- [ ] **Step 3: Run the two-file GREEN and complete five-file matrix**

First run the same two debug files with fresh basetemp
`C:\tmp\stm32tk-1001-public-bind-green-errors`. Then run all five affected files with another fresh
basetemp:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-public-bind-green-complete' `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py -q
```

Expected: all five files pass. A failure in an unchanged adjacent contract is a risk trigger only
for diagnosis; it does not authorize editing outside the allowlist or adding a broad suite.
Inspect and clean both exact basetemps after preserving concise results.

- [ ] **Step 4: Audit and commit the final code head**

```powershell
git diff --check
git diff --name-only
git status --short
git diff --name-status 52392e4910aea3a152b0d2dd4d3c4b7d61f8a410..HEAD
```

Require that every changed product/test path is on the exact allowlist; CLI, MCP, backend,
service, protocol, schemas, runtime, package, trusted evidence, and unrelated reports remain
unchanged.

```powershell
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py `
  tools/stm32-toolkit/src/stm32_toolkit/debug/read.py
git commit -m "fix(vs10a): preserve public bind probe errors"
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Record the exact code head and tree before adding a report.

---

### Task 5: Re-run code-head evidence and commit the report separately

**File:**

- Create:
  `docs/codex/returns/STM32TK-1001-PUBLIC-BIND-OBSERVATION-COMPATIBILITY/implementation-report.md`

**Produces:** One report-only commit for independent Sol review.

- [ ] **Step 1: Require a clean exact code head**

```powershell
git status --short --branch
git diff --check
git diff --name-status 52392e4910aea3a152b0d2dd4d3c4b7d61f8a410..HEAD
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Classify every unexpected tracked/untracked item and stop instead of hiding, deleting, or folding it
into the report.

- [ ] **Step 2: Re-run the exact five-file matrix at code head**

Use the complete five-file command from Task 4 with a new external basetemp:
`C:\tmp\stm32tk-1001-public-bind-final`. Record interpreter and PyOCD versions, start/end time,
exact code head/tree, command, exit code, pass/skip totals, and duration. Inspect and delete only
the resolved final basetemp; classify an access-denied residual as ENVIRONMENT cleanup residue.

- [ ] **Step 3: Write the implementation report**

The report must record:

- status `RETURNED FOR INDEPENDENT SOL REVIEW`;
- accepted base/tree and approved spec/plan commits;
- active branch, remote baseline, ahead/behind state, and no remote action;
- sole Luna/max implementer and Sol reviewer ownership;
- both RED commits and their observed failures;
- both GREEN commits, exact final code head/tree, and report boundary;
- exact changed product/test paths and unchanged frozen contracts;
- exact CPython 3.12 five-file evidence and cleanup state;
- no hardware execution and no claim that physical public bind/read now passes;
- remaining gate: independent complete-diff review, then a separately authorized single read-only
  physical confirmation.

The report must not contain its own future SHA or make an `ACCEPTED` claim.

- [ ] **Step 4: Commit only the report and return**

```powershell
git diff --check
git diff --name-only
git add -- docs/codex/returns/STM32TK-1001-PUBLIC-BIND-OBSERVATION-COMPATIBILITY/implementation-report.md
git commit -m "docs(vs10a): report public bind observation correction"
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Return the report head/tree, code head/tree, exact RED/GREEN lineage, verification totals, cleanup,
changed paths, and remote state. Do not review, push, or access hardware.

---

## Sol independent review checkpoint

The GPT-5.6-sol primary creates a fresh detached clean worktree at the returned report head and
reviews the complete
`52392e4910aea3a152b0d2dd4d3c4b7d61f8a410..CODE_HEAD` product/test diff plus the separate report
delta. The reviewer repeats only the five-file focused matrix unless a changed contract supplies a
written expansion trigger. Review must inspect:

- exact 100 kHz normal observation derivation and source-config immutability;
- MODIFY/CONTROL/recovery compatibility and unchanged PyOCD session policy;
- production OBSERVE and Monitor selection with one service/worker/backend;
- initial/final bind and every read-guard structured failure;
- mismatch-only `DEBUG_TARGET_MISMATCH` mapping;
- exact code/message/details preservation, cancellation, and safe unknown-error handling;
- unchanged attach counts, no read after failed guard, and no reset/retry/programming;
- unchanged public schemas/adapters and exact scope;
- accurate RED/GREEN/report lineage and clean run-owned cleanup.

Only Sol issues `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Software acceptance does
not authorize hardware or remote publication. After `ACCEPTED`, stop and request one explicit
authorization for a single read-only public bind plus `GPIOE.ODR` read. If authorized, run exactly
one attempt and stop on failure without retry. Do not enter another slice, VS10-B, release, or any
remote action automatically.
