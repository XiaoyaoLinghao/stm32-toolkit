# STM32TK-1001 PyOCD Connection Policy Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing single PyOCD backend connect through a bounded transient halt with Pack Debug Sequences, restore observation sessions to running, retain modification sessions halted behind the identity gate, and preserve zero-programming behavior on mismatch.

**Architecture:** `PyOCDBackend.open_attach()` owns the pinned PyOCD session options and pre-publication state validation. `ProbeService` maps its frozen lease operation level to the existing `halt_on_connect` boolean and performs the final canonical target comparison before returning an attach response. `flash_firmware()` converts only the existing `PROBE_IDENTITY_MISMATCH` attach error to its established public `FIRMWARE_IDENTITY_MISMATCH` result.

**Tech Stack:** CPython `>=3.12,<3.13`, PyOCD `0.45.1`, asyncio/aiohttp Probe Service, pytest 8, PowerShell on Windows.

## Global Constraints

- Full accepted base: `03036f912e16006b1d2030b212962d3704e8a20f`; accepted-base tree: `b7688538514a50f2e083d4bef788030f342daaba`.
- Approved specification lineage: `566b6f143a41652fcddbe1a6ee0aa624dfde8f16`, `27ee586f`, `7a6140f1`, and final corrected specification head `482c35f6aaddc3fd5dd3c6dba7ed5720b117e453`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; no remote action is authorized.
- Exactly one GPT-5.6-luna agent at reasoning effort `max` owns every product and implementation-test change in this plan.
- Product files are limited to `probe/pyocd_backend.py`, `probe/service.py`, and `probe/flash.py`.
- Public CLI/MCP, Probe protocol/schema, attachment response, selector, authorization, lease, runtime, backend count, provider count, controller count, and Agent adapters remain unchanged.
- Every PyOCD session keeps `auto_unlock=false`, explicit SWD/frequency/target, `no_config=true`, `resume_on_disconnect=false`, and `user_script=os.devnull`; no reset, erase, unlock, fallback, auto-selection, or retry is added.
- Failing tests are committed before product code. The implementer does not accept its own diff, run hardware, or perform any remote action.
- All pytest commands use the named CPython 3.12 interpreter, `-p no:cacheprovider`, and a fresh external run-owned `--basetemp`; clean only that exact basetemp after preserving the result.

---

## File ownership map

- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`: single owner of PyOCD options, candidate state validation, bounded resume, publication, and candidate cleanup.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`: single owner of lease-level-to-attach-state mapping, canonical target response gate, mismatch restoration/close, and attach timeout/cancellation cleanup.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`: single owner of the existing public flash error translation.
- `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`: deterministic PyOCD target state transitions used by existing direct adapter tests.
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`: direct adapter options/state/cleanup contract.
- `tools/stm32-toolkit/tests/test_probe_service.py`: operation-level mapping, target-response gate, timeout/cancellation, and service cleanup contract.
- `tools/stm32-toolkit/tests/test_flash.py`: zero-programming and stable flash error contract.
- `tools/stm32-toolkit/tests/test_debug_firmware.py`, `test_hardware_workflows.py`, and `test_monitor_observation.py`: unchanged downstream regression consumers; modify them only if a frozen assertion lacks direct causal coverage, never to weaken behavior.
- `docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md`: implementation evidence only, committed after code/tests.

---

### Task 1: Commit the complete backend RED contract

**Files:**
- Modify: `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- Modify: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

**Interfaces:**
- Consumes: existing `PyOCDBackend.open_attach(probe_id, target, *, halt_on_connect=False)` and the deterministic PyOCD fakes.
- Produces: failing tests that freeze exact options, successful return state, identity validity, zero programming, and candidate cleanup.

- [ ] **Step 1: Make the shared PyOCD target double model real state transitions**

Change only these three fake methods so all existing direct adapter tests observe the same state
machine as PyOCD:

```python
def halt(self) -> None:
    self.calls.append(("halt",))
    self.state = "halted"

def resume(self) -> None:
    self.calls.append(("resume",))
    self.state = "running"

def reset(self) -> None:
    self.calls.append(("reset",))
    self.state = "running"
```

- [ ] **Step 2: Add a local failure-injection target without widening the shared fake API**

Add this test-only class near `backend_with_probes()`:

```python
class ConnectionPolicyTarget(FakePyOCDTarget):
    def __init__(
        self,
        *,
        part_number: object = "stm32f407vg",
        state: object = "halted",
        resume_error: BaseException | None = None,
    ) -> None:
        super().__init__(part_number=part_number, state=state)
        self.resume_error = resume_error

    def resume(self) -> None:
        self.calls.append(("resume",))
        if self.resume_error is not None:
            raise self.resume_error
        self.state = "running"
