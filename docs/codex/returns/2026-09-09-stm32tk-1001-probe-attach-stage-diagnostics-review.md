# STM32TK-1001 Probe Attach Stage Diagnostics Review

Verdict: `ACCEPTED`

- Accepted base: `1d461f23fdde8a04c845b7e3989fe41318dd3ed8`
- Spec/plan head: `c623034a9934d320de87bc21b2f62ffa26bb8068`
- Reviewed CodeHead: `9fca124a354a1f751acd6a6c465b574c23d33d3f`
- Implementer: one GPT-5.6-luna/max agent
- Reviewer: GPT-5.6-sol
- Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
- Remote actions: none

The worker now publishes only an allowlisted attach `stage` for `PROBE_ATTACH_FAILED`. The pyOCD backend assigns a closed stage to session creation/opening, target resolution, halt/resume verification, and cleanup-resume failure. Error code and generic message remain stable. Extra keys, unknown stages, wrong types, raw backend messages, paths, and arbitrary details remain blocked. Existing service/client/flash forwarding required no product changes, and attach failure still performs zero programming.

Independent review found one first-round defect: the initial implementation rebound a normalized typed attach error but used bare `raise`, which rethrew the original error. The same implementer corrected that path and added a typed session-open regression. The complete `1d461f23..9fca124a` diff was reviewed after correction; `git diff --check` passed and no remaining finding was identified.

Implementation evidence recorded a minimal RED, focused GREEN, then 201 affected-file cases collected and completed without failure. Independent focused verification first had an ENVIRONMENT-only collection failure because `python -I` excluded the review worktree source path; no test executed in that invocation. With the review source path explicitly selected, 19 cases passed before the review correction and 15 final-head cases passed after it. The final set covered typed and untyped session-open failures, cleanup-resume, exact safe IPC preservation, malformed IPC rejection, public flash propagation, zero programming, and child cleanup.

This acceptance is limited to the local diagnostic contract. The deployed runtime remains the earlier `1d461f23` candidate and was not changed during this slice. No packaging, deployment, probe access, reset, resume, retry, flash, or OBSERVE occurred. The completed physical failure remains historically `PROBE_ATTACH_FAILED`; this code cannot reconstruct the stage that the prior worker discarded. Old-board attempt 7 remains PASS. The three observations, Task 9, Task 10, and VS10-A remain incomplete.
