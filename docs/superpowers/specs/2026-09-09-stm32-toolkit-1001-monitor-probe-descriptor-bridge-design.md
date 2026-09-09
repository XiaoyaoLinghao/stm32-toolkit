# STM32TK-1001 Monitor probe descriptor bridge correction design

Status: approved by the user's 2026-09-09 instruction to continue the local repair.

## Ledger and authority

- Module/phase: STM32TK-1001 Task 8 follow-on Monitor probe discovery correction within the
  VS10-A legacy-hardware closed-loop campaign.
- Full accepted base: `b464d9573ba0cba71bee2f600b4ab73d1de70460` (tree
  `c922fae99665ad71ea25d4a95f6b14ee09522762`).
- Sole continuation branch:
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Specification/plan owner and independent reviewer: GPT-5.6-sol.
- Product implementation and implementation-test owner: one GPT-5.6-luna agent at reasoning
  effort `max`.
- Local commits and a final clean fast-forward of the sole continuation branch are authorized.
- Hardware/probe operations, runtime installation or replacement, candidate packaging, firmware or
  campaign-project changes, push, PR mutation, merge, tag, release, closure, and remote branch
  deletion are not authorized.
- Active PR: not established by local evidence. Ownership override: none.

## Diagnosed defect

The default Monitor probe-list factory is Toolkit `probe_list_workflow`. A successful Toolkit
workflow returns each `ProbeDescriptor` with the exact six fields `probeId`, `hardwareId`,
`probeFingerprint`, `vendor`, `product`, and `boardName`. Monitor currently accepts only exact
four-field items (`probeId`, `vendor`, `product`, `boardName`), so every successful non-empty
production listing fails before observation creation with `MONITOR_PROBE_ENUMERATION_FAILED`.

The retained historical attempt does not expose whether its worker enumeration succeeded, so this
design corrects the independently proven product seam without relabeling that attempt's inner cause.

## Runnable user scenarios

1. **List one real-contract descriptor.** Given a successful production `probe_list_workflow`
   result containing one valid six-field descriptor, `monitor.probes.list` succeeds and returns only
   the four Monitor-public fields. Neither raw `hardwareId` nor `probeFingerprint` crosses the
   Monitor protocol boundary.
2. **Connect through production discovery.** Given the same valid six-field listing and a matching
   public selector, `monitor.probe.connect` passes discovery and reaches the existing observation
   factory exactly once. Existing attach, firmware, sampler, release, and error behavior is unchanged.
3. **Fail closed on invalid identity or shape.** A six-field descriptor with a missing or extra
   member, invalid hardware identifier, selector/hardware mismatch, fingerprint/hardware mismatch,
   invalid display text, a mixed four/six-field listing, or a duplicate public selector returns the
   existing stable `MONITOR_PROBE_ENUMERATION_FAILED` with empty details and never calls the
   observation factory.
4. **Retain the existing constructor seam.** A homogenous exact four-field listing supplied through
   the existing `MonitorRuntime(probe_list_factory=...)` injection seam retains current behavior.
   This is compatibility for the existing internal/test seam, not a new Toolkit production result
   schema or a new external Monitor request format.

## Frozen contract

`MonitorRuntime._list_probes` continues to require a successful `OperationResult` whose `data` is a
mapping and whose `probes` member is the tuple snapshot produced by `OperationResult`. The list is
bounded at 64 entries. Empty listings remain valid and contain no schema choice.

For non-empty listings, every item must be a mapping and the whole listing must use exactly one of
these closed schemas:

- Compatibility schema: `probeId`, `vendor`, `product`, `boardName`.
- Production schema: those four fields plus `hardwareId` and `probeFingerprint`.

The production schema is validated using the existing Toolkit `ProbeDescriptor` identity contract:
`hardwareId` must be a valid hardware probe ID; `probeId` must equal the public selector derived
from it; and `probeFingerprint` must equal the fingerprint derived from it. Monitor's existing
bounded NFC display-text and public-selector checks still apply. The compatibility schema receives
the same existing four public-field checks. Mixed schemas and arbitrary extra keys fail closed.

After validation, Monitor sorts and deduplicates by `probeId`, retains no raw identity value, and
constructs a fresh four-field public projection. `hardwareId` and `probeFingerprint` are validation
inputs only and must not appear in a Monitor result, binding, status, log, details mapping, or error.

Factory exceptions, upstream non-OK results, invalid descriptor results, and duplicates keep the
current public code/message/details:

- code: `MONITOR_PROBE_ENUMERATION_FAILED`
- message: `Debug probe enumeration failed`
- details: empty

No lifecycle, timeout, cancellation, cleanup, operation ordering, workspace/session identity, or
hardware access behavior changes. Monitor remains the sole owner of its four-field public discovery
view; Toolkit remains the source of truth for the six-field probe identity descriptor.

## Dependency and implementation boundary

The production change is limited to:

- `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- `tools/stm32-monitor/tests/test_runtime.py`

Runtime may construct the existing Toolkit `ProbeDescriptor` to reuse its selector/fingerprint
identity validation and then create a new Monitor-public mapping. It must not import private client
helpers, change Toolkit descriptor/schema files, add a new adapter, or persist identity state.

## Non-goals

- No attempt to recover the discarded inner error from the historical observation.
- No change to PyOCD, worker IPC, Toolkit Probe Service, `probe_list_workflow`, descriptor schemas,
  selector/fingerprint algorithms, or public Monitor protocol schemas.
- No broad error-diagnostic redesign or new public error details.
- No change to accepted post-flash reset/v2-terminal behavior.
- No hardware enumeration, connect, attach, read, halt/resume, reset, flash, catalog, or sampling.
- No runtime bootstrap/promotion, packaging, release matrix, firmware build, or full-repository suite.
- No claim that typed `testtime`, SVD `GPIOE.ODR`/PE4, correlated Monitor observation, Task 9,
  Task 10, or VS10-A is complete.

## Acceptance evidence

Luna/max must first preserve a focused RED proving the real six-field production seam fails at the
accepted base, then implement and pass:

- real `probe_list_workflow` plus injected fake backend through Monitor, with four-field-only output;
- matching connect reaches the observation factory;
- exact invalid production shape and identity mutations fail closed without observation;
- mixed schemas and duplicate selectors fail closed;
- existing four-field injection behavior and affected discovery/connect regressions remain green;
- source file scope, `git diff --check`, exact CodeHead/tree, and clean worktree.

Sol independently reviews the complete accepted-base-to-CodeHead diff in a separate clean detached
worktree and reruns the focused production seam, invalid-identity/privacy cases, and affected
regressions. The historical attempt 7 PASS and all named incomplete gates remain unchanged.