```

Keep resume-error injection local to `test_pyocd_backend.py`; do not add failure knobs to the shared
fake.

- [ ] **Step 3: Replace the accepted-base no-halt option assertion with the transient-halt observation contract**

Rename `test_exact_attach_uses_observation_only_session_options_without_halting` to
`test_observation_attach_uses_pinned_halt_policy_then_returns_running` and assert exactly:

```python
assert session.options == {
    "auto_unlock": False,
    "connect_mode": "halt",
    "dap_protocol": "swd",
    "frequency": 1_000_000,
    "no_config": True,
    "pack.debug_sequences.enable": True,
    "primary_core": 0,
    "project_dir": os.getcwd(),
    "resume_on_disconnect": False,
    "target_override": "stm32f407vg",
    "user_script": os.devnull,
}
assert target.calls == [("resume",), ("get_state",)]
assert target.state == "running"
```

Keep the existing exact four-field attachment-evidence assertion.

- [ ] **Step 4: Replace the old halt rejection with a successful modification-state contract**

Replace `test_halt_on_connect_is_rejected_before_hardware_enumeration` with:

```python
def test_modify_attach_returns_only_after_target_is_proven_halted():
    target = ConnectionPolicyTarget(state="halted")
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    evidence = PyOCDBackend(driver).open_attach(
        "probe-a", "stm32f407vg", halt_on_connect=True
    )

    assert evidence.resolved_part_number == "stm32f407vg"
    assert target.calls == [("get_state",)]
    assert target.state == "halted"
    assert driver.program_calls == []
```

- [ ] **Step 5: Add failure tests for restoration and cleanup before publication**

Add direct tests with these exact expectations:

```python
def test_observation_resume_failure_closes_candidate_and_publishes_nothing():
    target = ConnectionPolicyTarget(
        resume_error=RuntimeError(r"resume failed C:\private\target")
    )
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg")

    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert "private" not in str(caught.value)
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"


@pytest.mark.parametrize(
    "part_number",
    (None, "", "unknown\npart", r"C:\private", 1234),
)
def test_invalid_identity_resumes_and_closes_halted_candidate(part_number):
    target = ConnectionPolicyTarget(part_number=part_number)
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)

    with pytest.raises(ProbeBackendError) as caught:
        PyOCDBackend(driver).open_attach(
            "probe-a", "stm32f407vg", halt_on_connect=True
        )

    assert caught.value.code == "PROBE_TARGET_IDENTITY_UNAVAILABLE"
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    assert driver.program_calls == []
    assert driver.created_sessions[0].close_count == 1
```

Preserve the explicit `("get_state",)` assertion. Do not accept a close-only cleanup that leaves
the fake halted.

- [ ] **Step 6: Run the backend RED test file**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-pyocd-policy-red-backend-20260902' -q
```

Expected: failures at the exact options, observation resume, accepted modification attach, and
candidate restoration assertions. Existing selector, read, flash, and cleanup tests must still
collect and run; import or fixture failure is not valid RED.

- [ ] **Step 7: Commit backend RED**

```powershell
git add -- tools/stm32-toolkit/tests/fakes/fake_pyocd.py tools/stm32-toolkit/tests/test_pyocd_backend.py
git diff --cached --check
git commit -m "test(vs10a): define transient halt PyOCD policy"
```

---

### Task 2: Commit service, flash, and cancellation RED contracts

**Files:**
- Modify: `tools/stm32-toolkit/tests/test_probe_service.py`
- Modify: `tools/stm32-toolkit/tests/test_flash.py`

**Interfaces:**
- Consumes: `ProbeService._operation_level`, `FakeProbeBackend.events`, `ProbeClient.attach()`, and `flash_firmware()`.
- Produces: failing tests for lease-level mapping, response-before-identity rejection, restoration/close, attach cancellation, and stable public flash errors.

- [ ] **Step 1: Freeze lease-level mapping at the live service boundary**

Add this parametrized test to `test_probe_service.py`:

