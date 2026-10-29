# ATTACH-PROGRESS — reviewed procedure and one-shot hardware validation

Date: 2026-10-29. Procedure/card author, execution owner and result reviewer:
Primary Codex. Independent procedure/card/capture reviewer: local Claude Code CLI,
retaining configured `deepseek-v4.1-flash[1m]` route.

Verdict: **FAILED_AT_ATTACH_HARDWARE_VALIDATION_INCOMPLETE**.
The updated procedure passed independent review and the execution card was filled
and marked READY before the single authorized ordinary 1 MHz flash. That attempt
again failed at attach. New progress evidence ends at `session-create`; the
physical cause and the original IPSR=3 failure remain unverified. Prior
[offline acceptance](implementation-report.md) remains
**SOFTWARE_COMPLETE_HARDWARE_PENDING**. This is not release acceptance.

## Authorization and frozen identities

The current user authorized preparation, independent review of the updated
procedure, and one ordinary 1 MHz flash using the original board and probe, with
first failure stopping, no automatic recovery and no publication. A fresh reply
confirmed the original STM32F429ZG board powered/connected, external IDE detached,
exclusive Toolkit ownership and no device replacement. The authorized normal
workflow includes the previously specified pre-program SYSRESETREQ reset-and-halt,
HALTED confirmation and segment readback. No standalone control was authorized.
This one-attempt authorization is now **consumed**.

- Accepted base: `e4d9118e1c83f139db2959acbd4076a357c37992`.
- Clean executed source/report HEAD before this report:
  `f71efe4b63600c533ddd4263a9905f4816b2c2db`.
- Product/test CodeHead: `e8d7e16436dc7130ec70b6fea0efdc8650ce791a`.
- Branch: `codex/v135-attach-progress`; source:
  `C:/Users/zhy76/.codex/worktrees/v135-attach-progress/STM32-Toolkit`.
- Runtime: existing `D:/codex-tmp/kx23/venv/Scripts/python.exe`, Python 3.12.14,
  pyOCD 0.45.1, explicit candidate Toolkit/Monitor PYTHONPATH. This is a source-only
  experiment, not an installed/package v1.3.5 test. Source metadata remains 1.3.4;
  changes remain Unreleased, planned v1.3.5.
- Project: `C:/work/stm32/fresh-out`; original shared lease/data realm:
  `C:/data/stm32-toolkit`. No isolated registry, force reclaim or lease deletion.
- Target model: `STM32F429ZGTx`; debug target: `stm32f429xg`.
- Probe: `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`.
- Fresh session: `90406903-58b1-472d-a3e6-cd6ac22f120c`.
- Build ID: `8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc`.
- ELF: `build/arm-debug/LWIP.elf`, 1,046,128 bytes, SHA-256
  `b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53`.
- Input snapshot: `09b178c4a285f3033ac35ae9dafbc2431028a0bbbd73de3b9daa89809b0e66d8`,
  `sourceBaseline=input-snapshot-v1`; expected segment readback: 61,516 bytes.
- Initial physical CPU state: UNKNOWN after the prior failed attempt. Current
  power/exclusivity confirmation does not establish CPU state; identity/halt
  verification belongs inside the authorized normal operation.

## Independent entry review and offline readiness

Primary read the standard procedure, current checkpoint and latest execution
report before planning this run. Fresh read-only firmware admission passed;
parent and inert Windows spawn child resolved matching source modules and the
child exited 0. No discovery or device I/O was used. Six project files were
copied and hashed: model, build receipt, firmware identity, previous flash receipt,
MAP and ELF. Existing installed runtime was not modified.

The execution card binds the source/runtime/firmware identities, shared ownership
realm, exact argv, fresh session, selected normal 1 MHz policy, optional progress
semantics, one-call budget, 180-second outer bound, native deadlines, success
evidence, first-failure stop and existing owned cleanup. A guarded-main capture
wrapper rechecks admission and hashes immediately before launching the real CLI,
then exclusive-creates its one-attempt ledger before process startup. It has no
retry/frequency-fallback/recovery path. Outer termination would leave descendant,
lease and target state UNKNOWN; it would not prove successful cleanup.

