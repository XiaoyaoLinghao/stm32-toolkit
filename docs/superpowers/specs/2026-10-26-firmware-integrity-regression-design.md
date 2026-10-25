# External firmware integrity regression design

Accepted base `8e3aa106d07cbc11547d16be035a719c1f2c605f`. This offline test-only slice continues the authorized v1.3.1 regression goal. Primary owns specification, orchestration, independent complete-diff review and acceptance; local Claude Code CLI using the existing provider owns implementation and implementation verification. No remote, installation or hardware action is assigned.

## Existing contract to verify

Firmware import is an immutable, explicitly authorized snapshot. Admission rebuilds that snapshot and rejects invalid shape, incompatible version, changed bytes and project/data-root/identity mismatches. Rejected operations cannot repair, overwrite or silently accept corrupted records. Failed publication may clean only the exact staging files and directory owned by that call; foreign or replaced entries remain intact.

Compare actual missing native coverage against existing external firmware tests before adding scenarios. Prefer the public firmware import/admit workflows and real small synthetic BIN/ELF/HEX files. Verify stable error code and rule, source/store byte preservation and no unexpected output. Add useful neighboring controls only where they establish the refusal boundary. Cover non-duplicate portable input/authorization constraints, immutable record and normalized image reconstruction, and atomic publication/owned cleanup failures.

Deterministic external filesystem failure injection is allowed at an actual OS boundary, clearly labeled as injected rather than an observed race. Keep production validators and decisions intact. Do not replace analysis/validation with predetermined answers, mutate limits or construct states provably unreachable at the tested entry point. If private cleanup must be exercised, use a real owned directory and inode ledger matching its documented ownership contract. Distinguish such a unit check from public integration evidence. Do not count simulated reparse outcomes as physical symlink qualification.

## Boundaries

Only new `tools/stm32-toolkit/tests/test_external_firmware_integrity_boundaries.py` may be implemented. Reuse existing helpers without editing them. No product code, existing tests, conftest, dependencies, coverage configuration, documentation/Skills or release tooling changes. No flash/probe/backend calls, even a claimed hardware test; no original firmware project, network, runtime installation or global configuration. A genuine product defect is returned to primary for bounded design review, not fixed outside this task.

## Acceptance

Claude returns exact working-tree state, changed file, scenario list and limitations. File-only authoring is not execution. Primary reviews every line before freezing a CodeHead. Claude separately executes the new test file plus the entire existing `test_external_firmware.py` and offline CLI/MCP firmware-import entry-point tests when applicable, through exact native PowerShell commands. Primary independently runs the new file and relevant public callers at the same clean CodeHead in a separate tree. Failures remain retained and never count as passed.

Successful native branch evidence may supplement prior complete-matrix and migration-boundary evidence only with unchanged product source, fixed denominators and exact test identity reconciliation. This slice alone cannot qualify a release. Existing platform skips, pending actual VS Code/install verification and permanent thresholds remain visible.
