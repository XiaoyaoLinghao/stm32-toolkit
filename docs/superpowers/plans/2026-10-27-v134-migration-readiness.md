# v1.3.4 bounded implementation and delivery plan

Accepted base: `dc278ca226a0c1d4540657f48eb74fa1d5b361ca`.
Branch: `codex/v134-migration-readiness`. The user approved the scope in the
[specification](../specs/2026-10-27-v134-migration-readiness.md); no separate plan stop.

1. Claude file-only implementation: structural outer-guard recognition in
   `migration/constant_context.py`; bounded dependency encoding inventory in
   `migration/header_encoding.py` and preflight integration in `migration/preflight.py`;
   regressions in `test_migration_readiness_v134.py`, with precise existing-test
   updates only if additive diagnostics require them. No commands in the edit task.
2. Claude exact native PowerShell verification: new regressions, existing constant
   and ARMCC syntax/refusal tests, preflight/diagnostic and plan/delivery regressions.
   Use CPython `D:/codex-tmp/kx23/venv/Scripts/python.exe`, short isolated paths under
   `D:/codex-tmp/r134`, worktree-bound PYTHONPATH, native branch data and fresh JUnit.
   Main commands are short groups; no retries absent a separately bounded correction.
3. Primary independently reviews the entire diff, reconciles native events/reports,
   performs selected offline verification at the exact CodeHead in a clean tree,
   and runs read-only original/prepared project checks. Any fixes return to Claude;
   two correction rounds maximum per issue before design reconsideration.
4. Separate Claude version/docs alignment to 1.3.4 using the established release
   identity and upgrade contract. Do not edit dependency/schema versions blindly.
   Recompute trust pins from canonical Git bytes and run affected release/setup,
   version, documentation and real-GCC synthetic-journey checks. Reconcile branch
   coverage with matching v1.3.3 evidence, removing old data on changed source.
5. Freeze reviewed source. Two clean canonical official offline package builds,
   compare all 13 assets, verify extracted bundle, and retain qualification limits.
   Installation/VS Code remain user-owned; no hardware operations are authorized.
6. When qualification passes or a concrete exception is explicitly approved, verify
   remote ancestry/authentication without exposing credentials, non-force publish
   source and annotated v1.3.4 tag, upload verified assets to a draft, verify, publish
   Latest, and anonymously download/hash all assets. Record observed publication.

Primary owns all acceptance, packaging orchestration and remote actions. Claude's
model remains the configured `deepseek-v4.1-flash[1m]` route; actual init inventory
and native matched calls are the only tool evidence. No-action inventory and
verify-only harmless smoke precede each task according to claude-dispatch.
Missing numeric native exits remain null, and pending worker results end that run.
Retain exact source states, commands, reports and limits under `D:/codex-tmp/r134`;
tracked acceptance report identifies CodeHead before its own report commit.
