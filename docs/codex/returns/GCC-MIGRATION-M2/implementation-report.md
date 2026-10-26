# GCC-MIGRATION-M2 implementation report

Verdict: ACCEPTED_WITH_FIXES for the public independent-delivery interface. WFI source intent, prepared-source guidance and combined content-based build/flash integration remain pending. This is not release acceptance.

Accepted base: `277cb556ad1302079463da2e07989bbfa14e8c7b` (accepted M1 engine). Plan head: `0dd5e20c7353d6d7f53c7676adcfbef3cdb26902`. Reviewed CodeHead before this report: `514009d412979b134c43383668aa7f3b8ed34739`. Branch: `codex/gcc-migration-public`. Specification, plan, complete-diff review and acceptance owner: primary conversation agent. Product and test implementer: local Claude Code CLI using the user's existing configured provider/model. No remote authority or action.

## Delivered behavior

CLI `keil convert` and MCP `stm32_keil_convert` now require an explicit independent destination and use the accepted delivery engine. There is no public in-place fallback. PLAN exposes `planId`, complete output/source-patch previews and reviewed options. APPLY rechecks the same destination/options/plan and returns `outputRoot`, `configured=true`, `built=false`, `flashed=false`. Subsequent context/configure/build calls bind the delivered project root.

Preflight separates technical readiness from the unevaluated destination input. Missing Git, unborn HEAD, dirty files and a nested Git root remain optional evidence and never require init/commit/stash/clean. Technical blockers stop delivery PLAN with complete `DELIVERY_BLOCKED` details. Missing required options may make replanning technically blocked before plan-ID comparison; valid changed options produce `PLAN_CHANGED`. Tests retain precise diagnostics and verify the source tree is unchanged.

Context, MCP descriptions, workflow skills, architecture and concise bilingual READMEs describe independent delivery. Guide examples distinguish installed 1.3.2 commands from the unpublished development contract; they do not invoke `--destination` against an installed 1.3.2 executable. WFI/encoding and temporary cross-branch flash limitations are explicitly reserved for the next slices/integration.

## Verification

The maintained standard procedure/current checkpoint was read before execution. All checks used isolated fixtures; no original project, installed runtime, physical probe or remote state was modified.

| Owner | Exact code | Evidence run | Result |
| --- | --- | --- | --- |
| Claude CLI, native PowerShell | `3dce51e47f1b36c8604f92b8e208328d2009fed9` | m2a / m2r / m2g | 155 pass + 3 fail / 137 pass + 11 fail / 34 pass; retained |
| Primary, clean detached review | `3dce51e47f1b36c8604f92b8e208328d2009fed9` | m2p | 8 pass + 2 fail; retained |
| Claude CLI, native PowerShell | `514009d412979b134c43383668aa7f3b8ed34739` | m2b / m2s / m2h | 158 / 148 / 34 passed, no failures/errors/skips; source unchanged |
| Primary, clean detached review | `514009d412979b134c43383668aa7f3b8ed34739` | m2q | 10 passed, no failures/errors/skips; source unchanged |

The three final author groups cover public workflows/CLI/MCP, preflight/startup/memory/extra-region routing and AI/plugin guidance. Primary reran the complete new public-delivery test file. Counts between owners overlap. Public build integration uses a fake CMake provider; real ARM GCC output-only relocation evidence belongs to accepted M1 and is not misattributed to this run.

Evidence root: `D:/codex-tmp/gcc26/`, each named run retaining execution.json, argv, source hashes, stdout.log, JUnit and coverage. Exact test entry: `D:/codex-tmp/kx23/venv/Scripts/python.exe -X utf8 D:/codex-tmp/gcc26/run_checks.py <root> <CodeHead> <label> <group>`. Final delegated run: `migration-global-corrected-verify`, session `1b019bb2-2f84-4aa8-bd81-e288385ad31e`; initialization/smoke passed, exact native commands matched, no scope violations. Native numeric shell exit codes remain null when not supplied; test-runner subprocess exit 0 is separately recorded.

Primary reviewed the complete base-to-CodeHead diff and the correction delta. Findings corrected JSON tuple/list comparisons, precise blocker precedence, positive startup fixtures that previously included unrelated unsupported assembly, missing destination routing, actual public response fields, and installed-versus-development examples. File-only author runs that reached their turn limits are retained as incomplete CLI invocations; their resulting edits were independently reviewed and frozen before verification, not accepted on the strength of a model completion claim.

## Remaining integration work

Join this branch with accepted content-based flash/creation/regeneration changes, complete WFI intent and source preparation, remove temporary branch-state prose, then exercise both no-Git GCC/build/fake-flash journeys. Historical APIs remain internal for existing evidence; the public interface intentionally changed. No version bump, package, install, hardware qualification or publication was performed.
