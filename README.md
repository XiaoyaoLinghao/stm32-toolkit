# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local, agent-neutral toolkit for STM32 projects. Its CLI and stdio MCP server share the same project, build, Probe Service, test, and Monitor contracts. The eight Claude Code Skills are adapters to those public entry points; the core does not depend on an agent host.

**Current version: v1.2.0.** The accepted source includes the Monitor workbench, source catalog, preserved-state connection, u16 composition, and consistent-read updates. The distribution platform is Windows x86_64 with CPython `>=3.12,<3.13`. Check the [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) for asset availability, final qualification and limitations; [release status](docs/release-status.md) retains a dated pre-freeze evidence checkpoint.

## Download, verify, then set up v1.2.0

For a v1.2.0 installation, confirm that the [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) lists both `stm32-toolkit-1.2.0-windows-x86_64.zip` and `CHECKSUMS.sha256`, then download them from that same page. If either asset is absent, stop; do not substitute an earlier bundle or GitHub's automatic source archive. Verify the ZIP before extraction; a missing or mismatched checksum is a stop. The bundle contains the matching source archive, release manifest and offline wheels. Do not mix files from different versions. CPython 3.12 must be available to bootstrap the managed runtime.

```powershell
$Download = 'C:\Users\you\Downloads'
$Bundle = Join-Path $Download 'stm32-toolkit-1.2.0-windows-x86_64.zip'
$Checksums = Join-Path $Download 'CHECKSUMS.sha256'
$ExpectedLine = @(Get-Content -LiteralPath $Checksums | Where-Object {
  $_ -match '^[0-9a-f]{64}  stm32-toolkit-1\.2\.0-windows-x86_64\.zip$'
})
if ($ExpectedLine.Count -ne 1) { throw 'Missing or duplicate v1.2.0 bundle checksum' }
$Expected = ($ExpectedLine[0] -split '  ', 2)[0]
$Actual = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw 'Bundle SHA256 mismatch' }
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
if (Test-Path -LiteralPath $BundleRoot) { throw 'BundleRoot exists; choose a new path' }
Expand-Archive -LiteralPath $Bundle -DestinationPath $BundleRoot
```

Use a new, version-specific BundleRoot. If that path already exists, stop and choose another new directory; do not overwrite or delete it. The ZIP places `stm32-toolkit-1.2.0/` and an outer `release/` beside each other inside BundleRoot. ToolkitRoot is the former directory and has its own `release/release-manifest.json` for setup. Keep DataRoot durable and separate from BundleRoot, the project and disposable test directories. The setup script's `Check` is read-only and verifies the bundle/runtime contract. Inspect its result before explicitly choosing a missing-runtime `Bootstrap` or an authorized `Repair`; repeat `Check` afterward. The v1.2.0 CLI/MCP expects the managed interpreter in `DataRoot/runtime/1.2.0` and has no system-Python fallback. Existing v1.1.2, v1.0.1 and older approved runtimes can enter v1.2.0 only through authorized Repair, with the old runtime quarantined under the existing transaction recovery rules; see the [recorded rollback scope](docs/release-status.md).

```powershell
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
$ToolkitRoot = Join-Path $BundleRoot 'stm32-toolkit-1.2.0'
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

Use the installed v1.2.0 console launcher after a healthy `Check`. Detection, inspection, and the first configure call are read-only. Review the returned plan and blockers before any authorized apply. `.stm32-project.json` is the versioned project intent; managed generated-file ownership is tracked separately under `.stm32-toolkit/`.

```powershell
$Cli = Join-Path $DataRoot 'runtime\1.2.0\Scripts\stm32-toolkit.exe'
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot project detect --json
& $Cli --project-root $ProjectRoot keil inspect --uvprojx Project\blinky.uvprojx --json
& $Cli --project-root $ProjectRoot project configure --dry-run --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

Keil-to-GCC migration is **one-way** and does not rewrite the Keil project. v1.2.0 discovers nested Keil projects within the guarded root; multiple candidates require an explicit choice. Unsupported source encodings and ARMCC assembly require project-owned adaptation; Git changes, including untracked files, can block conversion. Configure preserves existing unowned regular `.vscode` target files while retaining managed-file drift protection; CubeMX regeneration has a separate inventory rule. Flash programming/readback does not establish that firmware is running. Probe access, handoff, reads, and physical tests require their explicit identity and authorization contracts.

Monitor is an observation UI with user-created monitor groups and no automatic probe connection. After a healthy `Check`, open it from the verified v1.2.0 launcher in a foreground terminal:

```powershell
$env:STM32_TOOLKIT_DATA_ROOT = $DataRoot
& (Join-Path $ToolkitRoot 'bin\stm32-monitor.cmd') open --project $ProjectRoot --data-root $DataRoot --port 8765
```

Use the current authenticated browser tab. The allowed local Host is `127.0.0.1`, not a hand-entered `localhost` URL; never copy or log its token fragment. Stop the foreground service with Ctrl-C. See the [user guide](docs/user-guide.md) for configuration constraints, all 22 issue remedies, and session recovery.

## Current documentation

- [User guide and troubleshooting](docs/user-guide.md): migration, generation, builds, Probe Service, Monitor, and upgrade decisions.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md): final runtime and debugger checks.
- [Architecture](docs/architecture.md), [development](docs/development.md), [standard test procedure](docs/testing/standard-test-procedure.md), and [release qualification](docs/testing/release-qualification.md).
- [Changelog](CHANGELOG.md) and [v1.2.0 source-delivery specification](docs/superpowers/specs/2026-10-21-monitor-v120-delivery-design.md). The [v1.0.1 execution ledger](docs/codex/returns/STM32TK-101/execution.md) retains its historical qualification record.

The current source inventory has 52 public MCP names, including `stm32_keil_preflight`, `stm32_firmware_import`, `stm32_firmware_admit`, and `stm32_flash_imported`, organized by project, build, probe, diagnostic, test, and acceptance workflows. The published v1.2.0 runtime remains the frozen 48-tool package and does not contain these source-only entries. `VS09-B` release construction uses the existing `tools/release/build_0900_artifacts.py` and pinned `release_0900_policy.json`; these historical filenames and the frozen policy remain current packaging inputs, not evidence that the source slice is packaged or deployed. Old plans and reports removed from the current tree remain retrievable with `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`.

The source-only external-firmware route imports an original ELF/AXF, Intel HEX, or BIN file into an immutable project-bound snapshot, admits it offline, and only then offers a separately authorized flash to one exact probe. It needs no managed manifest, Git repository, build receipt, or SVD. `capabilities.flash` in project context describes only the managed build route; an unmanaged project can use the imported route when the bound server actually exposes these tools. The imported source SHA-256 and the normalized programming image SHA-256 are separate fields, and an imported receipt never unlocks debug, Monitor, Target tests, or a fabricated build identity. See the [user guide](docs/user-guide.md).
