# STM32TK-1001 Public Flash Under-Reset Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. The single implementation owner must also use
> superpowers:test-driven-development before changing product code and
> superpowers:verification-before-completion before returning the candidate.

**Goal:** Add one explicit Agent-neutral public flash recovery selection that uses the existing
single PyOCD worker/backend at 100 kHz SWD with connect-under-reset, while preserving ordinary
1 MHz flash behavior and publishing the existing trusted flash result only after exact readback.

**Architecture:** Append one defaulted recovery boolean to the existing flash workflow request and
surface it as one CLI flag and one strict MCP boolean. The workflow converts exact `true` into a
closed internal `ProbeWorkerConfig` connection policy; that same worker constructs the same
`PyOCDBackend`, whose session options select `under-reset` only for the recovery policy. The
existing flash transaction, target gate, program call, readback, atomic result, service, IPC, and
consumers remain unchanged.

**Tech Stack:** CPython 3.12, pytest, dataclasses, argparse, FastMCP/Pydantic strict inputs, the
existing Probe Service/worker IPC, PyOCD 0.45.1, Git.

## Global Constraints

- Full accepted base: `f7865ed6e927403b51664705506237f4f69aa21d`; tree:
  `91bbcfa5314df8e5b7f0b510a7155187428a69b9`.
- Approved specification commit: `8a41d5ae542dfc81ffa35616809bb7418ef901a0`; specification:
  `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-public-flash-under-reset-recovery-design.md`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; remote baseline:
  `74ee5f4c7872af1bb612c9068af36319457e087b`; no remote action is authorized.
- One GPT-5.6-luna implementation owner at reasoning effort `max`; GPT-5.6-sol owns complete-diff
  review and acceptance. The implementer must not accept its own work.
- Failing tests are committed before any product-code change. Existing assertions may be
  strengthened but never removed or weakened to make the recovery path pass.
- Ordinary flash remains exactly 1 MHz with `connect_mode="halt"`. Recovery is selected only by
  exact public `true` and is exactly 100 kHz with `connect_mode="under-reset"`.
- Recovery retains `auto_unlock=false`, `resume_on_disconnect=false`, Pack Debug Sequences,
  `no_config=true`, primary core 0, explicit target override, null user script, sector erase,
  `trustCrc=false`, and `keepUnwritten=true`.
- One invocation performs at most one attach and one program call. No automatic retry, normal-first
  fallback, probe/target fallback, unlock, mass erase, chip erase, Option Bytes, reset-after-write,
  or automatic run is allowed.
- `flash-result.json`, Probe Service protocol, worker IPC methods, client, lease, flash transaction,
  binder, Fault, handoff, Monitor, runtime, packaging, Skills, and README schemas remain unchanged.
- Product changes are limited to `probe/worker.py`, `probe/pyocd_backend.py`,
  `hardware_workflows.py`, `cli.py`, and `mcp_server.py`.
- Test changes are limited to `test_probe_worker.py`, `test_pyocd_backend.py`,
  `test_hardware_workflows.py`, `test_cli_hardware.py`, `test_mcp_hardware.py`, `test_flash.py`, and
  `test_debug_firmware.py`.
- No hardware, full suite, coverage, package/install, UI, release, CI, collaboration automation,
  push, PR mutation, merge, tag, close, or remote branch deletion is part of implementation.

---

## File ownership map

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`: sole serialized source of truth for the
  two closed worker connection policies and the exact recovery-frequency invariant.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`: sole adapter that maps the closed
  policy to PyOCD session options.
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`: validates the public recovery value
  and selects a derived worker configuration for flash only.
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`: thin `--recovery-under-reset` adapter.
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`: thin strict
  `recoveryUnderReset` adapter.
- The seven named test files own direct RED/GREEN proof. No test creates a new product trust format.
- `docs/codex/returns/STM32TK-1001-PUBLIC-FLASH-UNDER-RESET-RECOVERY/implementation-report.md`:
  implementation evidence only, added after the final code head.

## Frozen interfaces

The existing request gains one trailing default only:

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

The worker configuration gains constants `NORMAL_CONNECTION_POLICY = "normal"` and
`UNDER_RESET_RECOVERY_CONNECTION_POLICY = "under-reset-recovery"`, a frozen string field named
`connection_policy`, a trailing keyword constructor parameter
`connection_policy: str = NORMAL_CONNECTION_POLICY`, and an exact method
`for_under_reset_recovery(self) -> ProbeWorkerConfig`.

The backend appends the trailing keyword constructor parameter
`connection_policy: str = NORMAL_CONNECTION_POLICY` after `target_transport_factory`; its existing
`open_attach(probe_id, target, *, halt_on_connect=False)` signature remains unchanged.

Public adapters append only these optional values:

```text
CLI: --recovery-under-reset
MCP: recoveryUnderReset: StrictBool = False
```

---

### Task 1: Commit internal worker/backend RED contracts

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_probe_worker.py`
- Modify: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

