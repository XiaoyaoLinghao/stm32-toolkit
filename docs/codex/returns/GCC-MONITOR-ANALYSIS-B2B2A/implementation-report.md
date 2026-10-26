# Monitor analysis and source-context consumers

Verdict: **ACCEPTED_WITH_FIXES**, bounded local software slice, 2026-10-26. Toolkit diagnostic/continuation edges remain the next separate slice.

- Accepted base: `cb95cedcd53d775a2c525d9b3d7f42a4f4db3d41` (B2b1).
- Initial implementation: `071d447c6c4a521ecf2f5b8d93673ee07f9f917b`.
- Final CodeHead before this report: `fe65ff9ede4bd0c29f61bc963d0ceb4f5f2793c7`.
- Branch: `codex/gcc-monitor-consumers`; no remote action or PR.
- Primary owns the [GCC contract](../../../superpowers/specs/2026-10-26-gcc-delivery-contract.md), [consumer plan](../../../superpowers/plans/2026-10-26-gcc-monitor-consumers.md), orchestration, independent full-diff review and acceptance. Local Claude Code CLI implements code/tests through the existing configured `deepseek-v4.1-flash[1m]` route.

Monitor analysis now carries the complete immutable source-baseline/unavailable-Git pair through reference-to-evidence and reference-to-observation projections and checks it when matching batches and TestRuns. Legacy dictionaries retain their original keys. Source-context signatures include a canonical immutable pair projection, so a provenance change invalidates the dependent catalog even with null Git fields. Existing source/build/target/session/probe/lease and lineage checks, analysis thresholds and physical-versus-recorded labels remain unchanged.

Primary independently reviewed the complete five-file accepted-base diff in the clean detached `gcc-delivery-review` checkout at final CodeHead; whitespace checks passed. The new tests exercise real synthetic replay ingestion, analysis publication/readback, changed-pair refusals, legacy serialization and source-catalog invalidation.

| Owner/run | Source | Result |
| --- | --- | --- |
| Claude `maa`; primary `map` | Initial implementation | Each 14 passed, 2 failed; retained |
| Claude `mab` | Initial implementation | 155 passed, 7 failed; retained |
| Claude `mac` | Initial implementation | 47 source-catalog cases passed |
| Claude `mad` | Initial implementation | 15 analysis boundary/authority cases passed |
| Claude `mae`; primary `maq` | Final CodeHead | Each 16 new cases passed |
| Claude `maf` | Final CodeHead | 162 analysis/workflow/CLI cases passed |

All failures arose from one implementation error: the new TestRun comparison called a nonexistent `EvidenceIdentity.git_evidence_document()` method. Claude corrected it to the existing canonical projection of the actual immutable `git_evidence` attribute. No identity comparison or test assertion was removed. The final verification reran both affected groups, including every failure. The 47 source-catalog checks exercise unchanged modules; the 15 boundary cases passed before and do not reach the corrected helper. Those cohorts are explicitly reused, not described as a final-head full matrix. There are 240 distinct author cases with passing evidence; overlapping primary checks are not added. No skips. Existing pytest collection warnings for imported domain classes are non-fatal.

Exact final commands:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/v133-review/STM32-Toolkit' 'fe65ff9ede4bd0c29f61bc963d0ceb4f5f2793c7' 'mae' 'monitor-analysis-new'
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/v133-review/STM32-Toolkit' 'fe65ff9ede4bd0c29f61bc963d0ceb4f5f2793c7' 'maf' 'monitor-analysis'
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' 'fe65ff9ede4bd0c29f61bc963d0ceb4f5f2793c7' 'maq' 'monitor-analysis-new'
```

`D:/codex-tmp/gcc26/{maa,mab,mac,mad,map,mae,maf,maq}` retain exact owner, head, argv, hashes, unchanged-source checks, stdout, JUnit and coverage. Global runs `monitor-analysis-global-{author,verify,method,final-verify}` retain initialization and native events. File-only author session `c16cf03c-1cc0-43e3-bb0b-64be3dfe7c27` and correction `41e3e234-cadf-4975-b289-23e97abb6d99` used only the requested file tools, without scope violations. Final verify session `233e7d72-ce41-4d6c-95ce-54d89dd4afdc` had matching native PowerShell inventory, a real harmless smoke and both designated commands with timeout 600000. Missing native numeric exits stay null; test-process records separately show exit 0.

Only synthetic recorded/software fixtures were accessed. No physical hardware, original firmware, installed runtime, version, release, remote or global configuration changed. Toolkit diagnostic/continuation/MCP pair propagation and cross-branch GCC-to-normal-managed-flash integration remain outstanding; this is not complete-product or release acceptance.
