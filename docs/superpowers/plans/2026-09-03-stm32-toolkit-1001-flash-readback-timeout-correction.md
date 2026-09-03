# STM32TK-1001 Flash Readback Timeout Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make public flash verification forward the existing validated flash transaction timeout to every bounded target readback while preserving the generic five-second observation-read default and all existing fail-closed evidence behavior.

**Architecture:** Add one keyword-only timeout to `ProbeClient.read_memory()` with the accepted 5,000 ms default, then pass `FlashRequest.timeout_ms` through `_verify_segments()` for each existing 65,536-byte-or-smaller read. No public contract, protocol schema, connection profile, retry policy, result schema, service, worker, backend, or binder behavior changes.

**Tech Stack:** CPython `>=3.12,<3.13` (reference evidence CPython 3.12.10), asyncio, aiohttp, pytest, PyOCD-backed Probe Service protocol, pyelftools, Git, Windows PowerShell.

## Global Constraints

- Full accepted base and complete-diff origin: `d462f0ba868ae3cb980544a5a3c746ee7fc996c2` (`ceeb30c228290bad48dacc2372d7978fe4acc113`).
- Approved specification commit: `8e12f2f7e697ecf5a0603411cc7d3f8302bc4014` (`182ea6204c8a2d917bf74691b2c7843769012688`).
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; no push, PR mutation, merge, tag, release, closure, or remote deletion is authorized.
- Specification and final acceptance owner: GPT-5.6-sol primary; implementation and implementation-test owner: exactly one GPT-5.6-luna agent at reasoning effort `max`.
- Product changes are restricted to `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py` and `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.
- Test changes are restricted to `tools/stm32-toolkit/tests/test_probe_client.py`, `tools/stm32-toolkit/tests/test_flash.py`, and only if required by the genuine producer-to-binder seam, `tools/stm32-toolkit/tests/test_debug_firmware.py`.
- The generic `ProbeClient.read_memory()` default remains exactly 5,000 ms; public flash verification forwards the exact validated `FlashRequest.timeout_ms`, whose accepted public default is 30,000 ms.
- The shared private `_verify_segments()` helper preserves its existing two-positional-argument read shape when no flash budget is supplied; debug binding and both handoff paths remain unchanged and continue to obtain the generic 5,000 ms client default.
- Existing readback chunks remain at most 65,536 bytes. Programming remains at most once per invocation. No retry, reconnect, target fallback, reset, resume, or run action is added.
- No public CLI/MCP/schema/configuration/environment option or result field is added. All current `flash-result.json` fields and trust consumers remain byte-compatible.
- No hardware action is authorized. The prior one-attempt authorization is consumed; another physical attempt requires new explicit authorization after independent software acceptance.
- Use candidate source/test `PYTHONPATH`, pytest `-p no:cacheprovider`, and a fresh repository-external run-owned basetemp. Preserve minimum failure evidence and clean only verified run-owned disposable output.

---

## Ownership Ledger and Execution Environment

Before editing, the Luna/max implementer records these facts in its return message:

```text
module / phase: STM32TK-1001 / VS10-A H2 flash readback timeout correction
full accepted base: d462f0ba868ae3cb980544a5a3c746ee7fc996c2
specification owner / reviewer: GPT-5.6-sol primary
implementation owner: one GPT-5.6-luna/max agent
active branch: codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl
remote action: none authorized
hardware action: none authorized
bounded override: none
```

From the exact implementation worktree, initialize a fresh external verification root without deleting or reusing an existing directory:

```powershell
$repoRoot = (git rev-parse --show-toplevel).Trim()
$runRoot = 'C:\tmp\stm32tk-1001-flash-readback-timeout-luna-20260903'
if (Test-Path -LiteralPath $runRoot) { throw "Run root already exists: $runRoot" }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$python312 = (Get-Command python -ErrorAction Stop).Source
& $python312 -c "import sys; assert sys.implementation.name == 'cpython'; assert sys.version_info[:2] == (3, 12); print(sys.version)"
$env:PYTHONPATH = (Join-Path $repoRoot 'tools\stm32-toolkit\src') + [IO.Path]::PathSeparator + (Join-Path $repoRoot 'tools\stm32-toolkit\tests')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $runRoot 'pycache'
git status --short --branch
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-list --left-right --count 'origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl...HEAD'
```

Expected before Task 1: HEAD is the committed implementation plan, the worktree is clean, and the tracking reference is behind only by the known local commits. Do not fetch, push, or edit the old user workspace. If any uncommitted or untracked file is present, stop and report its exact path and origin before editing.

### File responsibility map

- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`: owns the generic request encoding and the backward-compatible explicit read deadline seam.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`: owns the validated flash budget and exact segment-readback lifecycle.
- `tools/stm32-toolkit/tests/test_probe_client.py`: proves the generic five-second default and explicit timeout forwarding without changing operation level or payload.
- `tools/stm32-toolkit/tests/test_flash.py`: proves public 30-second propagation, exact 51,852-byte readback, per-chunk forwarding, no retry, mismatch closure, and unchanged success evidence.
- `tools/stm32-toolkit/tests/test_debug_firmware.py`: existing genuine producer-to-binder and missing-result trust tests; edit only if the imported flash fake cannot accept the new keyword-only seam.
- `docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md`: records exact RED/GREEN lineage, CodeHead, owned evidence, boundaries, and deferred physical acceptance in a separate report commit.

---

### Task 1: Commit the complete RED contract without product changes

**Files:**
- Modify: `tools/stm32-toolkit/tests/test_probe_client.py:64-104`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:154-199`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:315-365`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:563-578`
- Optional modify only if collection requires it: `tools/stm32-toolkit/tests/test_debug_firmware.py:99-142`

