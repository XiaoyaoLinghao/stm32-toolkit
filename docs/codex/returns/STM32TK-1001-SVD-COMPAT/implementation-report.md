# STM32TK-1001 SVD compatibility implementation report

## Ownership and boundary

- Accepted implementation base: `0cdd142f80421c6aea59e81e963936779b05f00f`.
- Code/tests head before this report-only commit: `798e6319c8e8777ea815723b6f8ed1bf59df0c4a` (tree `748386ec6db144a12a6219ecf0ef6b674e80c5a4`).
- Implementation branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- The SVD compatibility slice changed only the accepted product/test lineage through the Task 3 GREEN commit. This report is the only tracked path changed by this final report step.
- No hardware, pyOCD/backend, network, remote Git, campaign-project, runtime, or firmware action was performed. The implementer does not accept this result; it is awaiting independent Sol review.

## RED/GREEN lineage

- Task 1 RED tests were retained in the ledger as `5d497c0f` and `5823ddae`; Task 1 GREEN was `7df0898b1b10ed9e9ff233ba84afb0380362cb81`.
- Task 2 RED was `c6c4a68243aa25e0ae25657c6ca9052b1246d4ae`; Task 2 GREEN was `9df5cf7fa7cac241cc3623f32f1ea802ec7b65ef`.
- Task 3 RED wave 1 was `e7785fb1ecea8fa11ad584aea56ebe6d03792959`; GREEN wave 1 was `f5647d9ffde03f5f8d587cbd58efdd609f38e8be`.
- Task 3 RED wave 2 was `845a6aabc376467f466a7692198e8afb42a5eb2f`; GREEN wave 2 was `798e6319c8e8777ea815723b6f8ed1bf59df0c4a`.
- Wave 2 RED had one expected Monitor forwarding failure and 20 passing sentinels. GREEN added only the two required forwarding arguments and produced 21 passing targeted nodes plus `161 passed, 1 skipped` in the planned five-file regression.

## Aggregate verification

The focused aggregate used CPython 3.12, `-p no:cacheprovider`, and external basetemps over these complete files: `test_project_model.py`, `test_generation.py`, `test_svd.py`, `test_debug_firmware.py`, `test_debug_read.py`, `test_hardware_workflows.py`, `test_monitor_observation.py`, `test_cli_hardware.py`, `test_mcp_hardware.py`, `test_mcp_server.py`, and `test_mcp_roots.py`.

The first exact invocation used `python.exe -I` with inline source-path insertion. It exited 1 with `875 passed, 3 skipped, 2 failed in 198.06s`; both failures were existing subprocess lazy-import checks reporting `ModuleNotFoundError: stm32_toolkit`, because `-I` removed the source path from those child interpreters. This was classified `ENVIRONMENT/INVOCATION`, not a product failure.

The corrected invocation used the same CPython 3.12 and test set with `PYTHONPATH=tools/stm32-toolkit/src`, `-p no:cacheprovider`, and external basetemp `C:\tmp\stm32tk-1001-task4-aggregate-env-20260827`. It exited 0 with `877 passed, 3 skipped in 201.64s`.

Representative command form, with the complete file list above passed to `pytest.main`, was:

```text
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src'; & C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe -c "import sys; sys.path.insert(0, r'C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src'); sys.path.insert(0, r'C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'); import pytest; raise SystemExit(pytest.main([...]))"
```

## Offline external SVD proof

The original campaign project was never edited. Its observed pre-existing state was HEAD `9aae7ffd860405fadb7ac5f6278bcbb93add8d16`, tree `536a5aaedfefb35e7755cef22e9410b4bc6f27ea`, status `M .stm32-project.json` and `?? svd/`. The original manifest SHA remained `773b95786d72ee363b093ae6f6fe96e7f69ae97bf3ce30875b2ee225e16363cf`; the original SVD was `C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math\svd\STM32F429.svd`, size `2118594`, SHA-256 `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`.

A run-owned copy was created at `C:\tmp\stm32tk-1001-task4-svd-proof-20260827\project-standard-math-copy`. Only that copy received schema3 `debug.svdDevice = STM32F429` and the 12 requested readable ranges, represented as implicit `r--` bindings. Product model loading and exact SVD selection were run with no backend import/action:

- target: `STM32F429ZGTx`;
- document: `STM32F429` from `svd/STM32F429.svd`;
- readable regions: 12, all `r--`, unique bounded names;
- parsed registers: 1536;
- `GPIOE.ODR`: address `0x40021014`, size 4;
- `ODR4`: bit offset 4, width 1;
- `pyocd` in `sys.modules`: false before and after.

The self-contained run-owned proof is [offline-svd-proof.json](C:/tmp/stm32tk-1001-task4-svd-proof-20260827/offline-svd-proof.json), SHA-256 `64f5b481a3928059650051b43b25b1c7519fde5618cf45e640caab8918ff4917`. Its copy SVD SHA equals the original. An initial proof attempt exposed a decimal conversion typo for the final range (`0xE003E000` instead of `0xE0042000`); this was corrected only in the run-owned copy and the final proof exited 0. This is classified `REPORT_FIXTURE_CONVERSION_TYPO`.

## Diff and scope audit

At code/tests head, `git diff --check 0cdd142f80421c6aea59e81e963936779b05f00f...HEAD` exited 0. The corresponding name audit included inherited accepted docs/spec/plan and product/test paths from earlier slices; the current Task 3 commits themselves were limited to the authorized debug/monitor product and test paths. Post-commit status was clean. No remote mutation occurred.

## Cleanup

The exact run-owned aggregate basetemps were:

- `C:\tmp\stm32tk-1001-task4-aggregate-20260827` (failed invocation evidence);
- `C:\tmp\stm32tk-1001-task4-aggregate-env-20260827` (successful invocation evidence).

An exact `Remove-Item -LiteralPath ... -Recurse -Force` cleanup was attempted and rejected by execution policy. Both paths were rechecked and remain; no alternate deletion or policy bypass was used. The run-owned SVD copy and proof JSON remain intentionally as minimum external-input evidence.

## Implementer verdict

The assigned SVD compatibility implementation and offline proof are complete against the stated software gates. This is an implementer report only, not an acceptance decision; independent Sol complete-diff review remains required.
