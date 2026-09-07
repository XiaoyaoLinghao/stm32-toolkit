# STM32 Toolkit 1001 Task 8 post-flash run transition design

## Ledger

- Module/phase: `STM32TK-1001`, Task 8 physical Step 4 post-flash execution correction.
- Accepted Toolkit product base: `342447dd6049326e6df439b0adc778657ee548f2` (tree
  `c98ae4607514c30a486fae83776dfa0f2bb55521`).
- Accepted project head: `4bfcf9f95b1d761c9a82042d6ded751d068c1e06` (tree
  `a73fc32019989ef7ffa44619eefe767c5da3dab3`).
- Specification/plan owner and independent reviewer: GPT-5.6-sol primary.
- Implementation owner: one GPT-5.6-luna agent at reasoning effort `max`.
- Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Remote action: none authorized.
- Hardware action: none authorized during implementation or review. The consumed action
  `45b4cdb359ddc0d276fd5d91cdd705d067d935bd16b652667ef8056f05c3940e` must never be retried.

## Trigger and exact defect

The authorized recovery Target execute used the accepted 100 kHz SWD/connect-under-reset worker,
proved the expected STM32F429ZGTx identity, programmed and read back 54896 bytes successfully, and
then failed before a TestRun. The user observed that D4 remained off after the attempt.

That physical observation matches the production lifecycle exactly:

1. every Target execute owns a `MODIFY` Probe Service;
2. `probe.attach` therefore requires the target to be halted;
3. the accepted guarded flash deliberately performs no reset or automatic run and keeps
   `resume_on_disconnect=false`;
4. `TargetTestRunner.run()` verifies identity after flash and then opens the Target transport;
5. no operation between those steps resumes the target, and normal cleanup only closes it.

The general recovery-flash contract is correct and remains unchanged: its success proves bytes,
not application execution, and it may leave the target halted. Task 8 Target execute is the later
explicitly authorized operation that must run the newly programmed test firmware before reading
its mailbox. A RAM-order correction alone cannot produce frames while the core remains halted.

Classification: `PRODUCT / Target execution lifecycle`. The earlier flash/readback PASS remains
valid; application execution, mailbox frames, and a physical TestRun remain unproven.

## Runnable scenarios

### Scenario 1 - exact Target action resumes only after verified flash

For normal and recovery Target execute, Toolkit consumes the exact parent Target authorization,
attaches once in `MODIFY`, proves target identity, performs at most one guarded flash and complete
readback, and proves the same target identity again. Only then it derives and consumes one existing
`target.resume` CONTROL authorization bound to the same workspace, project, session, revision,
target, build ID, ELF SHA, and live target state. Probe Service must report `running` before the
Target transport is opened.

### Scenario 2 - target transport observes running firmware

On success, the event order is exactly:

`attach halted -> identity -> flash/readback -> identity -> resume/running proof -> transport open`.

Mailbox or RTT polling can then observe firmware output under the existing absolute Target-run
deadline. The resulting TestRun is published only after all existing protocol, identity, evidence,
and cleanup gates pass.

### Scenario 3 - failures remain terminal and fail closed

Attach, pre-flash identity mismatch, flash/readback failure, post-flash identity mismatch, CONTROL
authorization failure, resume failure, non-running state, or deadline expiry opens no Target
transport and publishes no TestRun. A mismatch before programming still performs zero programming;
a failure after programming never retries or programs again. The parent Target authorization stays
terminally consumed. Cleanup reports its existing error precedence and does not claim that the
target is running when the running proof failed.

### Scenario 4 - public flash and control contracts remain unchanged

Ordinary and recovery public flash retain their accepted behavior, including no reset/automatic
run and the possibility of a halted target after success. Public `target.resume` remains CONTROL,
uses the existing closed authorization store and service route, and gains no new request fields or
error codes. The Target workflow only composes that existing capability beneath its already
consumed, exact parent authorization.

## Frozen ownership and dependency direction

Allowed product files:

- `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`: make the physical Target flash adapter
  own the bounded post-flash resume composition and have the runner invoke it only after the
  existing post-flash identity proof and before transport open;
- `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`: inject the exact Probe Service
  CONTROL authorization store into that adapter.

Allowed test files:

- `tools/stm32-toolkit/tests/test_target_runner.py` for exact adapter/runner order, closed binding,
  deadline, failure, and no-retry behavior;
- `tools/stm32-toolkit/tests/test_physical_target_workflows.py` for the public normal/recovery
  production-composition order and publication boundary.

Dependency direction stays `testing_workflows -> TargetTestRunner/PhysicalTargetFlashAdapter ->
ProbeClient + ControlAuthorizationStore -> Probe Service -> existing backend`. No workflow may
reach into a backend or bypass the service protocol.

## Error and lifecycle contract

- The parent Target authorization remains the user-approved, single-use authority for the whole
  exact Target run. The derived CONTROL record is created and consumed synchronously only inside
  that consumed run and binds the same immutable target and firmware facts.
- Post-flash identity mismatch remains `TEST_IDENTITY_MISMATCH` and performs no resume.
- Expiry or outer absolute deadline remains `TEST_TIMEOUT` where the existing deadline wins.
- CONTROL preparation/consumption, resume, or running-proof failure maps to the existing
  `TEST_EXECUTION_FAILED` public result unless an existing more specific stable mapping applies.
- Transport failures after a proved resume retain `TEST_TRANSPORT_UNAVAILABLE`.
- No success or physical TestRun is published until running firmware produces a valid stream.

## Evidence and acceptance

The Luna/max owner commits RED before GREEN and changes only the frozen files. RED must prove the
current sequence opens transport while still halted or lacks the required resume. GREEN must prove
both normal and recovery paths, exact one-resume ordering, exact closed CONTROL binding, post-flash
identity before resume, no resume before successful flash/readback, no retry/second program, and no
publication on failure.

The Sol reviewer uses a fresh detached worktree at the returned code head, reviews the complete
`342447dd6049326e6df439b0adc778657ee548f2..CODE_HEAD` diff, and runs only the affected Target
runner/physical workflow/Probe CONTROL tests under CPython 3.12 with an external run-owned
basetemp. Hardware remains deferred until a new explicit action is authorized.

## Non-goals

- No reset, reset-after-program, second flash, retry, reconnect, normal-first fallback, probe or
  target fallback, unlock, erase-policy change, arbitrary target write, or direct backend access.
- No change to public flash, standalone debug CONTROL authorization, Probe protocol, backend,
  worker, project/schema, firmware, linker, mailbox protocol, CLI, MCP, runtime inventory, error
  vocabulary, package, release, Agent adapter, Python range, CI, or collaboration automation.
- No hardware action, push, PR mutation, merge, tag, release, closure, or remote branch deletion.

