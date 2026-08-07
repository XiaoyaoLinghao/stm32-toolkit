---
name: configure-stm32-project
description: Use when a Claude Code user asks to generate or update managed GCC/CMake and VS Code configuration for a validated STM32 project with an explicitly authorized apply.
---

# Configure STM32 Project

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). If `capabilities.configure` is `false`, report the context evidence and stop.
2. **Read-only plan.** Call `stm32_project_configure` with no `planId` and no `authorized` — this returns the deterministic `project-configuration-plan`. Show the plan's `plan_id`, every blocker, and each file's status and diff from `files` (create, update, unchanged, user-drift, unowned-collision).
3. **Stop on blockers.** If `blockers` is non-empty, or any target is `user-drift` or `unowned-collision`, report them and stop; never overwrite user changes.
4. **Authorize.** Ask the user for explicit authorization for the exact displayed `plan_id`. Never infer consent from the earlier read-only call.
5. **Apply.** Only after the user authorizes, call `stm32_project_configure(planId="<exact plan_id>", authorized=true)`. The core replans and rechecks the model, inputs, and drift guards before its first write.
6. **Return the result.** Report the `project-configuration-apply` result: the managed manifest path, generated file paths, and any warnings. If the result is a failure (`AUTHORIZATION_REQUIRED`, `PLAN_CHANGED`, `GENERATION_*`), report the exact code and details and stop.

## Rules

- The plan call is read-only; show it before any mutation.
- The apply call is the only mutation. Pass exactly the plan ID shown to the user.
- Do not edit generated files, run CMake, or invoke compilers yourself.
- Never claim success; report the returned `OperationResult` exactly as received and finish immediately.
