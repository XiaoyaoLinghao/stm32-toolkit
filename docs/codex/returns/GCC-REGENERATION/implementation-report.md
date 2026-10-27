# Content-based regeneration acceptance

Verdict: **ACCEPTED**, bounded offline software slice, 2026-10-26.

Primary owns the specification, plan, orchestration, complete independent diff review and acceptance. Implementation and implementation tests were authored through local Claude Code CLI 2.1.308 using the existing configured provider/model route. Accepted creation base: `b7895f771d9eeecab308af82124f487ed5d3bcbe`. Plan commit: `4dcb87fabb4e8fdb0b48a9217b9d17712d7b08a7`. CodeHead before this report: `a836791b9c5b7c96dc7621ae30aa6845c1ce1aa3`. Branch: `codex/gcc-regeneration-content`; no PR or remote action authorized.

## Behavior and review

Regeneration no longer requires Git or incorporates its optional metadata into the authoritative project-state/plan digest. Missing or unborn Git is reported explicitly rather than fabricated as clean. Existing content inventory, model, manifest, generator/environment, request, ownership, staging, conflict and authorization checks remain active. A change only to Git metadata does not invalidate unchanged content. Changed content still requires a new plan/authorization.

Primary reviewed the full three-file product/test diff in the clean detached `gcc-delivery-review/STM32-Toolkit` checkout at CodeHead. No unresolved finding remains within this slice. Tests use disposable fake-generator/build environments; they do not establish real CubeMX or physical hardware qualification. The test named `test_legacy_pending_plan_requires_fresh_plan_and_prepare` demonstrates stale-digest rejection, not replay of a historical golden authorization file.

## Evidence

| Owner / isolated run | Exact source | Result |
| --- | --- | --- |
| Claude, `rca`, complete five-file regeneration group | CodeHead | 132 passed, 1 skipped, 0 failures/errors |
| Primary, `rcp`, independent new content-baseline tests | CodeHead | 16 passed, 0 skipped/failures/errors |

The independent cases overlap the full group and are not summed. The existing destination-symlink case skips because Windows symlink creation is unavailable; it remains a named platform check for a capable integration environment, not a pass. No-Git/unborn flows, Git-only changes, changed source/environment and stale/reused authorization are covered offline.

Commands used verified Python `D:/codex-tmp/kx23/venv/Scripts/python.exe` and `D:/codex-tmp/gcc26/run_checks.py`, with root, full CodeHead, short run label and group passed explicitly. `rca` used author root `C:/Users/zhy76/.codex/worktrees/gcc-regeneration/STM32-Toolkit` and group `regeneration`; `rcp` used the clean independent review root and group `regeneration-new`. Both recorded sourceUnchanged=true and subprocess exit 0. Execution JSON, original stdout, fresh JUnit and coverage remain under `D:/codex-tmp/gcc26/{rca,rcp}`.

Claude verification used the global dispatch entry, run `regeneration-short-global-verify`, session `98d865d7-22fe-44ac-989d-8c10a7280061`. Inventory matched PowerShell; native harmless smoke and the exact designated command executed. The native success result supplied no numeric exit code (null); the separate runner recorded subprocess exit 0. External JUnit freshness/source identities were checked by primary, not claimed as an in-worktree report check by the dispatcher.

Initial same-head runs are retained: author 71 passed / 61 failed / 1 skipped, primary 2 passed / 14 failed. Primary traced a representative underlying FileNotFoundError to a 265-character authorization temporary filename. Shortening only the test-output label made all failures pass at unchanged CodeHead. Those initial failures remain environment failures, not overwritten passes; no execution policy, tool permissions or product validation was changed. Detailed diagnosis is retained in `D:/codex-tmp/gcc26/regeneration-path-diagnosis.md`.

This acceptance does not complete the broader GCC delivery integration, Monitor/diagnostic work, release, installation, IDE or hardware validation. Original projects, installed runtimes, global settings, versions and remote state are unchanged.
