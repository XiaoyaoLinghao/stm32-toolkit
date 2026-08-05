# STM32TK-0302-KEIL-INSPECT r001 Implementation Report

Status: `IMPLEMENTED`
Branch: `openclaw/STM32TK-0302-KEIL-INSPECT/r001`
Accepted base commit: `53321e8721cc479122c43285537dc108461a8e0e`
Reviewed predecessor: `50d263e378469ff0d6480eef8917a68c5c88d3e3`
Code head before report commit: `352a345f1ad6356603ae5fbdff74f93f89b335e9`
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/2
Work order: `docs/openclaw/modules/STM32TK-0302-KEIL-INSPECT.md`

## 1. Outcome

- Observable result: `inspect_keil(root, uvprojx=None, target_name=None) -> KeilInspection` performs read-only discovery, bounded namespace-agnostic XML parsing, exact target selection, option/compiler/memory extraction, path validation and normalization, ARMCC lexical scanning, framework inference, and exact-byte SHA-256 input hashing. `capture_keil_baseline(root, inspection) -> KeilBaseline` reads the validated AXF/MAP candidates with pyelftools 0.33, reports honest unavailable evidence for missing artifacts, and never writes. The complete project tree remains byte-for-byte, name-for-name, mtime- and permission-equivalent after every call (verified by automated and manual snapshots).
- Scope completed: all of work-order sections 2.1, 4, 5, 6, 7, 8 (OpenClaw gates), 9, 10, including the six revision findings below.
- Revision round: this is the r001 revision addressing the Codex review of the predecessor head. All six rejection items are fixed and covered by new regression tests (see section 1a).
- Known limitations:
  - The committed `keil-project` fixture references `Objects/legacy.sct` (scatter setting) without a committed `.sct` file; the missing scatter input is honestly excluded from digests and produces no fabricated evidence.
  - The parser implements the bounded field set of section 6, not a replacement for `PROJECT_PROJX.XSD` (per work-order section 3).
  - A NUL byte inside XML text makes the XML malformed before path extraction; NUL rejection is enforced for the root and explicit project paths (stable `KEIL_PROJECT_PATH_INVALID`/`KEIL_PATH_OUTSIDE_PROJECT`).
  - Real NTFS junction behavior and the Windows full-suite run are verified only on the Codex Windows host; they remain `DEFERRED_TO_CODEX` (Windows NT 10.0.26200.0, CPython 3.12.13). On Linux, in-root and escaping redirects are exercised with real symlinks; on Windows the same code paths are exercised through the platform-adapted fixture that maps `Path.resolve` (no administrator rights or Developer Mode required).
- Deviations: `NONE` for this revision round. The previous round's deviation ("in-root symlink redirects are rejected conservatively") is removed: in-root redirects whose canonical target stays inside the canonical project root are now accepted, matching work-order section 6.2 ("Existing symlink or Windows reparse-point traversal must resolve within the canonical root") and the revision instruction to reject only escapes, cycles, resolution failures, and inspection errors.

### 1a. Codex review observations and revision fixes

Codex review (Windows-focused run, 19 failed) observed the following on the predecessor head; each item is fixed in this revision. The Windows failures are recorded here as Codex review observations, not as OpenClaw-run evidence.

