# STM32TK-1001 OBSERVE Attach Absolute-Deadline Fencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an OBSERVE attach request's public timeout include lifecycle-lock queueing so expired
requests cannot later read cached evidence or dispatch hardware, while preserving same-session
reuse and existing recovery behavior.

**Architecture:** `ProbeService._run_backend()` captures one monotonic absolute deadline before
waiting for the private OBSERVE lifecycle lock. `asyncio.timeout_at()` encloses both lock admission
and the existing `_run_backend_inner()` call, so queueing consumes the same request budget while
the existing inner cancellation/timeout recovery remains authoritative after backend entry. The
lock remains held through recovery and is released structurally on every terminal path.

**Tech Stack:** CPython 3.12, `asyncio.timeout_at`, pytest 8.4.2, aiohttp, existing Probe
Service/client/backend test seams, Git.

## Global Constraints

- Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`; tree
  `c183a70a07de1cf404720b82303e2f2ff5f80420`.
- Approved original design: `1a54ed0f9b5c1dc9544ce3f15dc015e71e7216f3`.
- Approved original plan: `4639e4c53749a2341baea5340c1f470eefc2538b`.
- Approved deadline-fencing design: `0f214e5488f5d05e18eb882b5b27576c4ba297e4`;
  tree `c73e627514ef35f79eba8845bf5b75cb45144973`.
- Current unaccepted report head: `553450694eb7b33ad6d23580f81ebc11595bd685`; tree
  `0d1706238c80c450336583d1f194c5ff767353fd`.
- Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; remote baseline
  `74ee5f4c7872af1bb612c9068af36319457e087b`; no remote action is authorized.
- The same sole GPT-5.6-luna implementer at reasoning effort `max` owns all product and test tasks.
  GPT-5.6-sol owns this plan, independent complete-diff review, and acceptance.
- Product ownership is exactly
  `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`.
- Test ownership is exactly `tools/stm32-toolkit/tests/test_probe_service.py`.
- The report is corrected only after code/tests in
  `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`.
- Retain exactly one private OBSERVE lifecycle `asyncio.Lock`; add no other lock, shared future,
  provisional field, worker, backend, protocol operation, public method, schema, or persisted state.
- Capture the absolute deadline before lock acquisition. Expiry while queued performs no cache
  access, backend task creation, backend call, recovery, reset, retry, read, or program action.
- Once backend attach entered, the existing `_ATTACH_RECOVERY_SECONDS` cleanup budget and stable
  error precedence remain unchanged and cannot turn an expired request into success.
- CONTROL, MODIFY, flash, public client/protocol, debug logical guards, PyOCD configuration, 100 kHz
  OBSERVE policy, hardware identity, and target restoration remain byte-for-behavior unchanged.
- Preserve prior unaccepted commits and review evidence. Append RED, GREEN, and report-correction
  commits; do not rewrite, squash, delete, or relabel history.
- Use CPython 3.12 with source/test `PYTHONPATH`, `-p no:cacheprovider`, and fresh external run-owned
  basetemps. No hardware, full suite, coverage, packaging, install, release, CI, push, PR mutation,
  merge, tag, close, or remote branch deletion.

---

## File Structure

- `tools/stm32-toolkit/tests/test_probe_service.py` owns deterministic fake-backend event ordering,
  direct service timeout assertions, public client error mapping, recovery-close failure, and
  unchanged compatibility proofs.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py` remains the only owner of request
  admission, the private OBSERVE lifecycle lock, attachment evidence, backend task recovery, and
  service teardown. No new module is created.
- `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md` records the
  complete multi-wave lineage and final returned evidence without containing its own commit SHA.

---

