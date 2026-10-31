# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## Two core product routes

1. **New STM32 project** — create a project, configure the managed ARM GCC/CMake build, then build and flash through the normal authorized route.
2. **Existing Keil project** — inspect and preflight the Keil project read-only, review a deterministic delivery plan, then apply it to a **new independent output directory** (`keil convert --destination <absolute-new-output>`). The Keil source is never rewritten, and the delivered project builds on its own; bind its `outputRoot` and use the same configure, build and flash route.

Git is optional traceability for both routes, never an eligibility gate. Hardware operations require explicit device selection and authorization; this source tree makes no hardware-acceptance claim.

## Release status

Current latest published version: **v1.3.6**, published 2026-10-31 (15:22:13 Asia/Shanghai) as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.6) (release `429783935`, `draft=false`/`prerelease=false`, frozen source `b00cbc4e`). All 13 public assets were anonymously downloaded with HTTP 200, and every byte count and SHA-256 matches the frozen package. The previous published release is [v1.3.5](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5); [v1.3.4](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4) and older releases remain available. The [user guide](docs/user-guide.md) carries the current v1.3.6 receiving and upgrade recipe, the [v1.3.5 receiving guide](docs/v135-local-candidate.md) is the historical v1.3.5 record, and [release status](docs/release-status.md) retains publication evidence and coverage limits. Public download is not installation.

Current source version: **v1.3.6**, matching the published release above; later commits record publication only and change no product behavior. v1.3.6 keeps the 52-tool MCP inventory, 9 bundled Skills, the `pyocd==0.46.0` pin and the ordinary 100 kHz flash default with one authorized `SYSRESETREQ` reset-and-halt before programming. It deliberately does not add v1.3.5 runtime, project/`generatedBy` or build-identity compatibility. The release used a user-approved candidate-only non-regression condition: the permanent Toolkit overall/risk and Monitor risk gates remain unmet, and no fresh hardware or recipient installation/IDE/MCP acceptance is claimed. Final installation, upgrade/rollback and interactive validation remain user-owned and pending; this source tree makes no hardware-acceptance claim.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Documentation

- [User guide](docs/user-guide.md) — installation and upgrade, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- [v1.3.5 receiving guide](docs/v135-local-candidate.md) — previous-release identity checks, Check-first receiving and upgrade steps, and current limits.
- Claude Code: start with the bundled `/stm32-toolkit:setup-stm32-env` skill.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history and retained limitations.