```python
@pytest.mark.parametrize(
    ("level", "expected_halt"),
    (
        (OperationLevel.OBSERVE, False),
        (OperationLevel.CONTROL, False),
        (OperationLevel.MODIFY, True),
    ),
)
def test_attach_maps_service_level_to_required_return_state(
    level: OperationLevel, expected_halt: bool, tmp_path: Path
) -> None:
    async def scenario() -> None:
        backend = fake_backend()
        service = make_service(tmp_path, level=level, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            assert (
                "open_attach", "probe-a", "STM32F429ZITx", expected_halt
            ) in backend.events
            assert backend.halted is expected_halt
        finally:
            await client.close()
            await service.stop()

    run(scenario())
```

Current product must fail only the `MODIFY` case because it hard-codes `False`.

- [ ] **Step 2: Add a mismatch backend and prove response gating, restoration, and close**

Add a local subclass that returns a different portable identity and exposes closed target state:

```python
class MismatchedAttachBackend(FakeProbeBackend):
    def open_attach(self, probe_id, target, *, halt_on_connect=False):
        super().open_attach(
            probe_id, target, halt_on_connect=halt_on_connect
        )
        return ProbeAttachmentEvidence(probe_id, target, "STM32F407VG", 1)

    def target_state(self):
        return {
            "state": "halted" if self.halted else "running",
            "reason": "requested",
        }
```

Then add:

```python
def test_modify_attach_mismatch_resumes_closes_and_returns_no_evidence(tmp_path: Path):
    async def scenario() -> None:
        source = fake_backend()
        backend = MismatchedAttachBackend(
            probes=source.list_probes(), memory={}, registers={}
        )
        service = make_service(
            tmp_path, level=OperationLevel.MODIFY, backend=backend
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            with pytest.raises(ProbeClientError) as caught:
                await client.attach("probe-a", "STM32F429ZITx")
            assert caught.value.code == "PROBE_IDENTITY_MISMATCH"
            assert ("resume",) in backend.events
            assert backend.closed is True
            assert backend.halted is False
            assert backend.flashed_images == []
        finally:
            await client.close()
            await service.stop()

    run(scenario())
```

- [ ] **Step 3: Freeze attach cancellation cleanup**

Add a `BlockingAttachBackend` derived from `FakeProbeBackend` with `entered` and `release` threading
events. Its `open_attach()` waits after `super().open_attach(...)` and before returning evidence.
First test a client attach task, cancel it after `entered`, release the backend, require
`asyncio.CancelledError`, then require `backend.closed is True`, `backend.halted is False`, and
`backend.flashed_images == []` before service shutdown. This is the exact cancellation body:

```python
request = asyncio.create_task(client.attach("probe-a", "STM32F429ZITx"))
assert await asyncio.to_thread(backend.entered.wait, 2)
request.cancel()
backend.release.set()
with pytest.raises(asyncio.CancelledError):
    await request
for _ in range(100):
    if backend.closed:
        break
    await asyncio.sleep(0.01)
assert backend.closed is True
assert backend.halted is False
assert backend.flashed_images == []
```

Then use a fresh backend/service/client and test the service deadline with:

```python
request = asyncio.create_task(
    client.request(
        "probe.attach",
        {"probeId": "probe-a", "target": "STM32F429ZITx"},
        timeout_ms=20,
    )
)
assert await asyncio.to_thread(backend.entered.wait, 2)
await asyncio.sleep(0.05)
backend.release.set()
with pytest.raises(ProbeClientError) as caught:
    await request
assert caught.value.code == "PROBE_TIMEOUT"
assert backend.closed is True
assert backend.halted is False
assert backend.flashed_images == []
```

The bounded polling loop and 50 ms sleep are test synchronization only; production must not add
polling, sleep, or automatic retry.

- [ ] **Step 4: Freeze public flash mismatch translation and zero programming**

Import `ProbeClientError` in `test_flash.py`. Add a local client subclass:

```python
class RejectedIdentityFlashClient(RecordingFlashClient):
    async def attach(self, probe_id: str, target: str) -> object:
        self.events.append(("attach", probe_id, target))
        raise ProbeClientError(
            "PROBE_IDENTITY_MISMATCH", "Connected target identity does not match"
        )
```

Add this exact test using the existing project/build helpers and request factory:

```python
def test_flash_maps_attach_identity_rejection_without_programming(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RejectedIdentityFlashClient(
        _elf_with_flash_segment()[84 : 84 + 320]
    )

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert result.details == {"field": "connectedTarget", "rule": "identity"}
    assert client.events == [("attach", "probe-123", "stm32f407vg")]
    assert not any(event[0] == "program" for event in client.events)
    assert not (root / "artifacts/migration/flash-result.json").exists()
```

