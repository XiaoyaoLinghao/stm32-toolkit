# STM32TK-0306-CLI-MCP-RELEASE r001 Implementation Report (revision 1)

Status: `IMPLEMENTED`
Module: `STM32TK-0306-CLI-MCP-RELEASE` / r001 / revision-1
Branch: `openclaw/STM32TK-0306-CLI-MCP-RELEASE/r001`
Accepted base commit: `2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1`
Reviewed predecessor: `e65faba5e4e2751e725abc4f63b553eb332af332`
Code head before this report commit: `16b8b2cd90dbf39514064947c02508bb8a36d829`
Final branch head: supplied only in the return message and PR metadata
Work order: `docs/openclaw/modules/STM32TK-0306-CLI-MCP-RELEASE.md` (specification commit `1cc209506f5d7b7c91aae52267d3f5dd4fb09666`)

## 1. Revision-1 outcome

Codex review `REVISION_REQUIRED` on r001 listed four mandated fixes; all four
are implemented with TDD (RED commit on the reviewed predecessor, then the
product fix commit) and every OpenClaw gate now passes:

- **§4 P0 plugin release gate** — `.claude-plugin/marketplace.json` now uses
  the plugin source structure Claude Code 2.1.140 actually supports: the
  repo-relative `"./"` form (the bare `"."` value is rejected by this
  version). `claude plugin validate .` now exits 0; a fresh isolated
  `CLAUDE_CONFIG_DIR` completes `claude plugin marketplace add`, `claude
  plugin install stm32-toolkit@stm32-toolkit` (installed version 0.3.0,
  four Skills discovered, no second MCP registration), and `claude plugin
  list`; the official `claude plugin update stm32-toolkit@stm32-toolkit`
  upgrades an isolated 0.2.0 install to 0.3.0. The plugin manifest, Python
  distribution, managed runtime, and CLI all stay exactly 0.3.0. Because
  every release gate now genuinely passes, the roadmap 0.3.0 checkbox
  remains checked and the 0.3 plan Step-3 gate record is updated.
- **§5 P0 real end-to-end workflows** — a committed, naturally convertible
  Keil fixture (`tools/stm32-toolkit/tests/fixtures/keil-convertible/**`)
  replaces the surgical copy. The e2e copy performs only copy + Git init;
  no uvprojx/source/scatter/include/FPU/ABI content is rewritten before the
  first public workflow call, and the generated Schema v2 manifest is used
  exactly as produced (its empty `debug` spec is no longer hand-edited).
  The chain runs inspect → conversion plan/apply → configuration plan/apply
  → fake build entirely through public workflows/CLI/MCP and links planId,
  conversion report, managed manifest, build result, firmware identity, ELF
  SHA-256, and Git HEAD. The three accepted-core integration seams are now
  closed in the product: empty debug no longer blocks build-only
  configuration (4.1), raw Keil float-ABI text is normalized or blocked
  (4.2), and source/include overlap is deduplicated in the input snapshot
  (4.3); all previously accepted blockers (ARMASM, unknown pragma,
  non-empty scatter, and friends) are preserved unchanged (4.4).
- **§6 P1 authorization fail-closed** — only `authorized is False` enters
  read-only planning, only `authorized is True` (with the exact current
  plan ID) applies, and every non-bool value (`"true"`, `"false"`, `1`,
  `0`, `None`, `[]`, `{}`, with or without a plan ID) returns
  `AUTHORIZATION_REQUIRED` before any inspect/plan/apply work. The
  parameterized RED regression covers all of those combinations for
  convert, configure, and build.
- **§7 P1 build capability evidence** — `capabilities.build` no longer
  follows a bare `CMakeLists.txt`. It is true only when the managed
  manifest is present and valid (parse, tool/template version, model
  digest) and every managed file it records exists un-drifted on disk;
  missing/drifted/invalid/version-mismatched states return `build=false`
  with stable evidence fields, and the capability check is strictly
  read-only (project tree and Git porcelain unchanged across calls).

