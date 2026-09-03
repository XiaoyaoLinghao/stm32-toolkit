# STM32TK-1001 OBSERVE Session Attach Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development`,
> `test-driven-development`, and `verification-before-completion` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every accepted public bind/read logical identity guard while making one authenticated
OBSERVE Probe Service perform exactly one physical backend attachment for its fixed probe and
target.

**Architecture:** `ProbeService` owns one private, in-memory record of the first successfully
validated OBSERVE attachment. Later `probe.attach` requests for the same exact probe selector and
canonical-equivalent target return that immutable evidence without backend dispatch; changed
identity fails closed before hardware. The public client/protocol and all debug bind/read logical
attach calls remain unchanged, while MODIFY and CONTROL retain their current backend dispatch.

**Tech Stack:** CPython 3.12, pytest, asyncio/aiohttp, frozen dataclasses, existing Probe
Service/client/worker, PyOCD 0.45.1, Git.

## Global Constraints

- Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`; tree
  `c183a70a07de1cf404720b82303e2f2ff5f80420`.
- Approved specification commit: `1a54ed0f9b5c1dc9544ce3f15dc015e71e7216f3`;
  specification:
  `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-observe-session-attach-reuse-design.md`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; remote baseline
  `74ee5f4c7872af1bb612c9068af36319457e087b`; no remote action is authorized.
- Exactly one GPT-5.6-luna/max implementation owner makes all product/test/report changes. The
  GPT-5.6-sol primary owns the complete accepted-base review and verdict.
- Product code may change only in
  `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`.
- Tests may change only in `tools/stm32-toolkit/tests/test_probe_service.py`.
- Commit all failing tests before changing product code. Do not remove or weaken an existing
  assertion to make the new behavior pass.
- The first accepted OBSERVE `probe.attach` is the only backend `open_attach()` in that service.
  Later same-identity logical attaches return the original immutable evidence without probe
  enumeration, close, reconnect, halt/resume, reset, read, retry, or program.
- A changed probe selector or non-equivalent target after the first accepted OBSERVE attachment
  returns `PROBE_IDENTITY_MISMATCH` before backend dispatch and does not replace the session.
- A failed or mismatched first physical attachment is never cached. Existing restoration,
  cleanup, timeout, cancellation, and error-precedence behavior remains unchanged.
- MODIFY and CONTROL repeat-attach behavior remains accepted-base compatible.
- Reuse state is private to one Probe Service instance and is discarded during service teardown.
- No CLI, MCP, protocol, client, backend, worker, schema, error inventory, runtime, package, Agent
  adapter, frequency, connection-policy, flash, authorization, or persisted-evidence change.
- No hardware, full suite, coverage, packaging, install, release, CI, push, PR mutation, merge,
  tag, close, or remote branch deletion during implementation or software review.

## File Structure and Frozen Interfaces

### Product ownership

`tools/stm32-toolkit/src/stm32_toolkit/probe/service.py` remains the sole owner of the authenticated
endpoint, lease, operation level, serialized backend, and new OBSERVE attachment record. Add no
new module or public type.

The private field has this exact type and initial value:

```python
self._observation_attachment: tuple[
    str, str, ProbeAttachmentEvidence
] | None = None
```

The tuple values are the exact accepted public probe selector, the `_canonical_target()` value,
and the immutable evidence returned by the first successful backend attach.

Add one private helper with this signature:

```python
def _reused_observation_attachment(
    self, probe_id: str, target: str
) -> ProbeAttachmentEvidence | None:
```

It returns `None` when the service is not OBSERVE or no accepted record exists. For an existing
OBSERVE record, it returns the stored evidence only when `probe_id` is byte-for-byte equal and
`_canonical_target(target)` equals the stored canonical target. Otherwise it raises:

```python
ProbeBackendError(
    "PROBE_IDENTITY_MISMATCH",
    "Connected target identity does not match",
)
```

The existing `probe.attach` response stays `ProbeAttachmentEvidence.to_dict()`. The existing
`ProbeClient.attach(probe_id: str, target: str) -> ProbeAttachmentEvidence` and wire operation
`probe.attach` do not change.

### Test ownership

`tools/stm32-toolkit/tests/test_probe_service.py` proves the physical-dispatch semantics using
the existing live loopback `ProbeService`, real `ProbeClient`, and `FakeProbeBackend.events`.
Tests must assert events at the backend boundary rather than inspecting the new private field.

---

### Task 1: Commit the OBSERVE lifecycle RED contract

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_probe_service.py`

