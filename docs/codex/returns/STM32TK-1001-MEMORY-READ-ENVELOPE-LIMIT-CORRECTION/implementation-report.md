# STM32TK-1001 Memory Read Envelope Limit Correction Implementation Report

Status: implementation evidence returned for independent Sol review; not accepted.

- Full accepted base: `4e6719e9447f69e3fffbe7842f4156df71464955`; tree `641f5677c60d9942af83b2b87e132f1ab29b8d7d`
- Approved specification: `e8c3c31fb13275699fdb20ff0b4e989efffc5ee7`; tree `b3e367f54c2a5e53c7d0b694817a1f6854279e50`
- Frozen plan: `257619c4e2c18970a567a7ad496f5784f9f6ae79`; tree `45c1ae69ff84c75544ea91a7fd420accbcd85c14`
- RED commit: `a5b27c692d036119e0a7d415baaaf145bb0634db`; tree `94a35976a8f30273d36605e842fec1f9ebc42df3`
- RED oracle correction: `e4ff287d684a270614496bd131da55ea1e495ae5`; tree `ecdc1ed8c0e2cca9a9d3401f758bb3c1683e3c50`
- CodeHead before this report commit: `fdaa50c92c3388bd0e05d3f34b93062fdfb09602`; tree `289a2b11ba9b5b624563d15621e9129b9bf142ff`
- Implementer/evidence owner: one GPT-5.6-luna agent, reasoning effort `max`
- Independent reviewer: GPT-5.6-sol primary, pending
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
- Hardware: not run for this correction; a new explicit authorization is required after software acceptance
- Remote actions: none

## Trigger and classification

The prior accepted flash readback-timeout correction was followed by one explicitly authorized
public under-reset recovery flash attempt. Its retained physical evidence is:

- Path: `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-under-reset-recovery-evidence-limit-20260903-02.json`
- SHA-256: `b1577b42e1f2aadc3bff18e1e6a5dddde50adde6c3c94978e291bafffbe643ff`

The one attempt passed its accepted source/runtime, opaque probe, 100 kHz SWD under-reset,
Build ID, and ELF preflight gates, entered the irreversible programming path, emitted two
complete PyOCD progress bars, and returned exactly:

```json
{
  "ok": false,
  "operation": "stm32_flash",
  "code": "EVIDENCE_LIMIT_EXCEEDED",
  "message": "JSON string exceeds the string limit"
}
```

Toolkit published no `flash-result.json`, performed no retry or follow-on hardware read, released
the probe lease, and left zero Toolkit/PyOCD hardware-owner processes. Target contents are
unknown because programming was entered without a complete trusted Toolkit readback comparison;
this report claims neither physical readback comparison nor physical PASS. The failure is
classified `PRODUCT`: the public 65,536-byte raw-read declaration, lowercase-hex response
encoding, canonical 65,536-byte per-string safety limit, and flash chunk authority disagreed.

The zero-hardware boundary reproduction at the exact accepted source recorded 32,768 raw bytes
as a 65,536-character response that passes, while 32,769 raw bytes (65,538 hex characters) and
larger tested requests return `EVIDENCE_LIMIT_EXCEEDED` at canonical response validation.

## Implemented behavior

- Legacy `memory.read` accepts lengths `1..32768` inclusive. Exactly 32,768 bytes traverse the
  real service/client boundary as one 65,536-character lowercase-hex response and decode to the
  exact bytes. A 32,769-byte request is rejected before backend dispatch with the existing stable
  `PROBE_REQUEST_INVALID` code and `data.length` / `maximum` details.
- Root and packaged probe schemas are byte-identical and declare the `memory.read` maximum as
  32,768. `probe/protocol.py` owns the single typed `MAX_READ_BYTES = 32_768` authority.
- The canonical per-string Evidence limit remains 65,536 UTF-8 bytes. Lowercase-hex encoding,
  canonical JSON decoding, response fields, byte order, request-body/transport limits, and all
  unrelated schema limits remain unchanged.
- `probe/flash.py` imports and directly consumes `MAX_READ_BYTES`; the parallel numeric
  `_READ_CHUNK` authority is removed. The existing verification loop reads a 51,852-byte segment
  as exactly `32,768 + 19,084`, and a 70,064-byte segment as exactly
  `32,768 + 32,768 + 4,528`.
- Each chunk receives the unchanged caller-selected timeout, including the unchanged 30,000 ms
  default. Exact byte comparison, one-program behavior, unchanged success-result field set, and
  atomic result publication remain unchanged. Final-byte mismatch remains `FLASH_VERIFY_FAILED`
  with no result; any chunk timeout remains fail-closed with no retry, reconnect, second program,
  reset, resume, or alternate evidence path.
- Debug-read and sampling consumers continue using the shared protocol authority without public
  output drift. CLI/MCP/Monitor/Agent adapters, Probe Service, worker, PyOCD backend, connection
  profile, and result schema remain unchanged.

## TDD lineage

The exact seven-node RED command was run with CPython `3.12.10`, candidate source/test
`PYTHONPATH`, `-q -p no:cacheprovider`, and the repository-external Luna run root. Its result was
`1 passed, 6 failed`:

```text
test_probe_protocol.py::test_memory_read_limit_matches_the_hex_response_envelope
test_probe_service.py::test_maximum_memory_read_round_trips_through_service_and_client
test_probe_service.py::test_oversized_memory_read_is_rejected_before_backend_dispatch
test_flash.py::test_flash_default_timeout_covers_exact_accepted_segment_in_protocol_chunks
test_flash.py::test_flash_final_byte_mismatch_in_exact_accepted_segment_never_commits_success
test_flash.py::test_flash_readback_is_chunked_to_protocol_limit
test_flash.py::test_flash_second_chunk_timeout_never_retries_or_commits_success
```

The one RED PASS was the existing real service/client 32,768-byte round trip. The six PRODUCT
failures exposed the old 65,536 protocol authority, the pre-attach rejection mismatch, one-read
flash verification for the 51,852-byte segment, the old two-read high-level sequence for the
70,064-byte fixture, and the unreachable second-chunk timeout seam. The 70,064-byte detailed
oracle was already `32,768 + 32,768 + 4,528`; Task 1 review then required one missing high-level
`read` entry. The correction was exactly one insertion in `test_flash.py` and was committed as
`e4ff287d684a270614496bd131da55ea1e495ae5`; no product or unrelated assertion changed.

Against the Task 2 CodeHead, the same exact seven nodes completed `7 passed`, exit `0`.

The complete unchanged affected-matrix command was:

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

The first invocation used a long temporary root and returned `158 passed, 43 failed, 30 errors`;
the failures were classified `ENVIRONMENT` after Windows path-depth exhaustion in generation
staging. The exact same selectors and options were rerun with short fresh basetemp
`C:\tmp\mre2-0903-01\green-focused`, completing `231 passed`, exit `0`. This short-root result is
the accepted affected-matrix evidence for CodeHead `fdaa50c92c3388bd0e05d3f34b93062fdfb09602`.

## Changed paths and scope audit

The accepted specification and plan are frozen lineage inputs at the supplied commits. Relative
to the full accepted base, their files are present in the complete reviewed lineage, but no
Task 1, Task 2, or Task 3 agent modified either file after its approved commit:

- `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-memory-read-envelope-limit-correction-design.md`
  — approved specification, frozen.
- `docs/superpowers/plans/2026-09-03-stm32-toolkit-1001-memory-read-envelope-limit-correction.md`
  — frozen implementation plan, frozen.

The accepted-base-to-CodeHead product/test change set contains exactly these paths:

Test-only RED lineage:

- `tools/stm32-toolkit/tests/test_probe_protocol.py` — Task 1 RED contract.
- `tools/stm32-toolkit/tests/test_probe_service.py` — Task 1 RED service/client contract.
- `tools/stm32-toolkit/tests/test_flash.py` — Task 1 RED flash contracts plus the reviewed oracle
  correction in `e4ff287d684a270614496bd131da55ea1e495ae5`.

Task 2 product/schema correction:

- `schemas/probe-protocol.schema.json` — canonical schema maximum.
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json` — packaged schema,
  byte-identical to the canonical copy.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py` — shared typed limit.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py` — shared flash chunk authority.

Task 3 report:

- `docs/codex/returns/STM32TK-1001-MEMORY-READ-ENVELOPE-LIMIT-CORRECTION/implementation-report.md`
  — this tracked evidence report only.

The ignored SDD task reports are implementation notes and are not part of the tracked report
commit. Apart from the two supplied frozen lineage documents above, all frozen product, test,
runtime, dependency, packaging, README, adapter, worker, backend, service, debug-read, sampling,
and handoff paths remained byte-identical. No Task 3 change touched product, tests, specification,
or plan.

## Deferred external evidence

No physical probe attach, flash, target read, or public Toolkit recovery attempt was run for this
correction. Replay, fake, fixture, subprocess, and software service/client evidence is not a
physical PASS. The one earlier public trigger attempt is consumed and its target contents remain
unknown; it cannot be reused or relabeled. After independent Sol software acceptance only, a new
one-attempt public recovery flash may be authorized separately, followed by one read-only bind/read
confirmation. No retry is implied, and this report does not grant that authorization.

## Cleanup and status

The exact Task 3 Luna run root
`C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903` was inspected with its canonical full
path and was absent; its attributed output had already been cleaned. The Task 2 short-run root
was moved to `C:\tmp\mre2-0903-01-discarded`, where recursive cleanup left disposable residue.
Earlier Task 2 roots also remain: `C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903-task2-discarded`,
`C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903-task2-final`, and
`C:\tmp\stm32tk-1001-memory-read-envelope-luna-20260903-task2-diag2`. Their cleanup encountered
the exact environment/ACL residual `Access to the path 'redirect-parent' is denied`; no ACL was
changed and no parent/shared cache/source/reusable fixture was touched. The separately root-owned
Sol diagnostic residue `C:\tmp\mrdiag-0903-01` remains (including `pycache` and `t`) and was not
removed by this implementation owner. Attributed matrix/diagnostic logs were removed after the
minimum evidence was preserved in the reports.

The implementation worktree is clean apart from no uncommitted tracked changes after this report
is committed. No remote mutation occurred. This is an implementer evidence return for independent
Sol review, not an acceptance verdict.
