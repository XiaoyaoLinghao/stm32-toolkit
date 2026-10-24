# STM32TK-130 Implementation Report

## Identity

- Module: `STM32TK-130`
- Phase: local v1.3.0 Release candidate — version integration, official artifact build and local verification
- Branch: `codex/v1.3.0`
- Accepted base: `6b4c13b6fa76f320503b14679c8eb7bfc712c9af`
- Source CodeHead before this report commit: `1e6ea849c21fb3786d60dba0254acb375d016a62`
- Implementation/integration worktree (Claude-authored changes and CLI test runs): `C:/Users/zhy76/.codex/worktrees/build-snapshot-review/STM32-Toolkit`
- Primary independent clean review checkout and official build source: `C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit`
- Governing design and plan (primary-owned): `docs/superpowers/specs/2026-10-24-v130-local-release-design.md`, `docs/superpowers/plans/2026-10-24-v130-local-release-plan.md`
- Integrated feature slice: EXTERNAL-FIRMWARE, historical feature CodeHead `4f002cd1479dc98c2dc9c48d7e75dddf896de2f2`, accepted separately with fixes for the offline software scope (`docs/codex/returns/EXTERNAL-FIRMWARE/`). The report source is the later integrated CodeHead `1e6ea849`, not `4f002cd1`.
- Delivery location: `D:/WorkSpace/STM32-Toolkit/dist/v1.3.0` — a **local** delivery directory, not a public download.

This report records the source CodeHead reached before the report commit. It contains no own future commit SHA, no moving commit totals and no remote identity.

## Ownership and review status

The primary conversation agent owns the requirement, architecture, specification, plan, orchestration, independent complete-diff review and acceptance. The local Claude Code CLI 2.1.308, on the unchanged configured `deepseek-v4.1-flash[1m]` route, owns implementation, product/test changes, version alignment and slice-level tests. The implementer did not approve its own diff. The primary independently reviewed the complete accepted-base-to-CodeHead diff, ran independent focused tests and independently verified the produced artifacts.

This report is not an acceptance verdict. The primary records the verdict separately.

Nothing in this phase published, pushed, tagged, installed over an existing runtime, promoted a runtime, built or modified the original project, or touched hardware. No remote mutation occurred. No v1.2.0-only qualification exception was transferred.

## What shipped (local candidate)

The candidate aligns the Toolkit, Monitor, UI, plugin, launchers, runtime state and release policy/schema identity to `1.3.0`, and recognizes an existing `1.2.0` managed runtime and `1.2.0` generation producer as legacy inputs while retaining older `1.1.2`/`1.0.1`/`1.0.0`/`0.9.0` compatibility. Recognition is read-only; advancing a runtime still requires an explicit authorized `Repair`, and existing `generatedBy` values are not rewritten.

Product behavior present in the source:

- **External-firmware route** (accepted feature slice): read-only import PLAN → authorized APPLY of the exact `planId` → offline ADMIT, and a separately authorized `stm32_flash_imported` to one exact probe. Imported source SHA-256 and normalized image SHA-256 are distinct fields. An imported receipt does not unlock debug, Monitor, Target tests, a managed build identity or legacy flash evidence.
- **Read-only Keil preflight**: `keil preflight` / `stm32_keil_preflight` reports structured capability diagnostics and separates `planReadiness` from `applyReadiness`; it writes no files and emits no plan ID. `keil inspect` still works without a migration baseline.
- **Standalone read-only probe discovery**: `probe list` / `stm32_probe_list` is decoupled from preflight/manifest/build facts and does not grant hardware authority.
- **Content-snapshot managed build**: `schemaVersion: 2` with `sourceBaseline: "input-snapshot-v1"`, explicit null Git fields and bounded `gitEvidence`; freshness depends on the exact input snapshot, target/preset/model and ELF/MAP hashes. The hardware-managed flash/debug/Target/Monitor route still requires a Git-verified build identity.
- **Opt-in bounded CMSIS GCC startup generation** for conventional ST/CMSIS Cortex-M3/M4/M7 ARMCC5 startup, plus an explicit five-role `memoryLayout` (`flash`, `data`, `bss`, `heap`, `stack`). Multiple RAM candidates require an explicit reviewed selection; no RAM is chosen by default.
- **Ninth bundled Skill** `normalize-source-comments`: an explicit, preview-first, per-file encoding helper that writes comment-only UTF-8 copies outside the project. It is not a migration step and adds no MCP tool.