**Interfaces:**

- Consumes: current `ProbeWorkerConfig`, `PyOCDBackend`, `FakePyOCDDriver`, and the accepted exact
  normal session-options assertion.
- Produces: failing tests for the closed policy set, exact recovery frequency, worker-to-backend
  propagation, and exact under-reset session options without changing normal behavior.

- [ ] **Step 1: Add the closed worker-config RED tests**

Import the worker module inside the tests as the existing file already does. Add this exact
behavioral test next to `test_production_worker_uses_only_closed_serializable_pyocd_and_task8_config`:

```python
def test_worker_config_derives_only_the_fixed_under_reset_recovery_profile() -> None:
    from stm32_toolkit.probe import worker as module

    normal = module.ProbeWorkerConfig(
        target_profile={"backend": "pyocd", "mcu": "stm32f429zgtx"}
    )
    recovery = normal.for_under_reset_recovery()

    assert normal.frequency_hz == 1_000_000
    assert normal.connection_policy == module.NORMAL_CONNECTION_POLICY
    assert recovery.frequency_hz == 100_000
    assert recovery.connection_policy == module.UNDER_RESET_RECOVERY_CONNECTION_POLICY
    assert recovery.target_profile() == normal.target_profile()
    assert recovery.transport_provider == normal.transport_provider
```

Extend `test_worker_config_and_direct_production_child_fail_closed` with these rejected inputs:

```python
{"connection_policy": "under-reset"},
{"connection_policy": "UNDER-RESET-RECOVERY"},
{"connection_policy": True},
{"frequency_hz": 1_000_000, "connection_policy": "under-reset-recovery"},
```

Also corrupt a constructed configuration's `connection_policy` and require `_worker_main()` to
return its existing sanitized backend failure rather than constructing a PyOCD session.

- [ ] **Step 2: Add exact backend session-option RED tests**

Keep `test_observation_attach_uses_pinned_halt_policy_then_returns_running` byte-for-behavior
unchanged. Add a separate MODIFY recovery test:

```python
def test_modify_recovery_attach_uses_only_under_reset_at_100khz_and_stays_halted() -> None:
    target = ConnectionPolicyTarget(state="halted")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(
        driver,
        frequency_hz=100_000,
        connection_policy="under-reset-recovery",
    )

    evidence = backend.open_attach(
        "probe-a", "stm32f429zgtx", halt_on_connect=True
    )

    assert evidence.resolved_part_number == "stm32f429zgtx"
    assert driver.created_sessions[0].options == {
        "auto_unlock": False,
        "connect_mode": "under-reset",
        "dap_protocol": "swd",
        "frequency": 100_000,
        "no_config": True,
        "pack.debug_sequences.enable": True,
        "primary_core": 0,
        "project_dir": os.getcwd(),
        "resume_on_disconnect": False,
        "target_override": "stm32f429zgtx",
        "user_script": os.devnull,
    }
    assert target.calls == [("get_state",)]
    assert target.state == "halted"
    assert driver.program_calls == []
```

Extend the invalid-backend-constructor test so unknown policies, non-string policies, and recovery
at any frequency other than exactly `100_000` raise `ValueError` before probe enumeration or
session creation.

- [ ] **Step 3: Run the two-file RED proof**

Run from the implementation worktree:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-flash-recovery-red-internal' `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py -q
```

Expected: new tests fail because the policy constants, field, derivation method, and backend
constructor argument do not yet exist. Existing tests must remain green. Preserve the concise RED
failure summary, then remove only the exact basetemp after confirming it contains no needed
additional evidence.

- [ ] **Step 4: Commit internal RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- tools/stm32-toolkit/tests/test_probe_worker.py tools/stm32-toolkit/tests/test_pyocd_backend.py
git commit -m "test(vs10a): define under-reset recovery profile"
```

The commit must contain no product or report path.

---

