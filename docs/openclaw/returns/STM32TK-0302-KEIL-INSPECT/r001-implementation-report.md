# STM32TK-0302-KEIL-INSPECT r001 Implementation Report

Status: `IMPLEMENTED`
Branch: `openclaw/STM32TK-0302-KEIL-INSPECT/r001`
Accepted base commit: `53321e8721cc479122c43285537dc108461a8e0e`
Code head before report commit: `129dc2c11f2507801abfa10cb2309c4e1130f431`
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/2
Work order: `docs/openclaw/modules/STM32TK-0302-KEIL-INSPECT.md`

## 1. Outcome

- Observable result: `inspect_keil(root, uvprojx=None, target_name=None) -> KeilInspection` performs read-only discovery, bounded namespace-agnostic XML parsing, exact target selection, option/compiler/memory extraction, path validation and normalization, ARMCC lexical scanning, framework inference, and exact-byte SHA-256 input hashing. `capture_keil_baseline(root, inspection) -> KeilBaseline` reads the validated AXF/MAP candidates with pyelftools 0.33, reports honest unavailable evidence for missing artifacts, and never writes. The complete project tree remains byte-for-byte, name-for-name, mtime- and permission-equivalent after every call (verified by automated and manual snapshots).
- Scope completed: all of work-order sections 2.1, 4, 5, 6, 7, 8 (OpenClaw gates), 9, 10.
- Known limitations:
  - The committed `keil-project` fixture references `Objects/legacy.sct` (scatter setting) without a committed `.sct` file; the missing scatter input is honestly excluded from digests and produces no fabricated evidence.
  - The parser implements the bounded field set of section 6, not a replacement for `PROJECT_PROJX.XSD` (per work-order section 3).
  - A NUL byte inside XML text makes the XML malformed before path extraction; NUL rejection is enforced for the root and explicit project paths (stable `KEIL_PROJECT_PATH_INVALID`/`KEIL_PATH_OUTSIDE_PROJECT`).
- Deviations:
  - Path safety is intentionally stricter than the literal sentence in section 6.2: any symlink or reparse-point component in a referenced path is rejected (`KEIL_PATH_OUTSIDE_PROJECT`), including redirects that would resolve inside the root. This follows the existing `paths.py` precedent and eliminates TOCTOU swap windows. All required rejection tests (escape, simulated reparse, in-root redirect) pass; the in-root-symlink case is documented as a conservative rejection.
  - `ARMCC_CUSTOM_SECTION` "named section linker input" is implemented as a `section(...)` construct in the linker misc-controls string, reported at the scatter path with line/column zero (mirroring the `ARMCC_SCATTER_FILE` reporting pattern).

