# STM32TK-1001 Memory Read Envelope Limit Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the declared legacy `memory.read` maximum truthfully represent the largest raw payload that the existing hexadecimal response and canonical JSON safety boundary can transport, then make flash and shared observation grouping consume that one limit.

**Architecture:** Tighten the byte-identical Probe protocol schemas and `MAX_READ_BYTES` from 65,536 to 32,768 raw bytes, then replace flash's parallel numeric chunk constant with the protocol authority. Preserve protocol v2, lowercase-hex responses, the 64 KiB canonical string limit, all timeouts, complete byte comparison, and all public CLI/MCP/Agent adapter shapes.

**Tech Stack:** CPython `>=3.12,<3.13` (reference CPython 3.12.10), asyncio, aiohttp, jsonschema, pytest, Probe Service protocol v2, PyOCD-backed worker/backend, Git, Windows PowerShell.

## Global Constraints

- Full accepted base and complete-diff origin: `4e6719e9447f69e3fffbe7842f4156df71464955` (`641f5677c60d9942af83b2b87e132f1ab29b8d7d`).
- Approved specification: `e8c3c31fb13275699fdb20ff0b4e989efffc5ee7` (`b3e367f54c2a5e53c7d0b694817a1f6854279e50`).
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; no push, PR mutation, merge, tag, release, closure, or remote deletion is authorized.
- Specification, plan, architecture, and final acceptance owner: GPT-5.6-sol primary. Product and implementation-test owner: exactly one GPT-5.6-luna agent at reasoning effort `max` for all tasks in this plan.
- Product changes are restricted to the two Probe protocol schema copies, `probe/protocol.py`, and `probe/flash.py` named below.
- Test changes are restricted to `test_probe_protocol.py`, `test_probe_service.py`, and `test_flash.py`.
- Legacy `memory.read` accepts `1..32768` raw bytes. Length 32,769 is rejected before backend dispatch with `PROBE_REQUEST_INVALID` and `{"field":"data.length","rule":"maximum"}`.
- `ProbeClient.read_memory()` signature, lowercase-hex response, default 5,000-ms observation timeout, protocol v2, Toolkit 0.9.0, and the canonical 65,536-byte per-string Evidence limit remain unchanged.
- Flash uses the protocol `MAX_READ_BYTES` as its sole chunk authority. The accepted 51,852-byte segment becomes 32,768 plus 19,084 bytes; the 70,064-byte fixture becomes 32,768 plus 32,768 plus 4,528 bytes.
- Programming remains at most once per invocation. Every read receives the exact already-validated flash timeout. No retry, reconnect, reset, resume, target fallback, or alternate evidence path is added.
- Root and packaged Probe protocol schemas remain byte-identical.
- CLI, MCP, Monitor, service dispatch, worker, backend, debug/read/sampling product files, runtime, dependencies, README, Skills, and Agent adapters remain byte-identical.
- No hardware action is authorized. The trigger attempt consumed its one-attempt authorization; another physical attempt requires new explicit authorization after independent software acceptance.
- Use candidate source/test `PYTHONPATH`, pytest `-p no:cacheprovider`, and fresh repository-external run-owned basetemps. Preserve minimum failure evidence and clean only exact verified run-owned disposable output.

---

## Ownership Ledger and Execution Environment

Before editing, the Luna/max implementer records:

```text
module / phase: STM32TK-1001 / VS10-A H2 memory-read envelope correction
full accepted base: 4e6719e9447f69e3fffbe7842f4156df71464955
approved specification: e8c3c31fb13275699fdb20ff0b4e989efffc5ee7
specification owner / reviewer: GPT-5.6-sol primary
implementation owner: one GPT-5.6-luna/max agent
active branch: codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl
remote action: none authorized
hardware action: none authorized
bounded override: none
```

Initialize one fresh external root. Do not delete or reuse an existing path:

```powershell
$repoRoot = (git rev-parse --show-toplevel).Trim()
$runRoot = 'C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903'
if (Test-Path -LiteralPath $runRoot) { throw "Run root already exists: $runRoot" }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$python312 = 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe'
& $python312 -c "import sys; assert sys.implementation.name == 'cpython'; assert sys.version_info[:2] == (3, 12); print(sys.version)"
$env:PYTHONPATH = (Join-Path $repoRoot 'tools\stm32-toolkit\src') + [IO.Path]::PathSeparator + (Join-Path $repoRoot 'tools\stm32-toolkit\tests') + [IO.Path]::PathSeparator + 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $runRoot 'pycache'
git status --short --branch
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Expected before Task 1: HEAD is this committed plan, the tracked/untracked worktree is clean, and no remote state has changed. If any path is present, stop and report its exact origin.

### File responsibility map

- `schemas/probe-protocol.schema.json`: repository-root Probe request authority distributed outside the Python package.
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`: packaged byte-identical request authority loaded by `decode_request()`.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py`: typed Python maximum consumed by debug read, sampling, tests, and flash after this correction.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`: complete ELF-segment readback loop; it consumes but does not redefine the protocol maximum.
- `tools/stm32-toolkit/tests/test_probe_protocol.py`: exact schema/constant boundary and stable request failure semantics.
- `tools/stm32-toolkit/tests/test_probe_service.py`: real Probe Service → HTTP → canonical JSON → ProbeClient maximum-payload proof and pre-backend rejection proof.
- `tools/stm32-toolkit/tests/test_flash.py`: accepted-segment and larger-segment chunk ordering, timeout propagation, one-program/no-retry, mismatch, and unchanged success evidence.
- `docs/codex/returns/STM32TK-1001-MEMORY-READ-ENVELOPE-LIMIT-CORRECTION/implementation-report.md`: separate report commit with exact RED/GREEN lineage and no physical-pass claim.

---

### Task 1: Commit the complete RED contract without product changes

**Files:**
- Modify: `tools/stm32-toolkit/tests/test_probe_protocol.py:48-70`
- Modify: `tools/stm32-toolkit/tests/test_probe_service.py:980-1015`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:350-450`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:660-690`

**Interfaces:**
- Consumes: current `MAX_READ_BYTES = 65_536`, both schemas with `memory.read.data.length.maximum = 65536`, real `ProbeService`, real `ProbeClient`, and `_verify_segments()` with the current private 65,536-byte flash chunk.
- Produces: committed failing contract for exact 32,768/32,769 protocol behavior and safe flash chunking; no product implementation in this task.

- [ ] **Step 1: Freeze the schema and typed protocol boundary.**

Add this helper and test after the byte-identity test in `test_probe_protocol.py`:

```python
def _memory_read_schema(schema: dict[str, object]) -> dict[str, object]:
    clauses = schema["allOf"]
    assert isinstance(clauses, list)
    matches = [
        clause
        for clause in clauses
        if clause.get("if", {}).get("properties", {}).get("operation", {}).get("const")
        == "memory.read"
    ]
    assert len(matches) == 1
    return matches[0]


def test_memory_read_limit_matches_the_hex_response_envelope() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (repo_root / "schemas" / "probe-protocol.schema.json").read_text(
            encoding="utf-8"
        )
    )
    length = _memory_read_schema(schema)["then"]["properties"]["data"][
        "properties"
    ]["length"]

    assert MAX_READ_BYTES == 32_768
    assert length == {"type": "integer", "minimum": 1, "maximum": 32_768}

    accepted = valid_request_dict()
    accepted["data"] = {"address": 0x20000000, "length": 32_768}
    decoded = decode_request(json.dumps(accepted).encode("utf-8"), TOOLKIT_VERSION)
    assert decoded.data == {"address": 0x20000000, "length": 32_768}

    rejected = valid_request_dict()
    rejected["data"] = {"address": 0x20000000, "length": 32_769}
    with pytest.raises(ProbeProtocolError) as error:
        decode_request(json.dumps(rejected).encode("utf-8"), TOOLKIT_VERSION)
    assert error.value.code == "PROBE_REQUEST_INVALID"
    assert error.value.details == {"field": "data.length", "rule": "maximum"}
```

