# MEMORY-LAYOUT Implementation Report

## Identity

- Module: `MEMORY-LAYOUT`
- Phase: final report-only stage
- Branch: `codex/memory-layout`
- Accepted base: `8d0334462291b84f24822e4dfafc5e575e1d9cd1`
- Approved specification and plan: `d4fe78f5f015ef04fb039bbaa09ed94de451eda3`
- Product freeze: `29bbac1a75d58d32533e953e091e4efa4077e1dc`
- Final CodeHead: `328e18b76ffb168e7dc97e43d97a241222d773cd`
  - `74f7b59809220ae8f9d51d61d1c85822515601bc` corrected test-only CLI dry-run requirements.
  - The final descendant corrects a generic stderr test expectation and clarifies MCP schema/framework diagnostics in documentation.
- Working tree: this report is the only change created at this stage. The coordinator independently confirmed the branch clean at CodeHead immediately before the report.

The report records the accepted base and the CodeHead before the report commit. It does not record its own future commit SHA or moving commit totals.

## Ownership and review status

The primary conversation agent owns the specification, orchestration, independent review, and acceptance. The local Claude Code CLI 2.1.308, using the unchanged configured `deepseek-v4.1-flash[1m]` route, owns implementation, tests, corrections, and this report. The implementer does not approve its own diff. The primary agent independently reviews the complete accepted-base-to-CodeHead diff in a clean exact-head worktree and records the verdict separately. No acceptance verdict is claimed here.

## Delivered behavior

- Added an optional explicit five-role managed memory layout: `memoryLayout` in the public MCP interface, `--memory-layout` taking its JSON object in the CLI, and `memory.layout` in the project manifest/schema. The mapping has exactly five required string roles: `flash`, `data`, `bss`, `heap`, `stack`, each naming an existing region.
- Added one shared immutable layout-validation/selection implementation used by project configuration and migration. Validation covers named regions, role access rules, duplicates/overlaps, bounded 32-bit address arithmetic, and required fields.
- Flash must be readable and executable and non-writable; RAM roles must be readable and writable. The layout never infers DMA accessibility from writeability and never places buffers in CCM automatically.
- Without an explicit layout, defaults are inferred only when there is exactly one Flash candidate and exactly one RAM candidate. Ambiguous managed memory returns actionable `MEMORY_LAYOUT_REQUIRED` with the unresolved roles, actual candidate names/ranges/attributes, and remediation. Explicitly keeping all standard sections in one main RAM is valid and is displayed as a deliberate choice, not inferred.
- Unknown or missing roles and incompatible named regions are rejected. Native-linker projects retain ownership of their linker script when no new option is supplied; an explicit layout combined with `generation.nativeLinkerScript` is rejected rather than pretending to control native-owned sections.
- Generated managed sections place `.data` LMA in the selected Flash while its VMA and `bss`/`heap`/`stack` reside in the selected RAM. Existing startup constructors, copy/zero initialization, alignment, size guards, and the fixed-address `NOLOAD` limitations are preserved. `_sidata` and the `bss` clear symbols remain consistent with the chosen regions.
- Layout choices are bound to plan identity and fresh apply re-analysis. Preflight returns `analysis.memoryLayout` with `status` (`implicit`, `explicit`, or `requires-selection`), resolved `layout` or null, and actual `candidates` for flash and RAM; the PLAN response exposes `data.memory_layout` with the chosen layout or required candidates alongside existing blockers.
- MCP dictionary shape and non-string values fail framework schema validation; schema-valid semantic failures use structured Toolkit errors. CLI JSON with duplicate keys, huge integers, deep nesting, or invalid keys fails safely. The parser deliberately redacts details to generic invalid-arguments diagnostics rather than exposing raw tracebacks.
- Public options and examples are source-only candidate behavior. The installed/published v1.2.0 runtime is unchanged and lacks them. Root and packaged schema/template copies are synchronized.

## Corrections before freeze

- Corrected the oversized-integer JSON exception path.
- Corrected native-conflict fixture prerequisites.
- Corrected byte/hash baseline regression expectations.
- Exercised the actual registered MCP route instead of helper-only coverage.
- Synchronized root and packaged templates.
- Corrected workflow stub keywords and nested temporary directories.
- Test-only follow-ups fixed the required `--dry-run` assertions and preserved existing generic argparse diagnostics instead of changing product error exposure.
- Corrected the newly authored generic stderr expectation to match the existing parser output.