Do not change the existing `test_flash_rejects_resolved_target_identity_mismatch`; it remains an
independent proof that a malformed successful attachment also cannot program.

- [ ] **Step 5: Run the complete RED matrix**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py `
  -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-pyocd-policy-red-complete-20260902' -q
```

Expected: the newly named connection-policy tests fail for product reasons; unchanged downstream
tests pass. Stop if an existing unrelated blocker prevents a new test from proving its target
behavior. Do not delete assertions or alter unrelated product behavior to manufacture RED.

- [ ] **Step 6: Commit the remaining RED tests**

```powershell
git add -- tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_flash.py
git diff --cached --check
git commit -m "test(vs10a): gate attach identity before programming"
```

---

### Task 3: Implement the minimum GREEN product correction

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`

**Interfaces:**
- Consumes: the RED tests and existing `ProbeBackendError`, `ProbeAttachmentEvidence`, `OperationLevel`, `_canonical_target`, and `_FlashFailure` contracts.
- Produces: the same public attach/flash interfaces with corrected internal connection and cleanup semantics.

- [ ] **Step 1: Add one pre-publication state reader in `PyOCDBackend`**

Factor the existing `target_state()` mapping into a private static helper that accepts a candidate
target before `self._target` is assigned:

```python
@staticmethod
def _read_target_state(target: object) -> str:
    try:
        state = getattr(target, "get_state")()
        raw = getattr(state, "name", state)
    except Exception as error:
        raise ProbeBackendError(
            "PROBE_BACKEND_ERROR", "Target state is unavailable"
        ) from error
    mapped = {
        "running": "running",
        "halted": "halted",
        "reset": "reset",
        "lockedup": "faulted",
    }.get(str(raw).lower())
    if mapped is None:
        raise ProbeBackendError(
            "PROBE_BACKEND_ERROR", "Target state is unavailable"
        )
    return mapped
```

Make `target_state()` call this helper and retain its existing response keys and reason mapping.

- [ ] **Step 2: Add candidate restoration without publishing partial state**

Add a private helper that takes local `session`, `probe`, and candidate `target`. When restoration
is required it calls `target.resume()`, requires `_read_target_state(target) == "running"`, and then
calls existing `_close_external(session, probe)`. If restoration fails, still attempt close. If
close fails, raise existing `PROBE_CLOSE_FAILED`; otherwise propagate a sanitized
`PROBE_ATTACH_FAILED` chained from the restoration error. It must never assign `self._session`,
`self._target`, or identity fields.

- [ ] **Step 3: Apply the frozen PyOCD options and successful-return state semantics**

In `open_attach()`:

```python
"connect_mode": "halt",
"pack.debug_sequences.enable": True,
```

Remove the accepted-base rejection of `halt_on_connect=True`. After validating target, cores, and
portable part number but before assigning backend state:

```python
if halt_on_connect:
    if self._read_target_state(session_target) != "halted":
        raise ProbeBackendError(
            "PROBE_BACKEND_ERROR", "Target halt state is unavailable"
        )
else:
    getattr(session_target, "resume")()
    if self._read_target_state(session_target) != "running":
        raise ProbeBackendError(
            "PROBE_BACKEND_ERROR", "Target resume state is unavailable"
        )
```

Track whether `session.open()` succeeded. Any later failure uses candidate restoration and close;
an open failure closes only acquired resources. Assign `self._session` and the other owned fields
only after the required final state is proven.

- [ ] **Step 4: Map service operation levels and gate the successful response**

Import the existing `_canonical_target` from `.flash`. Change the attach call to:

```python
halt_on_connect=self._operation_level is OperationLevel.MODIFY
```

After receiving evidence and before `return evidence.to_dict()`, compare the canonical requested
and resolved targets. On mismatch:

1. For `MODIFY`, call `self._backend.resume()` and require
   `dict(self._backend.target_state())["state"] == "running"`.
2. Call `self._backend.close()` for every operation level.
3. If close fails, raise `PROBE_CLOSE_FAILED`; if restoration fails but close succeeds, raise a
   sanitized `PROBE_BACKEND_ERROR`; otherwise raise existing `PROBE_IDENTITY_MISMATCH`.

Do not include raw selector, hardware ID, host path, or underlying exception text in the public
message/details.

- [ ] **Step 5: Make attach timeout/cancellation terminate or close its candidate**

Treat `request.operation == "probe.attach"` as a reversible native-effect operation in the existing
timeout/cancellation branch. If the backend exposes `abort_owned_execution`, invoke the existing
bounded abort/join path. For a direct in-process fake without that method, await its bounded test
completion and call `self._backend.close()` before re-raising timeout/cancellation. Do not change
the guarded-flash commit-point rule for `flash.program` or any CONTROL operation.

- [ ] **Step 6: Preserve the public flash mismatch error**

Wrap only `client.attach()` in `flash_firmware()`:

```python
try:
    attachment = await client.attach(typed.probe_id, typed.target)
