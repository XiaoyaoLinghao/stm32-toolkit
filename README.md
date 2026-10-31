# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## Two core product routes

1. **New STM32 project** — create a project, configure the managed ARM GCC/CMake build, then build and flash through the normal authorized route.
2. **Existing Keil project** — inspect and preflight the Keil project read-only, review a deterministic delivery plan, then apply it to a **new independent output directory** (`keil convert --destination <absolute-new-output>`). The Keil source is never rewritten, and the delivered project builds on its own; bind its `outputRoot` and use the same configure, build and flash route.

Git is optional traceability for both routes, never an eligibility gate. Hardware operations require explicit device selection and authorization; this source tree makes no hardware-acceptance claim.

## Release status

Current source version: **v1.3.6**. [Release v1.3.6](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.6) was published on 2026-10-31. Use [Latest release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/latest) for current downloads. [v1.3.5](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5) and earlier releases remain available as historical versions.

**Documentation revision — 2026-10-31:** This English README and its Chinese counterpart correct the original v1.3.6 archives' outdated claim that v1.3.6 was unpublished. The v1.3.6 tag remains at `b00cbc4edee191712dd6da7e1beb073ff4a74f28`; the revised archives have a separate documentation source commit, recorded in `release-manifest.json`, and updated `CHECKSUMS.sha256`. Runtime source, product/dependency wheels, firmware behavior and identity checks are unchanged. Other bundled documentation remains a build-time snapshot; use the [v1.3.6 receiving and installation guide](https://github.com/XiaoyaoLinghao/stm32-toolkit/blob/2606eb7b1fd3f105c3d5442f417d47fdb06acb8f/docs/user-guide.md) and the Release page for current instructions and publication facts. The bundled [v1.3.5 receiving guide](docs/v135-local-candidate.md) is historical.

Existing v1.3.6 installations need no reinstall or runtime repair for this documentation correction. Using the revised archive to repair an original v1.3.6 installation intentionally produces `source-conflict` under the existing same-version identity check; do not edit runtime state or bypass it. For an existing installation, read the corrected README online.

v1.3.6 retains 52 MCP tools, 9 bundled Skills, `pyocd==0.46.0`, ordinary 100 kHz flash and the authorized pre-programming `SYSRESETREQ` reset-and-halt. It adds no v1.3.5 runtime, project/`generatedBy` or build-identity compatibility. Permanent Toolkit overall/risk and Monitor risk coverage gates remain unmet under the separately approved original-candidate exception. A documentation revision makes no new hardware or recipient installation/IDE/MCP acceptance claim.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Documentation

- [User guide](https://github.com/XiaoyaoLinghao/stm32-toolkit/blob/2606eb7b1fd3f105c3d5442f417d47fdb06acb8f/docs/user-guide.md) — installation and upgrade, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- [v1.3.5 receiving guide](docs/v135-local-candidate.md) — historical v1.3.5 release identity checks, Check-first receiving and upgrade steps, and retained limits.
- Claude Code: start with the bundled `/stm32-toolkit:setup-stm32-env` skill.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history and retained limitations.
