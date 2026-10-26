# README delivery plan

Base: `ae53ac0ffb8db0a4c798d9bcaddca443e9e842d1`.
Primary freezes scope; Claude CLI rewrites only README.md and README_zh-CN.md
and updates the existing README contract test in
tools/stm32-toolkit/tests/test_plugin_layout.py. No other product/test changes.

Primary independently reviews the complete diff in a clean worktree, checking
language parity, actual release links, useful concise setup/usage and preserved
argument/authorization semantics. Claude runs the existing complete plugin-layout
file through the single supplied native PowerShell command; primary reconciles
actual source and results. No package rebuild or full regression is triggered.

After acceptance, push this bounded README delivery first under the user's
existing publication/update authorization, then integrate remaining reviewed
post-publication documents. Preserve all earlier partial edits and CLI logs.
No original firmware project, installed runtime, global setting or hardware action.
