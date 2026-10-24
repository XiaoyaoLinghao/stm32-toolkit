# KEIL-SCOPED-INCLUDES plan

Governing [specification](../specs/2026-10-24-keil-scoped-includes-design.md), accepted base `e9b242ec8f97f30135693ca5b0f3f9d8465a7615`. Primary specification/review owner; Claude Code CLI implementation/evidence owner; no remote or hardware actions authorized.

1. Verify current CLI native PowerShell registration and actual harmless shell execution. File-only authoring and exact-command PowerShell testing are separate invocations with empty MCP configuration.
2. Implement deterministic bounded include analysis, model/report/plan identity wiring and preflight presentation. Retain no-scope behavior and all apply guards.
3. Add synthetic regression tests and update VS Code/migrate-keil instructions. Author returns changed files, source state and limits; file-only completion is not a test result.
4. Coordinator freezes CodeHead locally. Claude runs new tests plus migration plan/apply, Keil inspect/preflight and MCP migration routing. Exact argv, source and native tool results are retained. Fix actual failures through the same Claude session, not primary code patches.
5. Primary independently reads the entire diff in a clean isolated review worktree and runs the focused module/public-path tests. Two unsuccessful rounds on one finding require returning to design.
6. Record implementation and independent acceptance evidence. Continue to a separately specified common ARMCC syntax slice from the accepted include result. No package rebuild or installation in this bounded source work.
