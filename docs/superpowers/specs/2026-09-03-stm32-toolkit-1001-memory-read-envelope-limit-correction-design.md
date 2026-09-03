# STM32TK-1001 Memory Read Envelope Limit Correction Design

Date: 2026-09-03
Module / phase: STM32TK-1001 / VS10-A H2 physical acceptance correction
Status: FROZEN FOR USER REVIEW
Full accepted base: `4e6719e9447f69e3fffbe7842f4156df71464955`
Accepted-base tree: `641f5677c60d9942af83b2b87e132f1ab29b8d7d`
Accepted product CodeHead below the report commits: `b4ce29c66d19e10ec9bd5b68f4c0c4ac127be9bd`
Accepted product tree: `272708ae49d8842ae30ced44a41736e62f41ad0a`
Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
Specification owner and final reviewer: GPT-5.6-sol primary
Implementation owner after separate specification and plan approval: exactly one GPT-5.6-luna
agent at reasoning effort `max`
Remote action: none authorized
Hardware action: the one-attempt authorization was consumed by the trigger below; no additional
hardware action is authorized by this specification

## 1. Trigger, evidence, and failure classification

After the flash readback-timeout correction was independently accepted, the user authorized one
new public recovery flash. The exact accepted Toolkit source, CPython 3.12.10, PyOCD 0.45.1,
accepted opaque probe selector, fixed 100 kHz SWD / connect-under-reset profile, Build ID, and ELF
SHA-256 passed their preflight gates. The command entered the irreversible flash path, emitted two
complete PyOCD progress bars, and then returned:

```json
{
  "ok": false,
  "operation": "stm32_flash",
  "code": "EVIDENCE_LIMIT_EXCEEDED",
  "message": "JSON string exceeds the string limit"
}
```

Toolkit published no `flash-result.json`, performed no retry or follow-on hardware read, released
the probe lease, and left no Toolkit/PyOCD hardware-owner process. The target contents remain
unknown because programming was entered without a complete trusted Toolkit readback comparison.