Codex acceptance verdict: `ACCEPTED_WITH_FIXES`. After reviewing the returned
revision on the named Windows and real ARM GNU environments, Codex applied one
bounded acceptance-fix commit on top of `557b3de1a1eaab117cd9979a679143aaef983db3`:

- Windows test fixtures now use byte-exact writes and an unprivileged hard-link
  identity case instead of relying on text-mode newline behavior or symlink
  privilege.
- The committed Keil fixture now contains portable CMSIS intrinsic shims plus a
  real C startup/vector definition, so the unchanged public workflow output is
  linkable by ARM GNU rather than only by the fake-CMake seam.
- The MAP parser now accepts the real GNU ld 2.44 wrapped output-section row
  form for long section names, including LMA accounting, while malformed,
  missing, and duplicate continuations still fail closed.
- Codex reran the Windows focused/full gates and a real inspect -> convert ->
  configure -> CLI Debug build -> MCP Release build chain. All previously
  deferred gates now pass; details and hashes are recorded in section 4.

Known limitations carried forward: `test_planned_actions.py`,
`test_mcp_roots.py`, and `tests/fixtures/minimal-gcc/.stm32-project.json`
remain modified relative to the accepted base as the explicitly retained
compatibility exceptions from r001 (they assert behavior this work order
mandates: `migrate-keil` available, the seven-tool registry, and the
unified 0.3.0 `generatedBy` version). No new exception paths were added in
revision 1. Blockers are `NONE`; this module has no remaining deferred gate.

## 2. Complete changed-path inventory (accepted base → code head)

Reconciled with `git diff 2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1..16b8b2cd90dbf39514064947c02508bb8a36d829 --name-status`. The
revision-1 delta on top of the reviewed predecessor consists of the
fixture, the four product fixes, the test regressions, the marketplace
manifest fix, the plan-doc gate record, and this report; everything else is
carried over unchanged from r001.

