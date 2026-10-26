# Retest diagnostics and migration guidance

Verdict: **ACCEPTED_WITH_FIXES**, local software slice only, 2026-10-26.

## Ownership and source

- Accepted base: `f5d8978a2a60c59ec5afee4fc014707311210fe5`.
- CodeHead before this report: `9d8b06427cd237309c5f3061316b37ebc0a73d06`.
- Branch: `codex/v132-retest-diagnostics`; no PR or remote action authorized for this slice.
- Primary owns the [specification](../../../superpowers/specs/2026-10-26-retest-guidance.md), [plan](../../../superpowers/plans/2026-10-26-retest-guidance.md), orchestration, independent complete-diff review and acceptance.
- Implementation and tests: local Claude Code CLI 2.1.308, existing configured model `deepseek-v4.1-flash[1m]`. This identifies the configured CLI route, not an Anthropic model.
- Independent review checkout: `C:/Users/zhy76/.codex/worktrees/retest-guidance-review/STM32-Toolkit`, clean and detached at the final CodeHead.

The user clarified that accurate guidance takes precedence over mechanically implementing each proposed rewrite. This slice therefore preserves semantic guards and explains the actual dependencies; it also fixes the CLI JSON encoding defect.

## Accepted behavior

1. `__align` macro arrays and `at()` placements already have supported rewrites. In the supplied test copy, UTF-8 C files depend on a non-UTF-8 `MALLOC/malloc.h`; decoding that header prevents constant resolution. Diagnostics now identify the project-relative dependency and distinguish encoding, missing paths, cycles and unsupported syntax. Existing error codes remain intact. Internal trusted cause metadata is not inferred from user-controlled filenames and is not added to the serialized migration plan.
2. Encoding remediation directs callers to declare the affected header charset, preview the comment-only normalization skill and use an explicitly reviewed external copy. Missing-path diagnostics request include-path evidence instead. Neither case claims that preparing one dependency makes the whole declaration or project supported; callers must rerun inspect/preflight and inspect all remaining blockers.
3. Known embedded-assembly bodies without a return remain blocked. The diagnostic explains the possible fall-through and asks for Keil disassembly/control-flow evidence. No return instruction is invented and no bare WFI is silently replaced with a CMSIS call. ARM's [armcc compiler guide, section 7.30](https://documentation-service.arm.com/static/5eb946b50f1c1e0dae6ee21e) documents fall-through when the return instruction is omitted.
4. CLI JSON uses ASCII Unicode escapes, so redirected JSON remains UTF-8-decodable under GBK stdout while parsed Unicode values remain unchanged. No persistent console or environment setting is changed.
5. `docs/user-guide.md` and `skills/migrate-keil/SKILL.md` describe the diagnostic decision path, header dependencies, explicit preview/copy approval and missing-return boundary. They distinguish this local unreleased patch from installed v1.3.2. README, version numbers and frozen release assets are unchanged.

## Evidence and corrections

All test commands used CPython `D:/codex-tmp/kx23/venv/Scripts/python.exe`; compiler tests used the existing CubeCLT ARM GCC. Tests ran with isolated output directories and recorded source hashes. No installed runtime was replaced.

| Owner / run | Source | Result |
| --- | --- | --- |
| Claude, initial complete affected group `retest-a` | `d9387116f95b5a79de99c390b133c4c291c5b28d` | 312 passed, 4 failed; retained |
| Claude, final complete affected group `retest-b` | Final CodeHead | 317 passed, 0 failed, 0 skipped |
| Primary, independent `review-b` | Final CodeHead in clean review checkout | 23 passed, 0 failed, 0 skipped |

The 23 independent cases overlap the 317 and are not added as distinct coverage. They include real ARM GCC compilation/disassembly and a real CLI subprocess with `PYTHONIOENCODING=gbk`, `PYTHONUTF8=0` and a Unicode project filename. The complete group also covers migration plans, constant boundaries, preflight, CLI and AI guidance. One existing runpy CLI warning is retained; it is not a failure.

Three initial failures were incorrect new test expectations/placement. The fourth exposed message compatibility: the original `(unreadable)` token had changed. Claude restored the existing parenthesized token and appended dependency context outside it; the existing boundary test was not weakened. Review also required trusted diagnostic causes, a misleading-filename regression and neutral wording that does not claim unsupported syntax is otherwise valid. All corrections are in the final tested CodeHead. No open review finding remains within this slice.

Exact final commands:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/r132-retest/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/v132-readme/STM32-Toolkit' 9d8b06427cd237309c5f3061316b37ebc0a73d06 retest-b retest
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/r132-retest/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/retest-guidance-review/STM32-Toolkit' 9d8b06427cd237309c5f3061316b37ebc0a73d06 review-b review
```

Evidence directories `D:/codex-tmp/r132-retest/{retest-a,retest-b,review-b}` retain execution JSON, stdout, JUnit and native coverage. Failed-run coverage was not imported into any release qualification. This is a complete affected-group rerun, not a repository-wide release matrix.

Native PowerShell inventory and an actual harmless command were verified before delegation. File-only authoring and exact-command verification were separate. CLI logs under `D:/codex-tmp/r132` retain `retest-inventory`, `retest-harmless`, `retest-author`, `retest-author-review-fixes`, `retest-author-final-corrections`, `retest-verify-a` and `retest-verify-b`. Two author calls reached their turn budgets; edits and logs were retained and continued in the same author session, without claiming tests had executed. There were no permission denials or shell fallbacks. Final verification session `c6486602-871b-42b0-be25-eabc596a1df4` contains one actual native PowerShell tool call and its exit-0 result.

## Supplied project evidence and limits

The primary read only `D:/WorkSpace/mobile-robot-controller-v132-test` and the user's saved evidence. Final-source preflight retained **8 blockers**: seven now identify the header-encoding dependency and one identifies the missing assembly return. The 178-file before/after snapshots are equal. This is useful actionable diagnosis, not a claim that migration now has zero blockers or produces equivalent firmware.

Final capture: `D:/codex-tmp/r132-retest/supplied-final.stdout.json`, 65,293 bytes, SHA-256 `8b900ee656d574c0377c9e469efe9b000677d8a4208d6e1be18af108ba058309`. The CLI exited 0 with empty stderr; its bytes were ASCII and independently parsed as UTF-8 JSON. Exact argv, source identity and before/after hashes are in `supplied-final-evidence.json`. Initial audit and earlier captures remain alongside it.

The user's report of installed v1.3.2 is user-owned evidence, not primary installation or hardware acceptance. This local patch has not been installed, packaged, pushed, tagged or released. Original firmware, the supplied test copy, hardware, global settings and global skills were not modified. Final installed-runtime/VS Code validation belongs to the user after a separately authorized future delivery; existing release exceptions do not qualify this new source.
