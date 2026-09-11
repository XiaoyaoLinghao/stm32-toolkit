# Controlled Fault Snapshot Implementation

- Accepted base: `71184baf04fb5df93dd18d69aee87a07f5dee27f`
- CodeHead before this report commit: `333f456dfd0382ceb6b1904e5e29a7592a9ebda9`
- Usage documentation follow-up: `ee0e7a01c30380a69d56a5744fc2e054fd04e789` (`docs: document controlled Fault snapshot usage`)
- Branch: `codex/fault-controlled-snapshot`

The implementation adds an explicit default-false Fault halt selection through the CLI, MCP wrapper and registered schema. The selected path uses a CONTROL service with the observation worker configuration (100 kHz), binds the validated firmware, validates live PyOCD identity using empty-profile debug-target defaults or explicit worker profile, and preserves the complete identity snapshot for separate halt and resume authorizations. It verifies running to halted to analysis to running, keeps recovery within one absolute 45 second budget, records controlledSnapshot lifecycle facts, and preserves initiating errors when restoration or cleanup fails. The existing OBSERVE path and Fault report schema remain unchanged. CONTROL Fault identity checks use target_identity reads and do not reattach after the halt.

The public result boundary retains details only for results carrying `controlledSnapshot`; ordinary success envelopes keep their existing details behavior. Cleanup failure copies original details only for controlled snapshots, keeps the old attachDiagnostic-only behavior for ordinary operations, and passes through the same root sanitization boundary. Recovery deadline checks occur before invoking the factory, so an expired recovery operation does not create an unowned coroutine.

The debug-firmware usage skill now documents the explicit `haltForAnalysis=true` MCP / `--halt-for-analysis` CLI selection, the one halt/analyze/resume lifecycle, the running postcondition, and the fail-closed no-retry/no-reconnect/no-reset/no-flash boundary. The skill change is documentation only and does not require another product test run.

## Verification

The test runtime was Python 3.12 with pytest 8.4.2 from `D:\codex-tmp\stm32tk-vs10a-corrective-review-preflight-20260908\review-venv-system`. `PYTHONPATH` pointed to this worktree's `tools\stm32-toolkit\src`. The final suite ran from the worktree root so the Fault fixture's repository-relative ELF path resolved. Process-scoped `TEMP`, `TMP` and pytest basetemp used short D-drive paths because the Windows staging fixture can reach the 260-character path limit.

The final five-module command was:

```powershell
$env:PYTHONPATH = 'D:\workspace\stm32tk-fault-controlled-snapshot-impl\tools\stm32-toolkit\src'
$env:TEMP = 'D:\codex-tmp\fc-final-all'
$env:TMP = 'D:\codex-tmp\fc-final-all'
& 'D:\codex-tmp\stm32tk-vs10a-corrective-review-preflight-20260908\review-venv-system\Scripts\python.exe' -m pytest --basetemp='D:\codex-tmp\fc-final-all\p' tools/stm32-toolkit/tests/test_fault.py tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_cli_hardware.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_hardware_workflows.py
```

Result: **392 passed in 113.61s (1:53), exit 0**. The retained output is `D:\codex-tmp\fault-controlled-snapshot-20260911\final-five-output.txt` and the exit marker is `final-five-exit.txt`. The output includes the existing fatal-enumeration test's expected `SystemExit(8)` task traceback; pytest still exited 0.

Additional final-candidate checks were **5 passed, 87 deselected, exit 0** for the cleanup boundary after the envelope correction, **3 passed, 51 deselected, exit 0** for both CONTROL analyzer snapshot/default mapping cases, `python -m compileall -q tools/stm32-toolkit/src/stm32_toolkit` exited 0 with `PYTHONPYCACHEPREFIX=D:\codex-tmp\fc-final-compile2`, and `git diff --check` was clean for the implementation commits.

A first Fault command from the package directory failed during fixture setup because the test uses a repository-root relative ELF path; the same tests passed from the repository root. The long staging path failure was reproduced on the accepted base at the Windows 260-character boundary and avoided with the attributed short D-drive basetemps; neither was a product failure.

Only offline fixtures and the direct PyOCDBackend identity function were used. No probe enumeration, hardware attach, flashing, deployment, network or remote operation was performed. A one-off manual control diagnostic was used only to inspect existing entry behavior; it was not added to the product or test framework and emitted no authorization digest in retained evidence.

Cleanup of the attributed disposable basetemp/compile roots was attempted with literal paths and rejected by the active policy. No blocked baseline or shared directory was bypassed or removed.

## Independent review and local integration

Verdict: **SOFTWARE_COMPLETE_HARDWARE_PENDING**. The primary agent reviewed the complete accepted-base-to-CodeHead difference in the clean isolated `D:\workspace\stm32tk-fault-controlled-snapshot-review` worktree, including the final `333f456dfd0382ceb6b1904e5e29a7592a9ebda9` correction and subsequent usage/report changes at `802d6547c9655d3c268bc5d52ada5b9c6461c0ec`. No product blockers remain. Product/test/usage bytes in the local integration worktree match that reviewed candidate; no packaging, deployment, hardware or remote action was performed.

Review closed the production empty-profile identity mapping mismatch, preserved the validated live snapshot for fresh authorizations, removed post-halt reattachment, retained 100 kHz configuration, and checked the absolute restoration budget. The controlled result now preserves lifecycle/initiating-error details through sanitized cleanup while ordinary success and cleanup-failure envelopes retain their prior behavior. Existing halted-register stability and default OBSERVE paths remain in place.

The reviewer independently ran four existing integration instances against `ae1ab87f`: normal controlled lifecycle, analyzer-error plus cleanup failure, and both production-analyzer snapshot modes without reattachment. All four passed. Two analyzer instances first stopped at fixture setup because the reviewer selected package cwd; root cwd resolved the unchanged fixture, and only those unexecuted instances were rerun. The final correction only narrows ordinary cleanup-error details; its new regression and affected default/controlled boundaries passed in the implementer's final 392-test suite at the final product bytes. Minimum reviewer evidence: `primary-review-checks.log`, `primary-review-analyzer.log` and their exit markers in the same evidence directory. Final complete diff check passed. The expected fatal-enumeration fixture traceback in the suite log is not an actual hardware event.

The SOP increment at `a7bb705a8cd52caaf1f42ebcab7228379ebfb4ba` received an independent read-only ACCEPTED verdict from acceptance_regression_ledger: deployed/default versus candidate behavior, root cwd, authority and recovery budget are correctly separated. T9 remains accepted by evidence reuse; FullFault physical evidence, remaining Task7 observations, T10, Task11/12 and VS10-A remain incomplete. Current installed runtime remains the previously verified e88 candidate. A later deployment and finite controlled Fault hardware run require fresh scoped authorization and an execution card sized for the full lifecycle.

Automatic review also rejected cleanup of the review-owned `D:\codex-tmp\fcr1`, `fcr2`, and `fcr1-t` directories with `blocked by policy`. They were retained without alternate deletion attempts, along with the previously denied baseline/implementation output directories.
