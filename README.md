# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## Two core product routes

1. **New STM32 project** — create a project, configure the managed ARM GCC/CMake build, then build and flash through the normal authorized route.
2. **Existing Keil project** — inspect and preflight the Keil project read-only, review a deterministic delivery plan, then apply it to a **new independent output directory** (`keil convert --destination <absolute-new-output>`). The Keil source is never rewritten, and the delivered project builds on its own; bind its `outputRoot` and use the same configure, build and flash route.

Git is optional traceability for both routes, never an eligibility gate. Hardware operations require explicit device selection and authorization; this source tree makes no hardware-acceptance claim.

## Release status

Current source: **v1.3.3 release candidate**. Published release: [v1.3.2](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2). See the [user guide](docs/user-guide.md) for installation, upgrades, migration differences and validation limits.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Documentation

- [User guide](docs/user-guide.md) — installation and upgrade, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- Claude Code: start with the bundled `/stm32-toolkit:setup-stm32-env` skill.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history and retained limitations.