**Interfaces:**

- Consumes: existing `make_service()`, `fake_backend()`, `ProbeClient`, `ProbeClientError`,
  `OperationLevel`, `FakeProbeBackend.events`.
- Produces: direct regression contracts for one physical attach, fail-closed identity changes,
  non-OBSERVE compatibility, failed-first-attach non-caching, and service-local lifetime.

- [ ] **Step 1: Audit the implementation worktree before RED edits**

Run from `C:\tmp\stm32tk-1001-legacy-hardware-impl`:

```powershell
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
git diff --check
```

Expected: clean branch at the approved plan parent; no tracked or untracked item. If any item is
present, classify its source and stop rather than hiding, deleting, or folding it into this slice.

- [ ] **Step 2: Add the failing same-session public-sequence test**

Add one live service/client test with the following behavior and assertions:

```python
def test_observe_reuses_one_backend_attachment_across_logical_guards(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        backend = fake_backend()
        service = make_service(
            tmp_path,
            level=OperationLevel.OBSERVE,
            backend=backend,
        )
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            first = await client.attach("probe-a", "STM32F429ZITx")
            assert await client.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
            second = await client.attach("probe-a", "stm32-f429.zitx")
            assert await client.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
            third = await client.attach("probe-a", "STM32F429ZITx")

            assert first.probe_id == second.probe_id == third.probe_id == "probe-a"
            assert first.resolved_part_number == second.resolved_part_number == third.resolved_part_number
            assert [event for event in backend.events if event[0] == "open_attach"] == [
                ("open_attach", "probe-a", "STM32F429ZITx", False)
            ]
            assert backend.events.count(("list_probes",)) == 1
            assert not any(event[0] in {"close", "halt", "resume", "reset", "flash_elf"} for event in backend.events)
        finally:
            await client.close()
            await service.stop()

    run(scenario())
```

This sequence models initial bind attach, firmware readback, final bind attach, a bounded read, and
a later read guard. Canonical target spelling varies deliberately; the returned evidence remains
the first accepted immutable evidence.

- [ ] **Step 3: Add fail-closed changed-identity tests**

Add a parameterized test for `("probe-b", "STM32F429ZITx")` and
`("probe-a", "STM32F407VGTx")`. After one successful OBSERVE attach, snapshot
`tuple(backend.events)`, call the changed attach, and assert:

```python
with pytest.raises(ProbeClientError) as error:
    await client.attach(changed_probe, changed_target)

assert error.value.code == "PROBE_IDENTITY_MISMATCH"
assert error.value.message == "Connected target identity does not match"
assert error.value.details == {}
assert tuple(backend.events) == accepted_events
assert await client.read_memory(0x20000000, 4) == b"\x01\x02\x03\x04"
```

The event snapshot proves the mismatch does not enumerate, attach, close, halt/resume, read, reset,
or program before returning the error. The final explicit read proves the accepted backend session
was not replaced or closed by the mismatch.

- [ ] **Step 4: Add first-failure and non-OBSERVE compatibility tests**

For first-failure non-caching, wrap `backend.open_attach` with a callable that raises
`ProbeBackendError("PROBE_ATTACH_FAILED", "Debug probe attach failed")` on its first invocation and
delegates to the original method on its second explicit invocation. Assert the first client call
returns the exact stable error with no read event, the second explicit test call reaches the
backend again and succeeds, and the counter equals two. State in the test name that this is a unit
proof of non-caching, not an automatic product retry.

Add a parameterized compatibility test for `OperationLevel.CONTROL` and
`OperationLevel.MODIFY`. Perform two same-identity logical attaches and assert two backend
`open_attach` events with `halt_on_connect=False` for CONTROL and `True` for MODIFY. Do not alter
their existing target-state or authorization contracts.

- [ ] **Step 5: Add the service-lifetime isolation test**

Start and stop one OBSERVE service after two same-identity logical attaches, then start a new
OBSERVE service instance with the same fake backend under a distinct `tmp_path` child. Its first
logical attach must create a second backend `open_attach` event. Assert one physical attach per
service and two in total; do not inspect `_observation_attachment` directly.

- [ ] **Step 6: Run the exact RED proof**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-red' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'observe_reuses_one_backend_attachment or observe_rejects_changed_attachment_identity or explicit_second_attach_after_first_failure_is_not_cached or non_observe_repeat_attach or observation_attachment_is_service_local' `
  -q