| Status | Path | Revision-1 purpose |
|---|---|---|
| M | `.claude-plugin/marketplace.json` | plugin source `"."` → supported repo-relative `"./"` (P0 gate) |
| M | `.claude-plugin/plugin.json` | carried over: plugin manifest version 0.3.0 |
| M | `bin/setup-stm32-env.ps1` | carried over: exact 0.3.0 bootstrap/repair/check target |
| M | `bin/stm32-toolkit-mcp.cmd` | carried over: fail-closed managed runtime path `runtime/0.3.0` |
| M | `README.md` | carried over: 0.3 workflows, commands, authorization, upgrade notes |
| M | `README_zh-CN.md` | carried over: byte-equivalent factual Chinese documentation |
| M | `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.3-project-migration-build.md` | revision-1 gate-evidence record under Step 3 |
| M | `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md` | carried over: 0.3.0 release checkbox stays checked (all gates now pass) |
| A | `skills/build-firmware/SKILL.md` | carried over: thin build workflow Skill |
| A | `skills/configure-stm32-project/SKILL.md` | carried over: thin configuration workflow Skill |
| A | `skills/migrate-keil/SKILL.md` | carried over: thin migration workflow Skill |
| M | `skills/setup-stm32-env/SKILL.md` | carried over: managed runtime 0.3.0 contract |
| M | `tools/stm32-toolkit/pyproject.toml` | carried over: Python distribution version 0.3.0 |
| M | `tools/stm32-toolkit/src/stm32_toolkit/__init__.py` | carried over: `__version__ = "0.3.0"` |
| M | `tools/stm32-toolkit/src/stm32_toolkit/build/identity.py` | **revision-1 fix (4.3)**: include/source overlap counts a canonical regular file once; duplicate declarations of the same canonical file and casefold/escape cases fail closed |
| M | `tools/stm32-toolkit/src/stm32_toolkit/build/map_file.py` | **Codex acceptance fix**: parse real GNU ld wrapped long output-section rows and LMA values; malformed/missing/duplicate continuations fail closed |
| M | `tools/stm32-toolkit/src/stm32_toolkit/cli.py` | carried over: exact CLI grammar and adapter dispatch |
| M | `tools/stm32-toolkit/src/stm32_toolkit/context.py` | **revision-1 fix (§7)**: managed-configuration-backed build capability with read-only evidence |
| M | `tools/stm32-toolkit/src/stm32_toolkit/detection.py` | carried over: migrate-keil/configure-project available |
| M | `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` | **revision-1 fix (4.1)**: empty debug allows build-only configuration; deterministic launch config without hardware-debug claims |
| M | `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` | carried over: four project-bound tools and roots guard |
| M | `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | **revision-1 fix (4.2)**: Keil float-ABI normalization to soft/softfp/hard and stable blocker for unknown/ambiguous values |
| A | `tools/stm32-toolkit/src/stm32_toolkit/workflows.py` | **revision-1 fix (§6)**: non-bool authorization fails closed in every mode; carried-over two-phase plan/apply adapters |
| A | `tools/stm32-toolkit/tests/fixtures/keil-convertible/legacy.uvprojx` | revision-1 fixture, completed by Codex with the tracked C startup source for a real ARM GNU link |
| A | `tools/stm32-toolkit/tests/fixtures/keil-convertible/Main/main.c` | revision-1 fixture: convertible ARMCC main source |
| A | `tools/stm32-toolkit/tests/fixtures/keil-convertible/Common/common.c` | revision-1 fixture: convertible ARMCC source with intrinsic/fixed-section rules |
| A | `tools/stm32-toolkit/tests/fixtures/keil-convertible/Libraries/STM32F4xx_StdPeriph_Driver/inc/stm32f4xx.h` | revision-1 fixture: tracked SPL header with portable ARMCC/ARM GNU intrinsic shims |
| A | `tools/stm32-toolkit/tests/fixtures/keil-convertible/Startup/startup.c` | **Codex acceptance fix**: portable vector table and `Reset_Handler` required by the generated linker contract and firmware-identity validation |
| M | `tools/stm32-toolkit/tests/fixtures/minimal-gcc/.stm32-project.json` | carried-over compatibility exception (0.3.0 `generatedBy` version); unchanged in revision 1 |
| M | `tools/stm32-toolkit/tests/test_build_runner.py` | carried over: unified version assertions only |
| M | `tools/stm32-toolkit/tests/test_build_map.py` | **Codex acceptance fix**: RED/GREEN regressions for real wrapped GNU ld rows, LMA, ambiguity, and duplicate rejection |
| M | `tools/stm32-toolkit/tests/test_cli.py` | **revision-1**: e2e uses the convertible fixture copy without surgery or manifest edits; empty-debug launch config asserted |
| M | `tools/stm32-toolkit/tests/test_context.py` | **revision-1**: build-capability regressions (CMakeLists-only → false, apply → true, drift/removal/stale/invalid/version-mismatch → false, read-only proof) |
| M | `tools/stm32-toolkit/tests/test_detection.py` | carried over: action availability tests |
| M | `tools/stm32-toolkit/tests/test_firmware_identity.py` | **revision-1 + Codex acceptance fix**: overlap dedup regressions using byte-exact writes and a privilege-free hard link on Windows |
| M | `tools/stm32-toolkit/tests/test_generation.py` | **revision-1**: empty debug build-only configuration and launch snapshot |
| A | `tools/stm32-toolkit/tests/test_mcp_migration_build.py` | **revision-1 + Codex acceptance fix**: e2e uses the convertible fixture without surgery and asserts real startup/vector prerequisites |
| M | `tools/stm32-toolkit/tests/test_mcp_roots.py` | carried-over compatibility exception (seven-tool registry); unchanged in revision 1 |
| M | `tools/stm32-toolkit/tests/test_mcp_server.py` | carried over: seven-tool registry/root binding |
| M | `tools/stm32-toolkit/tests/test_migration_plan.py` | **revision-1**: float-ABI normalization/blocker regressions and manifest-mapping update |
| M | `tools/stm32-toolkit/tests/test_planned_actions.py` | carried-over compatibility exception (mandated available actions); unchanged in revision 1 |
| M | `tools/stm32-toolkit/tests/test_plugin_layout.py` | **revision-1**: marketplace manifest source regression |
| M | `tools/stm32-toolkit/tests/test_result.py` | carried over: unified version assertion only |
| M | `tools/stm32-toolkit/tests/test_setup_runtime.py` | carried over: 0.3.0 setup/upgrade/rollback paths |
| A | `tools/stm32-toolkit/tests/test_workflows.py` | **revision-1**: parameterized non-bool authorization fail-closed regressions (with/without plan ID, convert/configure/build) |
| A | `docs/openclaw/returns/STM32TK-0306-CLI-MCP-RELEASE/r001-implementation-report.md` | this report (report-only final commit) |

The three compatibility exceptions (`test_planned_actions.py`,
`test_mcp_roots.py`, `tests/fixtures/minimal-gcc/.stm32-project.json`)
are untouched by revision 1 and are listed in section 1 as retained.

## 3. Revision-1 fixes in detail

### 3.1 Plugin release gate (§4)

- Root cause: Claude Code 2.1.140 rejects `plugins.0.source: "."`
  (`claude plugin validate .` exit 1, "plugins.0.source: Invalid input")
  and refuses install for unsupported source types.
- Fix: `.claude-plugin/marketplace.json` plugin source is now `"./"`, the
  repo-relative form this Claude Code version validates and installs for a
  marketplace whose plugin is its own repository root. The plugin entry's
  name/description/homepage/repository are unchanged.
- Gate (all run by OpenClaw on Claude Code 2.1.140, exact exits below in
  section 4): `claude plugin validate .` → 0; fresh isolated
  `CLAUDE_CONFIG_DIR` marketplace add → 0; `claude plugin install
  stm32-toolkit@stm32-toolkit --scope user` → 0 with installed version
  0.3.0 (gitCommitSha equals the code head); `claude plugin list` → 0 with
  `stm32-toolkit@stm32-toolkit 0.3.0 enabled`; `claude plugin details`
  shows exactly the four Skills (build-firmware, configure-stm32-project,
  migrate-keil, setup-stm32-env) and zero extra MCP registrations; the
  official upgrade path `claude plugin update stm32-toolkit@stm32-toolkit
  --scope user` upgrades an isolated 0.2.0 install to 0.3.0 (exit 0,
  "updated from 0.2.0 to 0.3.0").
- Version identity: `.claude-plugin/plugin.json` 0.3.0 == `__version__`
  0.3.0 == `pyproject.toml` 0.3.0 == CLI `version` output 0.3.0 ==
  `bin/setup-stm32-env.ps1` `$RuntimeVersion` 0.3.0 == installed plugin
  version 0.3.0. The roadmap 0.3.0 checkbox remains checked because every
  release gate now passes.

### 3.2 Real end-to-end workflows (§5)

- New committed fixture `keil-convertible` (five files listed in section
  2) is naturally convertible: no `#pragma arm section`/`#pragma import`/
  `#pragma O3`, no ARM assembly source, empty scatter, no FPU token and no
  `uFloatingPoint` element (so no float-ABI guess is needed), ARMCC V5.06
  with SPL defines plus the `Libraries/STM32F4xx_StdPeriph_Driver/inc`
  path evidence, and include paths that overlap the source directories so
  the 4.3 dedup is exercised end to end. The e2e copy performs only
  `copytree` + `.gitignore` + `git init`; the first public workflow call
  sees the fixture bytes exactly as committed.
