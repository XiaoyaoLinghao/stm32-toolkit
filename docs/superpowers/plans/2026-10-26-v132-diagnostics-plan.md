# v1.3.2 bounded implementation and delivery plan

Design: ../specs/2026-10-26-v132-diagnostics-design.md.
Accepted base `cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`; primary specification/
review owner, Claude CLI existing configured provider implementation/test owner.
User approved behavior and release; no separate written-plan approval stop.

1. Use clean isolated `codex/v132-guidance`. Verify native PowerShell inventory
   and one harmless exact command. File-only implementation first; exact-command
   verification second, with explicit AGENTS instructions and no permission bypass.
2. Implement only doctor/configure guidance, tests and caller documentation.
   Initial editable sources: doctor.py, generation/managed_files.py,
   generation/configure.py, vscode_configuration.py; affected doctor/generation/
   vscode/CLI/MCP tests; docs/user-guide.md and relevant setup/configure Skills.
   No generation content, hash, hardware, authorization or ownership changes.
3. Author runs complete affected test files with Python3.12.14 and actual JUnit
   output in short isolated D:/codex-tmp/r132 roots. Primary freezes CodeHead,
   reviews the entire diff in a separate clean worktree and verifies meaningful
   focused behavior/CLI/MCP checks. Corrections return to Claude, maximum two
   rounds for the same finding before redesign. Keep all failure evidence.
4. Claude aligns active version/compatibility/release files to1.3.2 in a second
   explicit phase; coordinator supplies the exact permitted file inventory after
   source inspection. Verify version, public inventory, setup/legacy1.3.1,
   generation producer, packaging and relevant CLI/doctor tests. Preserve published
   evidence and do not modify installed runtimes or original project.
5. Freeze accepted source and run official packaging twice in clean source trees,
   using the already verified wheelhouse. Verify all13 outputs, source/wheel/
   manifest versions and official bundle integrity. No new installation or physical
   matrix is authorized by this offline-first patch. Preserve named user-owned
   final installation/IDE validation and exact coverage limitations; request any
   necessary new candidate-only exception only with concrete reviewable artifacts.
6. Deliver the user-requested v1.3.2 source/tag/Release, verify anonymous public
   assets and Latest disposition as authorized, and record final state accurately.