Public inventory of the candidate source: **52 MCP tools and 9 bundled Skills**, including `stm32_keil_preflight`, `stm32_firmware_import`, `stm32_firmware_admit` and `stm32_flash_imported`. The published v1.2.0 package remains 48 tools and 8 Skills.

## Version and compatibility

| Item | Value |
| --- | --- |
| Toolkit package version | `1.3.0` (`tools/stm32-toolkit/pyproject.toml`, `__version__`) |
| Monitor package version | `1.3.0`; dependency `stm32-toolkit==1.3.0` |
| Monitor UI package and lock root | `1.3.0` (dependency graph unchanged) |
| Plugin manifest | `1.3.0` |
| Launchers | Both resolve `%STM32_TOOLKIT_DATA_ROOT%\runtime\1.3.0\Scripts\python.exe` |
| Runtime state schema | `stm32-toolkit-runtime-state/1` |
| Release policy | `version: 1.3.0`, `requiredPython: >=3.12,<3.13`, Windows x86_64 / cp312, `publicInventory: {mcpTools: 52, skills: 9}` |
| Project schemas | v2/v3 readable; v1 requires an explicit upgrade |
| Legacy runtime versions | `1.2.0`, `1.1.2`, `1.0.1`, `1.0.0`, `0.9.0`, `0.5.0`, `0.3.0` |
| Platform | Windows x86_64, CPython `>=3.12,<3.13` (CPython 3.12 only) |

The third-party runtime dependency pins and the 62 third-party dependency wheels are unchanged from the frozen packaging policy; exactly two product wheels are rebuilt as `1.3.0` (`stm32-toolkit` and `stm32-monitor`), so the closed runtime payload remains 64 wheels. Build-backend wheels are kept separate and are not part of that runtime closure. `compatibility.md` in the delivered assets lists the selected runtime wheels, including `stm32-toolkit==1.3.0` and `stm32-monitor==1.3.0`. Protocol/schema numbers and third-party pins were not changed by the version alignment. The setup bootstrap trust anchors were recomputed from the committed archive's utility and policy bytes (`$ReleaseUtilitySha256 = 72cc96a0457a2bfaed9a290dcff78687b3716c0d8990d259aef9a4bbc65e54ea`, `$ReleasePolicySha256 = 84028a6844537bcad455c3e8cdd7a9795aa1ed15d9b6a155d9247ac53f3fa4a6`). The utility hash matches the `utilitySha256` returned by the official `verify-bundle` run.

### Exact VS Code / MCP guide

