# Keil readiness implementation plan

- Accepted base: `89f76ee5551dfdc313f3f37d2d9e760af47daac8`.
- Specification: `docs/superpowers/specs/2026-10-23-keil-readiness-design.md`, authorized by the user's request to implement preflight, diagnostics, independent discovery and correct VS Code guidance.
- Branch: `codex/keil-readiness`; implementer: local Claude Code CLI using existing provider/model; reviewer and acceptance owner: primary agent. No PR or remote action authorized.
- Preserve the main checkout's previously requested AGENTS.md change. Copy that policy into this implementation worktree; historical agent identities in reports remain historical.

1. Factor the existing migration technical analysis from Git-bound plan construction. Add preflight workflow, CLI and MCP adapters and public inventory with precise descriptions; retain existing plan/apply guards and identifiers.
2. Add structured context readiness and hardware validation details. Separate the probe-list preparation path from target/model-dependent hardware preparation, preserving ownership, data-root and cancellation/cleanup behavior.
3. Update migration/build/flash guidance and current user docs to reflect actual arguments, status meanings, safe remediation and operation boundaries. Update only the current ownership sentence in the standard test procedure to match the user's Claude CLI instruction; do not rewrite historical records.
4. Implement focused offline regression tests for each specification requirement and run affected existing migration, context, hardware, CLI, MCP, root-safety and inventory/skill suites. Record commands, exits and summaries under `D:\codex-tmp\kx23`; use separate short basetemp/cache/temp paths for each run and explicit worktree PYTHONPATH.
5. Commit the implementation locally, report exact CodeHead and complete file/test inventory without claiming acceptance. Primary independently reviews the entire accepted-base diff and tests the final clean source; corrections return to the same Claude CLI task. Record acceptance and integrate reviewed changes locally while preserving unrelated user work. Remote publication and physical validation are separate work.