Do not remove the existing root/package byte-identity test or generic invalid-boundary parameterization.

- [ ] **Step 2: Add a real maximum response round-trip.**

Add beside `test_client_lists_attaches_and_reads_without_halting` in `test_probe_service.py`:

```python
def test_maximum_memory_read_round_trips_through_service_and_client(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        expected = bytes(index % 251 for index in range(32_768))
        backend = FakeProbeBackend(
            probes=(ProbeDescriptor("probe-a", "vendor", "product", None),),
            memory={0x20000000: expected},
            registers={},
        )
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            await client.attach("probe-a", "STM32F429ZITx")
            actual = await client.read_memory(
                0x20000000, 32_768, timeout_ms=30_000
            )
            assert actual == expected
            assert backend.events.count(("read_memory", 0x20000000, 32_768)) == 1
        finally:
            await client.close()
            await service.stop()

    run(scenario())
```

This test must use the real service and client. Do not replace `ProbeClient.request`, `_send`, or `_decode_response`.

- [ ] **Step 3: Prove 32,769 is rejected before backend invocation.**

Add a second service test:

```python
def test_oversized_memory_read_is_rejected_before_backend_dispatch(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        backend = fake_backend()
        attempts: list[tuple[int, int]] = []
        original = backend.read_memory

        def observed(address: int, length: int) -> bytes:
            attempts.append((address, length))
            return original(address, length)

        backend.read_memory = observed  # type: ignore[method-assign]
        service = make_service(tmp_path, backend=backend)
        endpoint = await service.start()
        client = ProbeClient(endpoint)
        try:
            with pytest.raises(ProbeClientError) as error:
                await client.read_memory(0x20000000, 32_769)
            assert error.value.code == "PROBE_REQUEST_INVALID"
            assert error.value.details == {
                "field": "data.length",
                "rule": "maximum",
            }
            assert attempts == []
        finally:
            await client.close()
            await service.stop()

    run(scenario())
```

The absence of backend attempts is mandatory. Do not accept `PROBE_NOT_ATTACHED`, `PROBE_READ_UNAVAILABLE`, or `EVIDENCE_LIMIT_EXCEEDED` as equivalent.

- [ ] **Step 4: Replace the old accepted-segment one-read oracle with safe exact chunks.**

Rename `test_flash_default_timeout_covers_exact_accepted_segment_without_splitting` to `test_flash_default_timeout_covers_exact_accepted_segment_in_protocol_chunks` and replace only its read assertions with:

```python
assert [event for event in client.events if event[0] == "read"] == [
    ("read", 0x08000000, 32_768),
    ("read", 0x08008000, 19_084),
]
assert client.read_timeouts == [30_000, 30_000]
```

Retain exact 51,852-byte fixture length, exactly one program call, exact result field set, and `verifiedBytes == 51_852`.

Update `test_flash_final_byte_mismatch_in_exact_accepted_segment_never_commits_success` to assert the same two reads and two 30,000-ms timeouts. Retain final-byte mutation, `FLASH_VERIFY_FAILED`, exactly one program, and no result file.

- [ ] **Step 5: Freeze the larger three-chunk sequence.**

In `test_flash_readback_is_chunked_to_protocol_limit`, require:

```python
assert [event[0] for event in client.events] == [
    "attach",
    "program",
    "read",
    "read",
    "read",
]
assert [event for event in client.events if event[0] == "read"] == [
    ("read", 0x08000000, 32_768),
    ("read", 0x08008000, 32_768),
    ("read", 0x08010000, 4_528),
]
assert client.read_timeouts == [12_345, 12_345, 12_345]
assert sum(event[0] == "program" for event in client.events) == 1
```

Do not change the 70,064-byte fixture, address origin, or custom timeout.

- [ ] **Step 6: Add a second-chunk timeout closure test.**

Add beside the existing timeout test:

```python
def test_flash_second_chunk_timeout_never_retries_or_commits_success(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    text_size = 51_788
    identity = _publish_current_debug_build(root, text_size=text_size)
    result_path = root / "artifacts" / "migration" / "flash-result.json"
    result_path.write_text('{"status":"success"}\n', encoding="utf-8")
    image = _elf_with_flash_segment(text_size=text_size)[84 : 84 + 51_852]

    class SecondReadTimesOut(RecordingFlashClient):
        async def read_memory(
            self,
            address: int,
            length: int,
            *,
            timeout_ms: int = 5_000,
        ) -> bytes:
            self.events.append(("read", address, length))
            self.read_timeouts.append(timeout_ms)
            reads = sum(event[0] == "read" for event in self.events)
            if reads == 2:
                raise ProbeClientError(
                    "PROBE_TIMEOUT", "Probe backend operation timed out"
                )
            offset = address - 0x08000000
            return self.image[offset : offset + length]

    client = SecondReadTimesOut(image)
    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "PROBE_TIMEOUT"
    assert [event[0] for event in client.events] == [
        "attach",
        "program",
        "read",
        "read",
    ]
    assert [event for event in client.events if event[0] == "read"] == [
        ("read", 0x08000000, 32_768),
        ("read", 0x08008000, 19_084),
    ]
    assert client.read_timeouts == [30_000, 30_000]
    assert sum(event[0] == "program" for event in client.events) == 1
    assert not result_path.exists()
```

- [ ] **Step 7: Run the exact RED nodes.**

```powershell
& $python312 -m pytest `
  tools/stm32-toolkit/tests/test_probe_protocol.py::test_memory_read_limit_matches_the_hex_response_envelope `
  tools/stm32-toolkit/tests/test_probe_service.py::test_maximum_memory_read_round_trips_through_service_and_client `
  tools/stm32-toolkit/tests/test_probe_service.py::test_oversized_memory_read_is_rejected_before_backend_dispatch `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_default_timeout_covers_exact_accepted_segment_in_protocol_chunks `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_final_byte_mismatch_in_exact_accepted_segment_never_commits_success `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_is_chunked_to_protocol_limit `
  tools/stm32-toolkit/tests/test_flash.py::test_flash_second_chunk_timeout_never_retries_or_commits_success `
  -q -p no:cacheprovider --basetemp (Join-Path $runRoot 'red')
```

Expected: all seven nodes fail for the intended PRODUCT gap. The protocol/schema test observes 65,536, the maximum service response trips `EVIDENCE_LIMIT_EXCEEDED`, the 32,769 request reaches backend dispatch or returns a non-schema error, and flash uses one/two reads instead of the required two/three. Existing exact-byte, one-program, timeout, mismatch, and no-result assertions must execute meaningfully. If fixture setup or another blocker prevents those assertions, stop and report the test-design conflict; do not delete or weaken assertions.

- [ ] **Step 8: Audit and commit RED tests only.**