### Task 2: Commit public workflow/CLI/MCP and trust-transition RED contracts

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_cli_hardware.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_hardware.py`
- Modify: `tools/stm32-toolkit/tests/test_flash.py`
- Modify: `tools/stm32-toolkit/tests/test_debug_firmware.py`

**Interfaces:**

- Consumes: the frozen trailing `FlashWorkflowRequest.recovery_under_reset`, CLI flag, MCP strict
  boolean, worker derivation method, unchanged `flash_firmware()`, and unchanged
  `bind_debug_firmware()`.
- Produces: failing tests that prove exact public forwarding, pre-service rejection, no default
  drift, no retry, unchanged flash-result schema, and a real producer-to-consumer trust transition.

- [ ] **Step 1: Add workflow selection and pre-service validation RED tests**

In `test_hardware_workflows.py`, add a helper that starts from `_seams(recorder)`, clears the
test-backend factory, and records the worker contract passed to the existing fake supervisor:

```python
def _capturing_worker_seams(
    recorder: _Recorder, captured: list[object]
) -> HardwareWorkflowSeams:
    base = _seams(recorder)
    return replace(
        base,
        _test_backend_factory=None,
        supervisor_factory=lambda config, manager, contract: (
            captured.append(contract) or _Supervisor(config, recorder)
        ),
    )
```

Add one test that invokes ordinary flash and recovery flash in separate fresh project/data/session
roots. Assert the captured ordinary config is exactly `ProbeWorkerConfig()` and the recovery config
has only `frequency_hz == 100_000` and
`connection_policy == UNDER_RESET_RECOVERY_CONNECTION_POLICY`; both operations remain MODIFY and
call the same flash callback once.

Add a parameterized test for recovery values `"true"`, `1`, `None`, `[]`, and `{}` with
`authorized=True`. Require `HARDWARE_INPUT_INVALID` and no supervisor/service event. Add a separate
`authorized=False, recovery_under_reset=True` case requiring `AUTHORIZATION_REQUIRED` and no
service event.

- [ ] **Step 2: Add CLI forwarding and grammar RED tests**

Extend the existing flash row in `test_cli_requests_are_constructed_from_explicit_roots` (the
parameterized request-construction table) to assert `recovery_under_reset is False` by default.
Add a dedicated invocation with `--authorized --recovery-under-reset` and assert the received
`FlashWorkflowRequest` has exact boolean `True`.

Add these grammar failures and assert the workflow is never called and stderr does not echo the
project path:

```python
["--recovery-under-reset=true"],
["--recovery-under-reset", "--recovery-under-reset"],
```

- [ ] **Step 3: Add MCP wrapper and registered-schema RED tests**

Extend the wrapper table so the normal `tool_flash_for_request` request has
`recovery_under_reset is False`. Add a direct wrapper call with `recovery_under_reset=True` and
assert exact forwarding.

Extend the registered `stm32_flash` tool test with `recoveryUnderReset=True`. Add a parameterized
registered-tool rejection for `"true"`, `"false"`, `1`, and `0`; require the strict validation
exception and zero workflow calls. A missing field must remain accepted as exact false.

- [ ] **Step 4: Prove unchanged flash transaction and producer-to-binder trust**

Do not change `probe/flash.py` or `debug/firmware.py`. In `test_flash.py`, preserve the existing
`test_flash_programs_exact_elf_reads_back_segments_and_commits_result` assertions, and add an exact
field-set assertion using the existing handoff `_FLASH_FIELDS` authority so recovery work cannot
silently add a second schema field.

In `test_debug_firmware.py`, add an integration test that:

1. creates a project with `prepare_project()` and `_publish_current_debug_build()`;
2. calls the real `flash_firmware()` with the existing `RecordingFlashClient` and exact request;
3. does not edit or replace the produced `flash-result.json`;
4. calls the real `bind_debug_firmware()` using `BindingClient` and matching
   `DebugBindingRequest`;
5. asserts flash succeeded, bind succeeded, attach/read occurred only after the produced flash
   result existed, and the produced result's key set is unchanged;
6. deletes the result and repeats bind only far enough to prove `DEBUG_FLASH_REQUIRED` occurs before
   the binding client records attach/read events.

Import the existing flash-test helpers rather than duplicating an ELF builder or manually creating
a success document.

- [ ] **Step 5: Run the five-file public RED proof**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-flash-recovery-red-public' `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py -q
```

Expected: recovery field/flag/MCP/profile-selection tests fail for missing behavior. Existing flash
and bind tests remain green. If the producer-to-binder test fails because an existing independent
consumer contract rejects an unchanged genuine flash result, stop and report the contract conflict;
do not edit a frozen consumer or weaken its exact-field validation.

- [ ] **Step 6: Commit all remaining RED tests before product code**

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py
git commit -m "test(vs10a): define public flash recovery transition"
```