**Interfaces:**
- Consumes: current `ProbeClient.request(operation, data, *, operation_level=OBSERVE, timeout_ms=5000)` and current `FlashRequest.timeout_ms: int = 30_000`.
- Produces: frozen test oracle for `ProbeClient.read_memory(address, length, *, timeout_ms=5_000) -> bytes` and flash readback timeout propagation; no product implementation in this task.

- [ ] **Step 1: Add the client compatibility and explicit-timeout test.**

Add a focused test beside `test_program_verified_elf_forces_modify_and_validates_telemetry`. Use a real `ProbeClient`, replace only its `request` method, and assert both the default and explicit calls exactly:

```python
def test_read_memory_preserves_default_and_forwards_explicit_timeout(monkeypatch):
    endpoint = ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version=__version__,
        host="127.0.0.1",
        port=43123,
        token="11" * 32,
        workspace_id="workspace-a",
        session_id="session-a",
        lease_id="lease-a",
    )
    client = ProbeClient(endpoint)
    calls = []

    async def request(
        operation,
        data,
        *,
        operation_level=OperationLevel.OBSERVE,
        timeout_ms=5_000,
    ):
        calls.append((operation, data, operation_level, timeout_ms))
        return {"bytes": "aabb"}

    monkeypatch.setattr(client, "request", request)

    import asyncio

    assert asyncio.run(client.read_memory(0x20000000, 2)) == b"\xaa\xbb"
    assert (
        asyncio.run(client.read_memory(0x20000002, 2, timeout_ms=30_000))
        == b"\xaa\xbb"
    )
    assert calls == [
        ("memory.read", {"address": 0x20000000, "length": 2}, OperationLevel.OBSERVE, 5_000),
        ("memory.read", {"address": 0x20000002, "length": 2}, OperationLevel.OBSERVE, 30_000),
    ]
```

Do not relax payload decoding or add timeout validation here; the existing protocol request decoder remains authoritative.

- [ ] **Step 2: Extend the flash fake without rewriting existing event assertions.**

In `RecordingFlashClient`, add a separate timeout list and accept the planned keyword while preserving the existing three-field `("read", address, length)` event:

```python
self.read_timeouts: list[int] = []

async def read_memory(
    self,
    address: int,
    length: int,
    *,
    timeout_ms: int = 5_000,
) -> bytes:
    self.events.append(("read", address, length))
    self.read_timeouts.append(timeout_ms)
    offset = address - 0x08000000
    return self.image[offset : offset + length]
```

Do not change `BindingClient.read_memory()` in `test_debug_firmware.py`; that is an unrelated observation consumer and must retain the accepted two-positional-argument seam.

- [ ] **Step 3: Freeze the exact accepted-size and success-evidence oracle.**

Update `test_flash_programs_exact_elf_reads_back_segments_and_commits_result` to assert:

```python
assert client.read_timeouts == [30_000]
```

Add this independent 51,852-byte regression using the real ELF fixture and default public flash budget:

```python
def test_flash_default_timeout_covers_exact_accepted_segment_without_splitting(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    text_size = 51_788
    identity = _publish_current_debug_build(root, text_size=text_size)
    image = _elf_with_flash_segment(text_size=text_size)[84 : 84 + 51_852]
    assert len(image) == 51_852
    client = RecordingFlashClient(image)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is True, result.to_dict()
    assert sum(event[0] == "program" for event in client.events) == 1
    assert [event for event in client.events if event[0] == "read"] == [
        ("read", 0x08000000, 51_852)
    ]
    assert client.read_timeouts == [30_000]
    document = json.loads(
        (root / "artifacts" / "migration" / "flash-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(document) == _FLASH_FIELDS
    assert document["verifiedBytes"] == 51_852
```

The explicit length and one-read assertion ensure the regression cannot pass by silently splitting, skipping, or truncating the physical evidence shape that triggered the defect.

- [ ] **Step 4: Freeze per-chunk exact propagation.**

Change only the request and assertions in `test_flash_readback_is_chunked_to_protocol_limit`:

```python
result = asyncio.run(
    flash_firmware(_request(root, identity, timeout_ms=12_345), client)
)

assert result.ok is True
assert reads == [
    ("read", 0x08000000, 65_536),
    ("read", 0x08010000, 4_528),
]
assert client.read_timeouts == [12_345, 12_345]
```

This proves the exact request value reaches every existing bounded chunk; do not change `_READ_CHUNK` or the fixture size.

- [ ] **Step 5: Freeze timeout failure as one program, one read, zero retry, zero result.**

Add a structured timeout test beside the mismatch test:

```python
def test_flash_readback_timeout_never_retries_or_commits_success(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    result_path = root / "artifacts" / "migration" / "flash-result.json"
    result_path.write_text('{"status":"success"}\n', encoding="utf-8")

    class TimingOutReadClient(RecordingFlashClient):
        async def read_memory(
            self,
            address: int,
            length: int,
            *,
            timeout_ms: int = 5_000,
        ) -> bytes:
            self.events.append(("read", address, length))
            self.read_timeouts.append(timeout_ms)
            raise ProbeClientError("PROBE_TIMEOUT", "Probe backend operation timed out")

    client = TimingOutReadClient(_elf_with_flash_segment()[84 : 84 + 320])
    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "PROBE_TIMEOUT"
    assert [event[0] for event in client.events] == ["attach", "program", "read"]
    assert sum(event[0] == "program" for event in client.events) == 1
    assert sum(event[0] == "read" for event in client.events) == 1
    assert client.read_timeouts == [30_000]
    assert not result_path.exists()
```

Also strengthen the existing mismatch test with `assert sum(event[0] == "program" for event in client.events) == 1`; retain its exact `FLASH_VERIFY_FAILED` and no-result assertions.

- [ ] **Step 6: Run the exact RED nodes.**

```powershell
& $python312 -m pytest `
  tools/stm32-toolkit/tests/test_probe_client.py::test_read_memory_preserves_default_and_forwards_explicit_timeout `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_programs_exact_elf_reads_back_segments_and_commits_result `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_default_timeout_covers_exact_accepted_segment_without_splitting `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_is_chunked_to_protocol_limit `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_timeout_never_retries_or_commits_success `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_mismatch_never_retains_success_evidence `
  -q -p no:cacheprovider --basetemp (Join-Path $runRoot 'red')
