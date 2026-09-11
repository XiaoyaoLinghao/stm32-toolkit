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