## Changed files

- `docs/architecture.md`
- `docs/superpowers/plans/2026-10-23-memory-layout-plan.md`
- `docs/superpowers/specs/2026-10-23-memory-layout-design.md`
- `docs/user-guide.md`
- `schemas/stm32-project.schema.json`
- `skills/build-firmware/SKILL.md`
- `skills/configure-stm32-project/SKILL.md`
- `skills/migrate-keil/SKILL.md`
- `templates/cmake/linker.ld.j2`
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`
- `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/src/stm32_toolkit/memory_layout.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py`
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json`
- `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/linker.ld.j2`
- `tools/stm32-toolkit/src/stm32_toolkit/workflows.py`
- `tools/stm32-toolkit/tests/test_generation.py`
- `tools/stm32-toolkit/tests/test_mcp_migration_build.py`
- `tools/stm32-toolkit/tests/test_memory_layout.py`
- `tools/stm32-toolkit/tests/test_memory_layout_compiler.py`
- `tools/stm32-toolkit/tests/test_memory_layout_migration.py`
- `tools/stm32-toolkit/tests/test_memory_layout_routing.py`
- `tools/stm32-toolkit/tests/test_workflows.py`

## Evidence

The primary conversation agent parsed the JUnit results. These counts are authoritative and override any earlier prose.

### CLI verify1 at `29bbac1a`

- 33 total, 31 passed, 2 failed, 0 skipped, 22.378 seconds.
- The two failures were CLI tests that omitted required `--dry-run`. This was corrected by the test-only follow-up at `74f7b598`.
- An earlier CLI prose statement claiming 33 passed plus 2 failed was incorrect and is not repeated.
- Evidence: `verify1.jsonl` / `verify1.xml`.

### Primary focused run at `74f7b598`

- 33 total, 32 passed, 1 failed, 0 skipped, 21.152 seconds.
- The only failure was the newly authored stderr expectation conflicting with the existing generic parser output. The final descendant corrected that test-only expectation.
- Evidence: `primary-focused.xml` / `primary-focused.log`.

### CLI verify2 at `74f7b598`

- ZERO tests executed.
- The changed literal supplied Python command became a call-operator absolute invocation and was rejected by the permission matcher (`multiple operations... approval required`).
- The invocation stopped, logs were preserved, and no alternate operation or permission bypass was attempted. No XML evidence was produced.
- Evidence: `verify2.jsonl` / `verify2-denied-command.txt`.

### CLI verify3 and verify3-native at `328e`

- ZERO tests executed and not passing evidence.
- `system/init.tools` was empty and the transcript contained only plaintext pseudo tool markup. There were no actual `tool_use`/`tool_result` events and no XML.
- The coordinator traced the default inventory switching to Bash despite the same CLI version. Official native PowerShell registration was enabled by setting `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` and `CLAUDE_CODE_POWERSHELL_RESPECT_EXECUTION_POLICY=1` only in the launching process. No permission widening, global setting change, model/provider change, or authentication change was made.
- A fresh no-action inventory verified `PowerShell`, then an exact harmless `Get-Location` truly executed. Session: `1c6b439e-621b-4132-97de-d2f7c1defb95`.
- Evidence: `powershell-inventory.jsonl` / `powershell-smoke.jsonl`.
- Reference: https://code.claude.com/docs/en/tools-reference#enable-the-powershell-tool
- The primary synchronizes governance guidance for this native registration separately.

### Primary independent final clean run at exact `328e`

- 33 passed, 0 failed, 0 skipped, 22.135 seconds.
- Covered the four new memory-layout test modules and used a real GNU ARM 14.3.1 ELF/MAP link plus a negative overflow case. It exercised the public CLI and registered MCP route, schema/identity/apply/native-linker behavior, and generation coverage.
- Evidence: `primary-final.xml` / `primary-final.log`, `p2` / `pc2`.

### CLI verify4 FINAL at exact `328e`

- 1043 total: 1040 passed, 0 failed/errors, 3 skipped, 503.347 seconds.
- Actual native PowerShell `tool_use`/`tool_result` events and JUnit confirm real execution. Session: `5d10c75d-782a-4c86-89c0-6847bf910ef6`.
- The run covered 20 affected integration modules, not the full repository or release matrix.
- Evidence: `verify4.jsonl` / `verify4.xml`.

