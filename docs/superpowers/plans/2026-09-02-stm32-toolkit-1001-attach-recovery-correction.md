# STM32TK-1001 Attach Recovery Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct partial-open and attach-cancellation recovery so a target that may have been halted is restored and closed before terminal propagation, with hard termination reported only as `PROBE_CLOSE_FAILED`.

**Architecture:** Keep the existing PyOCD backend, Probe Service, worker process, IPC, CLI, MCP, schemas, and runtime. `PyOCDBackend` captures a local target before `session.open()` and owns candidate restoration/error chaining; `ProbeService` waits one second for the exact attach task, restores a successful MODIFY attachment through the existing backend methods, and uses the existing worker abort only as a last-resort safety failure.

**Tech Stack:** CPython 3.12, pytest, asyncio, multiprocessing worker proxy, PyOCD adapter, Git.

## Global Constraints

- Full accepted product base is `03036f912e16006b1d2030b212962d3704e8a20f`, tree `b7688538514a50f2e083d4bef788030f342daaba`.
- Reviewed but unaccepted predecessor product head is `1783b33ab77bdce2f6103e7f765db8bad8cd3d00`, tree `fdf79c8b8c043c3434251dcc6edb6dd6c4d184dc`.
- Approved correction specification is `docs/superpowers/specs/2026-09-02-stm32-toolkit-1001-attach-recovery-correction-design.md` at `562efee620e536ef861a445576111dac330a788b`.
- One GPT-5.6-luna agent at reasoning effort `max` owns every implementation and implementation-test change in this correction.
- GPT-5.6-sol independently reviews the complete `03036f91..FINAL_CODE_HEAD` diff from a fresh detached clean worktree; the implementer does not accept its own work.
- Product changes are limited to `pyocd_backend.py` and `service.py`. `worker.py` and `flash.py` stay byte-identical to `1783b33a`.
- Test changes are limited to `fake_pyocd.py`, `test_pyocd_backend.py`, `test_probe_service.py`, and `test_probe_worker.py`.
- The recovery wait is exactly one second. It is not a retry and creates no second probe, session, worker, connection, backend, controller, runtime, or IPC method.
- No reset, erase, unlock, mass erase, programming, reopen, fallback probe, family fallback, protocol/schema change, new Python support, CI, or collaboration automation.
- No hardware, full suite, coverage, package/install, UI, release, push, PR mutation, merge, tag, release, remote branch, or other remote action.
- Every pytest command uses CPython 3.12, source/test `PYTHONPATH`, `-p no:cacheprovider`, and an exact external run-owned basetemp that is cleaned after evidence is retained.
- If any product path outside the two named files is required, stop and report the exact design conflict. Do not widen scope or weaken tests.

---

## File responsibility map

- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`: pre-open candidate target capture, one-shot restoration, close precedence, sanitized explicit cause chain, and attachment publication order.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`: one-second attach task recovery, successful MODIFY restoration, existing worker abort fallback, terminal precedence, and direct close normalization.
- `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`: deterministic partial-open-after-halt test seam only.
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`: partial-open restoration and sanitized cause-order contracts.
- `tools/stm32-toolkit/tests/test_probe_service.py`: direct and production-worker cancellation/timeout recovery contracts.
- `tools/stm32-toolkit/tests/test_probe_worker.py`: existing-worker hard-termination/no-late-action integration evidence without worker product changes.
- `docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md`: exact complete correction lineage and evidence; committed separately after code.

---

### Task 1: Commit the PyOCD partial-open and cause-chain RED contract

**Files:**
- Modify: `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- Modify: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

**Interfaces:**
- Consumes: `PyOCDBackend.open_attach(probe_id, target, *, halt_on_connect=False)`, `FakePyOCDDriver`, `FakePyOCDSession`, `FakePyOCDTarget`, and `ProbeBackendError`.
- Produces: deterministic RED tests for a target halted during a failing `session.open()` and for sanitized `PROBE_CLOSE_FAILED.__cause__` ordering.

- [ ] **Step 1: Add a partial-open-after-halt fake seam**

Add one default-disabled flag to `FakePyOCDSession` and `FakePyOCDDriver`:

```python
class FakePyOCDSession:
    def __init__(
        self,
        probe: FakePyOCDProbe,
        *,
        options: Mapping[str, object],
        target: FakePyOCDTarget | None,
        halt_before_open_error: bool = False,
    ) -> None:
        ...
        self.halt_before_open_error = halt_before_open_error

    def open(self) -> None:
        self.open_count += 1
        self.probe.is_open = True
        if self.halt_before_open_error and self.board.target is not None:
            self.board.target.state = "halted"
        if self.open_error is not None:
            raise self.open_error
```