```

Expected RED: the explicit `ProbeClient.read_memory(..., timeout_ms=...)` call fails because the keyword is absent, and the flash propagation assertions observe 5,000 ms instead of the requested 30,000/12,345 ms. Existing success, mismatch, program-count, chunk-size, and evidence assertions must otherwise remain meaningful. If RED fails because of fixture setup, unrelated product behavior, or an existing blocker that prevents these assertions from executing, stop and report the test-design conflict; do not delete assertions or change unrelated product behavior.

- [ ] **Step 7: Audit and commit RED tests only.**

```powershell
git diff --check
git diff --name-only
git diff -- tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_debug_firmware.py
git status --short
git add -- tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_flash.py
git commit -m "test(vs10a): expose flash readback timeout gap"
```

If `test_debug_firmware.py` was unavoidably changed only for the imported producer seam, include it explicitly in `git add`; otherwise it must remain byte-identical. Record the RED commit SHA, tree, exact failing nodes, and observed failure text.

---

### Task 2: Implement the minimal timeout propagation and make the focused contract GREEN

**Plan correction after blocked GREEN attempt:** The first Task 2 candidate at test head
`966d1aaf4ca1ea5dae962be3648bc3d941d25fee` made `_verify_segments(..., timeout_ms)` required.
The six target nodes passed, but the required focused binder control reproducibly returned
`DEBUG_READBACK_MISMATCH` because unchanged `debug/firmware.py` calls the shared private helper
with its accepted two positional arguments. Read-only call-site tracing found two additional
unchanged consumers in `probe/handoff.py`. The implementer reverted the candidate and created no
product commit. The corrected private interface below preserves the original call shape when no
flash budget exists and forwards an explicit budget only for `flash_firmware()`. This is a
compatibility correction within the approved specification, not a new public design or scope
expansion.

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py:440-450`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:527-539`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:579-588`
- Test: committed Task 1 tests only; do not add or weaken tests in this task unless a genuine product-contract omission is first reported to Sol.

**Interfaces:**
- Consumes: `FlashRequest.timeout_ms`, already validated by `_validate_request()` to `1..30_000`, and `ProbeClient.request(..., timeout_ms=...)`.
- Produces: `ProbeClient.read_memory(address: int, length: int, *, timeout_ms: int = 5_000) -> bytes` and `_verify_segments(client, segments, *, timeout_ms: int | None = None) -> int`. `None` means preserve the accepted two-positional-argument read call for existing debug/handoff consumers; flash always supplies its validated integer.

- [ ] **Step 1: Add the backward-compatible client seam.**

Replace only the current `read_memory` method with:

```python
async def read_memory(
    self,
    address: int,
    length: int,
    *,
    timeout_ms: int = 5_000,
) -> bytes:
    data = await self.request(
        "memory.read",
        {"address": address, "length": length},
        timeout_ms=timeout_ms,
    )
    encoded = data.get("bytes")
    try:
        if not isinstance(encoded, str):
            raise ValueError
        return bytes.fromhex(encoded)
    except ValueError as error:
        raise ProbeClientError(
            "PROBE_RESPONSE_INVALID", "Probe Service response is invalid"
        ) from error
```

Do not change `request()` defaults, operation level, response decoding, HTTP timeout, or any other client method.

- [ ] **Step 2: Thread the already validated flash budget through the existing chunks.**

Change `_verify_segments` to accept a keyword-only optional flash deadline. Preserve the accepted call shape for existing debug and handoff consumers, and forward the deadline only when flash supplies it:

```python
async def _verify_segments(
    client: object,
    segments: tuple[FlashSegment, ...],
    *,
    timeout_ms: int | None = None,
) -> int:
    verified = 0
    for segment in segments:
        offset = 0
        while offset < len(segment.data):
            length = min(_READ_CHUNK, len(segment.data) - offset)
            if timeout_ms is None:
                actual = await client.read_memory(segment.address + offset, length)
            else:
                actual = await client.read_memory(
                    segment.address + offset,
                    length,
                    timeout_ms=timeout_ms,
                )
            expected = segment.data[offset : offset + length]
            if type(actual) is not bytes or actual != expected:
                raise _fail(
                    "FLASH_VERIFY_FAILED",
                    "Programmed firmware readback did not match",
                    address=segment.address + offset,
                    length=length,
                )
            verified += length
            offset += length
    return verified
```

Then change the sole production caller to:

```python
verified = await _verify_segments(
    client,
    firmware.segments,
    timeout_ms=typed.timeout_ms,
)
```

Do not add a constant, recovery branch, retry loop, smaller chunk, public field, or alternate readback path. Do not edit `debug/firmware.py` or `probe/handoff.py`: their unchanged calls intentionally exercise the `None` compatibility branch.

- [ ] **Step 3: Re-run the exact RED command and require GREEN.**

Repeat Task 1 Step 6 exactly with a fresh basetemp path `(Join-Path $runRoot 'green-target')`.

