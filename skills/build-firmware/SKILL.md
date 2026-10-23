---
name: build-firmware
description: Use when a Claude Code user asks to build STM32 firmware with the managed ARM GNU/CMake configuration and report reproducible firmware identity evidence.
---

# Build Firmware

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). Read `capabilityDetails.build`: `available` means build evidence is complete; `blocked` means the stated prerequisite is missing; `not-evaluated` means context did not check it. If the status is `blocked`, report the evidence and next step and stop. Never stop solely because a legacy hardware boolean is `false`: those booleans mean "not evaluated in context", not "the tool is unavailable".
2. **Doctor.** Call `stm32_doctor` (no arguments). Show the toolchain evidence: ARM GCC, ARM GDB, CMake, and Ninja availability. Report missing tools and stop when the toolchain is not healthy. CubeMX/VS Code versions come from static metadata; `unknown` is not a verified version. VS Code extensions marked `not-probed` were not enumerated. `probeCore.registry` describes the Probe lease directory; `missing` does not mean PyOCD has no targets and does not change its `safe` result.
3. **State the invocation.** Show the preset (`arm-debug` or `arm-release`), `clean` (only when the user asked for a clean build), the timeout, and the toolchain evidence for this exact build invocation.
4. **Authorize.** Ask the user for explicit authorization for this build invocation. `stm32_build` is not a dry run; it never runs without `authorized=true`.
5. **Build.** After explicit authorization, call `stm32_build` with the exact preset, clean value, and timeout shown in step 3 and approved in step 4, plus `authorized=true`. Do not substitute a default for an approved clean build.
6. **Report evidence.** From the returned `build` result, report: the build ID, identity `schemaVersion`, provenance (`sourceBaseline`), Git HEAD and dirty state, ELF and MAP SHA-256 hashes, memory usage per region, warnings, and the portable artifact paths (`buildLogPath`, `buildResultPath`, `identityPath`). A schema-1 identity has a 40-character `gitHead` and boolean `gitDirty`. A schema-2 identity means Git was unavailable: `sourceBaseline` is `input-snapshot-v1`, `gitHead` and `gitDirty` are JSON `null`, and `gitEvidence` is bounded to `{status:"unavailable", code:"BUILD_GIT_INVALID", rule:"head"|"status"}`. Never report null as clean and never invent a commit. If the result is a failure (`AUTHORIZATION_REQUIRED`, `BUILD_*`, `RAM_OVERFLOW`, `FLASH_OVERFLOW`, ...), report the exact code and details and stop.

## Rules

- Never run CMake, Ninja, or a compiler directly; the Toolkit build is the only build path.
- Never fabricate success: a failed build returns no fresh identity, and the previous ELF is stale.
- Git failure alone is not a build failure, but never run `git init`, commit, stash, or otherwise change Git state to make a build pass.
- A schema-2 snapshot identity is build-only evidence. Do not suggest flash, debug, Target tests, Monitor or acceptance for it; shared firmware admission returns `FIRMWARE_PROVENANCE_UNSUPPORTED` before any probe effect, and wrappers may map it (acceptance recovery maps it to `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID`). To use hardware, restore a Git repository with a committed HEAD and rebuild.
- Distinguish unavailable, blocked, and not-evaluated evidence. A missing managed manifest or drifted managed file is blocked; probe/hardware capabilities are not evaluated by context and do not by themselves prevent a build. Probe discovery (`stm32_probe_list`) remains independent of firmware provenance.
- Report the returned `OperationResult` exactly as received and finish immediately.
