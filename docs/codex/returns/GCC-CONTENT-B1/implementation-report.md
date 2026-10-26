# GCC-CONTENT-B1 implementation report

Verdict: ACCEPTED_WITH_FIXES for optional-Git evidence, Host/Target/replay producers and controlled-debug revision projection. Monitor/browser/replay-reference consumers remain B2; combined GCC delivery/flash integration remains pending. This is not release or physical acceptance.

Accepted base: `f73ce706ac17d7c198153825dd3667f2ac2fc131` (accepted content firmware admission). Plan head: `9e8fa0f18f63cc8f80d37146cd010394b24ee440`. Reviewed CodeHead before this report: `23b4afe6edd4d60825c302a6b2a2e94883ae4f74`. Branch: `codex/gcc-content-evidence`. Primary owns specification, plan, complete-diff review and acceptance. Local Claude Code CLI using the user's configured provider/model authored all product/test changes. No remote authority or action.

## Delivered behavior

Evidence identity and context accept two closed forms: historical real Git commit plus strict dirty boolean, or explicit input-snapshot provenance with null Git fields and bounded unavailable-Git metadata. Legacy serialization remains unchanged. Partial/mixed/null-only discriminator pairs and unknown fields fail validation. The shared provenance helper is a leaf module; build.model re-exports its unchanged literal constants without creating an import cycle. Generic authorization revisions use the real Git commit or an explicitly namespaced snapshot digest; a content revision is never stored as a Git commit.

Host discovery/run no longer require Git. Target v1/v2 preparation, consumption and fake execution preserve complete snapshot identity, reject stale input/authorization/provenance and publish matching evidence. Existing v1 replay accepts the snapshot form without changing the firmware transport contract. Controlled debug binds the content revision. Recovery producers retain pre-build build/ELF placeholders but never fabricate a clean/zero Git record or zero input baseline; input enumeration failure returns a typed error. A public begin test enumerates a real configured no-Git project and verifies its persisted source digest.

## Review and verification

The maintained standard procedure/current checkpoint was read. All checks were offline with isolated temporary projects and fake transport/probe providers. No original firmware project, installed runtime, physical hardware or remote state changed.

Primary reviewed the complete accepted-base-to-CodeHead diff in a clean detached checkout, including both schema copies and all implementation/test deltas. Findings corrected legacy binding discrimination, present-null wire forms, namespaced revision validation, a build/evidence circular import, test wire serialization/project paths, stale raise-site inventory and recovery fixtures that had relied on swallowed enumeration failures. Fresh-interpreter import-order regression passes.

| Owner / code | Runs | Results |
| --- | --- | --- |
| Claude native PowerShell / `732c833525172a1787b7200285e9c86b2a61979b` | b1n, b1m, b1h, b1t, b1r, b1c, b1a | Initial import/fixture failures retained; not accepted |
| Claude native PowerShell / `48d83172c6deea2de7ff55bf2357d6974c5d4e62` | b2n / b2h / b2t / b2r / b2c | 18 / 188 / 268 / 77 / 72 passed; source unchanged |
| Claude native PowerShell / same code | b2m / b2a | 226 pass, 1 stale-test failure, 1 platform skip / 25 pass, 36 fixture failures; retained |
| Claude native PowerShell / `23b4afe6edd4d60825c302a6b2a2e94883ae4f74` | b3f | All four changed test files: 147 passed, no failures/errors/skips; source unchanged |
| Primary clean exact-head review / same final code | b3p | Full new workflow file: 19 passed, no failures/errors/skips; source unchanged |

Counts overlap and are not summed. Final production code is byte-identical to 48d83172; only the four test files changed in the final commit, and all four were rerun. The unaffected Host/Target/replay/schema/store evidence is explicitly reused, not described as a final-commit full rerun. The Windows symlink-dependent evidence-store case remains deferred to a symlink-capable integration environment; no code failure is deferred.

Evidence root: `D:/codex-tmp/gcc26/`. Per-run execution.json records exact argv, owner, source hashes and subprocess exit; stdout.log/JUnit/coverage remain alongside it. Command entry: `D:/codex-tmp/kx23/venv/Scripts/python.exe -X utf8 D:/codex-tmp/gcc26/run_checks.py <root> <head> <short-label> <group>`. Final global delegated verification session: `8f4c2553-c85d-4119-9204-58aeff8518de`; requested/actual native PowerShell inventory, harmless smoke and exact test command passed without scope violations. Numeric native shell exits remain null when absent; runner exit 0 and fresh reports are separate evidence.

## Delegation audit retained

Early file-only runs reached their turn limits and retained partial work. One continuation edited the diagnostic test seam outside its then-listed files; primary reviewed the five-line collector seam change and admitted that exact correction in the subsequent task, preserving the original violation. Another correction read project configuration outside a narrowly listed read scope; no extra product edits resulted, and its original failed audit remains retained. Later edit tasks used the explicit whole-checkout read scope with exact write lists.

The b2a command actually started through PowerShell and was moved to background at its default 120-second timeout. Claude then called unavailable `DeferredToolPlaceholder`; the launcher stopped that invocation. No alternative tool/retry was used. Primary observed the original runner finish at 215.289 seconds with its real failure report and unchanged source. That launch's `is_error=false` background notification is not test success. Subsequent exact-command verification explicitly used the verified 600000-ms foreground parameter. File-edit completion, command execution and passing tests remain distinct claims.

## Remaining scope

Monitor live/status/history and UI, Monitor replay/analysis/diagnostic/continuation consumers and final combined source-to-GCC-to-fake-flash journeys remain pending. No packaging, installation, version bump, hardware qualification or publication occurred.