| # | Codex observation | Type | Fix (this revision) | Regression coverage |
|---|---|---|---|---|
| 1 | Windows path serialization violated the contract: `project_file`, sources, include paths, linker inputs, scatter, AXF/MAP, findings, and input digests used backslashes on Windows; framework inference split on `/` and failed on Windows SPL/HAL/LL. | architecture | Every public repository-relative path is produced through `Path.relative_to(...).as_posix()` (host-independent); framework inference consumes only POSIX-normalized paths; scoped-option include paths are normalized the same way. | `test_windows_style_paths_serialize_posix`, `test_framework_inference_windows_style_paths`, `test_framework_hal_windows_style_paths`, `test_framework_ll_windows_style_paths`, existing `assert_no_absolute` checks |
| 2 | UTF-16 DTD/ENTITY bypassed the safety check: a UTF-16 `.uvprojx` containing `<!DOCTYPE ... <!ENTITY ...>>` was accepted and returned Target 1 without `KEIL_XML_UNSAFE`. | security | Case-insensitive DTD/ENTITY rejection now covers UTF-8, UTF-8 BOM, UTF-16 LE/BE with BOM, declared encodings (including BOM-less UTF-16 declared in the XML declaration), and a NUL-prolog UTF-16 heuristic — all before `xml.etree.ElementTree` sees the document. | `test_utf16_dtd_and_entity_rejected`, `test_utf16_declared_without_bom_dtd_rejected`, `test_utf8_bom_dtd_rejected`, `test_utf16_project_xml_parses`, `test_utf16_project_xml_declared_without_bom_parses` |
| 3 | Unbounded reads before resource caps: `.uvprojx` was fully read before the 8 MiB check; sources and AXF/MAP were read with unbounded `read_bytes()` after `stat()`, leaving a grow/replace TOCTOU window. | architecture | All reads (XML, sources, scatter, AXF, MAP, digest re-reads) use a bounded `limit + 1` read helper; per-file and aggregate limits are re-enforced on the actual bytes read. The project digest is computed from the already-bounded parse bytes (no second read). | `test_source_grows_between_stat_and_read`, `test_aggregate_limit_reenforced_after_read`, `test_axf_grows_between_stat_and_read`, existing `test_xml_size_cap`, `test_scan_file_limit`, `test_scan_total_limit`, `test_scatter_file_limit`, `test_axf_size_cap`, `test_map_size_cap` |
| 4 | A legal nested-project parent path was rejected: project at `root/MDK-ARM/nested.uvprojx` referencing `..\Common\main.c` (target `root/Common/main.c`) returned `KEIL_PATH_OUTSIDE_PROJECT`. | missing feature | Keil relative paths resolve `.`/`..` against the `.uvprojx` directory first (`base_dir.joinpath(*parts)`), then require the final canonical target inside the root; only a final escape is rejected. | `test_nested_project_parent_relative_paths` (Windows, POSIX, and mixed separators), `test_nested_parent_relative_escape_rejected` |
| 5 | In-root symlink/junction was unconditionally rejected: `_check_redirects` rejected every symlink/reparse point; a real NTFS junction to an in-root directory returned `KEIL_PATH_OUTSIDE_PROJECT`. | missing feature | Redirects are resolved to their canonical target; accepted when the target stays in the canonical root; escapes, cycles, resolution failures, and inspection errors are rejected conservatively. Applies to source, include, scatter, and AXF/MAP paths. | `test_symlink_inside_root_accepted`, `test_in_root_redirects_accepted_source_include_scatter`, `test_artifact_in_root_redirect_accepted`, `test_simulated_reparse_inside_root_accepted`, `test_symlink_escape_rejected`, `test_simulated_reparse_escape_rejected`, `test_artifact_symlink_escape_rejected` |
| 6 | Windows tests depended on administrator rights and POSIX permission semantics: 3 tests called `os.symlink()` directly (WinError 1314 on ordinary Windows) and 2 tests used `chmod(0)` to simulate unreadable files (files stay readable on Windows). | architecture | Redirect tests use a platform-adapted fixture: real `os.symlink` on POSIX, simulated `Path.resolve` mapping on Windows (no admin rights). Unreadable-source/artifact tests inject `PermissionError` at the `Path.open` boundary instead of `chmod(0)`. Linux symlink tests still run (no skip); Windows runs the identical test bodies. | `redirect` fixture in both test files, `raise_on_open` helper, `test_unreadable_source_warning`, `test_artifact_unreadable_permission` |

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

This revision round (predecessor `50d263e` -> code head `352a345`) changes exactly the five allowed implementation/test paths listed in the revision work order; the report is the only additional path. No other path changed; the 0.3 plan checkbox, roadmap, architecture, CLI, MCP, schemas, Skills, model.py, `__init__.py`, and pyproject.toml are untouched by this revision.

## 3. Public contracts delivered

