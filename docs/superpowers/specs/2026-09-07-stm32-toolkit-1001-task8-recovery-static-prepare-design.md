# STM32TK-1001 Task 8 Recovery Static-Prepare Design

Date: 2026-09-07

Module / phase: STM32TK-1001 / VS10-A H2 Task 8 physical closure

Status: FROZEN BY THE USER'S CONTINUE DIRECTION AND STANDING AUTONOMOUS-REPAIR AUTHORIZATION

Full accepted product base: `fe01c4fcd28792c512dd71beb51b47aa391db6f7`

Accepted-base tree: `905d6739d3d3ea402e0ebd0d4f0f04549de43ae4`

Specification owner and independent reviewer: GPT-5.6-sol primary

Implementation owner after this freeze: the existing Task 8 GPT-5.6-luna agent at reasoning
effort `max`

Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

Remote action: none authorized

Hardware action after software acceptance: the existing authorization permits exactly one
recovery guarded flash; no hardware operation is allowed during implementation or review

## 1. Trigger and classification

Two independent public recovery-prepare sessions found the expected probe but returned
`TEST_EXECUTION_FAILED` before creating an authorization. The first implementation bound the
recovery profile only to execute. The second passed the exact recovery worker into OBSERVE
prepare, but production OBSERVE attach uses `halt_on_connect=false`; PyOCD therefore resumes the
target after connect-under-reset and requires it to be running. That conflicts with the recovery
condition. Making prepare MODIFY would violate its non-mutating public contract.

Classification: `PRODUCT / integration lifecycle`. This is not a USB-discovery failure, flash
failure, or reason to retry hardware. The two-round convergence rule stops further local patching
until this interface is frozen.

## 2. Runnable scenarios

### Scenario 1 - normal prepare and execute are unchanged

With `recovery_under_reset=false`, prepare retains the accepted OBSERVE supervisor, normal
1 MHz/SWD attach, physical target-identity proof, freshness revalidation, and canonical
authorization. Execute retains the normal worker and all existing identity, flash, readback,
transport, deadline, cleanup, and publication behavior.

### Scenario 2 - recovery prepare authorizes only static intent

With `recovery_under_reset=true`, prepare validates the request and a portable public probe
selector, loads the exact project/build/ELF/transport/support/case facts, calculates the existing
inventory and case digests, re-reads the firmware facts to reject static drift, and writes the
existing canonical one-time authorization with the exact recovery boolean.

Recovery prepare does not create a supervisor, start a worker or service, acquire a probe lease,
enumerate a probe, attach, reset, halt, resume, read target memory, or program. Success means only
that the closed static intent is authorized. It does not prove that a probe is present, that the
chip identity matches, or that any physical behavior passed.

The public response shape and action-digest ownership remain unchanged. A well-formed selector
may be authorized while its probe is disconnected; execute is the physical authority. Empty,
non-string, control-bearing, non-portable, or overlong selectors fail before authorization.

### Scenario 3 - recovery execute owns the first target access

Execute receives only the probe selector and prepared action digest. It loads and terminally
consumes the action once, checks the exact recovery boolean, expiry, project/workspace/session,
revision and dirty state, input snapshot, build ID, ELF path/hash, transport, support profile,
inventory digest, protocol, and case digest before service creation.

For a recovery action it creates exactly one existing MODIFY worker using
`ProbeWorkerConfig.for_under_reset_recovery()`: 100 kHz, SWD, connect-under-reset. Its first target
access is attach. It proves the returned physical identity equals the authorized target and probe
hash before the existing flash adapter is constructed or called. Identity mismatch and attach
failure perform zero program calls. A match allows at most the existing one program/readback/run
flow. No normal-first attempt, retry, fallback, arbitrary frequency, or second backend exists.

### Scenario 4 - failure and evidence remain fail-closed

Any static drift fails before service creation. Any attach, identity, programming, readback,
transport, timeout, cleanup, or publication failure publishes no physical PASS. Once execute
consumes an action, every outcome is terminal; a caller cannot reuse it. The existing execute
per-operation and target-run deadline owners remain unchanged by this correction, and no expired
request may dispatch a later hardware operation.