Retained physical evidence:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-under-reset-recovery-evidence-limit-20260903-02.json`;
- SHA-256 `b1577b42e1f2aadc3bff18e1e6a5dddde50adde6c3c94978e291bafffbe643ff`.

The zero-hardware boundary reproduction at the exact accepted source established:

| Requested raw bytes | Hex string bytes | Canonical response result |
| ---: | ---: | --- |
| 32,768 | 65,536 | PASS |
| 32,769 | 65,538 | `EVIDENCE_LIMIT_EXCEEDED` |
| 51,852 | 103,704 | `EVIDENCE_LIMIT_EXCEEDED` |
| 65,536 | 131,072 | `EVIDENCE_LIMIT_EXCEEDED` |

The conflict is deterministic. Probe protocol v2 and both schema copies currently permit one
legacy `memory.read` request of 65,536 raw bytes. The service returns those bytes as one lowercase
hex JSON string, which requires two characters per raw byte. `ProbeClient` verifies the response
with the accepted canonical JSON decoder, whose per-string safety limit is 65,536 UTF-8 bytes.
Therefore the truthful end-to-end maximum for this operation and encoding is 32,768 raw bytes.

The accepted flash helper independently uses `_READ_CHUNK = 65_536`, so the accepted 51,852-byte
first ELF load segment is sent as one response that the client cannot represent. Debug read and
sampling grouping also consume the protocol's current `MAX_READ_BYTES = 65_536` and can construct
the same impossible request through non-flash workflows.

Failure classification: `PRODUCT` — the public protocol limit, workflow grouping, response
encoding, and canonical response safety limit disagree. This is not a probe enumeration, USB,
VS Code, Keil, PyOCD attach, connection-policy, timeout, or Agent-adapter failure.

## 2. Runnable user scenarios

### Scenario 1 - the maximum declared legacy memory read succeeds end to end

An attached client requests exactly 32,768 bytes through the real Probe Service HTTP boundary.
The backend receives one 32,768-byte read, the service emits one 65,536-character lowercase hex
string, the canonical decoder accepts it, and `ProbeClient.read_memory()` returns the exact bytes.

### Scenario 2 - an oversized legacy memory read fails before backend access

A raw `memory.read` request for 32,769 bytes is rejected by protocol schema validation with the
existing stable `PROBE_REQUEST_INVALID` code and `data.length` / `maximum` details. The backend is
not attached, read, or otherwise invoked for the invalid request. The failure no longer occurs
after a target read as `EVIDENCE_LIMIT_EXCEEDED`.

### Scenario 3 - flash verifies the complete accepted segment in safe chunks

After one authorized program operation, the accepted 51,852-byte ELF segment is read as exactly
32,768 plus 19,084 bytes. Both reads receive the same validated `FlashRequest.timeout_ms`; the
default remains 30,000 ms per chunk. All bytes must compare exactly before disk/build revalidation
and the unchanged atomic `flash-result.json` publication.

A larger 70,064-byte fixture is read as exactly 32,768, 32,768, and 4,528 bytes. Programming still
occurs exactly once. There is no retry, reconnect, second program, reset, resume, or alternate
evidence path.

### Scenario 4 - shared observation workflows consume the truthful limit

Debug variable-read grouping and sampling continue to import the single protocol
`MAX_READ_BYTES`. They may split a large contiguous observation into more requests, but total
requested data, item order, decoded values, error semantics, generic 5,000-ms observation timeout,
and public CLI/MCP result shapes remain unchanged. Ordinary small variable, register, fault,
Monitor, and binder reads behave identically.

## 3. Selected architecture

### 3.1 Make the protocol constant and schemas truthful

Change legacy `memory.read` only:

```python
MAX_READ_BYTES = 32_768
```

Set `data.length.maximum` for `memory.read` to 32,768 in both byte-identical schema authorities:

- `schemas/probe-protocol.schema.json`;
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`.

The schema remains the request-decoding authority. Probe protocol stays
`stm32-toolkit-probe/2`; Toolkit stays 0.9.0. This is an intentional tightening of a range that was
not usable end to end, not a new operation or alternate protocol.

`target.memory.read` remains independently capped at 4,096 bytes. Transport read limits, backend
native read capability, request-body size, response-body size, and every non-`memory.read` schema
remain unchanged.

### 3.2 Make flash consume the same limit

`probe/flash.py` imports `MAX_READ_BYTES` from `probe/protocol.py` and uses that value as its sole
readback chunk bound. It must not retain a parallel numeric `_READ_CHUNK = 32_768` authority.

The existing `_verify_segments()` loop, address progression, timeout propagation, exact byte
comparison, verified-byte count, and fail-closed result publication remain unchanged. Only the
chunk boundary changes.

### 3.3 Preserve adapter and backend boundaries

The dependency path remains:

```text
CLI / MCP / thin Agent adapter
  -> public hardware workflow
  -> ProbeClient
  -> Probe Service protocol v2
  -> one worker / one PyOCD backend
```

No CLI, MCP, Monitor, Claude adapter, VS Code configuration, service dispatch, worker, PyOCD
backend, connection profile, result schema, runtime, or package entry point gains special logic.
All adapters inherit the corrected shared core behavior.

### 3.4 Keep the canonical Evidence safety boundary unchanged

The 65,536-byte per-string Evidence limit remains unchanged. The response continues to use the
existing lowercase hex field and deterministic canonical JSON. No decoder bypass, response
special case, larger global string allowance, or second serializer is introduced.

## 4. Alternatives considered

### Change only the private flash chunk to 32,768

Rejected. It would unblock this flash fixture but leave protocol v2, debug grouping, and sampling
able to issue 32,769-65,536-byte requests that necessarily fail after backend access. The declared
public limit would remain false and state ownership would remain duplicated.

