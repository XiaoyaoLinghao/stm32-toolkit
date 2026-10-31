# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local toolkit for STM32 development. The CLI and the MCP server share one backend and one project model, so the same operations work from a terminal, an MCP-capable AI host, or VS Code.

## Two core product routes

1. **New STM32 project** — create a project, configure the managed ARM GCC/CMake build, then build and flash through the normal authorized route.
2. **Existing Keil project** — inspect and preflight the Keil project read-only, review a deterministic delivery plan, then apply it to a **new independent output directory** (`keil convert --destination <absolute-new-output>`). The Keil source is never rewritten, and the delivered project builds on its own; bind its `outputRoot` and use the same configure, build and flash route.

Git is optional traceability for both routes, never an eligibility gate. Hardware operations require explicit device selection and authorization; this source tree makes no hardware-acceptance claim.

## Release status

Current latest published version: **v1.3.6**, published 2026-10-31 (15:22:13 Asia/Shanghai) as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.6) with 13 downloadable assets. The release is formal Latest (`draft=false`/`prerelease=false`, ID `429783935`) and binds frozen source `b00cbc4e`; all 13 uploaded filenames, sizes and server SHA-256 digests match the frozen package, whose Windows ZIP is 119432768 bytes with SHA-256 `61170df3c700e1fceb0fc9e9c3f3845d92f7e6a17bca54614f707630d14bdbc1`. Anonymous public download and re-hash verification is still in progress, so no public-download PASS is recorded yet. The previous published release is [v1.3.5](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5), the earlier one is [v1.3.4](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4), and older releases remain available. The [v1.3.5 receiving guide](docs/v135-local-candidate.md) retains that previous release's identity checks and Check-first receiving steps; the [user guide](docs/user-guide.md) carries the v1.3.5 published installation and upgrade recipe and general workflows, while keeping the v1.3.4 release recipe as previous published guidance, and [release status](docs/release-status.md) records publication evidence and retained limitations. Public download is not installation.

Current source version: **v1.3.6**, matching the published release above; later commits in this tree record publication only and change no product behavior.

v1.3.6 keeps the 52-tool MCP inventory and 9 bundled Skills and pins the isolated pyOCD distribution to `0.46.0`. Ordinary managed and imported flash default to `100000 Hz` (100 kHz) as selected configuration, not a measured clock; a higher frequency is an optional explicit choice and no 1 MHz gate applies. A normal confirmed flash performs one authorized `SYSRESETREQ` reset-and-halt and requires `HALTED` before programming; failure stops the route with no automatic retry or recovery, and a successful flash still reports `targetState=unknown` and `runVerified=false`. The v1.3.6 source changes are evidence-only for migration ABI provenance, build-result `toolkitVersion`, preset-owned receipt paths and nullable backend programming telemetry. v1.3.6 deliberately does not add v1.3.5 to the legacy managed-runtime or `generatedBy` allowlists: no v1.3.5-to-v1.3.6 `Repair`, project/`generatedBy` compatibility or build-identity compatibility is promised, existing allowlisted older behavior is unchanged rather than expanded, and a real `Check` or schema rejection is never worked around by relabelling. A fresh v1.3.6 install in its own clean DataRoot with a matching `Check` is the supported current route; the versioned v1.3.5 bundle remains its own historical route. The publication used a user-approved non-regression coverage condition recorded with the [v1.3.6 authorization](docs/codex/returns/STM32TK-136/authorization-2026-10-31.md): permanent Toolkit overall/risk and Monitor risk gates remain unmet, 9,720 distinct Python passes with 20 named skips and source-bound reuse remain as recorded, and no fresh hardware or recipient installation/IDE/MCP acceptance is claimed.

v1.3.5 (previous published release) established the 100 kHz default and pre-program `SYSRESETREQ` reset-and-halt, and retained the 52-tool/9-Skill inventory with `pyocd==0.46.0`; v1.3.6 keeps those settings. Existing v1.3.4 and earlier runtimes are explicit upgrade inputs and never advance by a restart alone. The per-group non-regression condition passed, while permanent Toolkit overall/risk and Monitor risk coverage gates remain unmet. Public download is not installation: final recipient installation/upgrade/rollback, VS Code/MCP and interactive validation remain user-owned and pending, and this source tree makes no hardware-acceptance claim.

v1.3.4 (older published release) accepts structurally balanced outer include guards that allow independent nested conditionals, while true nested macro definitions remain rejected, and its read-only preflight discovers potential quoted-header encoding blockers without transcoding. Neither change alters ABI decisions, debug-address inference or transcoding. Permanent coverage/risk gates remain unmet under a candidate-only user-approved exception, and final installation and VS Code verification remain user-owned and pending. The earlier [v1.3.3](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3) release remains available.

## Requirements

Windows x86_64, CPython 3.12 (`>=3.12,<3.13`) for the managed runtime, and native PowerShell 7 (`pwsh`). The runtime never falls back to a system Python. Firmware builds additionally need the ARM GNU toolchain, CMake and Ninja; `doctor` reports their availability, and read-only Keil inspection does not require them.

## Documentation

- [User guide](docs/user-guide.md) — installation and upgrade, Keil migration, configuration, builds, probes, Monitor, MCP server, VS Code, and troubleshooting.
- [v1.3.5 receiving guide](docs/v135-local-candidate.md) — previous-release identity checks, Check-first receiving and upgrade steps, and current limits.
- Claude Code: start with the bundled `/stm32-toolkit:setup-stm32-env` skill.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md) — runtime, debugger and extension checks.
- [Changelog](CHANGELOG.md) — version history and retained limitations.