```powershell
git diff --check
git diff --name-only
git diff -- tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_flash.py
git status --short
git add -- tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_flash.py
git commit -m "test(vs10a): expose memory read envelope mismatch"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Expected committed paths: exactly the three allowed test files. Record the RED SHA/tree and each failure cause.

---

### Task 2: Implement one truthful limit and make the focused contract GREEN

**Files:**
- Modify: `schemas/probe-protocol.schema.json:44`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json:44`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py:15`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:25-50`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:527-550`

**Interfaces:**
- Consumes: committed Task 1 tests, canonical response per-string limit 65,536, and existing lowercase-hex `memory.read` response.
- Produces: `MAX_READ_BYTES = 32_768`, byte-identical schemas with `memory.read` maximum 32,768, and flash chunking that directly consumes `MAX_READ_BYTES`.

- [ ] **Step 1: Tighten both schema authorities mechanically.**

In both schema files, change only the `memory.read` clause:

```json
"length": {"type": "integer", "minimum": 1, "maximum": 32768}
```

Do not change the 65,536 limits for request bodies, transport operations, or any other schema clause. Immediately verify the copies:

```powershell
$rootSchema = 'schemas\probe-protocol.schema.json'
$packageSchema = 'tools\stm32-toolkit\src\stm32_toolkit\schemas\probe-protocol.schema.json'
$rootHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $rootSchema).Hash
$packageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packageSchema).Hash
if ($rootHash -ne $packageHash) { throw 'Probe schemas differ' }
```

- [ ] **Step 2: Change the typed protocol authority.**

In `probe/protocol.py`, change only:

```python
MAX_READ_BYTES = 32_768
```

Do not add a second limit or change request/error decoding.

- [ ] **Step 3: Remove the parallel flash authority.**

In `probe/flash.py`, add:

```python
from .protocol import MAX_READ_BYTES
```

Delete:

```python
_READ_CHUNK = 65_536
```

In `_verify_segments()`, replace:

```python
length = min(_READ_CHUNK, len(segment.data) - offset)
```

with:

```python
length = min(MAX_READ_BYTES, len(segment.data) - offset)
```

Do not change any other loop, timeout, comparison, error, or publication behavior.

- [ ] **Step 4: Re-run the exact RED command and require GREEN.**

Repeat Task 1 Step 7 with basetemp `(Join-Path $runRoot 'green-target')`.

Expected: seven passed. The 32,768-byte real response traverses service/client, 32,769 is rejected before the observed backend method, accepted flash reads are two chunks, large flash reads are three chunks, final-byte mismatch and second-chunk timeout remain fail-closed, and programming occurs exactly once.

- [ ] **Step 5: Run the complete proportionate affected matrix.**

```powershell
& $python312 -m pytest `
  tools/stm32-toolkit/tests/test_probe_protocol.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  tools/stm32-toolkit/tests/test_sampling.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py::test_genuine_flash_result_is_consumed_by_binding_without_a_second_trust_schema `
  tools/stm32-toolkit/tests/test_debug_firmware.py::test_missing_or_invalid_firmware_and_flash_evidence_are_stable `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_persists_paused_stops_releases_then_marks_external `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_drains_modifications_before_final_target_readback `
  tools/stm32-toolkit/tests/test_debug_handoff.py::test_end_reacquires_revalidates_and_consumes_one_time_ticket `
  -q -p no:cacheprovider --basetemp (Join-Path $runRoot 'green-focused')
```

This is the complete slice matrix. `test_debug_read.py` and `test_sampling.py` are risk-triggered because their production modules import `MAX_READ_BYTES`; the binder/handoff nodes are risk-triggered because they share `_verify_segments()`. Do not run full suite, CLI/MCP, Monitor, package, release, recovery, coverage, or hardware checks without a newly classified affected failure.

- [ ] **Step 6: Audit allowed product bytes and commit GREEN.**

```powershell
git diff --check
git diff --name-only
git diff -- schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git status --short
```

Expected uncommitted paths: exactly the four allowed product paths. The three tests are already committed RED. If any other path changed, stop without committing.

```powershell
git add -- schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git commit -m "fix(vs10a): align memory reads with response envelope"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Record this commit as CodeHead only after the exact target and focused matrix pass against these bytes.

---

### Task 3: Reconcile evidence, clean output, and commit the report separately

**Files:**
- Create: `docs/codex/returns/STM32TK-1001-MEMORY-READ-ENVELOPE-LIMIT-CORRECTION/implementation-report.md`
- Do not modify product or tests.

**Interfaces:**
- Consumes: approved spec/plan, Task 1 RED SHA/tree, Task 2 CodeHead/tree, exact test results, changed-path audit, trigger evidence hash, and cleanup result.
- Produces: a tracked report naming the immutable CodeHead before the report commit and accurately deferring physical acceptance.

- [ ] **Step 1: Inspect and clean only the exact Luna run root.**

```powershell
$resolvedRunRoot = [IO.Path]::GetFullPath($runRoot)
$expectedRunRoot = [IO.Path]::GetFullPath('C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903')
if ($resolvedRunRoot -ne $expectedRunRoot) { throw 'Unexpected run root' }
Get-ChildItem -LiteralPath $resolvedRunRoot -Force
```