- Types/signatures (all `@dataclass(frozen=True)`): `KeilInspectionError(code, message, details)`; `KeilInputDigest`, `KeilMemoryRegion`, `KeilScopedOptions`, `KeilSource`, `KeilOutputSpec`, `KeilEvidence`, `KeilFinding`, `KeilWarning`, `KeilInspection`, `KeilArtifactEvidence`, `KeilSectionEvidence`, `KeilSymbolEvidence`, `KeilProgramSize`, `KeilBaseline`; every container has a fresh JSON-safe `to_dict()` with repository-relative `/` paths and no host absolute path (project_root omitted from `KeilInspection.to_dict()`).
- Functions: `inspect_keil(root, uvprojx=None, target_name=None)`, `capture_keil_baseline(root, inspection)`.
- Stable errors: all 15 codes of section 6.5 with the exact required details.
- External interfaces: `NONE` (no CLI, MCP, Skill, network, or subprocess).

## 4. Environment-separated verification

OpenClaw environment: Linux x86_64 (Ubuntu 26.04 LTS), CPython 3.10.11 (`/home/openclaw/.local/share/uv/python/cpython-3.10.11-linux-x86_64-gnu`), venv deps `jsonschema==4.23.0`, `mcp==1.27.0`, `pyelftools==0.33`, `pytest==8.3.5`, `pytest-cov==6.0.0`. All commands run from repository root.

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| Focused GREEN (revision): `python -m pytest tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_keil_baseline.py -q` | OpenClaw | Linux; CPython 3.10.11; pytest 8.3.5 | `352a345` | 0 | 112 collected, 0 failed, 0 skipped, 0 xfailed (predecessor round: 95) | PASS |
| Full suite + branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` | OpenClaw | same | `352a345` | 0 | 419 collected (402 passed, 17 skipped, 0 failed); branch coverage 93% (TOTAL 2252 stmts / 628 branches); keil modules: armcc_scan 94%, baseline 91%, model 96%, uvprojx 90%; the 17 skips are pre-existing platform skips (Windows-only plugin/setup tests), identical count on the predecessor head in this environment | PASS |
| Compile: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `352a345` | 0 | silent | PASS |
| Dependency: `python -c "from importlib.metadata import version; assert version('pyelftools') == '0.33'"` | OpenClaw | same | `352a345` | 0 | `pyelftools 0.33`; `stm32-toolkit` Requires-Dist = jsonschema, mcp, pyelftools (only addition) | PASS |
| Diff hygiene: `git diff --check 53321e87..HEAD` and `git diff --check 50d263e..HEAD` | OpenClaw | same | `352a345` | 0 | silent | PASS |
| Diff scope: `git diff --name-status 50d263e..HEAD` | OpenClaw | same | `352a345` | 0 | exactly the five allowed revision paths (uvprojx.py, armcc_scan.py, baseline.py, test_keil_inspect.py, test_keil_baseline.py) | PASS |
| Working tree: `git status --short` | OpenClaw | same | `352a345` | 0 | clean (only report addition after final commit) | PASS |
| Read-only tree: snapshot of bytes/SHA-256/names/mtimes/modes before vs after inspect+capture on a disposable copy | OpenClaw | same | `352a345` | 0 | identical snapshots; disposable data removed afterwards; see manual evidence below | PASS |
| Performance (7.3): inspect/capture medians | OpenClaw | same | `352a345` | 0 | see section 5 performance | PASS |
| Placeholder/cache/credential/binary scan | OpenClaw | same | `352a345` | 0 | no TODO/FIXME/placeholder markers, no credential patterns, no tracked `__pycache__`/`.pyc`/`.coverage`/binary build artifacts | PASS |
| Windows focused/full suite (19 predecessor failures) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | latest head | — | re-run required on the revision head | `DEFERRED_TO_CODEX` |
| Windows real NTFS junction gate (8.1, 8.5.7) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | latest head | — | real junction in-root acceptance and junction-escape rejection must be re-run by Codex | `DEFERRED_TO_CODEX` |

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| 8.5.1 disposable copy + full snapshot | OpenClaw | recursive relative paths, exact bytes/SHA-256, modes, mtimes captured before and after `inspect_keil` + `capture_keil_baseline`; snapshots identical; Git status clean | automated: `test_inspection_read_only_snapshot`, `test_baseline_read_only_snapshot`; manual run in temp script (disposable data removed) |
| 8.5.2 inspect + repeat | OpenClaw | `target=Legacy device=STM32F429ZGTx compiler=armcc V5.06 update 7 (build 750)`; memory IROM1 0x8000000/0x100000, IRAM1 0x20000000/0x30000; 3 sources; 10 findings; 4 digests; framework `None ('spl',)`; equal `to_dict()` across calls | `test_repeated_inspection_equal_serialization` |
| 8.5.3 capture on fixture | OpenClaw | MAP facts: `Program Size: Code=8124 RO-data=720 RW-data=92 ZI-data=16988`, flash 8936, ram 17080; AXF honestly unavailable; snapshot unchanged | `test_committed_fixture_map_only_baseline` |
| 8.5.4 disposable ELF at AXF candidate | OpenClaw | entry 0x08000000, sections `[.text]`, SHA-256 exact; disposable data removed afterwards; snapshot unchanged | `test_elf_exact_parse` |
| 8.5.5 multiple targets/projects | OpenClaw | selection errors carry sorted relative names; no writes | `test_multiple_projects_require_selection`, `test_multiple_targets_require_selection` |
| 8.5.6 symlink to sibling outside root | OpenClaw | `KEIL_PATH_OUTSIDE_PROJECT`; no external content in details | `test_symlink_escape_rejected`, `test_artifact_symlink_escape_rejected` |
| 8.5.6b in-root symlink redirect | OpenClaw | accepted; public path is the canonical target inside the root (`Src/a.c`); applies to source/include/scatter and baseline AXF/MAP | `test_symlink_inside_root_accepted`, `test_in_root_redirects_accepted_source_include_scatter`, `test_artifact_in_root_redirect_accepted` |
| 8.5.7 real NTFS junction | Codex | same stable behavior (in-root accepted, escape rejected), no skip | `DEFERRED_TO_CODEX` |
| 8.5.8 injected `PermissionError` | OpenClaw | conservative stable error; no exception text/absolute path in details | `test_permission_error_during_inspection_rejected`, `test_generic_oserror_during_inspection_rejected`, `test_unreadable_source_warning`, `test_artifact_unreadable_permission` |
| Visual/UI (7.4) | N/A | `NOT_APPLICABLE` — no UI/visual asset/rendered output created | N/A |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| Keil inspection package | `tools/stm32-toolkit/src/stm32_toolkit/keil/` | 5 modules (model 215 lines, uvprojx ~1,100, armcc_scan ~360, baseline ~310, `__init__` 41) |
| Keil fixture project | `tools/stm32-toolkit/tests/fixtures/keil-project/` | legacy.uvprojx 3,125 B; common.c 570 B; main.c 90 B; startup_stm32f4xx.s 134 B; legacy.map 1,778 B |
| Focused tests | `test_keil_inspect.py`, `test_keil_baseline.py` | 112 tests collected |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security checks (all automated, all pass):
  - DTD/entity declaration rejected before XML parse in every XML-legal encoding (`KEIL_XML_UNSAFE`, rule `doctypeOrEntity`); no external resource fetch; XML capped at 8 MiB with a bounded read.
  - Path rejection on every host: POSIX absolute, drive absolute, drive relative, UNC, mixed separators, escaping `..` (final canonical target outside root), NUL, escaping symlink/reparse/junction, resolution failure, `PermissionError`, generic `OSError` (`KEIL_PATH_OUTSIDE_PROJECT` with stable fields only). In-root redirects whose canonical target stays inside the root are accepted (work-order section 6.2).
  - Only confirmed `FileNotFoundError`/`NotADirectoryError` treated as missing; permission/inspection failures reject conservatively.
  - All reads are bounded to `limit + 1` bytes (XML 8 MiB, per-source 8 MiB, aggregate scan 64 MiB, AXF 256 MiB, MAP 32 MiB, scatter 8 MiB); per-file and cumulative caps are re-enforced on the bytes actually read, closing the stat/read grow-or-replace TOCTOU window. The project digest is computed from the bounded parse bytes without a second read.
  - No source-tree recursion: only files referenced by the selected target plus the two artifact candidates are read; no `.git`, credentials, environment, or unrelated files.
  - Baseline revalidates containment and redirect behavior before every artifact read; root must canonicalize to `inspection.project_root`.
- Privacy/redaction: errors, warnings, findings, and `to_dict()` contain no host exception text, stack trace, absolute path, temporary-directory path, or source content beyond the 200-code-point evidence cap; verified by `assert_no_absolute` helpers in both test files and the manual `PermissionError` run.
- Performance (7.3, measured with `time.perf_counter`, warm-up 3, runs 20):
  - `inspect_keil`: 1,004,878-byte `.uvprojx` with exactly 1,000 file nodes and 100 referenced UTF-8 sources of 1,024 bytes → **median 245.58 ms** (min 244.22, max 254.68) — budget <500 ms PASS.
  - `capture_keil_baseline`: 2,097,152-byte valid ELF + 2,097,163-byte MAP → **median 20.81 ms** (min 20.53, max 24.35) — budget <500 ms PASS.
  - Memory is O(XML + referenced inputs + artifact size within caps); no unrelated data loaded. No timing-fragile assertions added.
- Accessibility/input: no UI; stable English messages and structured fields for later CLI/MCP adapters.
- Compatibility: Windows 10/11 and Linux path forms (public paths always serialize with `/`; Windows-specific behavior covered by the platform-adapted fixture and resolve simulations on Linux; real NTFS junction gate deferred to Codex); CPython 3.10+; namespace-qualified and unqualified Keil MDK 5 XML including UTF-16 LE/BE documents; ARM Compiler 5 inspection; ArmClang identified (`armclang`) without conversion claims.

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  - Real Windows NTFS junction behavior and the Windows full-suite re-run are verified only by the Codex Windows host; the gates are `DEFERRED_TO_CODEX` (Windows NT 10.0.26200.0, CPython 3.12.13). On Linux these paths are exercised with real symlinks; on Windows the identical test bodies run through the `Path.resolve` simulation fixture without administrator rights.
  - Keil project-file completeness is bounded to the section-6 field set; a future real-project/board acceptance gate (0.3 plan Task 2 follow-ups) remains out of scope for this module.
  - A file that grows or is replaced between two sequential reads (e.g., between scan and digest) is handled conservatively: the bounded re-read either sees a file within the caps (digest over exact current bytes) or raises the stable limit error; an adversarial swap between reads remains an inherent TOCTOU residual for any two-phase read design, bounded by the `limit + 1` reads and stable errors.
- Follow-up recommendation: `NONE` (migration/plan/generation layers are separate work orders).

## 7. Author checklist

- [x] Accepted base, reviewed predecessor, and revised code head are full SHAs (`53321e8721cc479122c43285537dc108461a8e0e`, `50d263e378469ff0d6480eef8917a68c5c88d3e3`, `352a345f1ad6356603ae5fbdff74f93f89b335e9`).
- [x] Final head will be returned out of band after this report commit (PR metadata + return message).
- [x] This revision changes exactly the five allowed implementation/test paths plus this report (`git diff --name-status 50d263e..HEAD`).
- [x] Every required OpenClaw gate has direct observed evidence on the revision code head (focused/full/coverage/compile/dependency/diff/read-only/performance/scans, all exit codes above).
- [x] Codex Windows observations (19 predecessor failures) are recorded as Codex review observations; OpenClaw does not claim Windows evidence. Windows gates remain `DEFERRED_TO_CODEX`.
- [x] The previous "unconditionally reject in-root redirects" deviation statement is removed; in-root redirect acceptance matches work-order section 6.2.
- [x] No credentials, private data, caches, build output, binary fixtures, temp projects, or unredacted diagnostics are committed (ELF baselines are generated in tests, never committed).
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed.
- [x] Every instructional value in this report is replaced with actual evidence; no self-referential final SHA and no moving commit totals.
