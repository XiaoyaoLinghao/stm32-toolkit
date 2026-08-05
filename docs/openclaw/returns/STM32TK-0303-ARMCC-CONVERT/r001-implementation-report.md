# STM32TK-0303-ARMCC-CONVERT r001 Implementation Report

Status: `IMPLEMENTED`
Module: `STM32TK-0303-ARMCC-CONVERT` / r001
Branch: `openclaw/STM32TK-0303-ARMCC-CONVERT/r001`
Accepted base commit: `c01a7d5a6bc669db30f65ea47d72357906d192e5`
Code head before report commit: `8a54e7ea4a61d02a82ef9d1f78066469acd7ce2d`
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: supplied in the return message
Work order: `docs/openclaw/modules/STM32TK-0303-ARMCC-CONVERT.md` (specification commit `d1fb9e08a1bd8f7ca2f279ba7461b1e7cb293726`)

## 1. Outcome

- Observable result: `plan_keil_conversion(root, inspection) -> MigrationPlan` produces a deterministic, read-only conversion plan from one validated ARMCC 5 `KeilInspection`: canonical-root and fresh-inspection validation, byte-exact input revalidation with SHA-256 guards, bounded read-only Git evidence, token-aware ARMCC transforms (`__irq`, `__nop`/`__wfi`, absolute placement), explicit stable blockers for every unsupported construct, a validated Schema v2 `.stm32-project.json` proposal, fixed-section requirements for the later generation module, deterministic plan ID, and unified diffs. `apply_keil_conversion(plan) -> OperationResult` revalidates every plan field/digest, Git HEAD, porcelain status, patch targets, a freshly re-run inspection and plan, and the absence of blockers before its first write; then stages under `.stm32-toolkit/migration-staging/<plan_id>` with exclusive creation, fsync, sibling temporaries and `os.replace`, and rolls back byte/mode-exactly on any recoverable failure. A successful apply changes exactly the planned source/manifest paths plus `artifacts/migration/conversion.patch` and `conversion-report.json`; `.uvprojx`, Git index/HEAD/config/remotes, ignored files, and unrelated files are never touched.
- Scope completed: all of work-order sections 2.1, 4, 5, 6, 7 (OpenClaw gates), 8, 9, 10. TDD RED (exit 2, collection fails only for the missing `stm32_toolkit.migration` module) → focused GREEN (102 tests) → full suite (505 passed, 17 skipped) with branch coverage 92% (fail_under 90 satisfied) → compile/diff/dependency/read-only/atomicity/rollback/performance gates all pass on Linux.
- Known limitations:
  - `ARMCC_FINDING_UNSUPPORTED` is reachable only through the internal finding-mapping unit path: every blocker-severity finding the current inspection can produce (`ARMCC_SOURCE_ENCODING_UNSUPPORTED`, `ARMCC_UNSUPPORTED_PRAGMA`, `ARMCC_ABSOLUTE_PLACEMENT`, `ARMCC_INLINE_ASSEMBLY_FUNCTION`) is exactly resolved by a supported rule. The fallback is unit-tested (`_finding_blockers`).
  - `conversion-report.json`'s `includedAssembly` list is necessarily empty on a successful apply (any included non-empty asm source is a blocker); the report inventory path is exercised by tests and the success gate only ever observes the empty case.
  - After a successful apply the empty `.stm32-toolkit` state directory remains (work-order 6.5 success protocol: "never remove `.stm32-toolkit`"); Git porcelain does not list empty directories.
  - Directory fsync after `os.replace` is performed on POSIX and skipped where opening a directory fails (Windows); the rollback path treats a failed staging removal as recoverable (staging retention is the only failure allowed to retain staging).
  - Cross-file absolute-placement address reuse blocks the later declaration's file (by `(source_path, line)` ordering) and keeps the first; per-file invalid placement grammar blocks every placement rewrite in that file (no partial rewrite) while the other supported rules still produce their edits.
  - The revalidation defense accepts in-root redirects whose canonical target stays inside the root; the public `plan_keil_conversion` path records canonical target paths from the inspection, so the in-root redirect acceptance is exercised as a unit test of `_revalidate_inputs` (real symlinks on Linux), matching the 0302 module's approach.
