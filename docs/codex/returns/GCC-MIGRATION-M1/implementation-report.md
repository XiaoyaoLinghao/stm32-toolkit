# GCC-MIGRATION-M1 implementation report

Verdict: ACCEPTED for the bounded independent-delivery engine. Public CLI/MCP migration switching, WFI source intent, final combined GCC/flash journeys and remaining identity consumers are separate pending slices; this is not release acceptance.

Accepted base: `b7895f771d9eeecab308af82124f487ed5d3bcbe` (accepted creation slice). Implementation plan head: `587655bba9aa53d471edaa45c3bf540abc3349ac`. Reviewed CodeHead before this report: `273c779302725bb923c18ccfd3758202a5e6a284`. Branch: `codex/gcc-migration-delivery`. Specification/plan/review owner: primary conversation agent. Product implementation and test author: local Claude Code CLI using the user's existing configured provider/model. No remote action authorized or performed.

## Delivered behavior

The new engine analyzes a Keil source tree without requiring Git and plans a complete independent GCC output in an explicit disjoint absent/empty destination. It copies bounded regular files, preserves relative headers/licenses, overlays reviewed source changes and generated CMake/linker/editor configuration, and produces the managed manifest through the existing renderer. Source files are never edited. Preview includes copied/replaced/generated outputs, hashes, overwrite diffs and options.

Apply requires the exact current plan and authorization, recomputes source/destination/output evidence, verifies the complete staged tree, and publishes the new directory. Changed source/headers, occupied destinations, malformed plans, unsupported links, unexpected staging content and bounds failures stop the operation. Cleanup verifies the identity of the owned staging directory; replaced staging is retained with explicit cleanup status. This is bounded detection of concurrent filesystem changes, not an adversarial filesystem transaction guarantee.

Conversion report schema 2 uses sourceSnapshotSha256 and contentId; the final delivery planId also hashes the completed report, avoiding circular self-reference. Schema 1 remains readable under its original Git metadata contract. Historical extra-region evidence does not lock later legitimate project-model changes; current fixed-section containment remains enforced. Configuration results explicitly report built=false/flashed=false.

## Verification and review

Read the maintained standard test procedure/current checkpoint before execution. All tests used disposable fixtures and offline toolchains; no original firmware project, installed runtime or physical probe was touched.

| Owner | Exact code | Run | Result |
| --- | --- | --- | --- |
| Claude CLI, native PowerShell | `13ec1fce0574be3409556dba3b311e5316176611` | migration-author-tests | 21 passed, 2 failed; preserved, not accepted |
| Claude CLI, native PowerShell | `273c779302725bb923c18ccfd3758202a5e6a284` | migration-author-tests-fixed | 521 passed, 0 failed/error/skipped; source unchanged |
| Primary independent review | `273c779302725bb923c18ccfd3758202a5e6a284` | migration-primary-tests-fixed | 38 passed, 0 failed/error/skipped; source unchanged |

Counts overlap and are not summed. Final author group: test_migration_delivery, test_generation, test_migration_plan, test_migration_apply, test_linker_fragment_compiler and test_startup_gcc_compiler. Primary reran the complete new delivery test file in a clean detached review tree at CodeHead. Both include a genuine ARM GNU/CMake output-only relocation build with the original synthetic source removed; this is real compiler evidence, not physical target execution or a Toolkit build receipt.

Local evidence root: `D:/codex-tmp/gcc26/`, with per-run execution.json (argv/owner/source hashes), stdout.log, JUnit and native coverage. Verified interpreter: `D:/codex-tmp/kx23/venv/Scripts/python.exe`; offline tools: CubeCLT 1.22.0 ARM GNU/CMake/Ninja. Native CLI tool-use/result events are retained in migration-verify and migration-verify-fixed JSONL logs. File-only author invocations did not execute tests.

Primary reviewed the full accepted-base-to-CodeHead source/test/plan diff in the clean exact-head review tree. Initial findings corrected source-change diagnosis, report/final-plan identity naming, historical memory-map locking, complete staged-output verification, output bounds, owned cleanup and forged-preview validation. All required M1 checks then passed.

## Scope retained for integration

The public converter still uses the historical route until M2. M1 assumes supported UTF-8 input; comment preparation and explicit WFI return are M3. Full inventory deliberately retains old source output files but never treats them as a new build. Missing/out-of-root dependencies and unsupported source constructs remain explicit diagnostics. The engine's staged-directory identity uses filesystem device/inode information; no stronger claim is made for filesystems lacking stable identities. No version bump, packaging, installation, hardware acceptance or publication occurred.