## 2. Complete changed-path inventory

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| M | `tools/stm32-toolkit/pyproject.toml` | 5 | add only `pyelftools>=0.33,<0.34` |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/__init__.py` | 5, 6.1 | re-export public contracts and functions |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/model.py` | 5, 6.1/6.4 | frozen models, JSON-safe `to_dict`, stable errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py` | 5, 6.2 | discovery, XML parsing, selection, extraction, path validation, hashing, orchestration |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` | 5, 6.3 | bounded source scan, ARMCC findings, framework evidence |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/baseline.py` | 5, 6.4 | AXF/MAP artifact parsing and baseline assembly |
| M | `tools/stm32-toolkit/tests/fixtures/keil-project/legacy.uvprojx` | 5 | representative single-target namespace-qualified MDK XML fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Common/common.c` | 5 | UTF-8 ARMCC scan fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Main/main.c` | 5 | framework/source fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Startup/startup_stm32f4xx.s` | 5 | assembly-path fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Objects/legacy.map` | 5 | text-only Keil MAP baseline fixture |
| A | `tools/stm32-toolkit/tests/test_keil_inspect.py` | 5, 8.2 | discovery/XML/selection/path/scanner/framework/read-only tests |
| A | `tools/stm32-toolkit/tests/test_keil_baseline.py` | 5, 8.2 | AXF/MAP/missing/corrupt/read-only baseline tests |
| A | `docs/openclaw/returns/STM32TK-0302-KEIL-INSPECT/r001-implementation-report.md` | 9 | this report (report-only addition) |

Reconciled with `git diff --name-status 53321e87..HEAD`: exactly the 13 code/fixture paths plus this report. No other path changed; the 0.3 plan checkbox, roadmap, architecture, CLI, MCP, schemas, and Skills are untouched.

## 3. Public contracts delivered

- Types/signatures (all `@dataclass(frozen=True)`): `KeilInspectionError(code, message, details)`; `KeilInputDigest`, `KeilMemoryRegion`, `KeilScopedOptions`, `KeilSource`, `KeilOutputSpec`, `KeilEvidence`, `KeilFinding`, `KeilWarning`, `KeilInspection`, `KeilArtifactEvidence`, `KeilSectionEvidence`, `KeilSymbolEvidence`, `KeilProgramSize`, `KeilBaseline`; every container has a fresh JSON-safe `to_dict()` with repository-relative `/` paths and no host absolute path (project_root omitted from `KeilInspection.to_dict()`).
- Functions: `inspect_keil(root, uvprojx=None, target_name=None)`, `capture_keil_baseline(root, inspection)`.
- Stable errors: all 15 codes of section 6.5 with the exact required details.
- External interfaces: `NONE` (no CLI, MCP, Skill, network, or subprocess).

## 4. Environment-separated verification

OpenClaw environment: Linux x86_64 (Ubuntu), CPython 3.10.11 (`/home/openclaw/.local/share/uv/python/cpython-3.10.11-linux-x86_64-gnu`), venv deps `jsonschema==4.23.0`, `mcp==1.27.0`, `pyelftools==0.33`, `pytest==8.3.5`, `pytest-cov==6.0.0`. All commands run from repository root.

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| TDD RED: `python -m pytest tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_keil_baseline.py -q` (before implementation) | OpenClaw | Linux; CPython 3.10.11; pytest 8.3.5 | base `53321e87` + tests-only worktree | 2 | collection interrupted: `ModuleNotFoundError: No module named 'stm32_toolkit.keil'` for both test files; no other failure | PASS |
| Focused GREEN: identical command (after implementation) | OpenClaw | same | `129dc2c` | 0 | 95 collected, 0 failed, 0 skipped, 0 xfailed | PASS |
| Full suite + branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` | OpenClaw | same | `129dc2c` | 0 | 402 collected; branch coverage 93% (TOTAL 2222 stmts / 614 branches); keil modules: armcc_scan 93%, baseline 91%, model 96%, uvprojx 90%; no failure/error; pre-existing 12 skips unchanged (not new) | PASS |
| Compile: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `129dc2c` | 0 | silent | PASS |
| Dependency: `python -c "from importlib.metadata import version; assert version('pyelftools') == '0.33'"` | OpenClaw | same | `129dc2c` | 0 | `pyelftools 0.33`; `stm32-toolkit` Requires-Dist = jsonschema, mcp, pyelftools (only addition) | PASS |
| Diff hygiene: `git diff --check 53321e87..HEAD` | OpenClaw | same | `129dc2c` | 0 | silent | PASS |
| Diff scope: `git diff --name-status 53321e87..HEAD` | OpenClaw | same | `129dc2c` | 0 | exactly section-5 paths (13 paths) | PASS |
| Working tree: `git status --short` | OpenClaw | same | `129dc2c` | 0 | clean (only report addition after final commit) | PASS |
| Read-only tree (8.5.1-8.5.4, 8.5.8): snapshot of bytes/SHA-256/names/mtimes/modes before vs after inspect+capture | OpenClaw | same | `129dc2c` | 0 | identical snapshots; see manual evidence below | PASS |
| Performance (7.3): inspect/capture medians | OpenClaw | same | `129dc2c` | 0 | see section 5 performance | PASS |
| Windows real NTFS junction gate (8.1) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | latest head | — | real junction escape rejection must be re-run by Codex | `DEFERRED_TO_CODEX` |

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| 8.5.1 disposable copy + full snapshot | OpenClaw | recursive relative paths, exact bytes/SHA-256, modes, mtimes captured; Git status clean | automated: `test_inspection_read_only_snapshot`, `test_baseline_read_only_snapshot`; manual run output in return message |
| 8.5.2 inspect + repeat | OpenClaw | `target=Legacy device=STM32F429ZGTx compiler=armcc V5.06 update 7 (build 750)`; memory IROM1 0x8000000/0x100000, IRAM1 0x20000000/0x30000; 3 sources; 10 findings; 4 digests; framework `None ('spl',)`; equal `to_dict()` across calls | `test_repeated_inspection_equal_serialization` |
| 8.5.3 capture on fixture | OpenClaw | MAP facts: `Program Size: Code=8124 RO-data=720 RW-data=92 ZI-data=16988`, flash 8936, ram 17080; AXF honestly unavailable; snapshot unchanged | `test_committed_fixture_map_only_baseline` |
| 8.5.4 disposable ELF at AXF candidate | OpenClaw | entry 0x08000000, sections `[.text]`, SHA-256 exact; disposable data removed afterwards; snapshot unchanged | `test_elf_exact_parse` |
| 8.5.5 multiple targets/projects | OpenClaw | selection errors carry sorted relative names; no writes | `test_multiple_projects_require_selection`, `test_multiple_targets_require_selection` |
| 8.5.6 symlink to sibling outside root | OpenClaw | `KEIL_PATH_OUTSIDE_PROJECT`; no external content in details | `test_symlink_escape_rejected`, `test_artifact_symlink_escape_rejected` |
| 8.5.7 real NTFS junction | Codex | same stable rejection, no skip | `DEFERRED_TO_CODEX` |
| 8.5.8 injected `PermissionError` | OpenClaw | conservative stable error; no exception text/absolute path in details | `test_permission_error_during_inspection_rejected`, `test_generic_oserror_during_inspection_rejected`, `test_artifact_unreadable_permission` |
| Visual/UI (7.4) | N/A | `NOT_APPLICABLE` — no UI/visual asset/rendered output created | N/A |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| Keil inspection package | `tools/stm32-toolkit/src/stm32_toolkit/keil/` | 5 modules, 1,913 lines (model 215, uvprojx 1,014, armcc_scan 345, baseline 298, `__init__` 41) |
| Keil fixture project | `tools/stm32-toolkit/tests/fixtures/keil-project/` | legacy.uvprojx 3,125 B; common.c 570 B; main.c 90 B; startup_stm32f4xx.s 134 B; legacy.map 1,778 B |
| Focused tests | `test_keil_inspect.py` (1,345 lines), `test_keil_baseline.py` (516 lines) | 95 tests collected |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security checks (all automated, all pass):
  - DTD/entity declaration rejected before XML parse (`KEIL_XML_UNSAFE`, rule `doctypeOrEntity`); no external resource fetch; XML capped at 8 MiB.
  - Path rejection on every host: POSIX absolute, drive absolute, drive relative, UNC, mixed separators, `..` escape, NUL, symlink and simulated reparse point, `PermissionError`, generic `OSError` (`KEIL_PATH_OUTSIDE_PROJECT` with stable fields only).
  - Only confirmed `FileNotFoundError`/`NotADirectoryError` treated as missing; permission/inspection failures reject conservatively.
  - No source-tree recursion: only files referenced by the selected target plus the two artifact candidates are read; no `.git`, credentials, environment, or unrelated files.
  - Baseline revalidates containment and redirect behavior before every artifact read; root must canonicalize to `inspection.project_root`.
