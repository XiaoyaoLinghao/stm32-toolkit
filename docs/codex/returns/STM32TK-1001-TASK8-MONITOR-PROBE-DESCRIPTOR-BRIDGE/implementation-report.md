# STM32TK-1001 Task 8 Monitor probe descriptor bridge implementation report

Slice verdict: `ACCEPTED`.

This closes only the offline six-field Toolkit descriptor to four-field Monitor-public bridge
defect. It does not complete the pending physical Monitor observations, Task 9, Task 10, VS10-A, or
release acceptance.

## Ledger and scope

- Full accepted base: `b464d9573ba0cba71bee2f600b4ab73d1de70460` (tree
  `c922fae99665ad71ea25d4a95f6b14ee09522762`).
- Specification/plan head: `2973f6f7ec5c2f50c510aef0ddd375b9226e3d9b`.
- Implementation behavior CodeHead: `331c2ae9646e2e9fba192cafaccca8dc85c84747`.
- Final reviewed CodeHead: `e80831099f2a977ecc2723b314be05e2051c701d` (tree
  `1db616a4524911f05375666a31709fabda72d38f`). The only change after the behavior CodeHead renames
  the focused test to describe its final GREEN behavior.
- Sole continuation branch:
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Specification, plan, and independent review owner: GPT-5.6-sol.
- Product implementation and implementation-test owner: one GPT-5.6-luna/max agent.
- Product/test files changed: `tools/stm32-monitor/src/stm32_monitor/runtime.py` and
  `tools/stm32-monitor/tests/test_runtime.py`. The accepted-base diff also adds the approved design
  and plan. No other tracked path changed.
- Hardware, runtime installation/replacement, candidate packaging, firmware/project mutation, and
  remote actions were outside scope and were not performed.

## Resulting behavior

Monitor now accepts either a homogenous exact four-field constructor-seam listing or the homogenous
exact six-field production Toolkit listing. For production descriptors it uses the existing public
Toolkit `ProbeDescriptor` contract to verify the hardware identifier, derived public selector, and
derived fingerprint, while retaining Monitor's bounded display-text validation.

Successful results are rebuilt as exact four-field mappings containing only `probeId`, `vendor`,
`product`, and `boardName`. Raw `hardwareId` and `probeFingerprint` do not cross the Monitor public
result. Mixed schemas, missing or extra fields, invalid identity facts, invalid metadata, more than
64 probes, and duplicate selectors fail with the unchanged
`MONITOR_PROBE_ENUMERATION_FAILED` / `Debug probe enumeration failed` / empty-details result.

The production discovery path can now reach the existing observation factory for a matching
selector. No attach, timeout, lifecycle, cleanup, workspace/session, Toolkit workflow, worker,
PyOCD, protocol, or schema behavior changed.

The retained exact four-field injected factory is an internal constructor-seam compatibility path.
It is not declared as a new Toolkit production descriptor format or external Monitor request.

## Implementation evidence

At the product-unchanged SpecPlanHead, the new real `probe_list_workflow` plus fake-backend seam
failed as expected because Monitor rejected the six-field descriptor. The RED log records one
failure and is retained at
`D:\codex-tmp\stm32tk-1001-monitor-probe-contract-evidence\red-node-output.txt` (SHA-256
`d6c5071bafc0a6b9942bd3820dceb1c90cb613269150cdde52586c3f48e9cb14`).

The campaign D runtime intentionally had no pytest. That first attempt was classified ENVIRONMENT
and did not install or modify anything; the 106-byte record remains as
`red-environment-missing-pytest.txt`. Tests then used the allowed non-temporary base CPython 3.12.10
pytest with explicit D-worktree source paths and D-only basetemp/cache.

The implementation owner reported:

- production seam: 1 passed;
- focused production/identity/privacy cases: 9 passed, 50 deselected;
- affected discovery/connect regressions: 7 passed, 52 deselected;
- final test-name correction node: 1 passed;
- `git diff --check`, AST parse, allowed-file audit, and clean worktree: passed.

The retained final focused and affected logs have SHA-256
`99696f1e1c9d2479b13e445bce618f070634eeac03ee1400b18b0df0500ab9d7` and
`955417cd39920dcf0c4801e96e8c1f28584c1d65c0ae870082da9400c015c2ba`.

## Independent review

Sol reviewed the complete accepted-base-to-final-CodeHead diff in the separate clean detached
worktree
`D:\codex-tmp\stm32tk-1001-monitor-probe-contract-review-331c2ae9`. The review confirmed the exact
four/six-field closed union, homogenous-list requirement, production identity consistency checks,
four-field-only projection, duplicate rejection, stable empty-detail error mapping, and absence of
changes outside the approved four tracked files. `git diff --check` and an AST parse of the two
modified Python files passed.

Against final CodeHead, the reviewer ran the production workflow seam, all eight invalid
shape/identity parameters, existing four-field server-owned discovery/connect behavior, and the
existing 64-probe/public-value boundary. Result: 11 passed in 2.56 seconds.

The first review found one misleading test name; Luna changed only that name in
`e80831099f2a977ecc2723b314be05e2051c701d` and passed the renamed node. The reviewer verified the
correction diff is exactly one line removed and one line added, then ran the 11-node review set at
that final CodeHead.

No open product finding remains for this slice.

## Preserved boundaries

Attempt 7 remains a historical physical Target workflow PASS and was neither rerun nor weakened.
The later OBSERVE attempt's discarded inner worker/backend branch remains `UNDETERMINED`; this fix
does not retroactively prove which folded branch occurred in that run.

Still incomplete: typed `testtime`, SVD `GPIOE.ODR`/PE4, correlated Monitor observation, the three
recorded PyOCD protocol baseline failures, Task 9 handoff/parity, Task 10 real-fault closure, and
VS10-A as a whole. No full repository, release, package, firmware, launcher, runtime, or hardware
matrix was run.

The review basetemp/cache were run-owned and disposable, but the first exact recursive cleanup
command was rejected by automatic policy before a cleanup process started. It was not retried or
bypassed; the D-only review basetemp/cache remain. All diagnostic and implementation evidence was
preserved.