### Task 1: Commit deterministic absolute-deadline RED contracts

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_probe_service.py:276-292`
- Modify: `tools/stm32-toolkit/tests/test_probe_service.py:1320-1396`
- Test: `tools/stm32-toolkit/tests/test_probe_service.py`

**Interfaces:**

- Consumes: `BlockingAttachBackend`, `BlockingRecoveryCloseAttachBackend`,
  `_observe_attach_request(timeout_ms: int, request_id: str) -> ProbeRequest`, `make_service()`,
  `ProbeClient.request()`, and `ProbeBackendError`.
- Produces: deterministic RED contracts for queued expiry, public `PROBE_TIMEOUT`, no late backend
  dispatch, recovery-close failure precedence, lock release, and abandoned-candidate non-reuse.

- [ ] **Step 1: Audit the exact implementation worktree before RED edits**

Run from `C:\tmp\stm32tk-1001-legacy-hardware-impl`:

```powershell
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
git diff --check
```

Expected: a clean branch at this approved plan commit. If any tracked or untracked item exists,
classify its source and stop rather than hiding, deleting, or folding it into this correction.

- [ ] **Step 2: Add a one-shot recovery-close failure fake**

Immediately after `BlockingRecoveryCloseAttachBackend`, add:

```python
class BlockingFailingRecoveryCloseAttachBackend(
    BlockingRecoveryCloseAttachBackend
):
    def __init__(
        self,
        *,
        entered: threading.Event,
        release: threading.Event,
        close_entered: threading.Event,
        close_release: threading.Event,
    ) -> None:
        super().__init__(
            entered=entered,
            release=release,
            close_entered=close_entered,
            close_release=close_release,
        )
        self.fail_next_close = True

    def close(self) -> None:
        self.close_entered.set()
        self.close_release.wait(2)
        if self.fail_next_close:
            self.fail_next_close = False
            self.events.append(("close_failed",))
            raise RuntimeError("recovery close failed")
        super().close()
```

The first recovery close fails without changing product fakes globally. Later cleanup or a fresh
explicit attach can proceed through the same backend instance.

- [ ] **Step 3: Add the direct queued-expiry/no-late-dispatch test**

Add a test whose ordering is controlled by the backend-entered event, not task creation order:

```python
def test_observe_queued_attach_timeout_includes_lifecycle_lock_wait(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        entered = threading.Event()
        release = threading.Event()
        backend = BlockingAttachBackend(entered=entered, release=release)
        service = make_service(
            tmp_path, level=OperationLevel.OBSERVE, backend=backend
        )
        first = asyncio.create_task(
            service._run_backend(
                _observe_attach_request(
                    timeout_ms=30_000, request_id="request-observe-first"
                )
            )
        )
        queued: asyncio.Task[object] | None = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            queued = asyncio.create_task(
                service._run_backend(
                    _observe_attach_request(
                        timeout_ms=20, request_id="request-observe-expired"
                    )
                )
            )
            await asyncio.sleep(0.20)
            assert queued.done()
            with pytest.raises(asyncio.TimeoutError):
                await queued
            assert not release.is_set()
            assert [event for event in backend.events if event[0] == "open_attach"] == [
                ("open_attach", "probe-a", "STM32F429ZITx", False)
            ]

            release.set()
            await first
            await asyncio.sleep(0)
            assert [event for event in backend.events if event[0] == "open_attach"] == [
                ("open_attach", "probe-a", "STM32F429ZITx", False)
            ]
        finally:
            release.set()
            for task in (queued, first):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (queued, first) if task is not None),
                return_exceptions=True,
            )
            pending = tuple(service._backend_tasks)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if not backend.closed and not backend.attach_active:
                backend.close()

    run(scenario())
```

Against the current unaccepted code this must fail at `assert queued.done()` because lock waiting
is outside the timeout. The backend event assertion proves an expired queued request cannot be
revived after the first attach releases the lock.

- [ ] **Step 4: Add the public client error-mapping proof**

Add
`test_observe_queued_attach_timeout_maps_to_public_error(tmp_path: Path) -> None`. Start the real
loopback service with two `ProbeClient` instances. Begin the first client's normal
attach, wait for `backend.entered`, then issue the second client's raw public request:

```python
await second_client.request(
    "probe.attach",
    {"probeId": "probe-a", "target": "STM32F429ZITx"},
    timeout_ms=20,
)
```

After 200 ms while the first attach remains blocked, assert the second task is done and awaiting
it raises:

```python
with pytest.raises(ProbeClientError) as caught:
    await queued
assert caught.value.code == "PROBE_TIMEOUT"
assert caught.value.message == "Probe backend operation timed out"
assert caught.value.details == {}
```

Release and await the first attach, then assert exactly one `open_attach`. In `finally`, release
the backend event, gather both tasks, close both clients, and stop the service. This proves the
existing HTTP/client mapping without changing `ProbeClient.attach()`.

- [ ] **Step 5: Add recovery-close failure, queued expiry, and fresh-request proof**

Add
`test_observe_recovery_close_failure_releases_deadline_fence(tmp_path: Path) -> None`. Use
`BlockingFailingRecoveryCloseAttachBackend`. Start a 20 ms first OBSERVE attach and wait for
backend entry. Sleep 50 ms, release `open_attach`, and wait for `close_entered`. Only then create a
second OBSERVE attach with a 20 ms deadline. While `close_release` is still unset, wait 200 ms and
assert the second task is done with `asyncio.TimeoutError` and no second `open_attach` exists.

Set `close_release`. Assert the first task raises:

```python
with pytest.raises(ProbeBackendError) as caught:
    await first