## 3. Frozen state and dependency ownership

- `TargetTestRunner` remains the sole canonical authorization owner.
- `recovery_under_reset` remains the only recovery choice and remains covered by the action digest.
- The project model and fresh firmware facts remain the source of expected target identity.
- The caller-supplied public probe selector and its SHA-256 remain the selected-probe binding.
- Normal prepare owns physical identity proof only for normal actions.
- Recovery execute owns all physical proof for recovery actions.
- `ProbeServiceSupervisor`, the existing PyOCD worker/backend, flash adapter, TestRun publisher,
  protocol, schema, CLI, and MCP registrations remain shared and unchanged.

## 4. Errors and lifecycle

- Invalid recovery-prepare input returns the existing closed Target protocol failure before any
  authorization or hardware construction.
- Recovery prepare may succeed with a currently absent but syntactically valid probe selector;
  this is static authorization, never physical evidence.
- Execute consumes once before physical access and does not restore or recreate authorization on
  failure.
- Static mismatch occurs before service creation. Physical identity mismatch occurs after the
  single attach and before programming.
- Cleanup does not convert a failed run into success and no TestRun is published without the
  existing successful end-to-end flow.

## 5. Bounded ownership

Product changes are allowed only in:

- `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`.

Tests are allowed only in:

- `tools/stm32-toolkit/tests/test_physical_target_workflows.py`;
- `tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py` only if the real public path requires
  coverage not expressible in the narrower file.

No selector module change is authorized. The exact portable selector predicate may be local to
the workflow and must match the already accepted public MCP/PyOCD domain byte-for-byte.

## 6. Required evidence

Tests must prove:

- normal prepare still creates one OBSERVE supervisor and attaches normally;
- recovery prepare succeeds while any supervisor construction raises if called;
- recovery prepare creates no lease, backend, attach, target read, reset, halt, resume, or program;
- recovery prepare writes exact static identity, digests, probe hash, and `true` binding;
- invalid recovery selectors and static drift fail before authorization/service;
- the resulting real authorization is consumable by recovery execute;
- static execute drift fails before service, identity mismatch programs zero times, and identity
  match uses one exact recovery worker and one program with no retry;
- a failed/consumed action cannot execute again and no failure publishes a physical PASS;
- default CLI/MCP/Python shapes, inventory count, schemas, backend, and normal worker remain
  unchanged.

Use CPython 3.12, source `PYTHONPATH`, `-p no:cacheprovider`, `-o addopts=''`, and a short unique
external basetemp. Run the two affected workflow/public files first and expand to the existing
five-file Target matrix only because the action-record/public-chain risk crosses those files.
Clean only run-owned temporary output and classify protected residue.

## 7. Explicit non-goals

- No MODIFY prepare, recovery probe enumeration, physical proof, or physical PASS at prepare.
- No change to normal prepare/execute behavior.
- No arbitrary frequency, connect mode, retry, fallback, unlock, mass erase, chip erase, Option
  Bytes, reset/run automation, or target-state repair.
- No new runtime, service, worker, backend, provider, controller, schema, protocol, MCP
  registration, agent-specific behavior, Python range, CI, or collaboration automation.
- No project-firmware, Monitor, package, release, report, or remote change in implementation.
- No hardware operation until independent software acceptance; afterward at most the one already
  authorized recovery guarded flash.

## 8. Acceptance and stop boundary

The Luna/max owner commits RED before GREEN and does not accept its own diff. Sol reviews the full
`fe01c4fcd28792c512dd71beb51b47aa391db6f7..CODE_HEAD` diff in a fresh detached worktree and
issues one verdict. Only `ACCEPTED` permits rebuilding the exact local runtime and returning to
the public prepare/execute hardware path. Any hardware gate failure stops with zero retry and an
explicit PRODUCT/ENVIRONMENT/HARDWARE classification. No remote action is authorized.
