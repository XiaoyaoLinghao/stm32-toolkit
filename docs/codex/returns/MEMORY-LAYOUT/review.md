# MEMORY-LAYOUT independent acceptance

Verdict: ACCEPTED_WITH_FIXES (2026-10-23).

The primary owns specification, orchestration, independent complete-diff review and acceptance. Local Claude Code CLI 2.1.308, using the unchanged configured deepseek-v4.1-flash[1m] provider, owns product implementation, authored tests, corrections and the implementation report. No Codex-hosted implementation agent was used.

- Accepted base: 8d0334462291b84f24822e4dfafc5e575e1d9cd1.
- Specification/plan commit: d4fe78f5f015ef04fb039bbaa09ed94de451eda3.
- Product freeze: 29bbac1a75d58d32533e953e091e4efa4077e1dc.
- Final CodeHead: 328e18b76ffb168e7dc97e43d97a241222d773cd. Descendants of the product freeze correct tests and public guidance only.
- Implementation report head: 3bffc59605a3e3652e545f658fc3b9433673a482.
- Clean independent review tree: C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit, detached at the exact final CodeHead.
- Complete accepted-base-to-CodeHead diff: D:/codex-tmp/ml23/primary-complete-final.diff.

The full diff was independently reviewed: shared layout validation; schema/model compatibility; preflight, immutable plan identity and fresh apply; CLI and registered MCP routing; both linker templates and schema copies; all changed tests, skills and documentation. No blocking finding remains within the approved bounded design. git diff --check passed. Root/packaged schema blobs both equal 1c6f4316288d560c0983a2bfc6ee5fcc809c536c; linker template blobs both equal f1676a09b54f41d42b0f2bdd996cfc1c1273e94a.

## Accepted behavior and corrections

The explicit five-role mapping names flash, data, bss, heap and stack regions. Managed generation may infer only the unambiguous single-flash/single-RAM case. Ambiguous input reports MEMORY_LAYOUT_REQUIRED with actual candidates and remediation; explicit all-main-RAM selection is valid and leaves other RAM intentionally unused. Flash must be readable, executable and nonwritable; RAM roles must be readable and writable. No CCM/DMA placement is guessed. Existing native-linker ownership is preserved and explicit managed layout with a native linker is refused.

The generated linker script places .data, .bss, heap and stack in their selected RAM regions, with .data load bytes in the selected flash region. It preserves the preceding startup slice's constructors, copy/zero symbols, alignment/source-correspondence assertions and stack/heap sizes. Fixed NOLOAD handling remains bounded; this is not arbitrary initialized-section placement or scatter-file translation. Exact options participate in plan identity and fresh apply. Absent options retain old single-region bytes and identity payload.

Public guidance names memoryLayout for MCP, --memory-layout JSON for CLI and memory.layout in the manifest. Preflight reports data.analysis.memoryLayout; PLAN reports data.memory_layout. Registered MCP rejects wrong dictionary shapes/nonstring values at framework validation, while schema-valid logical errors return structured Toolkit failures. CLI invalid arguments retain the existing generic redacted stderr contract. Guides give the same-option preflight/plan/review/apply sequence and distinguish these source-only options from the unchanged released v1.2.0 runtime.

Closed review findings included numeric JSON exceptions, exact default-byte baseline assumptions, native-linker fixture prerequisites, workflow stub compatibility, nested fixture paths, actual registered MCP coverage, template synchronization and public response-path/schema wording. Later test-only corrections added required --dry-run and matched the existing generic argparse error. Production error exposure was not broadened to satisfy an assertion.

## Verification and provenance

The final CLI affected integration run at exact CodeHead completed 1043 tests: **1040 passed, 0 failures/errors, 3 skipped**, 503.347s. JUnit, actual native PowerShell tool_use/tool_result and the recorded final result agree. This is the 20-module affected integration suite, not a full release matrix. Complete command and environment are recorded in the implementation report; local evidence is D:/codex-tmp/ml23/verify4.jsonl and verify4.xml, Claude session 5d10c75d-782a-4c86-89c0-6847bf910ef6.

Primary independently ran the four new modules in the clean exact-head review checkout:

    python -m pytest tools/stm32-toolkit/tests/test_memory_layout.py tools/stm32-toolkit/tests/test_memory_layout_migration.py tools/stm32-toolkit/tests/test_memory_layout_compiler.py tools/stm32-toolkit/tests/test_memory_layout_routing.py --basetemp=D:/codex-tmp/ml23/p2 -o cache_dir=D:/codex-tmp/ml23/pc2 -q --tb=short --junitxml=D:/codex-tmp/ml23/primary-final.xml