### Keep 65,536 raw bytes and change the response to multiple strings or another encoding

Rejected. Base64 still exceeds 65,536 characters for 65,536 raw bytes. A chunk-array response can
represent the payload but changes the service/client response contract, adds a second framing
layer, and requires broader compatibility work with no current user scenario that needs a single
65,536-byte transaction.

### Raise or bypass the canonical JSON string limit

Rejected. It would weaken a repository-wide evidence safety boundary or introduce operation-
specific canonicalization. The product already supports bounded repeated reads, so increasing a
global parser limit is unnecessary.

### Use `target.memory.read` for flash verification

Rejected. That is a separate 4,096-byte public debug operation with different response fields,
hash semantics, target-operation errors, and lifecycle ownership. Replacing the existing flash
read path would widen the slice without resolving the legacy protocol's false maximum.

## 5. Public behavior, errors, and compatibility

- `memory.read` accepts lengths `1..32768` inclusive.
- Length 32,769 and above is rejected before backend dispatch with existing code
  `PROBE_REQUEST_INVALID`; details identify `data.length` and rule `maximum`.
- Addresses, address-range validation, operation level, request timeout, response field name,
  lowercase hex encoding, byte order, and response decoder remain unchanged.
- `ProbeClient.read_memory()` signature and its default 5,000-ms timeout remain unchanged.
- Flash retains the exact caller-selected timeout for every chunk, including the default 30,000
  ms public transaction.
- A 51,852-byte segment produces two reads; a 70,064-byte segment produces three reads.
- Complete readback still produces the same exact `flash-result.json` field set. Any timeout,
  mismatch, partial response, invalid response, cancellation, or freshness change produces no
  success evidence and no retry.
- Direct protocol clients that previously requested 32,769-65,536 bytes must split the request.
  That range previously performed backend work and then failed canonical response validation; the
  corrected contract fails early instead of claiming unusable support.
- CLI, MCP, Monitor, Skills, README, launcher, and thin Agent adapters have no signature or schema
  change.

## 6. Bounded implementation ownership

The sole GPT-5.6-luna/max implementer may change product code only in:

- `schemas/probe-protocol.schema.json`;
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`;
- `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.

