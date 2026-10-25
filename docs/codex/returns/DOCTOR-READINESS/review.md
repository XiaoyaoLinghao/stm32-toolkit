# DOCTOR-READINESS independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base `8737aaea950d2eec7f79c44b7b95bf07ca0ab471`; final tested CodeHead `353ab42f60324a1fb94ff8daf8875f80d138ce48`. Primary owns architecture, plan, complete-diff review and acceptance; local Claude Code CLI using the existing deepseek-v4.1-flash[1m] configuration owns implementation/tests/product guidance. Independent review and tests used the clean detached build-snapshot-final/STM32-Toolkit tree at the recorded heads. No ownership override or remote action. See [design](../../../superpowers/specs/2026-10-25-doctor-readiness-design.md), [plan](../../../superpowers/plans/2026-10-25-doctor-readiness-plan.md), [implementation return](implementation-report.md) and [evidence](evidence.json).

## Accepted behavior and review

Doctor now reports actual recommended extension inventory, selected executable/script, scope and bounded diagnostics. Unknown is distinct from absent; only complete valid inventory can establish installed/absent. Support-profile declarations retain their original meaning and carry explicit nested provenance. UV4 uses static file version only and ARMCC fixed --vsn only. Explicit invalid selection does not fall back; safe lexical parents and same-install launcher/script checks apply. Tool presence never unlocks a native Keil build backend. CLI options, strict MCP schema and root-before-probe order are verified. No installation, build, editor attach or hardware action is introduced.

Primary reviewed the entire accepted-base-to-CodeHead diff, including all correction diffs, in the independent clean review tree. Final source differed from the preceding reviewed module only in its platform seam and then its single bounded version regex; those deltas and their tests were independently inspected. No actionable finding remains in this scope.

| Finding | Correction and evidence |
| --- | --- |
| Success selection indexed failure-only code map | Successful selection carries no error code. All valid-layout paths pass. |
| Stale fixed cli.js could outrank installed hash launcher | Existing launcher is authoritative; unsafe/ambiguous/unrecognized launcher is refused. |
| Incomplete streams / stderr could produce false facts | Shared runner records incomplete capture; doctor and existing version/metadata consumers reject it. Creation regressions passed. |
| ARMCC arbitrary text could become a version | Parse bounded recognized Compiler 5 Product/Component records on both streams; reject conflicts; omit license/serial text. |
| Declared extension metadata lacked explicit provenance | Preserve declaration and add creationSupport.vsCodeExtensionsSource; public serialization and unrelated live result verified. |
| Missing extension diagnostics lacked identity / redirect test could skip | Add extensionId, mocked lexical-parent reparse refusal and root-before-probe zero-call test. |
| Test tuple/schema assumptions, misplaced parametrization and implicit host platform | Fix public response assertions, restore original decorator, add a private platform seam and unsupported-platform test. No product guard relaxed. |
| Actual official language-pack version failed the six-digit component bound | Permit bounded 16-digit numeric components; exact real format and oversized-component regression; full core matrix rerun. |

## Verification and practical limits

At final CodeHead both owners independently ran 305 core cases: **304 passed, 0 failed, 1 skipped**. Each also ran 97 related creation cases at f8e688cc; these are reused with unchanged shared tool-support/creation source and tests after the isolated regex correction. Thus 401 distinct cases passed with one platform skip per owner. Initial 21 failures were resolved; the first matrix and intermediate evidence remain recorded. No full release matrix or physical qualification is claimed. Non-failing runpy and pydantic_settings warnings are retained; source binding independently confirms imports from the reviewed checkout, with only third-party dependencies borrowed read-only from installed runtime.

The skipped real directory-symlink check requires host capability. **DEFERRED to primary-owned integration/release on a capable Windows/Linux environment**; mocked lexical-parent reparse tests pass. This is a platform-only limit, not an ignored product failure.

Actual read-only public CLI observation on an external empty directory passed: local-default-profile cpptools **1.34.4**, cmake-tools **1.24.42**, cortex-debug **1.12.1**. The matching cortex-debug value compares an observed version with the declared handoff profile; it does not prove activation, the active/remote window, IntelliSense or a debug session. UV4/ARMCC were absent from this host's PATH and bounded defaults; nonstandard installs can be selected explicitly. Real installed UV4/ARMCC versions, licensing and native builds are not qualified. The original project was not read or modified.

The initial installed observation returned unknown on a legitimate language-pack version. One bounded raw-listing diagnosis isolated the exact record, then the reviewed correction was independently tested and the public observation repeated. This was an offline compatibility correction; no hardware retry or permissive partial-inventory workaround. Raw unrelated inventory remains local and is not committed or exposed by doctor.

Fresh read-only Claude consumer simulation read the doctor guidance, MCP description and the no-Git section. It correctly distinguished installed runtime from source, null/false/declared facts, local-default scope, native-build unsupported, explicit path repair and managed/imported routes. The initial narrow simulation lacked the no-Git section; the expanded read resolved that evidence gap. No surviving contradictory guidance was found. This simulation is not a live VS Code AI/UI acceptance test.

The observation contract was checked against [VS Code CLI documentation](https://code.visualstudio.com/docs/configure/command-line) and the [Arm Compiler command-line reference](https://www.keil.com/support/man/docs/armcc/); installed launcher bytes were inspected and hashed. No speculative native-backend or MCP refresh mechanism was added.

## Delivery boundary and cleanup

Product remains **1.3.0**; frozen/installed packages do not contain this source patch. Restarting VS Code does not install it. User-requested unified **v1.3.1** follows completion of remaining optimizations: flash frequency/failure guidance, memory-margin warnings, combined regression and release/version work. Real IDE and authorized hardware qualification remain later integration obligations. No remote push/PR/tag/release, packaging, original project, installed runtime or global Skill changes occurred.

Native PowerShell inventory and a real harmless command were verified before delegation. File-only implementation and exact-command testing stayed separate; all delegations used the existing configured provider. Two file-authoring calls hit turn limits, retaining their work; no shell fallback or permission widening. Primary wrote only governance/evidence/orchestration, not product code or tests.

Cleanup preflight identified 10 contained non-reparse disposable directories, retaining four reparse-containing passed-fixture roots and initial failed fixtures. Automatic approval policy rejected the native PowerShell removal before process creation with **blocked by policy**. No deletion, retry or alternate tool occurred; all outputs remain. Previous policy-held directories were untouched. Current source acceptance does not depend on cleanup. Local delivery is recorded separately after the report commit, whose own SHA is deliberately absent here.
