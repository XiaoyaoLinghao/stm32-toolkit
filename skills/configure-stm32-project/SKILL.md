---
name: configure-stm32-project
description: Use when a Claude Code user asks to generate or update managed GCC/CMake and VS Code configuration for a validated STM32 project with an explicitly authorized apply.
---

# Configure STM32 Project

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). If `capabilities.configure` is `false`, report the context evidence and stop.
2. **Read-only plan.** Call `stm32_project_configure` with no `planId` and no `authorized` — this returns the deterministic `project-configuration-plan`. Show the plan's `plan_id`, every blocker, and each file's status and available diff from `files` (create, unchanged, update-managed, user-drift, unowned-collision, preserved-unowned). A `preserved-unowned` editor file has no original-content diff because Toolkit does not read it.
3. **Stop on blockers.** If `blockers` is non-empty, or any target is `user-drift` or `unowned-collision`, report them and stop; never overwrite user changes. The five fixed `.vscode` JSON targets may be `preserved-unowned` when they are regular files without prior managed records. They are safe to leave in place, but the user must align their IDE configuration with the generated build.
4. **Authorize.** Ask the user for explicit authorization for the exact displayed `plan_id`. Never infer consent from the earlier read-only call.
5. **Apply.** Only after the user authorizes, call `stm32_project_configure(planId="<exact plan_id>", authorized=true)`. The core replans and rechecks the model, inputs, and drift guards before its first write.
6. **Return the result.** Report the `project-configuration-apply` result: the managed manifest path, created/updated paths, `preservedPaths`, and warnings. The preserved paths are outside the managed manifest and must not be counted as generated or unchanged files. If the result is a failure (`AUTHORIZATION_REQUIRED`, `PLAN_CHANGED`, `GENERATION_*`), report the exact code and details and stop.

## Rules

- The plan call is read-only; show it before any mutation.
- The apply call is the only mutation. Pass exactly the plan ID shown to the user.
- Do not edit generated files, run CMake, or invoke compilers yourself.
- Configure preserving an editor file does not make CubeMX regeneration ready: regeneration has its own closed inventory and can still reject an unknown editor path. The generated linker template reserves the default 4 KiB heap and 1 KiB stack; memory usage reports linker allocation/reservation, not runtime peak use. A native linker script remains user-owned.
- Never claim success; report the returned `OperationResult` exactly as received and finish immediately.
