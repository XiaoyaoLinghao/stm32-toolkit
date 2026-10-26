# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development: inspect an existing Keil project, migrate it to an ARM GCC/CMake build, build it, flash a target and debug it through a real probe, and watch variables in a browser Monitor. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## What you can do

- **Inspect and migrate Keil projects** — read-only inspection, then a guarded, one-way conversion from Keil/ARMCC to GCC and CMake. The Keil project itself is never rewritten.
- **Build firmware** — configure the project once, then build with ARM GCC, CMake and Ninja.
- **Work with real hardware** — list probes, flash managed build artifacts or imported ELF/AXF/HEX/BIN images, hand off to GDB, read variables and registers, and analyze faults.
- **Observe a running target** — a local Monitor UI with user-created groups that never connects to a probe on its own.
- **Use one backend everywhere** — the CLI and MCP server expose the same operations; VS Code consumes the MCP server plus optional generated tasks, and the bundled Claude Code skills are thin adapters over the same entry points.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Install the current release

The current published Latest is **v1.3.2** (2026-10-26). Download both files from the same [v1.3.2 Release page](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2):

- [stm32-toolkit-1.3.2-windows-x86_64.zip](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.2/stm32-toolkit-1.3.2-windows-x86_64.zip)
- [CHECKSUMS.sha256](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.2/CHECKSUMS.sha256)

Check the ZIP's SHA-256 against its line in `CHECKSUMS.sha256`, then extract the ZIP into a new, empty folder. It contains a `stm32-toolkit-1.3.2/` directory (the ToolkitRoot) and a sibling `release/` directory.

Choose three absolute paths of your own — the extracted ToolkitRoot, a durable DataRoot outside it, and your project root — and run the read-only `Check`:

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit\stm32-toolkit-1.3.2'
$DataRoot    = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& pwsh -NoProfile -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports the managed runtime as missing and you want to install it, run `Bootstrap` once:

```powershell
& pwsh -NoProfile -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

Then repeat `Check`; continue only after it reports healthy for `runtime/1.3.2`. Upgrades and repair of an existing installation use the same script, and the [user guide](docs/user-guide.md) covers those paths. If the machine execution policy blocks the script, resolve that with the machine owner rather than adding an `-ExecutionPolicy` override.

## Use the CLI

With a healthy check, call the installed launcher by absolute path. `doctor` is usable for diagnostics; the build example assumes a GCC/CMake project that is already configured or migrated:

```powershell
$Cli = Join-Path $DataRoot 'runtime\1.3.2\Scripts\stm32-toolkit.exe'
& $Cli version
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

Every project-bound command needs its own absolute `--project-root`. These examples call the executable by absolute path, so no `PATH` modification is required.

## Use it from an AI host or VS Code

MCP hosts launch `bin\stm32-toolkit-mcp.cmd` by absolute path with an explicit project root and data root, and set `STM32_TOOLKIT_DATA_ROOT` to the same DataRoot; Claude Code uses the bundled skills and `.mcp.json`. VS Code consumes the same MCP server and can add toolkit-generated build and debug tasks. Copyable configurations and the full setup are in the [user guide](docs/user-guide.md).

## Documentation

- [User guide](docs/user-guide.md) — installation and upgrade details, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history; the v1.3.2 Release page above records its notes and retained limitations.
