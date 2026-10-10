# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local, agent-neutral toolkit for STM32 projects. Its CLI and stdio MCP server share the same project, build, Probe Service, test, and Monitor contracts. The eight Claude Code Skills are adapters to those public entry points; the core does not depend on an agent host.

**Release status:** [v1.0.0 is published](docs/release-status.md). This source candidate identifies as **v1.0.1** and contains the approved patch behavior, pending independent integration and release qualification. It has not been released or installed. Use a verified bundle and its matching data root for any installed workflow. Supported release platform: Windows x86_64 and CPython `>=3.12,<3.13`. Historical qualification limits remain in [release status](docs/release-status.md).

## Start with a verified runtime

Extract a verified bundle to a stable ToolkitRoot. Keep DataRoot durable and separate from the project and disposable test directories. The setup script's `Check` is read-only. Inspect its result before explicitly choosing a missing-runtime `Bootstrap` or an authorized `Repair`; repeat `Check` afterward. This candidate's CLI/MCP uses the managed interpreter in `DATA_ROOT/runtime/1.0.1`; the published v1.0.0 bundle uses `runtime/1.0.0`. There is no system-Python fallback. Existing v1.0.0 runtimes enter the 1.0.1 candidate only through authorized Repair, with the old runtime quarantined and rollback preserved.

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit-1.0.1'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `missing` and installation is authorized, run **Bootstrap only**:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` instead reports an authorized repairable/broken state, run **Repair only**:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Repair `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

Run at most one mutation command, then repeat `Check`. For Claude Code, `/stm32-toolkit:setup-stm32-env` uses the same setup contract. For any MCP host, configure an **absolute launcher** at `bin/stm32-toolkit-mcp.cmd`, explicit project/data roots, and `"STM32_TOOLKIT_DATA_ROOT"` pointing to that DataRoot. A copyable [generic MCP configuration and public inventory](docs/user-guide.md) are in the user guide. `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` are Claude adapter placeholders, not required by the generic CLI. The CLI needs an explicit absolute `--project-root` for project-bound commands.

## Work with a project

Run these from a shell where the verified runtime's `Scripts` directory is available. Detection, inspection, and the first configure call are read-only. Review the returned plan and blockers before any authorized apply. `.stm32-project.json` is the versioned project intent; managed generated-file ownership is tracked separately under `.stm32-toolkit/`.

```powershell
stm32-toolkit --project-root C:\work\blinky doctor --json
stm32-toolkit --project-root C:\work\blinky project detect --json
stm32-toolkit --project-root C:\work\blinky keil inspect --uvprojx Project\blinky.uvprojx --json
stm32-toolkit --project-root C:\work\blinky project configure --dry-run --json
stm32-toolkit --project-root C:\work\blinky build --preset arm-debug --json
```

Keil-to-GCC migration is **one-way** and does not rewrite the Keil project. The candidate discovers nested Keil projects within the guarded root; multiple candidates require an explicit choice. Unsupported source encodings and ARMCC assembly require project-owned adaptation; Git changes, including untracked files, can block conversion. Configure preserves existing unowned regular `.vscode` target files while retaining managed-file drift protection; CubeMX regeneration has a separate inventory rule. Flash programming/readback does not establish that firmware is running. Probe access, handoff, reads, and physical tests require their explicit identity and authorization contracts.

Monitor is an observation UI with user-created monitor groups and no automatic probe connection. Open it from the verified launcher and its current authenticated browser tab. The allowed local Host is `127.0.0.1`, not a hand-entered `localhost` URL; never copy or log its token fragment. See the [user guide](docs/user-guide.md) for configuration constraints, all 22 issue remedies, and the Monitor entry command.

## Current documentation

- [User guide and troubleshooting](docs/user-guide.md): migration, generation, builds, Probe Service, Monitor, and upgrade decisions.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md): final runtime and debugger checks.
- [Architecture](docs/architecture.md), [development](docs/development.md), [standard test procedure](docs/testing/standard-test-procedure.md), and [release qualification](docs/testing/release-qualification.md).
- [Changelog](CHANGELOG.md) and [v1.0.1 patch specification](docs/superpowers/specs/2026-10-10-stm32tk-101-patch-design.md). The candidate implementation still requires independent review and release qualification.

The MCP inventory has all 48 public names, organized by project, build, probe, diagnostic, test, and acceptance workflows. `VS09-B` release construction uses the existing `tools/release/build_0900_artifacts.py` and pinned `release_0900_policy.json`; these historical filenames remain current packaging inputs. Old plans and reports removed from the current tree remain retrievable with `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`.
