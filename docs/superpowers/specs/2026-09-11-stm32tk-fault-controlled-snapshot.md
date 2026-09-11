# Controlled Fault snapshot — proposed contract

Status: PROPOSED, governing behavior approval required before implementation. Accepted source base: `e8563a6fd0758350e91d24be71fa47292684693d`. Main owns specification/integration/review; one Luna/max owner will implement after approval. Active integration branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. No hardware, installation or remote action is authorized by this proposal.

## Problem and evidence

`hardware_workflows.py:fault_workflow` (1146–1166) calls `_bind_and_run`, whose line 1012 fixes OBSERVE. `probe/service.py:1010` requests halt-on-connect only for MODIFY; `probe/pyocd_backend.py:979–988` otherwise resumes and verifies running. `debug/fault.py:227–245` translates non-halted core-register access into FAULT_TARGET_NOT_HALTED. The actual 05 response records state=running and no Fault report. This is a public workflow capability gap, not evidence that the board is broken. Its original failed invocation and report classification remain historical evidence.

Existing evidence suffices to identify the conflict; no repeat hardware connection is needed. Do not relax Fault's initial/final halted-state checks, silently escalate all OBSERVE operations, or repurpose MODIFY merely to obtain a halted attach.

There are also two explicit permission checks: `debug/firmware.py:_endpoint` line 95 and `debug/fault.py:_endpoint` line 125 currently require OBSERVE. Switching the wrapper level alone would fail these checks. Both must retain OBSERVE as their default and accept CONTROL only through an explicit keyword-only expected-operation-level argument supplied by the controlled Fault workflow. The expected value must be exactly OBSERVE or CONTROL, must equal the actual endpoint at every existing validation point, and must never be inferred from a forged endpoint facade. MODIFY remains rejected. The Fault model and halted-state analysis contract remain unchanged; `debug/read.py` stays strictly OBSERVE.

## Three scenarios and boundaries

1. Existing callers omit the new option: current observe-only behavior and existing result/errors remain unchanged, with no extra target control.
2. An explicitly authorized caller requests a controlled snapshot of running firmware: one exclusive CONTROL session, exact firmware binding, one authorized halt, stable Fault analysis, then one authorized resume with running-state verification and owned cleanup.
3. Binding, halt, analysis, resume or cancellation fails: preserve the initiating error and concrete cleanup evidence; do not emit a successful workflow after failed restoration; never reset, flash, steal a lease or automatically retry.

This is a temporary-halt snapshot, separate from the existing non-halting sample path. Source mapping, sampling cadence, Target test execution, diagnostics lineage, T10 capture and new backends are out of scope. It does not promise preservation of a pre-existing halted target: current attach semantics may already resume it. The option explicitly requests a running postcondition and is intended for the approved running-board observation scenario.

## Public behavior and ownership

Add optional `halt_for_analysis: bool = False` to FaultWorkflowRequest, CLI `fault --halt-for-analysis`, and MCP `haltForAnalysis=false`. The true option is the explicit authorization for one halt and restoration in this operation; it is never inferred from a selected probe or prior call. Reject non-boolean input before service creation. No caller-selected target, memory range, identity, token or persistent control policy is added.

The Fault-specific workflow owns the lifecycle; other `_bind_and_run` callers remain OBSERVE. Reuse Probe Service CONTROL, the supervisor's existing ControlAuthorizationStore and ControlAuthorizationClient.prepare plus the existing client.target_control execution pattern used in testing/target.py. Do not use ControlAuthorizationClient.execute for the intermediate halt because it closes the client. Each halt/resume receives a distinct fresh authorization; never copy or replay a token. Binding sources are the validated DebugFirmwareBinding (workspace, logical project, session, git_head revision, build/ELF) and current target_identity, checked against selected probe/target. The service remains the authority for atomic consumption and identity/state revalidation.

After bind, verify running, prepare/consume halt and prove halted before invoking existing FaultAnalysisRequest/analyze_fault. A normally completed halt followed by analysis failure still requires one bounded restoration attempt. For ambiguous halt timeout/cancellation, first obtain current identity/state within the existing owned session: resume only when the same target is positively verified halted; if running, record restoration already satisfied; if ownership/identity/state is unavailable, report unknown and stop instead of guessing. Apply the existing bounded cancellation/cleanup pattern. A resume timeout/failure is terminal; no second control command or automatic reconnection.

Retain the canonical Fault report schema and existing analyzer errors. Successful controlled workflow requires restoration and lease/worker cleanup. Record lifecycle facts in OperationResult.details, not fabricated Fault fields: mode, verified pre-analysis/post-analysis state, halt/resume outcomes and cleanup. Use existing control and HARDWARE_CLEANUP_FAILED semantics; no generic error catalogue or diagnostic framework.

## Implementation boundary and required evidence

Product files under `tools/stm32-toolkit/src/stm32_toolkit/`: `hardware_workflows.py`, `cli.py`, `mcp_server.py`, `debug/firmware.py` and the endpoint/entry signature only in `debug/fault.py`; corresponding existing workflow/CLI/MCP/firmware/Fault tests and the debug-firmware usage skill. Probe protocol/service/backend, debug/model.py, debug/read.py and Fault register/state analysis internals are reuse boundaries, not planned edit targets. If they cannot support this contract, return to main before expanding scope.

Luna/max verifies the actual public CLI/MCP option through existing seams, including: omitted option has no control; invalid authorization input makes no service; complete running→halted→analysis→running order; firmware mismatch before control; one-shot control authorization identity; analysis failure restores; cancellation/ambiguous state does not guess; restore failure cannot PASS; unrelated variable/sample/register paths stay observe-only. Run affected existing regressions once, with D-only run-owned outputs. Main reviews the complete base-to-CodeHead diff independently. No new packaging or physical run until software acceptance and fresh scoped deployment/hardware authorization. Existing IDE/100ms/Target/CLI/MCP PASS remains scoped to its original bytes and behavior.
