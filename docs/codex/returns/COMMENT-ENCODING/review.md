# COMMENT-ENCODING independent acceptance

Verdict: ACCEPTED_WITH_FIXES (2026-10-23).

Primary owns specification, orchestration, complete-diff review and acceptance. Local Claude Code CLI, using the existing configured deepseek-v4.1-flash[1m] provider, owns implementation, tests and corrections. No Codex-hosted implementation agent was used.

- Accepted base: 863f0ec9adf5cb00a994fd5faa93be28efb0ec4d.
- Final CodeHead: aae4a733668414edea383c97b4ccead60a22df7a.
- Implementation report head: 80dc7c7819fdacc60ea78393828f9e039319d4a7.
- Reviewed clean worktree: C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit, exact code tree then report-only descendant.
- Full diff retained: D:/codex-tmp/ce23/primary-complete-final.diff. Entire helper, tests, final corrections and guidance were reviewed; no remaining blocking finding in the approved scope.

The skill is an explicit-charset, comment-only preview and selected-file copy workflow. It never guesses a charset or rewrites original files. Legacy non-ASCII outside comments, invalid encodings, private-use legacy text and unsupported lexical constructs remain blocked. Copy requires a freshly revalidated, reviewed ready plan and existing task authorization. It preserves all non-comment bytes, newline structure and file boundaries and produces only selected normalized files, not a complete migrated project.

Review corrections cover include/header-name contexts, late diagnostics and shared finding bounds, raw reparse ancestors, strict sizes/metadata and resource bounds, reserved output-name aliases, durable incomplete markers, linear token scanning, absolute loaded-skill helper resolution and accurate authorization/exit semantics. The implementation report retains the exact corrections and CLI evidence.

## Independent evidence

Primary ran the final clean CodeHead command using Python 3.12.14 at D:/codex-tmp/kx23/venv/Scripts/python.exe, explicit same-tree PYTHONPATH and isolated TEMP/TMP/TMPDIR:

    python -m pytest tools/stm32-toolkit/tests/test_normalize_source_comments.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_migration_plan.py::test_invalid_encoding_adds_blocker tools/stm32-toolkit/tests/test_keil_inspect.py::test_invalid_encoding_blocker --basetemp=D:/codex-tmp/ce23/bt-primary-final -o cache_dir=D:/codex-tmp/ce23/cache-primary-final -ra

Result: 65 passed, one existing pydantic-settings warning, 10.55 seconds, exit 0. Includes actual ARM GNU object-byte comparisons for GB2312, GBK, GB18030 and CP1252, and skill validation. Logs: primary-final.log and primary-final.exit.txt under D:/codex-tmp/ce23. git diff --check passed; clean review tree before this report. Earlier CLI 234 migration/Keil results are attributed to their recorded earlier source state, not re-labelled as final-head execution.

Primary also verified a real Windows directory junction ancestor fails with REPARSE_PATH before preview output (junction-eval evidence; guard unchanged since that test). The read-only original-project preview proposed Main/Main.c, kept valid UTF-8 unchanged, and blocked the selected damaged/PUA files. All 54 registered source hashes still match the retained inventory; no original-project copy/apply/build or hardware action occurred.

Fresh independent forward-use CLI session eec2b1c2-9beb-4dba-b2bd-5a2906de8b64 received a realistic minimal request with a valid GBK-comment file and a damaged file. Its first absolute ampersand interpreter form was denied and it correctly stopped. After the coordinator supplied the already-permitted python form, it previewed both, read the blocked plan, generated and reviewed a new plan for the valid subset, and copied only that subset. Primary verified exact output bytes, both original hashes, manifest/output hashes and plan identity. Evidence: D:/codex-tmp/ce23/forward-eval/primary-grade.json plus the two CLI logs. This passes the workflow after one host command adaptation; it is not an unassisted first-attempt host integration claim.

## Authorized global delivery

Three canonical files were installed to each previously absent directory:

- C:/Users/zhy76/.agents/skills/normalize-source-comments
- C:/Users/zhy76/.claude/skills/normalize-source-comments

All six installed hashes match the accepted project files (global-install-hashes.json). From a working directory outside the repository, each installed helper produced a ready preview with identical plan ID 890ccda3f2419a3a663f245a775ad9fe4527690ce36009f2950d427a91fa9b7c and exit 0. No global provider or permission settings changed.

Fresh CLI initialization metadata (session ac2a04be-1f2e-4253-abc0-525c8040b624) lists normalize-source-comments in skills; its Get-Location smoke succeeded and no permission denials occurred. The CLI's final natural-language answer incorrectly said it was absent; discovery acceptance relies on actual initialization metadata and successful installed-helper calls, not that answer. Codex's current session catalog and VS Code UI were not live-reloaded or qualified; existing sessions may need reopening to discover the installed directory.

## Boundaries and retained limitations

Earlier CLI compound/discovery command violations and the corrected invocation boundary are retained in implementation evidence. They are not passed tests. Global/project AGENTS now require one native command per call, coordinator-supplied paths/Git ledger, stop at first denial, and no alternate-tool retry. Coordinator records Git commits; implementation remains with the CLI.

The skill is deliberately conservative, not a compiler lexer for every extension. Invalid comments require manual source recovery. No generic sourceCharset flags or runtime string transcoding were introduced. Startup, memory layout, scoped options, scatter, Git apply baseline and equivalence checks remain independent. There are nine discoverable skills but eight existing release qualification workflows; this slice does not change the release matrix, runtime version, packaging, installed Toolkit runtime, remote repository or hardware qualification. The subsequent startup and memory slices remain outstanding.