Add `self.session_halt_before_open_error = False` to `FakePyOCDDriver.__init__()` and pass it to
`FakePyOCDSession`. Do not change the default behavior of any existing test.

- [ ] **Step 2: Add the partial-open restoration RED test**

Add:

```python
def test_partial_open_failure_after_halt_restores_before_close_and_publishes_nothing():
    target = FakePyOCDTarget(state="running")
    probe = FakePyOCDProbe("probe-a")
    driver = FakePyOCDDriver((probe,), target=target)
    driver.session_halt_before_open_error = True
    driver.session_open_error = RuntimeError(r"post-connect failed C:\private\pack")
    backend = PyOCDBackend(driver)

    with pytest.raises(ProbeBackendError) as caught:
        backend.open_attach("probe-a", "stm32f407vg")

    assert caught.value.code == "PROBE_ATTACH_FAILED"
    assert "private" not in str(caught.value)
    assert target.calls == [("resume",), ("get_state",)]
    assert target.state == "running"
    assert driver.created_sessions[0].close_count == 1
    assert probe.close_count == 1
    assert driver.program_calls == []
    with pytest.raises(ProbeBackendError) as detached:
        backend.read_memory(0x20000000, 4)
    assert detached.value.code == "PROBE_NOT_ATTACHED"
```

This test models the PyOCD order confirmed during review: halt can occur before later Pack/target
initialization fails. It must not call a product-only fake path.

- [ ] **Step 3: Freeze simultaneous failure cause ordering**

Add a test using a malformed resolved identity, a candidate `resume_error`, and
`driver.session_close_error = RuntimeError(r"close failed C:\private\probe")`:

```python
def test_candidate_close_failure_chains_only_the_initiating_sanitized_error():
    target = ConnectionPolicyTarget(
        part_number=None,
        resume_error=RuntimeError(r"resume failed C:\private\target"),
    )
    driver = FakePyOCDDriver((FakePyOCDProbe("probe-a"),), target=target)
    driver.session_close_error = RuntimeError(r"close failed C:\private\probe")

    with pytest.raises(ProbeBackendError) as caught:
        PyOCDBackend(driver).open_attach(
            "probe-a", "stm32f407vg", halt_on_connect=True
        )

    assert caught.value.code == "PROBE_CLOSE_FAILED"
    cause = caught.value.__cause__
    assert isinstance(cause, ProbeBackendError)
    assert cause.code == "PROBE_TARGET_IDENTITY_UNAVAILABLE"
    assert cause.message == "Selected target identity is unavailable"
    assert cause.details == {}
    assert "private" not in str(caught.value)
    assert "private" not in str(cause)
    assert target.calls == [("resume",)]
    assert driver.program_calls == []
```

The raw close/resume exceptions must not be the explicit cause exposed by the Toolkit error chain.

- [ ] **Step 4: Run the backend RED file**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-red-backend-20260902' -q
```

Expected: the two new nodes fail for PRODUCT reasons against `1783b33a` product bytes. Every other
backend node passes. Import, fixture, environment, or cleanup failure is not valid RED.

- [ ] **Step 5: Inspect and commit Task 1 RED**

Run:

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/tests/fakes/fake_pyocd.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py
git diff --cached --check
git diff --cached --name-only
git commit -m "test(vs10a): expose partial attach recovery gaps"
```

The cached list must contain exactly the two Task 1 files. Record the exact failing node names,
commit, tree, interpreter, basetemp cleanup, and branch state in the SDD scratch report.

---

### Task 2: Commit service and production-worker recovery RED contracts

**Files:**
- Modify: `tools/stm32-toolkit/tests/test_probe_service.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_worker.py`

**Interfaces:**
- Consumes: `ProbeService._run_backend(request)`, `ProbeRequest`, `OperationLevel.MODIFY`, `ProbeBackendWorker`, and the existing `abort_owned_execution()` fallback.
- Produces: RED tests that distinguish cooperative terminal recovery from immediate termination and prove `PROBE_CLOSE_FAILED` precedence without changing worker product bytes.

- [ ] **Step 1: Add a direct backend whose close does not resume**

Add a local fake derived from the existing blocking attach fake:

```python
class ExplicitRecoveryAttachBackend(BlockingAttachBackend):
    def __init__(
        self,
        *,
        entered: threading.Event,
        release: threading.Event,
        close_error: BaseException | None = None,
    ) -> None:
        super().__init__(entered=entered, release=release)
        self.close_error = close_error

    def target_state(self):
        self.events.append(("target_state", "halted" if self.halted else "running"))
        return {
            "state": "halted" if self.halted else "running",
            "reason": "requested",
        }

    def close(self) -> None:
        self.events.append(("close_without_resume", self.halted))
        self.close_called = True
        if self.close_error is not None:
            raise self.close_error
        self.attached_probe_id = None
        self.attached_target = None
        self.closed = True
```

Unlike `FakeProbeBackend.close()`, this seam deliberately preserves `halted` so a missing explicit
resume cannot pass accidentally.

- [ ] **Step 2: Freeze direct cancellation and timeout terminal order**

Build a private `ProbeRequest` helper for `probe.attach`, MODIFY, exact workspace/session/lease,
and caller-selected timeout. Add two tests that use a delayed 50 ms release and call
`service._run_backend()` directly.

For caller cancellation, cancel the service task after `entered`, then require that terminal
`CancelledError` is observed only after:

```python
assert backend.events[-4:] == [
    ("attach_returned",),
    ("resume",),
    ("target_state", "running"),
    ("close_without_resume", False),
]
assert backend.halted is False
assert backend.closed is True
assert backend.flashed_images == []
```

For timeout, use `timeout_ms=20`, expect service-side `asyncio.TimeoutError`, and assert the same
terminal event/state conditions before the exception is returned. The delayed release task must
already be complete when the terminal exception is observed.

- [ ] **Step 3: Freeze direct cleanup close-error precedence**

Repeat the direct cancellation test with
`close_error=RuntimeError(r"close failed C:\private\target")` and assert:

```python
with pytest.raises(ProbeBackendError) as caught:
    await operation
assert caught.value.code == "PROBE_CLOSE_FAILED"
assert "private" not in str(caught.value)
cause = caught.value.__cause__
assert isinstance(cause, ProbeBackendError)
assert cause.code == "PROBE_BACKEND_ERROR"
assert "private" not in str(cause)
assert backend.flashed_images == []
```

No raw close exception may escape for request-handler conversion to `PROBE_INTERNAL_ERROR`.

- [ ] **Step 4: Add a production-worker cooperative recovery seam**

In `test_probe_worker.py`, add one top-level picklable backend factory and backend class. The
backend receives an exact run-owned marker path, writes one JSON line per event, sleeps for 100 ms
inside `open_attach()`, returns a halted `ProbeAttachmentEvidence`, and implements `resume`,
`target_state`, and `close` using its own boolean state. It must never call hardware.

Construct the real `ProbeBackendWorker` with `_test_backend_factory=partial(...)`, pass it to a
real `ProbeService`, issue a direct `_run_backend()` attach with `timeout_ms=20`, and assert the
terminal timeout occurs only after the marker order is exactly:

```text
attach-entered
attach-returned
resume
target-state-running
close-running
```

Assert the exact owned worker is no longer alive and no programming marker exists.

- [ ] **Step 5: Add the unresponsive-worker last-resort test**

Use a second top-level test backend mode whose `open_attach()` writes `attach-entered`, sleeps for
five seconds, and would write `late-attach-returned` afterward. Run it through the real service
with `timeout_ms=20`.

Assert:

```python
with pytest.raises(ProbeBackendError) as caught:
    await service._run_backend(request)
assert caught.value.code == "PROBE_CLOSE_FAILED"
assert worker.is_alive is False
```

After waiting slightly longer than the existing worker termination grace, assert the marker still
contains no `late-attach-returned`, resume, close, reset, erase, unlock, or program event. The test
must inspect and remove only its exact run-owned marker root.

- [ ] **Step 6: Run the service/worker RED files**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-red-service-20260902' -q
```

Expected: only the new recovery/precedence nodes fail for PRODUCT reasons. Existing worker
termination/no-late-action, service cancellation, flash commit-point, protocol, and lease tests
must remain passing.

- [ ] **Step 7: Inspect and commit Task 2 RED**

Run:

```powershell
git diff --check
git diff --name-only
git add -- `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_worker.py
git diff --cached --check
git diff --cached --name-only
git commit -m "test(vs10a): define bounded attach recovery"
```

The cached list must contain exactly the two Task 2 files. Record exact RED nodes and cleanup.

---