The cumulative RED commits must still contain no product or report path.

---

### Task 3: Implement the minimum GREEN recovery path

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`

**Interfaces:**

- Consumes: both committed RED waves and every frozen interface above.
- Produces: exact normal/recovery configuration, one worker/backend path, and common CLI/MCP
  behavior without changing the flash transaction or trust schema.

- [ ] **Step 1: Implement the closed worker configuration**

In `probe/worker.py`, define the two string constants beside the other worker constants. Add
`connection_policy` to `ProbeWorkerConfig`, reject every value outside the two exact strings, and
require `frequency_hz == 100_000` whenever the recovery policy is selected.

Implement the derivation without mutating the frozen source config:

```python
def for_under_reset_recovery(self) -> "ProbeWorkerConfig":
    return ProbeWorkerConfig(
        frequency_hz=100_000,
        target_profile=self.target_profile(),
        transport_provider=self.transport_provider,
        connection_policy=UNDER_RESET_RECOVERY_CONNECTION_POLICY,
    )
```

In `_worker_main()`, pass `connection_policy=config.connection_policy` into the existing
`PyOCDBackend` constructor. Do not change `_METHODS`, `_VERSION`, codecs, process construction, or
error allowlists.

- [ ] **Step 2: Map the policy to PyOCD session options**

In `probe/pyocd_backend.py`, import the two policy constants from `worker.py`. This direction is
acyclic because `worker.py` imports `PyOCDBackend` only locally inside `_worker_main()` after worker
module initialization; do not duplicate the constants or create a new module.

Validate the constructor policy and recovery-frequency pair before storing driver/session state.
Store the admitted value in `_connection_policy`. In `open_attach()`, change only the option value:

```python
"connect_mode": (
    "under-reset"
    if self._connection_policy == UNDER_RESET_RECOVERY_CONNECTION_POLICY
    else "halt"
),
```

All other option keys, target-state checks, publication order, recovery cleanup, and error mapping
remain byte-for-behavior unchanged.

- [ ] **Step 3: Select recovery only inside authorized flash workflow**

Append `recovery_under_reset: object = False` to `FlashWorkflowRequest`. In `flash_workflow()`, keep
authorization precedence, then require `type(typed.recovery_under_reset) is bool`. Return
`HARDWARE_INPUT_INVALID` with message `Flash recovery selection is invalid` before `_one_shot()` for
any other type.

Select a local seams value without mutating the caller's frozen seams:

```python
selected_seams = _seams
if typed.recovery_under_reset:
    selected_seams = replace(
        _seams,
        worker_config=_seams.worker_config.for_under_reset_recovery(),
    )
```

Pass `selected_seams` to the existing `_one_shot()`. Do not add recovery data to `FlashRequest`,
Probe Service requests, program payloads, or result documents.

- [ ] **Step 4: Add the two thin public adapters**

In `cli.py`, add the flash-only argument using the existing duplicate-rejecting action:

```python
flash.add_argument(
    "--recovery-under-reset",
    action=_RejectDuplicateTrue,
    nargs=0,
    default=False,
)
```

Pass `args.recovery_under_reset` as the trailing `FlashWorkflowRequest` field.

In `mcp_server.py`, append `recovery_under_reset: object = False` to
`tool_flash_for_request()`, pass it into the request, and append
`recoveryUnderReset: StrictBool = False` to the registered `stm32_flash` tool. Forward the value
unchanged. Keep the existing exact authorization check before workflow dispatch.

- [ ] **Step 5: Run the focused GREEN matrix**

Use one fresh external basetemp:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-flash-recovery-green' `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py -q
```

Expected: all seven files pass. Do not expand to service, full-suite, coverage, package, UI, or
hardware tests unless a failure or complete-diff inspection identifies a concrete affected
contract. Preserve the exact totals and duration, inspect the basetemp, then delete only that exact
run-owned path.

- [ ] **Step 6: Audit scope and commit the GREEN code head**

```powershell
git diff --check
git diff --name-only
git status --short
git diff --stat 8a41d5ae542dfc81ffa35616809bb7418ef901a0..HEAD
```

Before committing, require that every uncommitted product path is in the five-file allowlist, every
test path is in the seven-file allowlist, `probe/flash.py`, `probe/service.py`, schemas, consumers,
runtime, and package files are unchanged, and no run-owned artifact is under the repository.

```powershell
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py `
  tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py `
  tools/stm32-toolkit/src/stm32_toolkit/cli.py `
  tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py
git commit -m "fix(vs10a): add explicit under-reset flash recovery"
```