- The generated Schema v2 manifest is consumed unmodified: `manifest["debug"]
  == {}` is asserted, configuration plan/apply succeeds with the empty
  debug spec, and the generated `.vscode/launch.json` contains
  `configurations: []` (deterministic, no cortex-debug entry, no pyOCD
  target guess). `flash`/`hostTest`/`targetTest`/`monitor`/
  `breakpointDebug` capabilities remain false.
- Chain linkage asserted: conversion report `planId` == applied plan ID;
  report/identity/build-result `gitHead` agree with `git rev-parse HEAD`;
  `firmware-identity.json` `buildId` == build-result `buildId`, preset
  `arm-debug`, ELF SHA-256 == the on-disk `legacy.elf`; managed manifest
  `toolVersion` 0.3.0; generated tasks contain exactly the two
  `build --preset ... --project ${workspaceFolder}` tasks; fake-CMake hit
  file proves the toolchain launch; context agrees with
  `managedManifestValid` true and `capabilities.build` true.
- 4.1 empty debug: `generation/configure.py` accepts a fully absent debug
  spec (`backend is None` and `target is None`) as build-only
  configuration; a partially specified spec (one of backend/target
  missing) and a non-pyocd/empty-target spec still raise the accepted
  `GENERATION_MODEL_INVALID` with `field debug.backend`.