```

Expected: the same-session reuse test fails because accepted-base dispatches each logical attach to
the backend; changed-identity tests fail because accepted-base replaces the attachment. Existing
non-OBSERVE and non-caching/lifetime guards may already pass. If an earlier accepted validation
prevents the new tests from reaching the intended service branch, stop and report a test-design
conflict rather than weakening the earlier gate.

Inspect the exact basetemp, preserve the concise RED summary, and remove only
`C:\tmp\stm32tk-1001-observe-attach-reuse-red` after it is no longer needed.

- [ ] **Step 7: Audit and commit RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- tools/stm32-toolkit/tests/test_probe_service.py
git diff --cached --check
git diff --cached --name-only
git commit -m "test(vs10a): define observe session attach reuse"
```

Expected staged path: exactly `tools/stm32-toolkit/tests/test_probe_service.py`. Confirm no product
file changed before the RED commit.

---

### Task 2: Implement service-owned OBSERVE attachment reuse

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py:23`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py:346-407`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py:825-871`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py:1409-1460`
- Test: `tools/stm32-toolkit/tests/test_probe_service.py`

**Interfaces:**

- Consumes: `_canonical_target()`, `OperationLevel.OBSERVE`, `ProbeBackend.open_attach()`,
  `ProbeAttachmentEvidence.to_dict()`, existing serialized `_backend_lock` execution.
- Produces: private `_observation_attachment` state and
  `_reused_observation_attachment(probe_id, target)`; no public interface.

- [ ] **Step 1: Import the existing immutable evidence type**

Change only the existing backend import:

```python
from .backend import ProbeAttachmentEvidence, ProbeBackend, ProbeBackendError
```

Do not add a new model, dataclass, protocol operation, or public export.

- [ ] **Step 2: Initialize and implement the private reuse state**

After the existing backend/task lifecycle fields in `ProbeService.__init__`, initialize:

```python
self._observation_attachment: tuple[
    str, str, ProbeAttachmentEvidence
] | None = None
```

Add the private helper near the existing closed validation helpers:

```python
def _reused_observation_attachment(
    self, probe_id: str, target: str
) -> ProbeAttachmentEvidence | None:
    accepted = self._observation_attachment
    if self._operation_level is not OperationLevel.OBSERVE or accepted is None:
        return None
    accepted_probe, accepted_target, evidence = accepted
    if probe_id != accepted_probe or _canonical_target(target) != accepted_target:
        raise ProbeBackendError(
            "PROBE_IDENTITY_MISMATCH",
            "Connected target identity does not match",
        )
    return evidence
```

This helper performs no backend call and has no exception catch. Existing service error handling
must serialize the stable `ProbeBackendError` unchanged.

- [ ] **Step 3: Make only OBSERVE repeat attach idempotent**

In the existing `request.operation == "probe.attach"` branch:

1. derive `probe_id` and `target` once from request data;
2. call `_reused_observation_attachment(probe_id, target)`;
3. call backend `open_attach()` only when that helper returns `None`;
4. retain the complete existing resolved-target mismatch restoration/close/error block;
5. call `evidence.to_dict()` before storing new state;
6. only after successful backend attach, resolved-target validation, and payload creation, store:

```python
self._observation_attachment = (
    probe_id,
    _canonical_target(target),
    evidence,
)
```

Store only when `self._operation_level is OperationLevel.OBSERVE`. Return the existing payload for
both the first and reused attach. A cached mismatch must occur before backend `open_attach()` and
must not close the accepted session.

Do not change request decoding, backend timeout/recovery, MODIFY mismatch restoration, service
serialization, client parsing, or response schemas.

- [ ] **Step 4: Clear private reuse state during owned teardown**

In `_stop_owned_state()`, clear:

```python
self._observation_attachment = None
```

Do this with the other owned in-memory state before propagating `first_error`, so a backend close
or lease-release error cannot leave reusable state in a stopped service object. Do not reorder
runner cleanup, outstanding backend-task joins, backend close, lease release, or endpoint unlink.

- [ ] **Step 5: Run the targeted GREEN proof**

Run the Task 1 command with a fresh basetemp
`C:\tmp\stm32tk-1001-observe-attach-reuse-green-targeted`. Expected: all selected tests pass.
Inspect and remove only that exact run-owned path.