- Deviations: `NONE`.

## 2. Complete changed-path inventory

Reconciled with `git diff c01a7d5a6bc669db30f65ea47d72357906d192e5..8a54e7ea4a61d02a82ef9d1f78066469acd7ce2d --name-status`: exactly the eight product/test paths in work-order section 5, plus this report as the report-only addition after the code head.

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/__init__.py` | 5, 6.1 | re-export public contracts and both functions |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py` | 5, 6.1 | frozen plan/patch/blocker/section models, stable errors, canonical hashing payloads, portable-path validation |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/git_guard.py` | 5, 6.2 | bounded read-only Git root/head/status evidence (fixed argv, 10 s timeout, 1 MiB output cap) |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` | 5, 6.3 | token-aware lexer, supported ARMCC transforms, blocker classification, fixed-address section requirements, cross-file placement uniqueness |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | 5, 6.2/6.4 | root/inspection validation, input revalidation, deterministic manifest proposal + Schema v2 validation, deterministic plan assembly |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py` | 5, 6.5 | forged-plan defense, preflight revalidation, private staging, atomic replace, byte-exact rollback, artifact emission |
| A | `tools/stm32-toolkit/tests/test_migration_plan.py` | 5, 8.2/8.3 | 61 tests: root/inspection/Git/input validation, determinism, rules, blockers, manifest, limits, read-only snapshots |
| A | `tools/stm32-toolkit/tests/test_migration_apply.py` | 5, 8.2/8.3 | 41 tests: success bytes/modes/artifacts, refusals, forged plans, failure injection, rollback, unrelated-state protection |
| A | `docs/openclaw/returns/STM32TK-0303-ARMCC-CONVERT/r001-implementation-report.md` | 9 | this report (report-only addition) |

No other path changed. `git diff --check c01a7d5..HEAD` exits 0; `git status --short` is empty before the report commit.

## 3. Public contracts delivered

- Types/signatures (all `@dataclass(frozen=True)`, tuples not lists; `to_dict()` returns fresh JSON-safe mappings, omits `project_root`, the inspection object, and raw before/after bytes, uses only portable `/` paths, and never includes host exception text):
  - `MigrationPlanError(code, message, details)`
  - `MigrationInput(path, sha256, size)`
  - `MigrationBlocker(code, rule_id, path, line, column, evidence, message)`
  - `FixedSectionRequirement(section, address, source_path, line, symbol)`
  - `FilePatch(path, before_sha256, after_sha256, before_size, after_size, rule_ids, unified_diff, before_bytes, after_bytes)`
  - `GitBaseline(head, root_marker=".")`
  - `MigrationPlan(project_root, inspection, plan_version=1, plan_id, inspection_sha256, git, inputs, patches, fixed_sections, blockers)`
  - `plan_keil_conversion(root: Path, inspection: KeilInspection) -> MigrationPlan`
  - `apply_keil_conversion(plan: MigrationPlan) -> OperationResult[Mapping[str, object]]`
- Stable planning errors with the exact required details from work-order 6.2 (`MIGRATION_ROOT_INVALID`, `MIGRATION_INSPECTION_INVALID`, `MIGRATION_GIT_UNAVAILABLE`, `MIGRATION_INPUT_INVALID`, `MIGRATION_INSPECTION_CHANGED`, `MIGRATION_MANIFEST_INVALID`, `MIGRATION_LIMIT_EXCEEDED`) and apply failures from 6.5 (`MIGRATION_PLAN_INVALID`, `MIGRATION_BLOCKED`, `MIGRATION_GIT_UNAVAILABLE`, `MIGRATION_GIT_HEAD_CHANGED`, `MIGRATION_GIT_DIRTY`, `MIGRATION_INPUT_CHANGED`, `MIGRATION_PATH_INVALID`, `MIGRATION_TARGET_EXISTS`, `MIGRATION_APPLY_FAILED`, `MIGRATION_ROLLBACK_FAILED`).
- Deterministic identity: `inspection_sha256` = SHA-256 over canonical JSON (`sort_keys=True`, separators `(',',':')`, `ensure_ascii=False`) of `inspection.to_dict()`; `plan_id` = SHA-256 over the canonical payload including plan version, inspection hash, Git head, input/patch metadata and digests, fixed sections, blockers, Toolkit version, and the SHA-256 of the concatenated patch content (raw bytes and unified diffs excluded); manifest UUIDv5 with namespace `a2e9f523-3c9e-5cb2-bf50-5cf9ff5d16a8` and name `<project_file>\n<target_name>\n<device>`.
- External interfaces: `NONE` (no CLI, MCP, Skill, network, or new dependency; stdlib only plus existing package APIs).

## 4. Environment-separated verification

OpenClaw environment: Linux x86_64 (Ubuntu 26.04 LTS, kernel `7.0.0-22-generic`); CPython 3.10.11 (`/home/openclaw/coding/venvs/tk0302`, uv-managed, outside the repository); jsonschema 4.23.0, mcp 1.27.0, pyelftools 0.33, pytest 8.3.5, pytest-cov 6.0.0; package installed `pip install -e "tools/stm32-toolkit[test]"` (stm32-toolkit 0.2.0, no dependency change); Git 2.53.0. All OpenClaw commands run from the repository root on branch `openclaw/STM32TK-0303-ARMCC-CONVERT/r001`.

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| TDD RED (8.3): `python -m pytest tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py -q` before implementation | OpenClaw | Linux; CPython 3.10.11; pytest 8.3.5 | `5ff4ba1` (tests added, modules absent) | 2 | collection interrupted: `2 errors`, `ModuleNotFoundError: No module named 'stm32_toolkit.migration'` in both files only | PASS |
| Focused GREEN (8.3/8.4): identical command after implementation | OpenClaw | same | `8a54e7e` | 0 | `102 passed in 10.06s` (61 plan + 41 apply); zero failures; no new skip/xfail | PASS |
| Full suite + branch coverage (8.4): `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` | OpenClaw | same | `8a54e7e` | 0 | `505 passed, 17 skipped in 24.44s`; zero failures/errors; branch coverage **92%** TOTAL (fail_under 90 satisfied); migration modules: `__init__` 100%, model 96%, rules 93%, planner 90%, apply 89%, git_guard 89%; the 17 skips are the pre-existing Windows-only platform skips in `test_plugin_layout.py`/`test_setup_runtime.py` | PASS |
| Compile (8.4): `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `8a54e7e` | 0 | silent | PASS |
| Dependency (8.4): `python -m pip install -e "tools/stm32-toolkit[test]"` + `python -c "from importlib.metadata import requires; r = requires('stm32-toolkit') or []; assert not any('jinja' in x.lower() for x in r)"` | OpenClaw | same | `8a54e7e` | 0 | no new dependency; `Requires-Dist` = jsonschema, mcp, pyelftools (+ test extras); jinja absent; installed versions above | PASS |
| Diff hygiene (8.4): `git diff --check c01a7d5..HEAD` | OpenClaw | same | `8a54e7e` | 0 | silent | PASS |
| Diff scope (8.4): `git diff --name-status c01a7d5..HEAD` | OpenClaw | same | `8a54e7e` | 0 | exactly the eight section-5 paths | PASS |
| Working tree (8.4): `git status --short` | OpenClaw | same | `8a54e7e` | 0 | empty before the report commit | PASS |
| Read-only plan (8.5.1/8.5.2 + automated) | OpenClaw | same | `8a54e7e` | 0 | recursive names/bytes/SHA-256/mtimes/modes and porcelain/index/HEAD identical before vs after repeated planning; repeated `to_dict`/plan ID equal; see manual evidence | PASS |
| Atomic apply/rollback (8.5.3/8.5.6 + automated) | OpenClaw | same | `8a54e7e` | 0 | exact changed/created path set; byte spans; preserved mode 0o640; artifact hashes; staging absent; injected replace/fsync/stage failures restore every original byte, mode, and clean status; injected rollback failure retains recoverable staging | PASS |
| Performance (7.3): `/tmp/perf0303.py` (disposable fixture; 3 warm-ups + 20 planning runs; 10 independent apply repos) | OpenClaw | same | `8a54e7e` | 0 | planning median **1064.7 ms** (min 1054.1, max 1096.7) < 2,000 ms; apply median **1562.9 ms** (min 1522.4, max 1632.5) < 2,000 ms; fixture 100 × 65,536 B = 6,553,600 B, 25 edits/file, 0 blockers; no timing assertions added to CI tests | PASS |
| Placeholder/cache/credential/binary scan | OpenClaw | same | `8a54e7e` | 0 | no TODO/FIXME/placeholder markers; no credential patterns (only lexer variable names matched `token`); no tracked `__pycache__`/`.pyc`/`.coverage`/`.egg-info`/binary build artifacts in the diff; the pre-existing `tests/fixtures/keil-project/Objects/legacy.map` fixture belongs to the accepted base | PASS |
| Windows focused/full suite + real NTFS junction gate (8.1 Windows row, 8.5.8) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13; Git | returned head | — | real NTFS junction in-root acceptance/escape rejection and the full Windows suite must be re-run by Codex on the returned head | `DEFERRED_TO_CODEX` |
| Visual/UI (8.1) | N/A | N/A | — | — | `NOT_APPLICABLE` — no UI or rendered artifact created | PASS |

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| 8.5.1 disposable repo + full snapshot | OpenClaw | committed HEAD `a058ca01…`, index tree `cbcaff55…`, porcelain empty; inventory with SHA-256 for `app.uvprojx 34b55c78…`, `Main/main.c 2d747c10…`, `Common/common.c 513c0156…`, plus `note.txt`, `.gitignore`, `ignored.txt`; snapshot includes modes and mtimes | manual run on disposable `/tmp` data, removed afterwards |
| 8.5.2 planning twice | OpenClaw | `plan_id 975d589e…`, `inspection_sha256 a0868cff…`, `logicalProjectId 9b961910-289f-59f3-91e8-a4bc792ff032`; identical `to_dict`/patches/blockers; snapshot and Git state unchanged | PASS |
| 8.5.3 blocker-free apply | OpenClaw | changedPaths `[Common/common.c, Main/main.c]`; createdPaths `[.stm32-project.json, artifacts/migration/conversion-report.json, artifacts/migration/conversion.patch]`; fixedSections `[{section: .stm32tk.abs.20000000, address: 536870912, sourcePath: Common/common.c, line: 13, symbol: pinned_value}]`; `patchSha256 1999ab90…`, `reportSha256 fac48f28…`; source spans transformed; `.uvprojx` bytes/HEAD/index unchanged; staging absent; porcelain exactly ` M Common/common.c`, ` M Main/main.c`, `?? .stm32-project.json`, `?? artifacts/` | PASS |
| 8.5.4 changed input after planning | OpenClaw | `MIGRATION_INPUT_CHANGED {"path": "Main/main.c"}`; no writes, no `.stm32-toolkit` | PASS |
| 8.5.5 dirty tracked/staged/untracked | OpenClaw | all three refuse with `MIGRATION_GIT_DIRTY {"rule": "cleanWorktree"}` before staging | PASS |
| 8.5.6 injected replace failure | OpenClaw | `MIGRATION_APPLY_FAILED {"phase": "replace"}`; every original byte and mode restored; porcelain clean; staging absent | PASS |
| 8.5.7 forged digest-consistent plan (changed after bytes) | OpenClaw | `MIGRATION_PLAN_INVALID {"rule": "patchDigest"}`; no writes (also covered for changed patch path / blocker removal / fixed sections via fresh-replan equality) | PASS |
| 8.5.8 real NTFS junctions + Windows replace failure | Codex | not run by OpenClaw; Linux real-symlink tests run without skip; simulated reparse tests supplement | `DEFERRED_TO_CODEX` |
| Visual/UI | N/A | `NOT_APPLICABLE` | N/A |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| Migration package | `tools/stm32-toolkit/src/stm32_toolkit/migration/` | 6 modules (model 128 lines, git_guard 98, rules 610, planner 640, apply 830, `__init__` 40) |
| Plan tests | `tools/stm32-toolkit/tests/test_migration_plan.py` | 61 tests |
| Apply tests | `tools/stm32-toolkit/tests/test_migration_apply.py` | 41 tests |
| Implementation report | `docs/openclaw/returns/STM32TK-0303-ARMCC-CONVERT/r001-implementation-report.md` | this file |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security checks (all automated, all pass):
  - Forged-plan defense at apply: exact `MigrationPlan` type, `plan_version == 1`, field/container/scalar types, portable paths (no absolute/drive/UNC/NUL/`.`/`..` components), reserved-path rejection (`.uvprojx`, `.git/`, `.stm32-toolkit/`, `artifacts/migration/`), unique paths, Unicode `casefold()` collisions, sorted orders, digest formats, before/after byte-vs-digest consistency, recomputed `inspection_sha256` and `plan_id`, canonical root == inspection root == Git toplevel, committed HEAD equality, clean porcelain, fresh `inspect_keil` + fresh `plan_keil_conversion` equality (every canonical field and raw patch byte), and no blockers — all before the first write.
  - Input revalidation at planning and apply: portable form, redirect resolution with in-root acceptance, escape/loop/permission/inspection-failure rejection, regular-file requirement, bounded `size + 1` reads, exact size and SHA-256; a changed inspected input returns `MIGRATION_INSPECTION_CHANGED` (planning) or `MIGRATION_INPUT_CHANGED` (apply) before any dirty-worktree or write path.
  - Git: fixed argv, `cwd=root`, `stdin=DEVNULL`, binary output, 10 s timeout, 1 MiB combined output cap, no shell, no human-formatted parsing, unborn HEAD/malformed SHA/non-repo → stable `MIGRATION_GIT_UNAVAILABLE` with the command's rule; ignored files never dirty the baseline.
  - Rules: comments, strings, character literals, C++ raw strings, preprocessor bodies (including continuations), and identifier substrings are never rewritten; rewrites replace exact code spans only; re-encoding preserves BOM and every original newline sequence; unsupported constructs are always explicit blockers; a per-file placement grammar failure drops every placement rewrite in that file; cross-file section-address reuse blocks the later declaration.
  - Atomicity: staging created only after all preflight checks pass (exclusive creation, `O_CREAT|O_EXCL`), staged and destination writes flushed and fsynced, sibling temporaries replaced with `os.replace`, containment re-checked immediately before each replace, directory fsync on POSIX; any recoverable failure restores every replaced byte and mode in reverse order, removes created destinations and newly created empty parents, and removes staging; rollback failure retains recoverable staging with portable paths.
  - Privacy/redaction: `OperationResult`, errors, details, plan `to_dict`, and the report contain no absolute root, username, environment value, timestamp, raw Git output, host exception text, or source content beyond capped blocker evidence (200 code points) and the unified diff; verified by `assert str(repo) not in json.dumps(...)` style checks and the manual run.
  - Bounds: 8 MiB/file and 64 MiB aggregate input limits, 8 MiB manifest read, 1 MiB Git output, 64 MiB serialized plan/patch/report caps (`MIGRATION_LIMIT_EXCEEDED` with `scope`), all enforced on the bytes actually read.
