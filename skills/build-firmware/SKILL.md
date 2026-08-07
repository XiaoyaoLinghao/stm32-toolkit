---
name: build-firmware
description: Use when a Claude Code user asks to build STM32 firmware with the managed ARM GNU/CMake configuration and report reproducible firmware identity evidence.
---

# Build Firmware

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). If `capabilities.build` is `false`, report the context evidence and stop.
2. **Doctor.** Call `stm32_doctor` (no arguments). Show the toolchain evidence: ARM GCC, ARM GDB, CMake, and Ninja availability. Report missing tools and stop when the toolchain is not healthy.
3. **State the invocation.** Show the preset (`arm-debug` or `arm-release`), `clean` (only when the user asked for a clean build), the timeout, and the toolchain evidence for this exact build invocation.
4. **Authorize.** Ask the user for explicit authorization for this build invocation. `stm32_build` is not a dry run; it never runs without `authorized=true`.
5. **Build.** After explicit authorization, call `stm32_build(preset="arm-debug|arm-release", clean=false, timeoutSeconds=300, authorized=true)`.
6. **Report evidence.** From the returned `build` result, report: the build ID, Git HEAD and dirty state, ELF and MAP SHA-256 hashes, memory usage per region, warnings, and the portable artifact paths (`buildLogPath`, `buildResultPath`, `identityPath`). If the result is a failure (`AUTHORIZATION_REQUIRED`, `BUILD_*`, `RAM_OVERFLOW`, `FLASH_OVERFLOW`, ...), report the exact code and details and stop.

## Rules

- Never run CMake, Ninja, or a compiler directly; the Toolkit build is the only build path.
- Never fabricate success: a failed build returns no fresh identity, and the previous ELF is stale.
- Report the returned `OperationResult` exactly as received and finish immediately.