The first independent invocation executed three exact ordinary material reads,
but the native tool persisted their large outputs and displayed only previews.
Its explicitly **partial** NO_BLOCKERS was retained and was not accepted for
hardware. The coordinator supplied the genuinely unreviewed material in 19
bounded, losslessly ASCII-escaped parts, at most 6,494 bytes each. The second
invocation read every part in order with full results and returned independent
**NO_BLOCKERS**. This reviewed Primary's procedure/card/wrapper, not acceptance
of the implementer's own product diff. Product acceptance remains the prior
Primary complete-diff review and affected offline matrix.

Both invocations registered exactly native PowerShell at inventory, smoke and
main; real harmless startup smoke matched native tool events. The complete review
has 19 exact matched terminal read commands, no unexpected command/scope
discrepancy or pending result, and CLI exit 0. Native numeric command exits were
absent and remain null. No tests or hardware were delegated. Primary reconciled
each surfaced full part against its hash and contents, allowing only CRLF/native
trailing-whitespace normalization. Scope limitations on unprinted unchanged
product internals are retained in the full verdict.

Two coordinator-only preparation errors are retained: the first content comparison
rejected native trimming of trailing whitespace, leaving the card pending; a
prematurely scheduled `--validate-only` then failed its READY assertion before
any hardware operation. The corrected content comparison reconciled all 19 parts.
Only card status/review fields then changed to READY, preserving reviewed operation
fields. Validation of that changed READY card returned `READY_OFFLINE`, exit 0,
`hardwareCalls=0`. No failed hardware operation was retried.

## Single operation and observed result

The wrapper launched exactly one CLI process with `shell=False`, pinned source
cwd/PYTHONPATH and run-local TEMP/TMP/TMPDIR:

```text
D:\codex-tmp\kx23\venv\Scripts\python.exe -m stm32_toolkit.cli --project-root C:\work\stm32\fresh-out flash --data-root C:\data\stm32-toolkit --session-id 90406903-58b1-472d-a3e6-cd6ac22f120c --probe pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c --expected-build-id 8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc --expected-elf-sha256 b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53 --frequency 1000000 --authorized --json
```

The record spans `2026-10-29T02:43:14.680918Z` to
`2026-10-29T02:43:24.490998Z`. Child CLI PID 17560 exited **2** with no outer
timeout, empty stderr and a complete JSON failure response. Coordinator PowerShell
reported exit 1; it is not conflated with the captured CLI exit 2.

| Evidence | Observed value |
| --- | --- |
| Response | `ok=false`, `PROBE_CLOSE_FAILED`, `Probe attach cleanup failed` |
| Primary | `service-attach-deadline`, `reason=timeout`, `sourceCode=PROBE_TIMEOUT` |
| Terminal wait | `service-terminal-wait`, `outcome=timed-out` |
| Worker settlement | `service-worker-abort`, `outcome=succeeded` |
| Subsequent owned cleanup | client close, runner cleanup, backend close, lease release and service stop recorded `succeeded` |
| Target state | `lastVerifiedTargetState=null`; physical state remains UNKNOWN |
| Configuration | normal, requested/configured 1,000,000 Hz, `preProgramReset=sysresetreq`, halt required, automatic retry false |
| Preparation/program/readback | Not reached through the unsuccessful attach; no new successful receipt |

The optional trace has `version=1`, `clock=parent-receipt`, snapshot
`elapsedMs=5983` and these received events:

| Stage entry | Parent receipt elapsed ms |
| --- | ---: |
| worker-dispatch | 0 |
| driver-acquire | 0 |
| probe-enumeration | 2983 |
| prior-attachment-close | 3688 |
| session-create | 3688 |