- [ ] **Step 6: Run the complete focused matrix**

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-green' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q
```

Expected: all three files pass. `test_probe_service.py` proves backend dispatch; unchanged
`test_debug_firmware.py` and `test_debug_read.py` prove every logical attach, provenance guard,
structured error, cancellation, and no-read-after-failed-guard contract remains intact.

A focused failure is only a diagnosis trigger. It does not authorize edits outside the two-file
allowlist or a full suite. Inspect and remove only the exact green basetemp after preserving the
concise result.

- [ ] **Step 7: Audit and commit the product GREEN**

```powershell
git diff --check
git diff --name-only
git status --short
git diff --name-status 391c3dd466eafaadbbadce188e1c2b2cba4028ca..HEAD
git add -- tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
git diff --cached --check
git diff --cached --name-only
git commit -m "fix(vs10a): reuse observe attachment session"
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Expected staged product path: exactly `probe/service.py`. The earlier test path is already committed
in RED. Record the exact code head and tree; no report file exists yet.

---

### Task 3: Return exact code-head evidence and a separate implementation report

**Files:**

- Create:
  `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`

**Interfaces:**

- Consumes: accepted base, approved spec/plan commits, RED/GREEN commits, exact code head/tree,
  focused CPython 3.12 evidence, cleanup and Git state.
- Produces: a report-only commit for independent Sol review; no acceptance claim.

- [ ] **Step 1: Require a clean exact code head**

```powershell
git status --short --branch
git diff --check
git diff --name-status 391c3dd466eafaadbbadce188e1c2b2cba4028ca..HEAD
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

The accepted-base-to-code-head change must contain only the approved specification, plan,
`test_probe_service.py`, and `probe/service.py`. Classify and stop on any unexpected path.

- [ ] **Step 2: Re-run final code-head evidence**

Run the complete three-file command from Task 2 with a new external basetemp:
`C:\tmp\stm32tk-1001-observe-attach-reuse-final`. Record interpreter, pytest and PyOCD versions,
start/end timestamps, command, exact code head/tree, exit code, pass/skip totals, and duration.

Inspect and delete only the resolved final basetemp. If deletion is blocked, classify the exact
residue as ENVIRONMENT and do not broaden cleanup into source, fixtures, shared caches, or user
files.

- [ ] **Step 3: Write the implementation report**

The report must record:

- status `RETURNED FOR INDEPENDENT SOL REVIEW`;
- accepted base/tree and approved spec/plan commits;
- active branch, remote baseline, and no remote action;
- sole Luna/max implementation owner and Sol reviewer ownership;
- exact RED commit and observed intended failures;
- exact GREEN/code commit, code head/tree, and separate report boundary;
- exact two changed product/test paths and unchanged public contracts;
- the one-physical-attach service semantics and fail-closed identity behavior;
- exact CPython 3.12 three-file evidence and run-owned cleanup state;
- no hardware execution and no claim that physical public bind/read now passes;
- remaining gate: independent complete-diff review, followed only by a separately authorized
  single physical public confirmation.

The tracked report must not contain its own future SHA or a moving ahead/behind commit total.

- [ ] **Step 4: Commit only the report and return**

```powershell
git diff --check
git diff --name-only
git add -- docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs(vs10a): report observe session attach reuse"
git status --short --branch
git show -s --format='%H%n%T%n%P%n%s' HEAD
```

Return the report head/tree, code head/tree, exact RED/GREEN lineage, verification totals, cleanup,
changed paths, and remote state. Do not review, push, or access hardware.

---

## Sol Independent Review Checkpoint

The GPT-5.6-sol primary creates a fresh detached clean worktree at the returned report head and
reviews the complete
`391c3dd466eafaadbbadce188e1c2b2cba4028ca..CODE_HEAD` product/test diff plus the report-only delta.
The reviewer repeats only the same three-file focused matrix unless a changed contract supplies a
written expansion trigger. Review must inspect:

- exactly one backend `open_attach()` for all same-identity OBSERVE logical guards;
- exact probe selector and canonical target matching;
- changed identity rejected before backend dispatch and without session replacement;
- first failure never cached and existing restoration/cleanup/error precedence unchanged;
- MODIFY/CONTROL repeat attach unchanged;
- state discarded at service teardown and never persisted or shared;
- unchanged client/protocol/debug logical attach counts and no new public surface;
- no reset, retry, fallback, programming, new worker/backend, or scope expansion;
- accurate RED/GREEN/report lineage and clean run-owned cleanup.

Only Sol issues `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Software acceptance does not
authorize hardware or remote publication. After `ACCEPTED`, stop and request one explicit
authorization for a single public read-only bind plus `GPIOE.ODR` read. If authorized, run exactly
one attempt and stop on failure without retry. Do not enter another slice, VS10-B, release, or any
remote action automatically.