assert caught.value.code == "PROBE_CLOSE_FAILED"
assert caught.value.message == "Probe attach cleanup failed"
```

Then make one explicit third request with `timeout_ms=30_000`. Assert it succeeds, exactly two
`open_attach` events exist in total, and `("close_failed",)` occurs before the second attach. This
proves abandoned evidence, error precedence, lock release, and no deadlock. The third request is
test-driven explicit caller work, not a product retry.

- [ ] **Step 6: Remove task-order ambiguity from the existing recovery test**

In `test_observe_attach_timeout_or_cancellation_does_not_reuse_candidate_while_recovering`, create
only the initiating operation first. Wait for `backend.entered`, trigger timeout or cancellation,
set the attach release, and wait for `backend.close_entered`. Create the long-deadline queued task
only after that event, assert it remains pending, release close, and retain the existing two-attach
and close-before-second-attach assertions.

This is a test determinism correction only. Do not weaken or delete any existing assertion.

- [ ] **Step 7: Run the exact RED selector**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-deadline-red' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'queued_attach_timeout_includes_lifecycle_lock_wait or queued_attach_timeout_maps_to_public_error or recovery_close_failure_releases_deadline_fence or observe_attach_timeout_or_cancellation_does_not_reuse_candidate' `
  -q
```

Expected: the new queued-expiry tests fail for the demonstrated missing absolute deadline. Existing
recovery cases may pass. If another accepted gate prevents the tests from reaching this exact
branch, stop and report a test-design conflict rather than modifying unrelated behavior.

- [ ] **Step 8: Audit and commit RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- tools/stm32-toolkit/tests/test_probe_service.py
git diff --cached --check
git diff --cached --name-only
git commit -m "test(vs10a): define observe attach absolute deadline"
```

Expected staged path: exactly `tools/stm32-toolkit/tests/test_probe_service.py`. Record the RED
commit/tree and exact intended failures. Inspect and remove only the exact RED basetemp after its
concise evidence is preserved.

---

### Task 2: Enforce one absolute deadline around OBSERVE lifecycle admission

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py:813-820`
- Test: `tools/stm32-toolkit/tests/test_probe_service.py`

**Interfaces:**

- Consumes: `ProbeRequest.timeout_ms`, `asyncio.get_running_loop().time()`,
  `asyncio.timeout_at()`, `_observation_attachment_lock`, and the unchanged
  `_run_backend_inner(request: ProbeRequest) -> object`.
- Produces: one request-local monotonic absolute deadline covering OBSERVE attach lock wait,
  backend execution, candidate commit/abandon, and entered-backend recovery. No new type, field,
  helper, public method, or schema is produced.

- [ ] **Step 1: Wrap only OBSERVE attach with the absolute deadline**

Replace the current OBSERVE branch in `_run_backend()` with:

```python
async def _run_backend(self, request: ProbeRequest) -> object:
    if (
        request.operation == "probe.attach"
        and self._operation_level is OperationLevel.OBSERVE
    ):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + request.timeout_ms / 1000
        async with asyncio.timeout_at(deadline):
            async with self._observation_attachment_lock:
                return await self._run_backend_inner(request)
    return await self._run_backend_inner(request)
```

Do not change `_run_backend_inner()`. The outer deadline starts before lock admission and cancels
the inner operation at the original absolute deadline. If backend attach has entered, the existing
`except (asyncio.TimeoutError, asyncio.CancelledError)` path finishes its bounded recovery while
the lifecycle lock remains held, then the timeout context returns `asyncio.TimeoutError` unless a
stable cleanup error such as `PROBE_CLOSE_FAILED` takes precedence.

External caller cancellation remains `CancelledError`; `asyncio.timeout_at()` converts only its
own deadline cancellation. Expiry during lock acquisition never calls `_run_backend_inner()` and
therefore creates no backend task or recovery action.

- [ ] **Step 2: Run the new targeted GREEN proof**

Repeat Task 1 Step 7 with fresh basetemp
`C:\tmp\stm32tk-1001-observe-deadline-green-targeted`.

Expected: every selected test passes. Confirm the short-deadline queued tasks finish before the
first backend release and the backend event list contains no late attach.

- [ ] **Step 3: Re-run the existing attach-reuse and teardown contracts**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-deadline-green-contracts' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'observe_reuses_one_backend_attachment or observe_rejects_changed_attachment_identity or explicit_second_attach_after_first_failure_is_not_cached or non_observe_repeat_attach or observation_attachment_is_service_local or observe_stop_clears_attachment' `
  -q