Exact CLI final command:

```text
python -m pytest tools/stm32-toolkit/tests/test_memory_layout.py tools/stm32-toolkit/tests/test_memory_layout_migration.py tools/stm32-toolkit/tests/test_memory_layout_compiler.py tools/stm32-toolkit/tests/test_memory_layout_routing.py tools/stm32-toolkit/tests/test_startup_gcc_generation.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py tools/stm32-toolkit/tests/test_startup_gcc_routing.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_regeneration.py tools/stm32-toolkit/tests/test_regeneration_workflows.py tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_public_inventory.py --basetemp=D:/codex-tmp/ml23/b4 -o cache_dir=D:/codex-tmp/ml23/c4 -q --tb=short --junitxml=D:/codex-tmp/ml23/verify4.xml
```

### Deferred platform checks

The three skips are unchanged Windows-privilege limitations and are not passes:

- `test_regeneration::test_destination_symlink_is_rejected_before_resolution`
- `test_project_model::test_file_symlink_cannot_escape_project_root`
- `test_project_model::test_directory_symlink_parent_cannot_escape_project_root`

They are deferred to the primary-led next symlink-capable platform/release qualification. Existing `pydantic_settings` lifespan forward-reference and `runpy` warnings were retained.

### Environment

- Python 3.12.14: `D:/codex-tmp/kx23/venv/Scripts/python.exe`
- Same-tree toolkit and monitor `PYTHONPATH`
- Isolated temporary and cache directories
- ARM GNU 14.3.1: `C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin`

### Baseline compatibility

- With no new option, all 9 generated files were byte-hash identical to the accepted startup product.
- Model hash: `10a807a4850f8a40060b416451c8f9381d5abb6d36b90dbaa9d408954bd90e1a`
- Linker SHA: `88b8414b398684f609098aa03c648f25bc7a1f9b13e322ed1fd2da8dbbb1b576`
- Evidence: `legacy-baseline.json` / `legacy-comparison.json`. The product at `74f7b598` compared identical to the final product.
- Root and packaged schema blob: `1c6f4316288d560c0983a2bfc6ee5fcc809c536c`
- Root and packaged templates: `f1676a09b54f41d42b0f2bdd996cfc1c1273e94a` (match)
- `git diff --check` passed.

### Original-project read-only preflight

- Available without Git. `memoryLayout` requires selection.
- Actual candidates: IROM1 `0x08000000` 1 MiB `r-x`; IRAM1 `0x20000000` 192 KiB `rwx`; IRAM2 `0x10000000` 64 KiB `rwx`.
- Blockers: `MEMORY_LAYOUT_REQUIRED1`, `encoding36`, `assembly1`, `ARMCC_OPTION_UNSUPPORTED2`.
- This default-options call does not assert that source absolute-placement blockers were reached. A prior separate source audit found macro `at(...)` and external SRAM `0x68000000` unresolved.
- 54 original source hashes remained unchanged.
- Evidence: `original-preflight.json` / `original-source-preservation.json`.

### Real final synthetic ELF

- `.data` at `0x20000000`; `.bss` at `0x10000000`.
- `_sidata` = `134218056`.
- Heap bounds: `268435464..268436488` (1024 bytes).
- Stack bounds: `268436488..268440584` (4096 bytes).
- Vector initial SP: `268440584`.
- The `.heap` section includes alignment padding; its whole section size must not be misstated as heap payload.
- Evidence: `primary-elf-evidence.json`, SHA `bbb5e5f6b63d6e30451e3f03f2f152d775eb459a6d95b82c5d762f07b77b2203`.
- This is offline linked-image evidence only. No hardware was used.

All evidence is under `D:/codex-tmp/ml23`; the primary full diff is `primary-complete-final.diff`.

## Limits

This is a bounded local software slice. It does not establish board runtime, ABI, or CCM/DMA equivalence. It does not migrate the whole robot project, translate macro addresses, fabricate external RAM, implement a native Keil backend, import external firmware, enumerate extension readiness, or compare baselines. Those remain separate work.

Existing build snapshots do not gain hardware authorization. No original project apply/build/flash, remote publication, version bump, installation, or full release qualification was performed. The slice does not claim that the historical blind-test gaps are all solved.

The primary conversation agent has not yet recorded acceptance in this report; independent review of the complete accepted-base-to-CodeHead diff remains the acceptance gate.