- Privacy/redaction checks: see above; the report contains no `reportSha256` of itself (apply success data carries both `patchSha256` and `reportSha256`).
- Performance measurements (7.3, `time.perf_counter`, 3 warm-ups then 20 planning runs / 10 independent apply repos, median): planning median **1064.7 ms** (min 1054.1, max 1096.7), apply median **1562.9 ms** (min 1522.4, max 1632.5) — both below the 2,000 ms budget on the declared OpenClaw environment (Linux 7.0.0-22-generic x86_64, CPython 3.10.11, Git 2.53.0, ext4-class filesystem with 4096-byte blocks). Fixture: 100 included UTF-8 C sources of exactly 65,536 bytes each (6,553,600 bytes total), 25 supported edits per file, no blockers; every apply repo recreated clean. No timing-fragile CI assertion added.
- Accessibility/input checks: `NOT_APPLICABLE` for UI; stable English errors with structured `details` for AI/CLI adapters.
- Compatibility checks: CPython 3.10+ (verified on 3.10.11); Git worktrees where `.git` is a file (dedicated tests pass); LF/CRLF/mixed-newline and UTF-8 BOM preservation; Windows path forms rejected on every host (`C:\x`, `C:x`, UNC, `\\x`, backslash traversal) plus Unicode casefold collision detection; real NTFS junction behavior deferred to Codex on Windows NT 10.0.26200.0 / CPython 3.12.13; no new runtime dependencies; dependency direction respected (migration depends on `keil`, `project_model`, `result`, `__version__`; upstream modules do not import migration).

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  1. The public planning path cannot end-to-end observe an in-root redirect acceptance (inspection canonicalizes redirect targets before recording input paths), so the acceptance defense is verified by direct `_revalidate_inputs` unit tests with real Linux symlinks; the escape path is additionally covered end-to-end at planning and apply. The real NTFS junction gate remains Codex's.
  2. `ARMCC_FINDING_UNSUPPORTED` and a non-empty `includedAssembly` report list are unreachable through any current real inspection/success flow and are covered by internal unit paths; a future inspection finding rule must be added to `_RESOLVED_BLOCKER_FINDINGS` to remain exactly resolved.
  3. Directory fsync is skipped where opening a directory is unsupported; a post-replace directory-fsync failure is reported as phase `fsync` with full rollback on POSIX.
  4. A successful apply leaves the empty `.stm32-toolkit` directory (6.5 success protocol); it is invisible to Git porcelain but present on disk.
