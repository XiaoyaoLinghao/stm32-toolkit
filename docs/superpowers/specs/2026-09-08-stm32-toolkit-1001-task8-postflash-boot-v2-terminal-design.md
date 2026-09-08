# STM32 Toolkit 1001 Task 8 post-flash boot and v2 terminal correction design

## Approval status

Approved by the user on 2026-09-08 for local offline implementation and independent review. The
previously approved post-flash design explicitly excluded reset and any change to the standalone
CONTROL/Probe protocol contract. This approved amendment deliberately replaces only those two
exclusions by adding `target.reset` to the existing Probe CONTROL protocol and using it from
physical Target execute. It preserves every other boundary of that design.
## Ledger

- Module/phase: `STM32TK-1001`, Task 8 corrective physical Target completion.
- Exact accepted Toolkit base: `f8ff521922ed366e1f1f30ae99220a8ff19f693e` (tree
  `f3336fb8c35679c385d15e639f94b83f01aab550`).
- Exact campaign project head: `4bfcf9f95b1d761c9a82042d6ded751d068c1e06` (tree
  `a73fc32019989ef7ffa44619eefe767c5da3dab3`); project bytes are out of scope.
- The sole continuation branch remains
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Implementation occurs in an isolated
  detached worktree at the exact accepted base; the original branch may be fast-forwarded locally
  only after it is rechecked clean. No replacement branch is created.
- Specification/plan owner and independent reviewer: GPT-5.6-sol primary.
- Implementation/test owner: one GPT-5.6-luna agent, reasoning effort `max`.
- Remote, runtime installation/promotion, release, and hardware actions: none authorized.

## Confirmed defects

1. Physical evidence captured the core halted at the installed CMSIS-Pack flash algorithm return
   breakpoint: PC `0x2002FEA8`, LR `0x2002FEA9`, SP/MSP `0x2002F6A0`, DFSR BKPT. Those values exactly
   equal the installed pack's `load_address`, `load_address + 1`, and `begin_stack`. The current
   post-flash ordinary resume therefore does not establish the firmware reset-vector application
   start context. The evidence does not establish the exact native-call timing or first exception
   during attempt 6.
2. Protocol v2 uses no streaming validator. A valid v2 `run_end` therefore does not terminate the
   collection loop, while the production memory mailbox reports `eof=False`; a complete run waits
   until `TEST_TIMEOUT` instead of reaching the existing v2 assembler.

Classification: both are `PRODUCT / Target execution lifecycle`. The earlier flash/readback proof
remains valid; it did not prove application execution or a TestRun.

## Runnable scenarios

### 1. Physical Target execute starts the flashed image from reset

After flash/readback and post-flash identity match, the physical adapter prepares and consumes one
exact `target.reset` CONTROL authorization bound to the same workspace, project, session,
revision, target identity, build ID, ELF SHA, and live pre-reset state. Reset has empty arguments.
The Probe Service invokes the existing backend `reset()` capability and returns one closed state.

If the returned state is running, transport open may proceed. If it is halted specifically for
reason `reset`, the adapter rechecks the live state, then prepares and consumes a separate exact
`target.resume` CONTROL record and requires `{"state":"running"}`. Any other state or reason fails.
The reset action is never represented by or charged to the resume authorization.

### 2. Protocol v2 completes on its terminal frame

For v2 execution, a decoded kind-5 `run_end` marks collection complete even when transport EOF is
false. The runner finishes processing all frames already decoded from that same chunk, then stops
polling. It still calls `decoder.finish()`, revalidates final transport identity, persists the exact
collected bytes, and invokes the existing `assemble_target_v2_run()` validation before publication.

### 3. Invalid or incomplete work remains terminal and closed

Identity mismatch performs no reset. Flash failure performs no reset. Reset failure performs no
resume or transport open. Resume fallback failure performs no transport open. A malformed or
invalid terminal frame reaches the existing v2 validation and publishes no TestRun. A v2 stream
without `run_end` still expires as `TEST_TIMEOUT`. No failure retries reset, resume, flash, attach,
or the parent Target action.

## Frozen contracts

The one new Probe protocol operation is `target.reset`. This expands the existing Probe request
operation enum and is callable only through the existing leased Probe Service with an exact
single-use CONTROL authorization. It adds no CLI command, MCP tool, or Skill:

- operation level: `CONTROL`;
- arguments: exactly `{}` plus the existing authorization digest in the request envelope;
- authorization: the existing single-use `ControlAuthorizationStore` record, including exact live
  identity and state snapshots;
- backend effect: the existing `ProbeBackend.reset()`/PyOCD target reset method;
- response: exact closed state data; only running, or halted with reason `reset`, is admissible to
  the physical Target start transition;
- timeout and public failure vocabulary: existing limits and error codes only.

Dependency direction remains `testing.target -> Probe client + authorization store -> Probe
Service -> Probe backend`. The Target runner never calls the backend or worker directly. The v2
decoder and assembler remain the sources of truth for frame syntax and run validity; EOF remains a
transport fact and `run_end` remains the protocol terminal fact.

Ordered lifecycle:

`consume parent -> revalidate -> attach/identity -> flash/readback -> identity -> reset CONTROL ->
running OR reset-halted -> optional resume CONTROL -> running -> transport open -> decode through
run_end -> decoder.finish -> final transport identity -> raw artifact -> full v2 assembly/validation
-> existing publication -> cleanup`.

The parent Target deadline owns every added read/control boundary. Deadline expiry retains
`TEST_TIMEOUT`. Reset/resume authorization, backend, or state failures retain
`TEST_EXECUTION_FAILED` unless an existing identity/timeout mapping is more specific. Primary
execution/protocol errors retain precedence; cleanup notes remain secondary.

## Allowed files

Product:

- `schemas/probe-protocol.schema.json`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/authorization.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`

Tests:

- `tools/stm32-toolkit/tests/test_probe_protocol_v2.py`
- `tools/stm32-toolkit/tests/test_probe_service.py`
- `tools/stm32-toolkit/tests/test_target_runner.py`
- `tools/stm32-toolkit/tests/test_physical_target_workflows.py`

No other file is writable by the implementation owner.

## Non-goals

- No change to general `flash.program` semantics, PyOCD backend reset implementation, worker,
  connection policy, unlock/erase/retry behavior, or public Target authorization shape.
- No direct PC/SP/register/vector writes, reset-after-program option inside `FileProgrammer`,
  backend bypass, reconnect, second attach, second flash, or fallback target/probe.
- No change to v1, mailbox ABI, frame v2 payload/schema/digest/count semantics, firmware, linker,
  campaign project, launcher, runtime, package version, CLI/MCP commands, 48 tools, or 8 skills.
- No new public error code, manifest, validator framework, backend, dependency, CI, or automation.
- No hardware action, push, PR mutation, merge, tag, release, closure, or remote deletion.

## Acceptance boundary

Luna must establish focused RED before GREEN and remain within the allowed files. Sol reviews the
complete accepted-base-to-CodeHead diff in a fresh detached worktree. Software acceptance requires
all focused offline gates below; physical confirmation remains separately authorized and deferred.