After preserving concise RED/GREEN facts, remove only that exact run-owned root. If Windows ACL blocks deletion, record the exact residual as `ENVIRONMENT`; do not change ACLs, touch a parent, or remove a shared cache, reusable fixture, source file, or user artifact.

- [ ] **Step 2: Write the implementation report with exact immutable lineage.**

The report must contain:

```markdown
# STM32TK-1001 Memory Read Envelope Limit Correction Implementation Report

Status: implementation evidence returned for independent Sol review; not accepted.

- Full accepted base and tree
- Approved specification SHA/tree
- Frozen plan SHA/tree
- RED SHA/tree
- CodeHead and CodeHead tree before this report commit
- Implementer/evidence owner: one GPT-5.6-luna agent, reasoning effort max
- Independent reviewer: GPT-5.6-sol primary, pending
- Hardware: not run; a new explicit authorization is required after software acceptance
- Remote actions: none

## Trigger and classification
Name the retained physical evidence path/hash, one consumed attempt, exact EVIDENCE_LIMIT_EXCEEDED result, unknown target contents, released lease, zero hardware-owner process, and PRODUCT classification. Do not claim a physical readback comparison or physical PASS.

## Implemented behavior
State exact 32,768/32,769 behavior, byte-identical schemas, unchanged hex/canonical limits, flash's shared protocol authority, exact two/three chunk shapes, unchanged timeouts, one-program/no-retry behavior, unchanged result schema, and unchanged adapters/backends.

## TDD lineage
List exact seven-node RED command/results, RED commit, seven-node GREEN result, complete focused matrix command/result, and CodeHead. Do not collapse RED and GREEN boundaries.

## Changed paths and scope audit
Classify every changed test, product/schema, and report path. Explicitly state all frozen paths remained byte-identical.

## Deferred external evidence
State that no hardware was run for the correction and that a new one-attempt public recovery flash remains separately authorized only after Sol acceptance.

## Cleanup and status
Record the exact run root, cleanup outcome, clean implementation worktree, and no remote mutation. Do not include moving ahead/behind counts or the report's own future SHA.
```

- [ ] **Step 3: Commit only the report.**

```powershell
git diff --check
git diff --name-only
git status --short
git add -- docs/codex/returns/STM32TK-1001-MEMORY-READ-ENVELOPE-LIMIT-CORRECTION/implementation-report.md
git commit -m "docs(vs10a): report memory read envelope correction"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git status --short --branch
```

Return the spec, plan, RED, CodeHead, and report SHAs/trees; exact test counts; exact changed paths; cleanup state; and classified residuals. Do not accept the diff, run hardware, or mutate remote state.

---

## Sol Independent Review Gate

After the Luna/max return, the Sol primary creates a fresh detached clean worktree at the report commit and independently:

1. confirms exact report HEAD/tree and detached clean status;
2. reviews the complete `4e6719e9447f69e3fffbe7842f4156df71464955..FINAL_HEAD` diff, not only CodeHead or the report;
3. verifies exact allowed test/product/schema/report paths and byte-identical schema copies;
4. runs `git diff --check 4e6719e9447f69e3fffbe7842f4156df71464955..HEAD`;
5. re-runs the exact seven-node target and complete Task 2 focused matrix with a fresh Sol-owned external basetemp under CPython 3.12;
6. verifies 32,768 real service/client success, 32,769 pre-backend rejection, unchanged canonical limit/hex encoding, exact flash chunk addresses and timeouts, one-program/no-retry closure, unchanged success evidence, debug/sampling compatibility, and binder/handoff compatibility;
7. reconciles the physical trigger evidence without labeling software tests as physical acceptance;
8. cleans only its exact run-owned output and classifies any residue;
9. issues `ACCEPTED`, `ACCEPTED_WITH_FIXES`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` without hardware or remote mutation.

After software acceptance, stop. A new public recovery flash requires a new explicit one-attempt authorization.