### Task 3: Implement the two-file recovery correction and make all focused tests GREEN

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`

**Interfaces:**
- Consumes: every accepted predecessor and correction RED test, `ProbeBackendError`, the existing worker proxy methods, and `abort_owned_execution()`.
- Produces: corrected partial-open restoration, one-second attach recovery, authoritative sanitized cleanup errors, and unchanged public CLI/MCP/protocol/schema behavior.

- [ ] **Step 1: Capture the candidate target before session open**

Add one private helper in `PyOCDBackend`:

```python
@staticmethod
def _candidate_target(session: object) -> object | None:
    board = getattr(session, "board", None)
    return None if board is None else getattr(board, "target", None)
```

Immediately after `create_session()`, assign `session_target = self._candidate_target(session)`.
After an open exception, repeat that same lookup once only if the first value was `None`. Do not
enumerate, create another session, or reopen.

- [ ] **Step 2: Centralize sanitized candidate cleanup precedence**

Change the candidate cleanup helper to receive the initiating `ProbeBackendError`:

```python
@classmethod
def _restore_candidate_and_close(
    cls,
    session: object,
    probe: object,
    target: object | None,
    initiating: ProbeBackendError,
) -> None:
    restoration_error: ProbeBackendError | None = None
    if target is not None:
        try:
            getattr(target, "resume")()
            if cls._read_target_state(target) != "running":
                raise ProbeBackendError(
                    "PROBE_BACKEND_ERROR", "Target resume state is unavailable"
                )
        except Exception:
            restoration_error = ProbeBackendError(
                "PROBE_ATTACH_FAILED", "Debug probe attach failed"
            )
    try:
        cls._close_external(session, probe)
    except ProbeBackendError:
        raise ProbeBackendError(
            "PROBE_CLOSE_FAILED", "Debug probe cleanup failed"
        ) from initiating
    if restoration_error is not None:
        raise restoration_error from initiating
```

Refine the exact original-code mapping where necessary so malformed identity, ambiguous target,
and state errors retain their predecessor codes when restoration/close succeeds. Raw resume/close
exceptions must never become the explicit cause.

- [ ] **Step 3: Route every post-create/open failure through the same cleanup authority**

Before calling `session.open()`, construct no public evidence and assign no backend-owned fields.
On `ProbeBackendError`, pass that sanitized error as `initiating`. On a raw exception, first create:

```python
initiating = ProbeBackendError(
    "PROBE_ATTACH_FAILED",
    "Debug probe attach failed",
    {"probeId": probe_id, "target": target},
)
```

Then perform candidate restoration/close. If cleanup succeeds, raise `initiating from None` so
the raw host/driver exception is not the explicit public cause.
Only after open, identity, core count, and required final state all pass may the method assign
`self._session`, `self._target`, identity fields, and return evidence.

- [ ] **Step 4: Add one-second cancellation-safe task waiting in Probe Service**

Add:

```python
_ATTACH_RECOVERY_SECONDS = 1.0
```

Add a private coroutine that waits for the exact task despite caller cancellation and returns one
of three closed outcomes: task success value, task exception, or recovery timeout. It must use
`asyncio.shield()` and an absolute loop deadline so repeated cancellation cannot restart the one
second budget.

- [ ] **Step 5: Recover a successful attach before terminal propagation**

In the existing attach timeout/cancellation branch:

1. Wait through the helper for at most one second.
2. If the task succeeded and the service operation level is MODIFY, call
   `await asyncio.to_thread(self._backend.resume)`, then read state and require `running`.
3. Call `await asyncio.to_thread(self._backend.close)` for every successful attach.
4. If recovery and close succeed, re-raise the original timeout/cancellation.
5. If the task completed with `ProbeBackendError(code="PROBE_CLOSE_FAILED")`, raise a new sanitized
   `PROBE_CLOSE_FAILED` from that sanitized error.
6. If the task completed with another backend failure, preserve the original timeout/cancellation;
   backend candidate cleanup already completed before that failure returned.

Do not change `flash.program` or non-attach CONTROL-operation cancellation behavior. A
`probe.attach` request uses this recovery branch at OBSERVE, CONTROL, and MODIFY levels; only a
successful MODIFY candidate requires the explicit resume because successful OBSERVE/CONTROL
attach already proves running.

- [ ] **Step 6: Make unsafe cleanup explicit and authoritative**

If the task is still live after one second:

```python
initiating = ProbeBackendError(
    "PROBE_TIMEOUT", "Attach recovery did not reach a terminal state"
)
abort = getattr(self._backend, "abort_owned_execution", None)
if callable(abort):
    try:
        await asyncio.to_thread(abort)
    except Exception:
        pass