Record the full code head and tree before any report commit.

---

### Task 4: Re-run exact code-head evidence and commit the report separately

**Files:**

- Create:
  `docs/codex/returns/STM32TK-1001-PUBLIC-FLASH-UNDER-RESET-RECOVERY/implementation-report.md`

**Interfaces:**

- Consumes: approved base/spec/plan, two RED commits, one GREEN code head, focused verification,
  cleanup evidence, and exact local/remote status.
- Produces: one report-only commit that makes no Sol acceptance, public hardware PASS, release, or
  remote-delivery claim.

- [ ] **Step 1: Verify exact committed code head and clean state**

```powershell
git status --short --branch
git diff --check
git diff --name-status f7865ed6e927403b51664705506237f4f69aa21d..HEAD
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

The implementation worktree must be clean before the evidence rerun. If it is not clean, classify
every tracked/untracked item and stop rather than hiding or deleting unrelated state.

- [ ] **Step 2: Re-run the seven-file matrix at the exact code head**

Use a new path, not the prior GREEN basetemp:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-flash-recovery-final' `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py -q
```

Record interpreter/PyOCD versions, command, UTC interval, exit code, pass/skip totals, duration,
and exact code head. Inspect and delete only the exact final basetemp after retaining the concise
result. Any protected residual is reported as ENVIRONMENT cleanup residue, not silently removed.

- [ ] **Step 3: Write the implementation report**

The report must contain:

- module/phase and status `RETURNED FOR INDEPENDENT SOL REVIEW`;
- full accepted base/tree and approved spec/plan commits;
- active branch and exact remote baseline/ahead state;
- one Luna/max implementer and Sol reviewer ownership;
- every RED commit, observed failure, GREEN code head/tree, and report boundary;
- exact changed product/test paths and unchanged frozen paths;
- exact seven-file CPython 3.12 evidence and cleanup;
- explicit statements that hardware was not run, direct recovery evidence was not relabelled,
  public Toolkit recovery remains physically unverified, and no remote action occurred;
- remaining gate: independent Sol full diff review, followed only then by separately authorized
  one-attempt hardware recovery.

The report must not contain its own future commit SHA or claim `ACCEPTED`.

- [ ] **Step 4: Commit only the report and return to Sol**

```powershell
git diff --check
git diff --name-only
git add -- docs/codex/returns/STM32TK-1001-PUBLIC-FLASH-UNDER-RESET-RECOVERY/implementation-report.md
git commit -m "docs(vs10a): report public flash recovery implementation"
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Return the full report head/tree, code head/tree, RED/GREEN lineage, focused totals, cleanup, exact
ahead/behind state, and confirmation that no hardware or remote operation ran.

---

## Sol independent review checkpoint

The GPT-5.6-sol primary must create a fresh detached clean worktree at the returned report head and
review the complete `f7865ed6e927403b51664705506237f4f69aa21d..CODE_HEAD` product/test diff plus
the separate report delta. The reviewer repeats only the seven-file focused matrix unless an exact
changed contract creates a written expansion trigger. Review must explicitly inspect:

- default 1 MHz/halt behavior and every pre-existing exact option assertion;
- recovery-only 100 kHz/under-reset selection and invalid-combination rejection;
- authorization and strict CLI/MCP inputs before service/hardware access;
- one service, worker, backend, attach, and program path with no retry/fallback;
- target identity and halted state before programming;
- unchanged sector-only program options and complete readback-before-publication;
- unchanged `flash-result.json` exact field set and genuine producer-to-binder consumption;
- cancellation/timeout/cleanup behavior inherited without scope drift;
- no code outside the product/test allowlists and accurate report lineage.

Only Sol issues `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. A software acceptance does
not authorize hardware. After `ACCEPTED`, stop and request one explicit authorization for a single
public Toolkit recovery flash. If authorized, run exactly one recovery attempt, then one read-only
public bind/read confirmation; on failure preserve evidence and stop without retry. Do not enter
VS10-B, publish remotely, or perform a release automatically.