- 4.2 Keil float ABI: `migration/planner.py` normalizes only verifiable
  Keil-format evidence — exact GCC spellings `soft`/`softfp`/`hard` pass
  through, and the documented Keil `uFloatingPoint` enumeration maps
  `0` ("Not Used") → `soft`, `1` ("Single precision") → `softfp`,
  `2` ("Double precision") → `softfp` (the ARM softfp ABI ARMCC/ARMCLANG
  apply for hardware FPU; a hard ABI can only be selected via misc
  controls, which are already blocked). Any other text (unknown or
  ambiguous) produces the stable blocker
  `MIGRATION_FLOAT_ABI_UNSUPPORTED` on the uvprojx path and never enters
  the manifest; apply is refused with `MIGRATION_BLOCKED`.
- 4.3 include/source overlap: `build/identity.py` input snapshot dedups a
  file reached by an explicit declaration and include traversal (same rel
  or same canonical `(st_dev, st_ino)` identity of a declared file);
  duplicate declarations of the same canonical file (hard links), Unicode
  casefold collisions, and redirect/reparse escapes still fail closed with
  the established rules; include-only overlaps (e.g. two case-variant
  names for one file) remain distinct so the casefold collision check
  still fires.
- 4.4 blockers preserved: the pragma/assembly/scatter/linker/option/
  compiler/framework/memory blocker classes are untouched; the existing
  `keil-project` fixture tests and all migration-apply blocker tests pass
  unchanged.

### 3.3 Non-boolean authorization (§6)

`workflows.py` now branches on the exact boolean value before any core
work: non-bool `authorized` returns `AUTHORIZATION_REQUIRED` with
`field authorized, rule type`; `authorized is False` with a plan ID
returns `AUTHORIZATION_REQUIRED` (`rule required`); `authorized is False`
without a plan ID returns the read-only plan; only `authorized is True`
with the exact freshly recomputed plan ID reaches the apply seam (the core
replan/race guards are unchanged). `build_firmware_workflow` requires the
exact boolean true as well. The MCP wrappers pass values through the same
workflow layer; the FastMCP schema continues to reject non-boolean JSON at
the schema boundary.

### 3.4 Build capability evidence (§7)

`context.py` adds a strictly read-only managed-configuration evidence
block to the build section (`managedManifestPresent`,
`managedManifestValid`, `managedFilesMissing`, `managedFilesDrifted`).
`capabilities.build` is true only when `CMakeLists.txt` is present AND the
managed manifest exists, parses (schema/keys/order), carries the current
tool/template version, agrees with the current model digest, and every
recorded managed file exists with the recorded SHA-256. Missing, drifted,
invalid, version-mismatched, or stale-manifest states return `build=false`
with the stable evidence fields; no capability call creates, repairs,
refreshes, or rewrites any file (project tree bytes/modes and Git
porcelain are proven unchanged across calls). The legacy v1
`configured_project` fixture (no managed manifest) now correctly reports
`build=false` (the build workflow itself requires managed configuration).

## 4. Environment-separated verification

OpenClaw environment: Linux x86_64 (Ubuntu 26.04 LTS, kernel
`7.0.0-22-generic`); CPython 3.10.11 (uv-managed,
`/home/openclaw/.local/share/uv/python/cpython-3.10.11-linux-x86_64-gnu`);
jsonschema 4.26.0, mcp 1.27.x, pyelftools 0.33, Jinja2 3.1.6, pytest
8.4.2, pytest-cov 6.x, Git 2.53.0, Claude Code 2.1.140; CMake/Ninja are
not installed (build gates use the deterministic fake-CMake launch seam;
the real ARM GNU toolchain gate belongs to Codex). All OpenClaw commands
run from the repository root on branch
`openclaw/STM32TK-0306-CLI-MCP-RELEASE/r001` with
`PYTHONPATH=tools/stm32-toolkit/src` for source-tree tests.