The implementer may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_protocol.py`;
- `tools/stm32-toolkit/tests/test_probe_service.py`;
- `tools/stm32-toolkit/tests/test_flash.py`.

`test_debug_read.py`, `test_sampling.py`, `test_probe_client.py`, binder/handoff tests, and the
earlier timeout tests are verification inputs and must remain byte-identical unless a failing RED
or affected regression proves a test-contract update is necessary. Any such need is reported to
Sol before editing.

The implementation report is limited to:

- `docs/codex/returns/STM32TK-1001-MEMORY-READ-ENVELOPE-LIMIT-CORRECTION/implementation-report.md`.

All CLI, MCP, Monitor, service, worker, backend, debug/read/sampling product files, runtime,
dependencies, packaging configuration, README, Skills, and Agent adapters are frozen. If TDD
proves another product file must change, implementation stops and reports the exact conflict.

## 7. Required TDD evidence

Tests must be committed RED before product code and directly prove:

- both schema copies remain byte-identical and declare `memory.read` maximum 32,768;
- `MAX_READ_BYTES` is exactly 32,768;
- protocol decoding accepts 32,768 and rejects 32,769 with exact stable code/details;
- the 32,769 rejection occurs without backend attach/read events;
- a real Probe Service plus real ProbeClient transports and returns exactly 32,768 nontrivial
  bytes through HTTP, hex encoding, canonical JSON, and decoding;
- the accepted 51,852-byte flash segment reads as 32,768 plus 19,084 with 30,000 ms on both reads;
- the 70,064-byte fixture reads as 32,768, 32,768, and 4,528 with the exact custom timeout on all
  three reads and exactly one program call;
- final-byte mismatch in the final chunk still fails `FLASH_VERIFY_FAILED` and publishes no
  result;
- a timeout on any chunk still performs no retry and publishes no result;
- complete matching readback retains the exact success-result field set;
- unchanged debug read and sampling suites continue to consume the shared limit without public
  output drift.

The service/client integration test must not call `_decode_response()` directly and must not use a
fake client that bypasses HTTP or canonical response validation. It may use the existing fake
backend behind the real service because the target bytes are not the boundary under test.

Tests must not weaken the 64 KiB canonical Evidence limit, delete earlier timeout assertions,
sleep for physical durations, forge a flash result, or change unrelated product behavior.

## 8. Proportionate verification and evidence owners

### Slice verification - Luna/max implementation owner

Use the accepted CPython 3.12 runtime, candidate source/test `PYTHONPATH`,
`-p no:cacheprovider`, and a fresh repository-external run-owned basetemp. Run:

1. exact new protocol/service/flash RED nodes;
2. complete `test_probe_protocol.py`, `test_probe_service.py`, and `test_flash.py`;
3. complete unchanged `test_debug_read.py` and `test_sampling.py` because both consume
   `MAX_READ_BYTES`;
4. the two genuine binder controls and three handoff controls already used by the timeout slice,
   because flash chunking still shares `_verify_segments()` with those consumers.

Do not run the full suite, recovery seven-file suite, package, release, CLI/MCP, Monitor, or
hardware checks unless a concrete new failure identifies an affected dependency. Run
`git diff --check`, audit exact paths, preserve minimum failure evidence, and clean only verified
run-owned disposable output.

### Independent review - Sol primary

Review the complete
`4e6719e9447f69e3fffbe7842f4156df71464955..FINAL_HEAD` diff in a fresh detached clean worktree,
including both schema copies, RED tests, product commit, and separate report commit. Re-run the
same focused matrix with a new Sol-owned basetemp. Acceptance requires exact boundary behavior,
real service/client coverage, unchanged Evidence limit and response encoding, exact flash
chunking/timeouts, one-program/no-retry closure, unchanged trust result, accurate report lineage,
and clean status.

### Physical acceptance - separate authorization after software acceptance

No hardware action belongs to implementation or software review. A new public under-reset
recovery flash requires a new explicit one-attempt authorization after software acceptance. On
success, run one read-only public bind/read confirmation. On failure, preserve minimum evidence
and stop without retry.

## 9. Explicit non-goals

- No change to the canonical Evidence 64 KiB string limit or 1 MiB envelope limit.
- No response encoding, response field, byte order, protocol version, or Toolkit version change.
- No change to `target.memory.read`, target transport, or backend native read limits.
- No second runtime, service, worker, backend, controller, provider, or MCP registration.
- No public timeout, chunk-size, recovery, frequency, or PyOCD option.
- No change to 100 kHz SWD / connect-under-reset or ordinary 1 MHz / halt policies.
- No retry, reconnect, second programming call, target fallback, reset, resume, or run action.
- No new Agent-, VS Code-, or Keil-specific product logic.
- No new Python, platform, probe, target, or board support claim.
- No CI, collaboration automation, package/release matrix, push, PR mutation, merge, tag, close,
  release, or remote branch deletion.
- No hardware operation before independent software acceptance and a new authorization.

## 10. Acceptance and stop boundary

This correction is accepted only when all four scenarios are directly proven, the focused
CPython 3.12 matrix passes, the complete accepted-base-to-final diff has no unresolved product,
safety, compatibility, scope, schema, or report defect, both schema copies are byte-identical, the
implementation report accurately separates the failed physical attempt from software evidence,
and implementation/review worktrees and run-owned artifacts are clean or explicitly classified.

After software acceptance, stop. Do not reuse the consumed hardware authorization, automatically
run another recovery flash, push remotely, or enter VS10-B.