`docs/user-guide.md` documents the matching host configuration. The exact snippet for a verified, installed, `Check`-healthy local v1.3.0 runtime is (paths must be replaced with real absolute paths; `--data-root` and `STM32_TOOLKIT_DATA_ROOT` must name the same persistent directory):

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit-1.3.0-bundle\\stm32-toolkit-1.3.0\\bin\\stm32-toolkit-mcp.cmd",
      "args": [
        "--project-root", "C:\\work\\blinky",
        "--data-root", "C:\\data\\stm32-toolkit"
      ],
      "env": {
        "STM32_TOOLKIT_DATA_ROOT": "C:\\data\\stm32-toolkit"
      }
    }
  }
}
```

The guide also states the VS Code/MCP client route that does not load `SKILL.md`: call `stm32_project_context()`, read `data.project.kind` and `data.capabilityDetails`; use `stm32_keil_inspect`/`stm32_keil_preflight` before any plan; apply only an exact `data.plan_id` with explicit authorization; call `stm32_build` only after `capabilityDetails.build` permits it; and for `.vscode/tasks.json`/`launch.json`, treat generated files as configuration targets only. It explicitly says the IDE path is not accepted or deployed until it has run in real VS Code with actual extension versions and a real debug session. Availability must be read from the actually bound server via `doctor --json` → `data.publicInventory.mcpTools`/`skills` and the real tool input schema, not inferred from documentation or source lists. The published v1.2.0 runtime is documented separately as a published-version example and download (48 tools, 8 Skills); it does not expose the v1.3.0-only entries and is never an implicit fallback for an unavailable v1.3.0 capability.

## Official build and artifact evidence

Two official clean builds were produced with the existing builder and a run-owned wheelhouse. Exact commands are retained verbatim at `D:/codex-tmp/fi24/build-a-command.txt`, `D:/codex-tmp/fi24/build-b-command.txt` and `D:/codex-tmp/fi24/verify-bundle-command.txt`:

```text
python C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit/tools/release/build_0900_artifacts.py build --repo-root C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit --code-head 1e6ea849c21fb3786d60dba0254acb375d016a62 --wheelhouse D:/codex-tmp/fi24/wheelhouse --output-root D:/codex-tmp/fi24/release-a
python C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit/tools/release/build_0900_artifacts.py build --repo-root C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit --code-head 1e6ea849c21fb3786d60dba0254acb375d016a62 --wheelhouse D:/codex-tmp/fi24/wheelhouse --output-root D:/codex-tmp/fi24/release-b
python D:/codex-tmp/fi24/extracted/stm32-toolkit-1.3.0/tools/release/build_0900_artifacts.py verify-bundle --toolkit-root D:/codex-tmp/fi24/extracted/stm32-toolkit-1.3.0 --json
```

Both invocations used the clean isolated build tree recorded in the command files at `C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit` (CodeHead `1e6ea849`), the pinned run-owned wheelhouse `D:/codex-tmp/fi24/wheelhouse`, and new output roots. That `build-snapshot-final` checkout is both the primary's independent clean review checkout, where the 59 independent tests ran, and the official build source. The `build-snapshot-review` worktree named in Identity is the implementation/integration worktree where the Claude Code CLI authored the changes and ran the shard tests. Git `autocrlf=false`/`eol=lf` were set per process only; no persistent Git or environment setting was changed. Before the builds, all 821 raw Git blobs at the source were confirmed byte-identical.

The CLI build tool invocations were captured with silent stdout in the delegate record, and no printed exit code was observed. That silence is **not** evidence of build failure or incompleteness, and this report does not claim an observed exit code. The build gate is closed by the actual 13 delivered files plus the independently verified properties below and the separate official `verify-bundle` result, not by CLI prose.

The official `verify-bundle` run returned native JSON (`D:/codex-tmp/fi24/verify-bundle-result.json`) with `status: "ok"`, `schema: "stm32-toolkit-release/1"`, `productVersion: "1.3.0"`, `sourceCommit: "1e6ea849c21fb3786d60dba0254acb375d016a62"`, `manifestSha256: "d36d7ef2344c1efd694d8b0573d2d33024f88948a605ddbbb394e4b9ecc1222c"`, `utilitySha256: "72cc96a0457a2bfaed9a290dcff78687b3716c0d8990d259aef9a4bbc65e54ea"` and 64 wheel entries.

Delivered assets in `D:/WorkSpace/STM32-Toolkit/dist/v1.3.0` (the primary copied all 13 and independently re-verified every hash):

| Asset | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `CHECKSUMS.sha256` | 1073 | `ed632d302dab80ebfcd11bab632ab770426c554d84f472fa1cedcb6aac448576` |
| `LICENSE` | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| `THIRD-PARTY-NOTICES.md` | 2615 | `53e3c4a33785dd02dc8b831c0e295dd97b432ad5e6f7746364ff33bdeefe4f20` |
| `compatibility.md` | 2014 | `7d8fcbe6fff9c77e35b130ed2fcde278216edbb83729ff3cc619312562f8cc20` |
| `licenses.zip` | 413750 | `f2977e5b81169e40babaa6c56d873384f65b6c0142a2b0c91a90f7a8815f6591` |
| `monitor-assets.json` | 970 | `6a4b79814313f3e77fd382d6ba5f7cb92c1d49beab883a1f458f55d5d33462b6` |
| `release-manifest.json` | 15814 | `d36d7ef2344c1efd694d8b0573d2d33024f88948a605ddbbb394e4b9ecc1222c` |
| `sbom.spdx.json` | 191430 | `558f81ef7d1f9f43b348087fb352ffab93785fca04e5a9548eebd4d3aaa9c55a` |
| `stm32-toolkit-1.3.0-source.zip` | 15753356 | `0779c753651026e64c2bde5341b1d75fb7115c43b1bc2ee1b23549d9f411db80` |
| `stm32-toolkit-1.3.0-windows-x86_64.zip` | 107265436 | `7f6892a6b0f6eafe65742877e021c347db5d2c98aaf46de49c4f5b42a6782af2` |
| `stm32_monitor-1.3.0-py3-none-any.whl` | 1519467 | `dee6e58621962f9762663454714a83ced87604857c5feaf5da4afd2c1ac9c8c3` |
| `stm32_toolkit-1.3.0-py3-none-any.whl` | 3544529 | `cc4705fbc1464f4264094ffa68504b1eb7801e3ac25b69eba556bdc9a74cb116` |
| `troubleshooting.md` | 1737 | `ae35c97eebf5387761d205e91e4e8fcf54de9f79f25e26919741d896c81a8e10` |

Independent artifact checks (recorded in `docs/codex/returns/STM32TK-130/artifact-verification.json`, primary-owned read-only evidence):

- 13 assets and 12 `CHECKSUMS.sha256` entries consistent.
- Two full builds byte-identical.
- All ZIP and wheel CRCs valid.
- Safe, unique archive members and exact bundle closure.
- The manifest source-archive SHA-256 matches the actual `stm32-toolkit-1.3.0-source.zip` bytes; the manifest commit is exactly `1e6ea849c21fb3786d60dba0254acb375d016a62`, and the archived payload maps to that source tree (821 source files, 1,138 bundle files).
- 64 wheel hashes and 6 artifact hashes verified.
- Both 1.3.0 wheel metadata and the exact Monitor dependency verified.
- Every product wheel payload bound to source.
- 52 tools / 9 bundled skills and 7 Monitor UI assets verified.
- Plugin/Python/UI versions consistent.
- `deliveredHashVerification: PASS`; `officialExtractedBundleVerification: PASS`.

## Test evidence

All native tests were run at the exact source CodeHead `1e6ea849c21fb3786d60dba0254acb375d016a62`. The exact commands are stored in `docs/codex/returns/STM32TK-130/test-results.json`; each used same-tree Toolkit/Monitor `PYTHONPATH`, isolated `--basetemp`/cache under `D:/codex-tmp/fi24`, and JUnit output.

| Shard | Owner | Tests | Result | JUnit |
| --- | --- | ---: | --- | --- |
| Version / packaging / generation | Claude Code CLI | 755 | 755 passed, 0 skipped/failed/error | `D:/codex-tmp/fi24/version.xml` |
| Setup runtime / plugin layout | Claude Code CLI | 63 | 63 passed, 0 skipped/failed/error | `D:/codex-tmp/fi24/setup.xml` |
| External firmware / debug / hardware / probe | Claude Code CLI | 1061 | 1061 passed, 0 skipped/failed/error | `D:/codex-tmp/fi24/feature130.xml` |
| Monitor | Claude Code CLI | 288 | 288 passed, 0 skipped/failed/error | `D:/codex-tmp/fi24/monitor.xml` |
| **Subtotal** | Claude Code CLI | **2167** | **2167 passed, 0 skipped/failed/error** | |
| Independent focused review | primary independent review | 59 | 59 passed, 0 skipped/failed/error | `D:/codex-tmp/fi24/primary130.xml` |

Exact committed shard commands:

```text
python -m pytest tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_0900_security.py tools/stm32-toolkit/tests/release/test_0900_artifacts.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_build_snapshot.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_startup_gcc_generation.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py tools/stm32-toolkit/tests/test_memory_layout_compiler.py tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py -q --tb=short --basetemp=D:/codex-tmp/fi24/p-version -o cache_dir=D:/codex-tmp/fi24/c-version --junitxml=D:/codex-tmp/fi24/version.xml