Codex acceptance environment: Windows NTFS, CPython 3.12.13, pytest 8.3.5,
jsonschema 4.23.0, pyelftools 0.33, Jinja2 3.1.6; CMake 4.3.1, Ninja
1.13.2, ARM GNU 14.3.1, and binutils 2.44. Codex gates ran against the
bounded acceptance-fix code head
`16b8b2cd90dbf39514064947c02508bb8a36d829` in a clean isolated worktree.

| Gate/command | Evidence owner | Environment | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| TDD RED (revision 1): regression tests against the reviewed predecessor | OpenClaw | Linux; CPython 3.10.11 | `aa5e991` (tests-only commit on the predecessor) | 1 | `45 failed, 568 passed, 5 skipped` — exactly the new regressions: non-bool authorization without plan ID, managed build capability, float-ABI normalization/blocker, include/source dedup, empty debug, marketplace source, both rewritten e2e tests | PASS (RED reproduced) |
| Focused GREEN (§10 command 1): `python -m pytest tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py -q` | OpenClaw | same | `b3dbd1e` | 0 | `727 passed, 17 skipped`; the 17 skips are the pre-existing Windows-only platform skips, unchanged and attributed | PASS |
| Full suite + branch coverage (§10 command 2): `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` | OpenClaw | same | `b3dbd1e` | 0 | `1185 passed, 17 skipped`; zero failures/errors; branch coverage **93%** TOTAL (fail_under 90 satisfied); `workflows.py` **100%** branch, `identity.py` 93%, `context.py` 92%, `configure.py` 91%, `planner.py` 91%; no file excluded; no new skip/xfail | PASS |
| compileall (§10 command 3) | OpenClaw | same | `b3dbd1e` | 0 | silent | PASS |
| Diff scope/whitespace (§10 commands 4-5): `git diff --check` and `git diff --name-status` base..HEAD | OpenClaw | same | `b3dbd1e` | 0 | silent; inventory matches section 2 | PASS |
| `claude plugin validate .` | OpenClaw | Linux; Claude Code 2.1.140 | `b3dbd1e` | 0 | `Validating marketplace manifest: … ✔ Validation passed` | PASS |
| Fresh isolated plugin install: `CLAUDE_CONFIG_DIR=$(mktemp -d) claude plugin marketplace add $PWD --scope user` | OpenClaw | same | `b3dbd1e` | 0 | `✔ Successfully added marketplace: stm32-toolkit (declared in user settings)` | PASS |
| Fresh isolated plugin install: `claude plugin install stm32-toolkit@stm32-toolkit --scope user` | OpenClaw | same | `b3dbd1e` | 0 | `✔ Successfully installed plugin: stm32-toolkit@stm32-toolkit (scope: user)`; installed version 0.3.0, `gitCommitSha` = code head | PASS |
| `claude plugin list` + `claude plugin details` (isolated config) | OpenClaw | same | `b3dbd1e` | 0 | `stm32-toolkit@stm32-toolkit  Version: 0.3.0  Scope: user  Status: ✔ enabled`; details inventory = exactly the four Skills, no second MCP registration | PASS |
| Official 0.2.0 → 0.3.0 upgrade: marketplace copy at the accepted base (plugin.json 0.2.0) installed in a fresh isolated config, then the source bumped to 0.3.0 and `claude plugin update stm32-toolkit@stm32-toolkit --scope user` | OpenClaw | same | `b3dbd1e` | 0 | `✔ Plugin "stm32-toolkit" updated from 0.2.0 to 0.3.0 for scope user. Restart to apply changes.`; `plugin list` shows 0.3.0 | PASS |
| Performance (spec 11.3): warm local filesystem, 20 measured runs after 3 warmups | OpenClaw | same | `b3dbd1e` | 0 | `convert_keil_workflow` median **74.05 ms** (< 500 ms), `configure_project_workflow` median **23.78 ms** (< 500 ms), MCP in-memory wrapper overhead (stubbed core) median **0.159 ms** (< 25 ms); no timing assertion in ordinary unit tests | PASS |
| Wheel gate (spec 11.3): `pip wheel` → fresh external venv → cwd outside the repository | OpenClaw | same | `b3dbd1e` | 0 | `stm32_toolkit-0.3.0-py3-none-any.whl` built and installed into a fresh CPython 3.10.11 venv; from `/tmp/tk0306-wheel-out` (outside the repo) the wheel CLI ran all four workflows against a convertible fixture copy with the fake-CMake launch seam: `keil inspect`, `keil convert` plan+apply, `project configure` plan+apply, `build --preset arm-debug` and `build --preset arm-release` all exit 0 with the expected operations; `stm32-toolkit version` prints `0.3.0`; packaged schemas (firmware-identity, stm32-project-v1, stm32-project) and 9 template resources importable from the wheel; identity `toolkitVersion` 0.3.0 with `elfSha256` matching the on-disk ELF; fake-CMake hit file (5 records) proves the full fake-toolchain build ran | PASS |
| Secret/placeholder scan | OpenClaw | same | `b3dbd1e` | 0 | no plaintext credential, `TODO`/`FIXME`/`pass`/ellipsis stub, debug print, or raw exception text in the revised deliverables; no XML/source-rewrite/CMake logic in Skill prose | PASS |
| Windows focused set from the work order | Codex | Windows NTFS; CPython 3.12.13 | `16b8b2c` | 0 | JUnit: **744 tests**, 744 passed, 0 failed/error/skipped; includes roots cancellation, path/case behavior, setup Repair/rollback, launcher, workflows, and e2e regressions | PASS |
| Windows full suite + branch coverage: `pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` | Codex | same | `16b8b2c` | 0 | **1206 passed, 3 skipped**, branch coverage **93%** (fail_under 90); skips are platform-inapplicable POSIX cases, with no failure/error | PASS |
| Final full-suite confirmation after the byte-exact fixture header update | Codex | same | `16b8b2c` | 0 | JUnit: 1209 collected, **1206 passed, 3 skipped**, 0 failed/error | PASS |
| `compileall` + `git diff --check` | Codex | same | `16b8b2c` | 0 | both silent | PASS |
| Real public workflow chain: inspect -> convert plan/apply -> configure plan/apply -> CLI Debug build -> MCP Release build | Codex | Windows; CMake 4.3.1; Ninja 1.13.2; ARM GNU 14.3.1/binutils 2.44 | `16b8b2c` | 0 | committed fixture copied without surgery; Debug `buildId=b9b2e39...`, ELF `d8b7299f...`, MAP `7eaa3222...`; Release `buildId=57a30f21...`, ELF `30fd1e7a...`, MAP `504a7b91...`; both identities match on-disk SHA-256, entry point, `.isr_vector`, and `Reset_Handler` | PASS |
| Visual/hardware | N/A | N/A | — | — | no UI or hardware surface in this module | `NOT_APPLICABLE` |

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| End-to-end fixture workflow (spec 11.1 class 9, revision 1) | OpenClaw | `test_mcp_migration_build.py::test_end_to_end_fixture_inspect_convert_configure_build` and `test_cli.py::test_end_to_end_inspect_convert_configure_build` pass with the committed `keil-convertible` fixture: copy + Git init only, no uvprojx/source/scatter/include/FPU edits, no manual manifest modification; `conversion-report.json` `planId` equals the applied plan ID and `fixedSections` contains address `0x20000000`; generated manifest `debug == {}`; `.vscode/launch.json` `configurations == []`; `.stm32-toolkit/generated-files.json` `toolVersion` 0.3.0; generated tasks contain exactly the two build tasks; `build-result.json` status success; `firmware-identity.json` `buildId`/`gitHead`/`elfSha256` agree with the record, the report, and `git rev-parse HEAD`; context reports `managedManifestValid` true, `capabilities.build` true, hardware capabilities false | PASS |
| No-write proof for capability checks | OpenClaw | `test_context.py::test_context_is_read_only_for_project_tree_and_git`: project tree bytes/modes and `git status --porcelain` unchanged across `build_project_context` calls; `_managed_configuration_evidence` never writes | PASS |
| No-write proof for authorization failures | OpenClaw | parameterized `test_workflows.py` regressions: non-bool authorization with/without plan ID leaves the tree and Git porcelain untouched and never calls the apply seam (hit counter 0) | PASS |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| Wheel | built from the code head | `stm32_toolkit-0.3.0-py3-none-any.whl` (built at `/tmp/tk0306-wheelhouse`, external) |
| Build identity document | `build/arm-debug/firmware-identity.json` (wheel-gate fixture, external `/tmp/tk0306-wheel-project`) | `toolkitVersion` 0.3.0; `elfSha256` matches the on-disk ELF |
| Isolated plugin install | `/tmp/tk0306-claude-isolated` (external) | `stm32-toolkit@stm32-toolkit` 0.3.0, `gitCommitSha` = code head |
| Isolated upgrade proof | `/tmp/tk0306-claude-upgrade` + `/tmp/tk0306-upgrade-mp` (external) | installed 0.2.0 → `claude plugin update` → 0.3.0 |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security: non-boolean authorization fails closed before any core call;
  capability checks are read-only and never repair or create files; the
  input snapshot still rejects portable-path violations, reserved paths,
  duplicate declarations (including hard-linked duplicates), Unicode
  casefold collisions, and redirect/reparse escapes; float-ABI unknowns
  produce a blocker instead of raw text in the manifest; empty-debug
  configuration generates no hardware-debug claims; marketplace plugin
  source uses the supported repo-relative form.