Expected: all six nodes PASS; the default read remains 5,000 ms, the accepted segment gets one 30,000 ms read, both chunked reads get exactly 12,345 ms, timeout performs one program and no retry, mismatch remains fail-closed, and the success document retains exact `_FLASH_FIELDS`.

- [ ] **Step 4: Run the proportionate affected regression matrix.**

```powershell
& $python312 -m pytest `
  tools/stm32-toolkit/tests/test_probe_client.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py::test_genuine_flash_result_is_consumed_by_binding_without_a_second_trust_schema `
  tools/stm32-toolkit/tests/test_debug_firmware.py::test_missing_or_invalid_firmware_and_flash_evidence_are_stable `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_persists_paused_stops_releases_then_marks_external `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_drains_modifications_before_final_target_readback `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_end_reacquires_revalidates_and_consumes_one_time_ticket `
  -q -p no:cacheprovider --basetemp (Join-Path $runRoot 'green-focused')
```

Expected: PASS on CPython 3.12. The three handoff nodes are the bounded risk-triggered expansion after the first GREEN candidate proved that `_verify_segments()` has three unchanged non-flash production callers. They prove begin ordering, final readback, and reacquisition remain compatible without widening product scope. This is the complete planned slice matrix. Do not run the prior seven-file recovery suite, full suite, coverage, package, release, CLI/MCP, Monitor, or hardware matrix unless a concrete failure proves a new affected dependency; classify such a failure before expanding verification.

- [ ] **Step 5: Audit the complete allowed product delta and commit GREEN.**

```powershell
git diff --check
git diff --name-only HEAD~1
git diff -- tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git status --short
```

Expected uncommitted product paths: exactly the two allowed source files. Tests must already be committed in RED. If any other product path changed, stop without committing.

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git commit -m "fix(vs10a): propagate flash readback timeout"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Record this commit as CodeHead only after the focused matrix has passed against these exact bytes.

---

### Task 3: Reconcile evidence, clean run-owned output, and commit the report separately

**Plan correction after report review:** Repository `AGENTS.md` prohibits moving commit totals in
the tracked implementation report. The original Task 3 wording incorrectly required local
ahead/behind counts inside that durable file. The tracked report records only clean-worktree and
no-remote-mutation facts; the implementer's return message may report the current ahead/behind
snapshot out of band. This correction changes no product, test, or evidence result.

**Files:**
- Create: `docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md`
- Do not modify product or tests in this task.

**Interfaces:**
- Consumes: exact Task 1 RED commit, Task 2 CodeHead/tree, focused test output, and Git scope evidence.
- Produces: a tracked implementation report that names the code head before the report commit and does not claim physical acceptance.

- [ ] **Step 1: Inspect and clean only the exact Luna-owned verification root.**

First list the exact root and confirm it equals the literal path created in the execution-environment block:

```powershell
$resolvedRunRoot = [IO.Path]::GetFullPath($runRoot)
if ($resolvedRunRoot -ne [IO.Path]::GetFullPath('C:\tmp\stm32tk-1001-flash-readback-timeout-luna-20260903')) { throw 'Unexpected run root' }
Get-ChildItem -LiteralPath $resolvedRunRoot -Force
```

Preserve the minimum failing RED output in the report as concise text, not as a repository artifact. Once GREEN evidence is recorded and no diagnostic file is needed, remove only this exact run-owned root:

```powershell
Remove-Item -LiteralPath $resolvedRunRoot -Recurse -Force
if (Test-Path -LiteralPath $resolvedRunRoot) { throw 'Run-owned cleanup failed' }
```

If cleanup fails, classify the exact residual as ENVIRONMENT and report it; do not touch a parent directory, shared cache, source fixture, or user-owned file.

- [ ] **Step 2: Write the implementation report with exact lineage and boundaries.**

Before writing, capture the immutable lineage values directly from Git:

```powershell
$planCommit = (git log -1 --format='%H' -- docs/superpowers/plans/2026-09-03-stm32-toolkit-1001-flash-readback-timeout-correction.md).Trim()
$planTree = (git show -s --format='%T' $planCommit).Trim()
$redCommit = (git log -1 --format='%H' --grep='^test(vs10a): expose flash readback timeout gap$').Trim()
$redTree = (git show -s --format='%T' $redCommit).Trim()
$codeHead = (git rev-parse HEAD).Trim()
$codeTree = (git rev-parse 'HEAD^{tree}').Trim()
```