```

Expected: all selected reuse, identity, failure, CONTROL/MODIFY, and teardown tests pass unchanged.

- [ ] **Step 4: Run the complete focused matrix**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-deadline-green-full' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q
```

Expected: all collected tests pass. A failure is a diagnosis trigger, not permission to edit
outside the two-file product/test allowlist or run a full suite.

- [ ] **Step 5: Audit and commit the product GREEN**

```powershell
git diff --check
git diff --name-only
git status --short
git add -- tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
git diff --cached --check
git diff --cached --name-only
git commit -m "fix(vs10a): enforce observe attach absolute deadline"
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Expected staged product path: exactly `probe/service.py`; the test path is already committed in
RED. Record the code head/tree. Inspect each exact basetemp, clear read-only attributes or
run-owned junction leaves only inside that root when necessary, and remove the root without
touching source, fixtures, user files, or shared caches.

---

### Task 3: Correct the implementation report and return the final candidate

**Files:**

- Modify:
  `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`

**Interfaces:**

- Consumes: accepted base, original and amended spec/plan commits, all prior RED/GREEN/review
  boundaries, new RED/GREEN commits, exact final code head/tree, focused CPython evidence, cleanup,
  and Git status.
- Produces: one report-only commit returned for independent Sol review; no acceptance claim.

- [ ] **Step 1: Require a clean exact code head**

```powershell
git status --short --branch
git diff --check
git diff --name-status 391c3dd466eafaadbbadce188e1c2b2cba4028ca..HEAD
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

The accepted-base-to-code-head diff may contain only the approved original/amended governance
files, `test_probe_service.py`, and `probe/service.py`. Stop on any unexpected path.

- [ ] **Step 2: Run fresh final CodeHead evidence**

Repeat Task 2 Step 4 with fresh basetemp
`C:\tmp\stm32tk-1001-observe-deadline-final`. Record Python, pytest, PyOCD, UTC start/end,
duration, exact code head/tree, command, collection counts, pass/fail/skip totals, and exit code.

- [ ] **Step 3: Correct the report's complete lineage and semantic claims**

Keep status `RETURNED FOR INDEPENDENT SOL REVIEW`. Record:

- accepted base/tree;
- original spec/plan and amended deadline-fencing spec/plan commits;
- initial RED `eff0b531`, initial GREEN `fb0868d5`, first report `ba5a8b4b`;
- first review stale-cache finding;
- fix RED `7114dd3f`, fix GREEN `32904e71`, second report `55345069`;
- second review queued-timeout/new-lock finding and its direct 20 ms / roughly 80 ms evidence;
- the new absolute-deadline RED and GREEN commits and final code head/tree;
- exact public behavior: queue wait consumes `timeout_ms`; queued expiry performs no cache/backend
  action; entered-backend expiry retains bounded recovery and error precedence;
- exact changed paths, focused test evidence, cleanup state, clean worktree, remote baseline, no
  hardware, and no remote action.

Delete or correct the prior false claim that timeout/recovery semantics did not change. State that
the approved amendment intentionally adds total OBSERVE lifecycle deadline accounting while
preserving public error codes and entered-backend recovery semantics. Do not include the report's
own future SHA or moving ahead/behind totals.

- [ ] **Step 4: Commit only the corrected report and return**

```powershell
git diff --check
git diff --name-only
git add -- docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs(vs10a): report observe attach deadline correction"
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Return the report head/tree, final code head/tree, full TDD lineage, exact commands/results,
cleanup/status evidence, changed paths, and remote state. Do not self-review, self-accept, access
hardware, or perform a remote action.

---

## Sol Independent Review Checkpoint

The GPT-5.6-sol primary creates a new detached clean worktree at the returned report head. It
reviews the complete
`391c3dd466eafaadbbadce188e1c2b2cba4028ca..FINAL_CODE_HEAD` product/test/governance diff, the
latest correction delta, and the report-only commit separately. It repeats the deadline/recovery
selector and the same three-file focused matrix with a fresh Sol-owned external basetemp.

Acceptance requires direct proof that lock queueing consumes the original absolute deadline; an
expired queued request never later reads cache or dispatches backend work; entered-backend timeout,
cancellation, and close failure abandon evidence and release admission without deadlock; same
session reuse and changed-identity rejection remain correct; CONTROL/MODIFY and public surfaces are
unchanged; and the report accurately records every review/fix boundary.

Only Sol issues `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Software acceptance does
not authorize hardware or remote publication. After `ACCEPTED`, stop and request separately
authorized single public read-only bind plus `GPIOE.ODR` read. Do not enter another VS10 slice or
VS10-B automatically.
