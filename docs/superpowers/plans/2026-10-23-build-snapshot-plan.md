# Build snapshot implementation plan

Accepted base `690f579d4efe1d2616e0c1d9289263c24069134a`; branch `codex/build-snapshot`; primary specification/review/acceptance, local Claude Code CLI implementation/tests. The user authorizes the bounded local software work. No remote, installation or hardware action.

1. Inventory the current strict identity/result contracts and all immediate build/context/firmware admission consumers. Preserve schema-1 behavior.
2. Add optional build Git evidence and strict snapshot identity/record support; retain exact inputs and stale-output protections.
3. Adapt context freshness and clearly refuse unsupported snapshot hardware provenance before effects. Update MCP and VS Code guidance.
4. Add and run bounded relevant regressions in external `D:/codex-tmp/kg23` temp/cache/log roots using the existing dedicated Python venv and explicit worktree PYTHONPATH. Do not rerun a passing combined suite merely to make a second log; stream-json retains tool evidence. No skip/xfail to hide failures.
5. Commit product/tests/docs locally, then write `docs/codex/returns/BUILD-SNAPSHOT/implementation-report.md` naming the full accepted base and actual CodeHead before a separate report commit. Return exact files, tests, failures, limits and clean state without self-acceptance. Primary independently reviews/fixes through the same CLI and records acceptance.
6. Continue sequentially with separately specified GBK, ARMCC startup and multi-RAM slices at the accepted resulting heads. Those later features must be implemented and verified before claiming the user's whole request complete; each receives an isolated worktree. Keep other blind-test gaps explicitly unclaimed.