**33 passed, 0 failed, 0 skipped**, 22.135s, exit0 (primary-final.xml/log). Python 3.12.14 was explicitly bound from D:/codex-tmp/kx23/venv/Scripts/python.exe with same-tree toolkit/monitor PYTHONPATH and isolated temporary/cache directories. Actual GNU ARM 14.3.1 links were performed. Tests cover role validation, missing/explicit mappings, option/plan drift and apply, native ownership, schema, public CLI/registered MCP behavior, valid split layout and link-time rejection of undersized RAM.

Independent ELF evidence (primary-elf-evidence.json) records .data VMA0x20000000, .bss VMA0x10000000, flash data-load address134218056, heap bounds268435464..268436488 (1024bytes), stack bounds268436488..268440584 (4096bytes), and vector initial SP268440584. The heap output section includes alignment padding, distinct from its payload size. ELF SHA256 bbb5e5f6b63d6e30451e3f03f2f152d775eb459a6d95b82c5d762f07b77b2203. This verifies offline linker/runtime symbol consistency, not execution on a board.

Independent comparison against the accepted prior startup product found all9 generated-file hashes unchanged when the new option is absent. Model hash10a807a4850f8a40060b416451c8f9381d5abb6d36b90dbaa9d408954bd90e1a and linker SHA25688b8414b398684f609098aa03c648f25bc7a1f9b13e322ed1fd2da8dbbb1b576 remain identical (legacy-baseline.json/legacy-comparison.json). Comparison ran at74f7b598, whose product files are identical to the final CodeHead.

The three unchanged symbolic-link tests skipped because this Windows host lacks creation privilege: test_regeneration::test_destination_symlink_is_rejected_before_resolution and test_project_model::{test_file_symlink_cannot_escape_project_root,test_directory_symlink_parent_cannot_escape_project_root}. They are not passes; the primary owns their next symlink-capable platform/release qualification. Existing pydantic-settings lifespan and runpy warnings remain recorded. No privilege or permission setting was changed.

Earlier runs are retained without being relabeled: CLI verify1 at29bbac1a was31 passed/2 failed; primary focused at74f7b598 was32 passed/1 failed. The final exact-head focused and affected integration runs above cover their corrected tests. Verify2 executed no tests because the CLI changed the supplied command form and the permission matcher rejected it. Verify3/native executed no tests because no PowerShell tool registered; text resembling a tool invocation was not execution evidence. Logs remain under D:/codex-tmp/ml23.

## Original project and delivery boundaries

A read-only preflight of D:/WorkSpace/mobile-robot-controller works without Git and identifies IROM1 at0x08000000/1MiB, IRAM1 at0x20000000/192KiB and IRAM2 at0x10000000/64KiB. It returns requires-selection instead of silently choosing main RAM. That default-options call still reports36 encoding blockers,1 assembly blocker and2 unsupported ARMCC option blockers, alongside the missing layout. It did not reach all deeper absolute-placement checks. A prior separate read-only source audit found unresolved macro at(...) expressions and external SRAM0x68000000. No region or conversion choice was invented for the user. All54 original source hashes remain unchanged (original-preflight.json/original-source-preservation.json).

The CLI registration issue was repaired using documented, process-local CLAUDE_CODE_USE_POWERSHELL_TOOL=1 and CLAUDE_CODE_POWERSHELL_RESPECT_EXECUTION_POLICY=1, followed by fresh initialization-inventory inspection and an actual harmless Get-Location smoke. This selects the native tool and respects machine policy; it does not grant command permission. Global/project AGENTS are synchronized in this acceptance documentation commit to preserve the verified launch procedure, exact-command permissions and file-only authoring/verification separation. Authentication, provider/model and global permission settings remain unchanged. Reference: https://code.claude.com/docs/en/tools-reference#enable-the-powershell-tool .

This verdict accepts the bounded local software slice. It does not assert physical startup behavior, ARMCC/GCC ABI equivalence, CCM/DMA suitability, full robot-project migration or general scatter/assembly conversion. Keil-native build, external firmware admission/import, extension enumeration and baseline comparison remain separate work. Existing snapshot-only builds do not gain hardware authorization. Original-project apply/build/flash, remote publication, version changes, installation and release qualification were not performed. Local integration follows this primary acceptance; the accepted source does not alter the installed/released v1.2.0 runtime.