raise ProbeBackendError(
    "PROBE_CLOSE_FAILED", "Probe attach cleanup failed"
) from initiating
```

For a completed successful attach whose resume, state proof, or close fails, still attempt close
once. Raise sanitized `PROBE_CLOSE_FAILED` from a sanitized `PROBE_BACKEND_ERROR` initiating
recovery error. No raw exception text/details may escape. Do not return while a bounded direct test
task is still live; its admitted test seam must release within the one-second budget.

- [ ] **Step 7: Run the three affected test files GREEN**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-green-focused-20260902' -q
```

Expected: all three files pass with only pre-existing platform skips, if any.

- [ ] **Step 8: Run the expanded seven-file integration matrix**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-green-integration-20260902' -q
```

Expected: all selected tests pass with only the existing Windows skip(s). No hardware runs.

- [ ] **Step 9: Inspect exact product scope and commit GREEN**

Run:

```powershell
git diff --check
git diff --name-only
git diff --name-only 1783b33ab77bdce2f6103e7f765db8bad8cd3d00..HEAD
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
git diff --cached --check
git diff --cached --name-only
git commit -m "fix(vs10a): recover cancelled attach safely"
```

The cached product list must contain exactly the two files. Confirm `worker.py` and `flash.py` are
byte-identical to `1783b33a`. Record product commit/tree, exact counts, cleanup, and boundaries.

---

### Task 4: Verify the returned code head and commit the implementation report separately

**Files:**
- Create: `docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md`

**Interfaces:**
- Consumes: the predecessor RED/GREEN lineage, correction RED commits, correction GREEN commit,
  seven-file verification, cleanup evidence, and Git state.
- Produces: a report-only commit that does not claim Sol acceptance, hardware PASS, runtime-launcher
  correction, release readiness, or remote delivery.

- [ ] **Step 1: Run pre-report scope checks**

Run:

```powershell
git diff --check
git status --short --branch
git diff --name-only 03036f912e16006b1d2030b212962d3704e8a20f..HEAD
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-list --left-right --count origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl...HEAD
```

Stop if the implementation worktree is dirty or any product/test path falls outside the combined
approved predecessor and correction specifications.

- [ ] **Step 2: Re-run only the expanded seven-file matrix if product bytes changed after Task 3 evidence**

If Task 3's final matrix was run against the exact current code head and no dependency/environment
changed, cite it without duplicate execution. Otherwise rerun the exact Step 8 command with a new
run-owned basetemp and clean it.

- [ ] **Step 3: Write the implementation report**

The report must state:

- accepted base `03036f912e16006b1d2030b212962d3704e8a20f` and tree;
- predecessor spec/plan heads, predecessor RED commits, test reconciliation `38cfc86b`, rejected
  product head `1783b33a`, and its `REVISION_REQUIRED` findings;
- correction spec head `562efee6` and this implementation-plan commit;
- every correction RED commit with exact failing nodes and classification;
- final code head/tree before the report commit;
- exact changed paths and proof that `worker.py` and `flash.py` remain byte-identical to
  `1783b33a`;
- exact focused/integration commands, interpreter, counts, skips, and cleanup;
- `HARDWARE NOT RUN BY IMPLEMENTER`;
- `RUNTIME LAUNCHER CORRECTION NOT INCLUDED`;
- `SOL COMPLETE-DIFF REVIEW PENDING`;
- `REMOTE ACTION NONE`.

Do not place the report commit's own SHA in the tracked report and do not claim acceptance.

- [ ] **Step 4: Commit only the report**

Run:

```powershell
git add -- docs/codex/returns/STM32TK-1001-PYOCD-CONNECTION-POLICY-CORRECTION/implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs(vs10a): report attach recovery correction"
git status --short --branch
```

Return the exact spec, plan, correction RED, final code, report, tree, verification, cleanup, and
remote-state ledger to the Sol primary. Do not issue an acceptance verdict.

---

## Sol review checkpoint after implementation

The Sol primary creates a fresh detached clean worktree at the returned report head and:

1. verifies exact HEAD/tree/status and remote ahead/behind state;
2. reviews the complete `03036f91..FINAL_CODE_HEAD` diff, not only the correction delta;
3. verifies every approved product/test/report path and byte-identity freeze;
4. runs the seven-file integration matrix only because worker-boundary risk was explicitly added;
5. verifies partial-open recovery, one-second cooperative recovery, hard-termination safety error,
   cause ordering, zero programming, and no raw sensitive error data;
6. cleans only its exact run-owned artifacts;
7. issues `ACCEPTED`, `ACCEPTED_WITH_FIXES`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`.

No hardware or remote action follows automatically from a software acceptance verdict.
