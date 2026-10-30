# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## Two core product routes

1. **New STM32 project** — create a project, configure the managed ARM GCC/CMake build, then build and flash through the normal authorized route.
2. **Existing Keil project** — inspect and preflight the Keil project read-only, review a deterministic delivery plan, then apply it to a **new independent output directory** (`keil convert --destination <absolute-new-output>`). The Keil source is never rewritten, and the delivered project builds on its own; bind its `outputRoot` and use the same configure, build and flash route.

Git is optional traceability for both routes, never an eligibility gate. Hardware operations require explicit device selection and authorization; this source tree makes no hardware-acceptance claim.

## Release status

Current latest published version: **v1.3.5**, published 2026-10-30 as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5) with 13 downloadable assets. The previous published release is [v1.3.4](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4), and earlier releases remain available. Release identity checks, Check-first receiving and upgrade steps, and current limits are in the [v1.3.5 receiving guide](docs/v135-local-candidate.md); the [user guide](docs/user-guide.md) now carries the current v1.3.5 installation and upgrade recipe and general workflows, while keeping the v1.3.4 release recipe as previous published guidance, and [release status](docs/release-status.md) records publication evidence and retained limitations.

Current source version: **v1.3.6**, a local candidate that is not yet published. No v1.3.6 release page exists, so the links and release facts above continue to describe the observed v1.3.5 Latest release; publication remains a separate authorized action, and publication or download is not installation.

v1.3.5 keeps the 52-tool MCP inventory and 9 bundled Skills and pins the isolated pyOCD distribution to `0.46.0`. Ordinary managed and imported flash default to `100000 Hz` (100 kHz) as selected configuration, not a measured clock; a higher frequency is an optional explicit choice and no 1 MHz gate applies. A normal confirmed flash performs one authorized `SYSRESETREQ` reset-and-halt and requires `HALTED` before programming; failure stops the route with no automatic retry or recovery, and a successful flash still reports `targetState=unknown` and `runVerified=false`. Existing v1.3.4 and earlier runtimes are explicit upgrade inputs and never advance by a restart alone. The per-group non-regression condition passed, while permanent Toolkit overall/risk and Monitor risk coverage gates remain unmet. Public download is not installation: final recipient installation/upgrade/rollback, VS Code/MCP and interactive validation remain user-owned and pending, and this source tree makes no hardware-acceptance claim.

v1.3.4 (previous published release) accepts structurally balanced outer include guards that allow independent nested conditionals, while true nested macro definitions remain rejected, and its read-only preflight discovers potential quoted-header encoding blockers without transcoding. Neither change alters ABI decisions, debug-address inference or transcoding. Permanent coverage/risk gates remain unmet under a candidate-only user-approved exception, and final installation and VS Code verification remain user-owned and pending. The earlier [v1.3.3](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3) release remains available.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Documentation

- [User guide](docs/user-guide.md) — installation and upgrade, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- [v1.3.5 receiving guide](docs/v135-local-candidate.md) — release identity checks, Check-first receiving and upgrade steps, and current limits.
- Claude Code: start with the bundled `/stm32-toolkit:setup-stm32-env` skill.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history and retained limitations.
