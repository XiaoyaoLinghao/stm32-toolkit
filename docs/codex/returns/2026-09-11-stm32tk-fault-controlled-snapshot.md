# Controlled Fault Snapshot Implementation

- Accepted base: `71184baf04fb5df93dd18d69aee87a07f5dee27f`
- CodeHead before this report commit: `ae1ab87f64a4c366462f207091fd1e27c9bb846e`
- Branch: `codex/fault-controlled-snapshot`

The implementation adds an explicit default-false Fault halt selection through the CLI, MCP wrapper and registered schema. The selected path uses a CONTROL service with the observation worker configuration (100 kHz), binds the validated firmware, validates the live PyOCD identity using the empty-profile debug-target defaults or explicit worker profile, and preserves the complete identity snapshot for separate halt and resume authorizations. It verifies running to halted to analysis to running, keeps recovery within one absolute 45 second budget, records controlledSnapshot lifecycle facts, and preserves initiating errors when restoration or cleanup fails. The existing OBSERVE path and Fault report schema remain unchanged. CONTROL Fault identity checks use target_identity reads and do not reattach after the halt.

The public result boundary retains details only for results carrying `controlledSnapshot`; ordinary success envelopes keep their existing details behavior. Cleanup failure now passes through the same root sanitization boundary and retains controlled snapshot and initiating-code facts. Recovery deadline checks occur before invoking the factory, so an expired recovery operation does not create an unowned coroutine.

## Verification

The test runtime was Python 3.12 with pytest 8.4.2 from `D:\codex-tmp\stm32tk-vs10a-corrective-review-preflight-20260908\review-venv-system`. `PYTHONPATH` pointed to this worktree's `tools\stm32-toolkit\src`; each run used process-scoped `TEMP`, `TMP` and a short D-drive basetemp because the Windows staging fixture can reach the 260-character path limit.

Post-CodeHead focused checks:

- From `tools\stm32-toolkit`, `tests/test_hardware_workflows.py -k "controlled or public_result or closed_production_worker_selection"` with basetemp `D:\codex-tmp\fc-impl-b7\p`: **19 passed, 72 deselected, exit 0**.
- From the repository root, `tools/stm32-toolkit/tests/test_fault.py -k "control_analyzer"` with basetemp `D:\codex-tmp\fc-impl-b10\p`: **3 passed, 51 deselected, exit 0**.
- From `tools\stm32-toolkit`, `tests/test_hardware_workflows.py -k "cleanup_failure or cleanup_success_merges or raw_operation_exception or cancellation_waits or repeated_cancellation"` with basetemp `D:\codex-tmp\fc-impl-b11\p`: **10 passed, 81 deselected, exit 0**.
- `python -m compileall -q tools/stm32-toolkit/src/stm32_toolkit` with `PYTHONPYCACHEPREFIX=D:\codex-tmp\fc-impl-compile-final`: **exit 0**.
- `git diff --check ae1ab87f^ ae1ab87f`: **exit 0**.

Before the final identity/detail review corrections, the five affected modules were run once and produced **388 passed**: Fault 53, debug firmware 137, CLI hardware 47, MCP hardware 62 and hardware workflows 89. The post-CodeHead checks above cover the changed identity, result-boundary, cleanup and recovery seams without repeating that full run. A first Fault command from the package directory failed during fixture setup because the test uses a repository-root relative ELF path; the same two tests passed from the repository root. The long staging path failure was reproduced on the accepted base at the Windows 260-character boundary and avoided with the attributed short D-drive basetemps; neither was a product failure.

Only offline fixtures and the direct PyOCDBackend identity function were used. No probe enumeration, hardware attach, flashing, deployment, network or remote operation was performed. A one-off manual control diagnostic was used only to inspect the existing entry behavior; it was not added to the product or test framework and emitted no authorization digest in retained evidence.
