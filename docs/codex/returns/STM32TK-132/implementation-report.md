# v1.3.2 diagnostics — phase 1

Status: **ACCEPTED_WITH_FIXES** for the advisory slice; release qualification,
version alignment and publication remain pending.

Accepted base: `cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`.
CodeHead: `978a723574a9db6933b70937cabbbc8946086690`.
Branch: `codex/v132-guidance`. Specification, orchestration and independent
complete-diff review: primary agent. Implementation/tests: local Claude Code CLI,
existing configured provider `deepseek-v4.1-flash[1m]`; file-only authoring followed
by separate native PowerShell verification. No Codex implementation subagents.

Doctor now explains PATH-command evidence separately from runtime distribution
metadata. Metadata does not prove importability or hardware readiness. Configure
PLAN and successful APPLY add derived `vscodeGuidance`: required executable
settings are explained without claiming to have evaluated effective VS Code
settings; preserved unowned tasks receive a warning without opening or overwriting
their contents. Existing evidence, generation hashes, ownership and hardware gates
are unchanged. User guide and configure/setup Skills carry the same boundaries.

The primary reviewed the complete base-to-CodeHead source, tests and documentation
diff in the clean independent `v132-review/STM32-Toolkit` worktree. Corrections
removed overclaims about metadata/settings and repaired an unrelated substring
expectation in a new test; no unresolved slice findings remain.

## Executed evidence

Evidence root: `D:/codex-tmp/r132`. All runs retain exact argv, source hashes,
JUnit, stdout and native branch coverage. Both final runs verified unchanged source.

| Owner / run | Source | Result |
| --- | --- | --- |
| Claude / guidance-a (retained failed run) | e86b481d979278326cda7b19d965fc65f01a0364 | 836 passed, 1 failed, 3 skipped |
| Claude / guidance-b | 978a723574a9db6933b70937cabbbc8946086690 | 837 passed, 3 skipped |
| Primary independent reviewer / review-a | 978a723574a9db6933b70937cabbbc8946086690 | 156 passed, 1 skipped |

The failed expectation required `setup-stm32-env` in the preserved-tasks remedy;
that remedy correctly describes manual review/binding, so only the incorrect
assertion was removed. Failed-run coverage is not eligible for qualification reuse.
The three complete-group skips require native Windows symlink privileges; mocked
redirect checks execute. Two non-failing warnings concern pydantic-settings forward
references and runpy module reuse. The independent group overlaps the full group;
its count is not added to a unique regression total.

Native symlink cases remain DEFERRED to the primary release-qualification owner
on a Windows host with symlink privileges; this task does not change host policy
to obtain them. Any release disposition retaining those skips must say so explicitly.

Claude verification session `39c3b312-5d53-4be0-aaef-f6fd072e3491` exposed only
PowerShell and executed the one supplied command with native tool-use/result
events, exit 0 and no permission denials. Exact command:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/r132/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/v132-guidance/STM32-Toolkit' 978a723574a9db6933b70937cabbbc8946086690 guidance-b guidance
```

This is offline software evidence, not installation, IDE or hardware acceptance.
The original firmware project, installed runtimes and global configuration are
unchanged. Final installation/VS Code validation remains user-owned. No v1.3.2
coverage exception or release acceptance is implied; the v1.3.1 exception remains
bound to its old candidate. The user has authorized v1.3.2 delivery after qualification.
