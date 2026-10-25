# VSCODE-TASKS implementation evidence

Accepted base: `e7614e49ba384117770ff8b01f57489da8676223`. CodeHead before this report: `4c79ef53111408ae2f5071f6edb52cbadb8363fb`. Branch: `codex/vscode-tasks`.

This report is compiled by the coordinator from the actual Claude Code CLI file-edit returns, native PowerShell execution events and JUnit artifacts; it is not an implementer approval. Local Claude Code CLI 2.1.308 used the user's existing `deepseek-v4.1-flash[1m]` configuration. The primary owns the specification, orchestration and independent acceptance. See the [design](../../../superpowers/specs/2026-10-25-vscode-tasks-design.md), [plan](../../../superpowers/plans/2026-10-25-vscode-tasks-plan.md), [review](review.md) and [machine evidence](evidence.json).

## Source changes

- `vscode_configuration.py`: paired native executable bindings, static lexical path validation including parent redirects, immutable configuration and structured diagnostics.
- `generation/configure.py`, `generation/managed_files.py`: deterministic portable settings or explicit absolute paths, immutable plan identity/revalidation, five independent process tasks, preserved user-owned files and existing transaction behavior.
- `ide_tasks.py`, `cli.py`: narrow flash/handoff adapter, default deny, exact context and current firmware admission, original-ticket forwarding, intact results and no automatic actions.
- `workflows.py`, `mcp_server.py`: paired configure arguments propagated through the existing workflow and public MCP schema; no new MCP tool.
- New `test_vscode_configuration.py` and `test_ide_tasks.py`; affected existing assertions in `test_generation.py`, `test_debug_configuration_workflows.py` and `test_mcp_migration_build.py`.
- `docs/user-guide.md`: executable binding, PLAN/APPLY replay, source/runtime distinction, task continuity and managed/imported routes. Templates and version files were not changed.

Authoring ran file-only; verification ran in separate native PowerShell calls with the exact coordinator-supplied commands. No Codex implementation subagent or primary product/test implementation was used. No original-project, hardware, installed runtime, global Skill, release or remote operation occurred.

## Actual verification

All author commands used `D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest`, bound cwd `C:/Users/zhy76/.codex/worktrees/build-snapshot-review/STM32-Toolkit`, source-first PYTHONPATH, isolated TEMP/TMP/TMPDIR and run-specific basetemp/cache/JUnit paths under `D:/codex-tmp/vs25`. Exact argv, heads, native tool names and hashes are in evidence.json. Third-party dependencies were borrowed read-only from the installed 1.3.0 site-packages; Toolkit code came from the bound source tree.

| Source / author run | JUnit result |
| --- | --- |
| `3822571f69648949e10bffbc3bda2fec282c3e9e` / core | 469 cases: 461 passed, 7 failed, 1 skipped |
| `3351f40ae83e90b908620a2ab196cace5340ef93` / corrected core | 483 cases: 482 passed, 0 failed, 1 skipped |
| Same head / related regression | 539 passed, 0 failed/skipped |
| `210b16a4873d430290c76eae2f96000d5bb24f55` / task and AI guidance | 51 passed, 0 failed/skipped |
| Final CodeHead / corrected real-end binding and AI guidance | 13 passed, 0 failed/skipped |

Core modules: test_vscode_configuration, test_ide_tasks, test_generation, test_debug_configuration_workflows, test_mcp_migration_build, test_cli_hardware. Related regression modules: test_cli, test_workflows, test_hardware_workflows, test_flash, test_debug_handoff, test_mcp_roots, test_ai_call_guidance, test_debug_configuration.

The initial seven failures were five manifestations of the new confirmation parser default bug and two outdated test expectations (absolute-path diagnostic and exact MCP schema fields). They were corrected without weakening admission. Independent review additionally required lexical parent-path checks and the existing DataRoot redirect guard, exact argv replay, default/duplicate confirmation tests, and accurate downstream handoff-end refusal evidence. The final fixture correction binds the adapter request to the supervisor's originating DataRoot.

The real file-symlink case is skipped because this host cannot create that link. Mocked leaf/parent reparse and revalidation checks passed. Real link verification belongs to the primary's capable Windows/Linux integration/release environment. CLI process success is not used as pytest success: actual native execution and JUnit establish counts; author tool output did not expose a separate pytest exit code.

There are 1,022 distinct applicable passing cases and one platform skip after accounting for the renamed handoff test. Unaffected results are reused; this is not a final whole-repository or release-matrix rerun. From 3351f40a to the final CodeHead, all executable product AST is unchanged; only ide_tasks docstrings changed in product source. Later test and guidance changes were rerun separately.

## Process and limitations

The initial read-only audit hit its eight-turn limit. Two author sessions reached the 65-turn limit; the first left no edits, the continuation left retained edits. Subsequent bounded correction sessions completed. Actual tools stayed within the file-only / native PowerShell split; no absent or denied shell was retried or bypassed. Ordinary missing-file or unmatched-edit errors were corrected within the file scope. Model, provider, credentials and global permissions were unchanged.

The primary corrected its initial overbroad expectation that a stale-source original ticket would necessarily reclaim ownership. The adapter adds no fresh admission for end, but the existing end workflow still validates firmware/flash evidence. The final fake-supervisor integration test observes `FIRMWARE_INPUT_CHANGED`, exact ELF details, no restart and the retained `reacquiring` state. No hardware was used.

Generated settings need real verified paths before use. Static path checks are not binary trust/version attestation. IntelliSense's compilerPath does not select the CMake build compiler. Live VS Code, extension input/rerun behavior, IntelliSense and physical handoff remain unverified here. Installed/frozen 1.3.0 does not contain this slice; restarting VS Code does not install it. Product remains 1.3.0, with unified v1.3.1 planned after the remaining agreed improvements.