- Privacy/redaction: no absolute host root, raw exception text,
  credentials, or raw bytes in any JSON/MCP payload (unchanged assertions
  pass); the new evidence fields contain only portable project-relative
  paths.
- Performance: section 4 (74.05 ms / 23.78 ms / 0.159 ms medians vs 500 /
  500 / 25 ms budgets).
- Accessibility/input checks: unchanged CLI discipline (one JSON document,
  exit 0/2/2/1, cwd preserved); MCP schemas unchanged.
- Compatibility: CPython 3.10.11 pinned environment; protocol
  `stm32-toolkit/1`; no new dependency; the two private identity helpers'
  signatures changed only for test callers (updated in the same commit);
  the `.claude-plugin/marketplace.json` source value is the only manifest
  change and is required for Claude Code 2.1.140 compatibility.
  Codex additionally verified the same source tree on CPython 3.12.13 and
  the real Windows ARM GNU toolchain named in section 4.

## 6. Blockers and residual risks

- Blockers: `NONE` for every OpenClaw-owned gate. The r001 plugin-gate
  blocker is resolved (validate/install/list/update all exit 0 on the
  installed Claude Code).
- Residual risks: no deferred gate remains for this module. OpenClaw's Linux
  suite retains 17 pre-existing Windows-only skips; Codex's Windows suite
  retains 3 platform-inapplicable POSIX skips. The three compatibility-
  exception test paths listed in section 1 remain modified relative to the
  base by the r001 reconciliation and are untouched by revision 1.
- Roadmap/PR consistency: the roadmap 0.3.0 checkbox stays checked only
  because every release gate now passes (evidence in section 4); the PR
  description is updated to the revision-1 status and matches this
  report's Blockers/Known limitations statements.

## 7. Author checklist

- [x] Accepted base, reviewed predecessor, and code head are full SHAs.
- [x] Final head will be returned out of band after this report commit.
- [x] Inventory matches the complete implementation diff and report addition.
- [x] Every required OpenClaw gate has direct observed evidence with real exits.
- [x] Codex completed the named Windows and real ARM GNU gates against the bounded acceptance-fix code head; no gate remains deferred.
- [x] No credentials, private data, caches, build output, or unredacted diagnostics are committed.
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed.
- [x] Every instructional value in this report is replaced with actual evidence.
