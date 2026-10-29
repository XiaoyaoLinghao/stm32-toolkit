# FLASH-FREQUENCY implementation plan

Current default policy is superseded by the [2026-10-29 100 kHz plan](2026-10-29-flash-default-100khz-plan.md): production omission now selects 100 kHz through the shared defaults; 1 MHz is optional, not a hardware gate. This original slice's historical evidence and other invariants remain unchanged.

Accepted base `449c30e056f614d1ecc9a4340c0ea5feda28f07b`; governing [design](../specs/2026-10-25-flash-frequency-design.md). User has authorized this slice; separate written-plan approval pause waived. Primary specification/reviewer; Claude Code CLI author with configured provider. No remote/hardware/install authority.

1. Implement bounded frequency validation and immutable worker config selection for managed and imported flash, preserving strict recovery compatibility. Keep all existing admission and owned operation/cleanup boundaries.
2. Add CLI/MCP arguments and structured response details/recovery suggestion with exact design eligibility; preserve complete existing failure fields and imported receipt checks.
3. Write meaningful offline tests, update user guide/MCP descriptions and repository flash Skill. Return any boundary conflict before expanding scope. File-only invocation; tests execute separately with exact coordinator commands.
4. Freeze CodeHead; author runs exact native PowerShell pytest commands and primary independently reviews/tests in clean detached review tree. Fixes return to Claude. Run relevant worker/backend/Target/flash regressions, Skill validator and a fresh consumer-guidance simulation; never use hardware or the original project.
5. Primary records source heads, actual commands/results, complete-diff verdict and standard procedure checkpoint, then syncs accepted changes to the local main directory only. Reports name preceding CodeHead, not their own report SHA. Product remains1.3.0.

Author tree: C:/Users/zhy76/.codex/worktrees/build-snapshot-review/STM32-Toolkit; review tree: build-snapshot-final/STM32-Toolkit. Python D:/codex-tmp/kx23/venv/Scripts/python.exe3.12.14 and GCC C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe verified. Source-first PYTHONPATH; installed1.3.0 third-party dependencies read-only. Per-run TEMP/TMP/TMPDIR, basetemp/cache/JUnit under D:/codex-tmp/ff25, separately named by owner. Claude2.1.308 native PowerShell inventory and actual Get-Location verified at launch. Preserve file-only authoring/exact single-command verification split. Do not repeat any prior policy-rejected cleanup.