Create the report with these sections and write the captured literal values, not variable names or placeholders:

```markdown
# STM32TK-1001 Flash Readback Timeout Correction Implementation Report

- Full accepted base: `d462f0ba868ae3cb980544a5a3c746ee7fc996c2`
- Approved specification: `8e12f2f7e697ecf5a0603411cc7d3f8302bc4014`
- Frozen implementation plan: the literal `$planCommit` and `$planTree` values captured above
- RED commit: the literal `$redCommit` and `$redTree` values captured above
- CodeHead: the literal `$codeHead` and `$codeTree` values captured above
- Implementer/evidence owner: one GPT-5.6-luna agent, reasoning effort `max`
- Independent reviewer: GPT-5.6-sol primary, pending
- Hardware: not run; new explicit authorization required after software acceptance
- Remote actions: none

## Implemented behavior

State the exact default 5,000 ms client behavior, explicit keyword forwarding, exact `FlashRequest.timeout_ms` propagation to every existing flash chunk, unchanged two-positional-argument helper behavior for debug/handoff, unchanged 65,536-byte bound, one-program/no-retry behavior, unchanged result schema, and unchanged binder/handoff trust paths.

## TDD lineage

List the exact RED command and observed missing-keyword/5,000-ms failures before product code, then the exact GREEN command and complete focused matrix result at CodeHead. Do not collapse or omit the RED and GREEN commit boundaries.

## Changed paths and scope audit

List every path changed after the approved plan and classify it as RED test, GREEN product, or report. State that CLI, MCP, schema, service, worker, backend, connection profiles, result consumers, runtime, dependencies, packaging, README, Skills, and Monitor remained unchanged.

## Deferred external evidence

Record that the earlier physical attempt entered programming and timed out during unpropagated readback; target contents remain unknown. This software report does not reuse that authorization or claim a physical PASS. A new one-attempt public recovery flash is deferred to the user-authorized hardware phase after Sol acceptance.

## Cleanup and status

Record the exact run-owned path, cleanup outcome, final clean-worktree status, and that no remote state changed. Do not write branch-relative ahead/behind counts into the tracked report; report the current snapshot only in the out-of-band return message.
```

The report must not contain its own future report commit SHA, a moving commit total, fabricated hardware evidence, or evidence attributed to Sol.

- [ ] **Step 3: Run final pre-report checks and commit only the report.**

```powershell
git diff --check
git diff --name-only
git status --short
```

Expected uncommitted path: only `docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md`.

```powershell
git add -- docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md
git commit -m "docs(vs10a): report flash readback timeout correction"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git status --short --branch
git rev-list --left-right --count 'origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl...HEAD'
```

Expected: clean implementation worktree and no remote mutation. Return the plan, RED, CodeHead, and report SHAs; exact test counts; exact changed paths; cleanup status; and any classified residual. Do not approve the diff and do not run hardware.

---

## Sol Independent Review Gate

After the Luna/max return, the Sol primary must create a fresh detached clean worktree at the report commit and independently:

1. confirm HEAD/report SHA/tree and clean detached status;
2. inspect the complete `d462f0ba868ae3cb980544a5a3c746ee7fc996c2..CodeHead` product/test diff plus the separate report commit;
3. verify only the allowed source/test/report paths changed after this plan;
4. run `git diff --check d462f0ba868ae3cb980544a5a3c746ee7fc996c2..HEAD`;
5. re-run the same complete focused matrix from Task 2 Step 4 under CPython 3.12 with a fresh Sol-owned external basetemp;
6. verify exact 5,000-ms compatibility, exact 30,000/custom flash propagation, unchanged two-positional-argument debug/handoff reads, 51,852-byte one-read proof, 65,536-byte chunk bound, one-program/no-retry timeout closure, exact success schema, genuine binder consumption, and the three bounded handoff controls;
7. clean only the verified Sol-owned basetemp and classify any residue;
8. issue `ACCEPTED`, `ACCEPTED_WITH_FIXES`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` without mutating remote state.

Hardware remains stopped after software acceptance. A new physical recovery attempt can occur only after the user separately authorizes that exact action.