- Follow-up recommendation: `NONE` (generation/build modules consume the Schema v2 manifest and `conversion-report.json` fixed sections in later work orders).

## 7. Author checklist

- [x] Accepted base and code head are full SHAs (`c01a7d5a6bc669db30f65ea47d72357906d192e5`, `8a54e7ea4a61d02a82ef9d1f78066469acd7ce2d`).
- [x] Final head will be returned out of band after this report commit (PR metadata + return message).
- [x] Inventory matches the complete implementation diff and report addition (eight section-5 paths + report).
- [x] Every required OpenClaw gate has direct observed evidence on the code head (RED exit 2; focused 102 passed; full 505 passed/17 skipped; coverage 92%; compileall; dependency; diff check/scope; status; read-only; atomicity/rollback; performance medians 1064.7/1562.9 ms).
- [x] Other-environment gates are accurately attributed or deferred (Windows suite + real NTFS junction `DEFERRED_TO_CODEX`; visual `NOT_APPLICABLE`).
- [x] No credentials, private data, caches, build output, binary fixtures, temp projects, or unredacted diagnostics are committed (venv outside the repository; `.coverage`/`__pycache__`/`.pytest_cache`/`*.egg-info` ignored; disposable repos removed; the committed `legacy.map` fixture predates this module).
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed (diff scope verified; `AGENTS.md`/`OPENCLAW_START_HERE.md`/work order/upstream modules untouched).
- [x] Every instructional value in this report is replaced with actual evidence; no self-referential final SHA and no moving commit totals.
- [x] Overall status `IMPLEMENTED`: complete suite exits 0 on CPython 3.10.11 (505 passed, 17 skipped), branch coverage 92%, performance budgets pass, Windows gates `DEFERRED_TO_CODEX`.