- Privacy/redaction: errors, warnings, findings, and `to_dict()` contain no host exception text, stack trace, absolute path, temporary-directory path, or source content beyond the 200-code-point evidence cap; verified by `assert_no_absolute` helpers in both test files and the manual `PermissionError` run.
- Performance (7.3, measured with `time.perf_counter`, warm-up 3, runs 20):
  - `inspect_keil`: fixture 1,016,117-byte `.uvprojx` with exactly 1,000 file nodes and 100 referenced UTF-8 sources of 1,024 bytes each → **median 280.80 ms** (min 278.22, max 289.98) — budget <500 ms PASS.
  - `capture_keil_baseline`: 2,097,428-byte valid ELF + 1,992,089-byte MAP → **median 18.82 ms** (min 17.93, max 19.86) — budget <500 ms PASS.
  - Memory is O(XML + referenced inputs + artifact size within caps); no unrelated data loaded. No timing-fragile assertions added.
- Accessibility/input: no UI; stable English messages and structured fields for later CLI/MCP adapters.
- Compatibility: Windows 10/11 and Linux path forms handled (Windows-specific branches covered by simulated reparse/flag tests on Linux; real NTFS junction gate deferred to Codex); CPython 3.10+; namespace-qualified and unqualified Keil MDK 5 XML; ARM Compiler 5 inspection; ArmClang identified (`armclang`) without conversion claims.

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  - Real Windows NTFS junction behavior is verified only by the simulated reparse-point test on Linux; the real gate is `DEFERRED_TO_CODEX` (Windows NT 10.0.26200.0, CPython 3.12.13).
  - Keil project-file completeness is bounded to the section-6 field set; a future real-project/board acceptance gate (0.3 plan Task 2 follow-ups) remains out of scope for this module.
  - In-root symlink redirects are rejected conservatively (see deviations); if a user's real Keil tree legitimately uses in-root junctions, they will see `KEIL_PATH_OUTSIDE_PROJECT`.
- Follow-up recommendation: `NONE` (migration/plan/generation layers are separate work orders).

## 7. Author checklist

- [x] Accepted base and code head are full SHAs (`53321e8721cc479122c43285537dc108461a8e0e`, `129dc2c11f2507801abfa10cb2309c4e1130f431`).
- [x] Final head will be returned out of band after this report commit (PR metadata + return message).
- [x] Inventory matches the complete implementation diff and report addition (`git diff --name-status 53321e87..HEAD` = 13 paths + this report).
- [x] Every required OpenClaw gate has direct observed evidence (RED/GREEN/full/compile/dependency/read-only/performance, all exit codes above).
- [x] Other-environment gates are accurately attributed or deferred (Windows junction gate → `DEFERRED_TO_CODEX`).
- [x] No credentials, private data, caches, build output, binary fixtures, temp projects, or unredacted diagnostics are committed (ELF baselines are generated in tests, never committed).
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed.
- [x] Every instructional value in this report is replaced with actual evidence.