except asyncio.CancelledError:
    raise
except Exception as error:
    if getattr(error, "code", None) == "PROBE_IDENTITY_MISMATCH":
        raise _fail(
            "FIRMWARE_IDENTITY_MISMATCH",
            "Connected target does not match the project",
            field="connectedTarget",
            rule="identity",
        ) from None
    raise
```

Keep `_validate_attachment()` immediately after this block, so malformed successful responses
retain the same error and zero-programming behavior.

- [ ] **Step 7: Run the focused GREEN matrix**

Run the exact six-file command from Task 2 with a fresh basetemp
`C:\tmp\stm32tk-1001-pyocd-policy-green-20260902`.

Expected: all six files pass. No hardware, full suite, coverage, package/install, UI, or release
matrix runs are authorized by this plan.

- [ ] **Step 8: Inspect scope and commit product GREEN**

```powershell
git diff --check
git diff --name-only
git diff --name-only 482c35f6aaddc3fd5dd3c6dba7ed5720b117e453..HEAD
git status --short
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/service.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git diff --cached --check
git commit -m "fix(vs10a): converge PyOCD connection policy"
```

Before committing, stop if any product file outside the three approved paths changed.

---

### Task 4: Verify the returned code head and commit the report separately

**Files:**
- Create: `docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md`

**Interfaces:**
- Consumes: exact RED commits, product GREEN commit, focused test evidence, and Git state.
- Produces: a report-only commit that does not claim acceptance, hardware PASS, runtime correction, or remote delivery.

- [ ] **Step 1: Run pre-report required checks**

Run from the implementation worktree:

```powershell
git diff --check 03036f912e16006b1d2030b212962d3704e8a20f..HEAD
git diff --name-only 03036f912e16006b1d2030b212962d3704e8a20f..HEAD
git status --short --branch
```

The complete path list may contain only the approved specification/plan, three product files,
approved tests actually changed, and no report yet. Stop on any unexplained tracked, untracked, or
uncommitted path.

- [ ] **Step 2: Re-run the final six-file matrix against the exact code head**

Use a new basetemp `C:\tmp\stm32tk-1001-pyocd-policy-final-20260902` and the exact Task 2 command.
Record interpreter version, full code-head SHA/tree, command, collected/pass/skip/fail counts,
duration, and cleanup result. Remove and verify absent only that exact basetemp after preserving the
minimum result.

- [ ] **Step 3: Write the implementation report**

The report must state:

- full accepted base and tree;
- final corrected specification commit and implementation-plan commit;
- branch/upstream and exact ahead/behind state;
- every RED commit, observed failure count/nodes, and product GREEN commit;
- final code head and tree before the report commit;
- exact changed paths and confirmation that no assertion was removed or weakened;
- exact focused verification and cleanup evidence;
- `HARDWARE NOT RUN BY IMPLEMENTER`;
- `RUNTIME LAUNCHER CORRECTION NOT INCLUDED`;
- `SOL REVIEW PENDING`;
- `REMOTE ACTION NONE`.

Do not include the report commit's own SHA or moving commit totals.

- [ ] **Step 4: Commit only the report**

```powershell
git add -- docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs(vs10a): report PyOCD connection policy correction"
git status --short --branch
```

Return the full specification, plan, RED, code-head, report-head, tree, verification, cleanup, and
remote-state ledger to the Sol primary. Do not issue an acceptance verdict.

---

## Sol review checkpoint after implementation

The Sol primary creates a clean detached review worktree at the report head, verifies the exact
accepted base, and reviews the complete `03036f912e16006b1d2030b212962d3704e8a20f..CODE_HEAD` diff,
then the report-only delta. Sol reruns only the six-file focused matrix with a new external
basetemp. If accepted, Sol may run the separately authorized one-shot 100 kHz SWD observation smoke
and must prove target return to running with zero flash/reset/erase/unlock. Hardware evidence never
substitutes for software diff review, and software tests never become physical PASS.