There is no received `target-resolve-before-open` or `session-open` marker.
In this pinned backend, the `session-create` entry precedes the existing
`_get_driver().create_session(...)`; the next entry follows its return. The default
driver constructs pyOCD `Session(..., auto_open=False, options=...)` there.
The trace narrows offline investigation to this construction boundary and possible
subsequent unreceived-frame/transport timing, rather than proving a line-level
stall. A missing received marker does not prove that a later target-side operation
never happened before owned abort. Receipt gaps are approximate software entry
observations, not precise import/USB/hardware durations or completed-stage proof.
The 5-second normal attach deadline and 1-second terminal wait were retained;
the snapshot's approximately 6-second age is not an extended attach allowance.

The flash workflow awaits successful attach before calling program preparation.
It did not reach the new pre-program reset/halt, programming or readback here.
Selected policy fields do not prove those actions executed or measure SWD clock.
No original IPSR=3 failure was observed in this run, and this is not evidence
that its cause or the reset preparation fix has been validated on the board.

## Preserved evidence and terminal boundary

Evidence root: `D:/codex-tmp/ap135-hw-20261029`.
`reconciled-result.json` binds the actual attempt, raw streams, reviewed/READY
cards, independent review evidence and project snapshots. Source HEAD and all
recorded candidate/pyOCD file hashes remained unchanged through execution.
All six project snapshots retain their pre-run hashes. The existing flash receipt
is still the OLD session `7e6220c6-a3eb-4232-ac8d-2310f883f417`, SHA-256
`db8165a19ee8f8bf0f101f77bd3c4cd822baeae2f8ef349453fa0d07e222a4a0`;
it is not a success receipt for the current session. The READY card is a preserved
pre-run artifact; the exclusive attempt ledger and reconciliation record the
consumed authorization and TERMINAL_STOPPED result.

Successful worker abort/lease-release records do not establish a known physical
CPU state, physical detach or successful terminal-wait cleanup. After failure,
only filesystem/source evidence was read. No recovery, retry, lower-frequency
connection, supplemental target read, reset/halt/resume, power action, lease
manipulation or subsequent hardware access occurred. No package/install, push,
PR mutation, tag or publication occurred. No product/test code changed.

| Artifact under evidence root | SHA-256 |
| --- | --- |
| reconciled-result.json | db075198b56a8972ae2ede0778cc54d3cc587227811ed6bce5af7e5736f19c83 |
| hardware-attempt.json | cdae2edc99b6cccd15c37f91020e4a83a26afce272a4c86b467d9c3331e77da4 |
| flash.stdout.json | cfb848b82b708a4a4cc9953c570b0da47c4d716ffe167f736e112633edb18a65 |
| flash.stderr.log (empty) | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| execution-card.json (READY snapshot) | cfef336a5b65c618642d514b05d4a9ed741adaed06c8f4df5a8fcdc4e224d951 |
| execution-card-reviewed-input.json | c7d7277babc9944a5982c593dabd42e520154e04357e419444094f02cff82b4a |
| preflight.json | 2f3b23e0d619785aa436b4187810f1d6c1b1ed4ed33464a3d5aa1f09e0cc76fe |
| perform_one_flash.py | 2c6b361df79d72a55368b5a700a88a2f2b948568d0629706e73f751222d99b67 |
| procedure-review-verdict.md | b3f9761a795d59fa4689f938d006951dde23885d0a6ebad8895ae2ebae56addf |
| procedure-review-completion-run/summary.json | 44af913a511f430e99f3debba6517850557e912a99f633fc443000207faaba15 |
| review-reconciled.json | 9ecb675d6d144e8db3f28398712c351053bc040a682869afd9fe433358bcd939 |

Next work is offline localization around the pyOCD Session-construction boundary.
Any implementation remains Claude-owned and independently reviewed. A further
hardware attempt requires a new bounded card and explicit authorization; this
report grants none. This one-shot result does not qualify the release, application
execution, same-image cell rewrite, recovery or packaged runtime. Result-only
checkpoint/report edits require no repeat hardware or software matrix.