python -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py -q --tb=short --basetemp=D:/codex-tmp/fi24/p-setup -o cache_dir=D:/codex-tmp/fi24/c-setup --junitxml=D:/codex-tmp/fi24/setup.xml

python -m pytest tools/stm32-toolkit/tests/test_external_firmware.py tools/stm32-toolkit/tests/test_external_firmware_workflow.py tools/stm32-toolkit/tests/test_external_firmware_routing.py tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_probe_worker.py tools/stm32-toolkit/tests/test_probe_backend.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_cli_hardware.py -q --tb=short --basetemp=D:/codex-tmp/fi24/p-feature130 -o cache_dir=D:/codex-tmp/fi24/c-feature130 --junitxml=D:/codex-tmp/fi24/feature130.xml

python -m pytest tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py -q --tb=short --basetemp=D:/codex-tmp/fi24/p-monitor -o cache_dir=D:/codex-tmp/fi24/c-monitor --junitxml=D:/codex-tmp/fi24/monitor.xml
```

The primary's 59-test independent run covered three external-firmware modules, `public_inventory`, CLI version, archive trust-anchor and release-identity checks. Its exact command is retained in the existing evidence file `docs/codex/returns/STM32TK-130/test-results.json` (entry `primary130`); it is not reproduced here and must not be inferred from the shard commands.

All hardware, probe and programming paths in these tests used injected fakes or explicit offline fixtures. A fake installation is software evidence only; it is not a real installation, upgrade or rollback result.

## Changed files (accepted base → CodeHead)

### Implementation, product, version alignment and tests (Claude Code CLI)

```text
.claude-plugin/plugin.json
CHANGELOG.md
README.md
README_zh-CN.md
bin/setup-stm32-env.ps1
bin/stm32-monitor.cmd
bin/stm32-toolkit-mcp.cmd
docs/architecture.md
docs/codex/returns/EXTERNAL-FIRMWARE/implementation-report.md
docs/release-status.md
docs/user-guide.md
schemas/probe-protocol.schema.json
schemas/stm32-release.schema.json
skills/build-firmware/SKILL.md
skills/flash-firmware/SKILL.md
skills/migrate-keil/SKILL.md
skills/setup-stm32-env/SKILL.md
tools/release/build_0900_artifacts.py
tools/release/release_0900_policy.json
tools/stm32-monitor/pyproject.toml
tools/stm32-monitor/tests/test_cli.py
tools/stm32-monitor/tests/test_exports.py
tools/stm32-monitor/tests/test_models.py
tools/stm32-monitor/tests/test_package_boundary.py
tools/stm32-monitor/tests/test_runtime.py
tools/stm32-monitor/tests/test_service.py
tools/stm32-monitor/ui/package-lock.json
tools/stm32-monitor/ui/package.json
tools/stm32-toolkit/pyproject.toml
tools/stm32-toolkit/src/stm32_toolkit/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/cli.py
tools/stm32-toolkit/src/stm32_toolkit/external_firmware.py
tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py
tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py
tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py
tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py
tools/stm32-toolkit/src/stm32_toolkit/probe/client.py
tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py
tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py
tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py
tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py
tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json
tools/stm32-toolkit/tests/fakes/fake_probe.py
tools/stm32-toolkit/tests/fakes/fake_pyocd.py
tools/stm32-toolkit/tests/release/test_0900_artifacts.py
tools/stm32-toolkit/tests/test_0900_security.py
tools/stm32-toolkit/tests/test_build_runner.py
tools/stm32-toolkit/tests/test_cli.py
tools/stm32-toolkit/tests/test_debug_firmware.py
tools/stm32-toolkit/tests/test_doctor.py
tools/stm32-toolkit/tests/test_external_firmware.py
tools/stm32-toolkit/tests/test_external_firmware_routing.py
tools/stm32-toolkit/tests/test_external_firmware_workflow.py
tools/stm32-toolkit/tests/test_generation.py
tools/stm32-toolkit/tests/test_mcp_hardware.py
tools/stm32-toolkit/tests/test_mcp_migration_build.py
tools/stm32-toolkit/tests/test_migration_plan.py
tools/stm32-toolkit/tests/test_plugin_layout.py
tools/stm32-toolkit/tests/test_probe_protocol_v2.py
tools/stm32-toolkit/tests/test_public_inventory.py
tools/stm32-toolkit/tests/test_setup_runtime.py
tools/stm32-toolkit/tests/test_startup_gcc_generation.py
tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py
```

### Primary-owned governance, specification, review and procedure files

```text
docs/codex/returns/EXTERNAL-FIRMWARE/review.md
docs/superpowers/plans/2026-10-23-external-firmware-plan.md
docs/superpowers/plans/2026-10-24-v130-local-release-plan.md
docs/superpowers/specs/2026-10-23-external-firmware-design.md
docs/superpowers/specs/2026-10-24-v130-local-release-design.md
docs/testing/standard-test-procedure.md
```

Attribution above follows document ownership. Within the source range, implementation, product, test, version-alignment, documentation and report files were authored by the Claude Code CLI, including `docs/codex/returns/EXTERNAL-FIRMWARE/implementation-report.md` and `docs/release-status.md`, which the primary independently reviewed. The primary authored the specifications, the plans, `docs/codex/returns/EXTERNAL-FIRMWARE/review.md` and `docs/testing/standard-test-procedure.md`. The earlier feature slice's own files and acceptance are recorded in `docs/codex/returns/EXTERNAL-FIRMWARE/` and are not re-characterized here.

## Retained limits

- **Not released.** There is no v1.3.0 tag, GitHub Release, public asset, public download link or remote identity. The v1.2.0 Release remains the current public download. The 13 files are a local delivery only.
- **No full qualification and no coverage matrix.** Permanent coverage floors were not measured for this candidate and remain unchanged. If a new release coverage measurement begins, `external_firmware.py` must first enter Toolkit risk-core scope as a declared amendment.
- **No real installation, upgrade, rollback, browser, IDE or physical qualification.** The setup tests are software-level; injected/fake installation evidence is not a real deployment. The VS Code extension readiness probe is not implemented (`vscodeExtensions` remains `not-probed`), so no claim is made that an actual extension set is ready.
- **No original-project, hardware or existing-runtime mutation.** No user runtime was promoted or replaced, and no probe or target was accessed.
- **The v1.2.0-only user-approved qualification exception does not transfer** to v1.3.0 in any form.
- **Remaining product gaps:** no native Keil UV4 build backend; no automated VS Code extension readiness probe; no migration-baseline comparison verdict (a discovered AXF/MAP baseline is not proof of toolchain, source or binary comparability); migration remains one-way, with PLAN and APPLY Git-gated while the read-only preflight does not require Git; it refuses unknown source encodings and arbitrary ARMCC assembly, and only generates startup for the bounded conventional ST/CMSIS Cortex-M3/M4/M7 case. Scatter, memory and multi-RAM decisions require explicit reviewed input.
- **Retained nonfatal warning:** a `pydantic` lifespan warning was observed during the software runs and remains recorded. No test was skipped or weakened to hide a failure.
- **Retained nonblocking diff-check artifact:** a trailing EOF blank line at `tools/stm32-toolkit/tests/test_external_firmware_routing.py:569` remains. It is nonblocking and was deliberately not edited in this phase; therefore this report does **not** claim that `git diff --check` passed.

## Invocation scope of this report

This report invocation was documentation-only. No shell, Git command, test, build, installation, network access or MCP call was executed; no product code or test was changed. The read-only evidence files `artifact-verification.json` and `test-results.json` in this folder were not modified. Tests are **NOT RUN** in this report invocation; the results above are the previously executed evidence at source CodeHead `1e6ea849`.
