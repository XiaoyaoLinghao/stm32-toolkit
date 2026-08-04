# STM32TK-0301-SCHEMA-V2 r001 Implementation Report

Status: `IMPLEMENTED`
Branch: `openclaw/STM32TK-0301-SCHEMA-V2/r001`
Accepted base commit: `2a3114290ab8d4f4f6933b88c036d9f02b48e826`
Code head before report commit: `42372d3f5e42afe47a7329ee0feea22ec201fc49`
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: `https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/1`
Work order: `docs/openclaw/modules/STM32TK-0301-SCHEMA-V2.md` (specification commit `e505483e8672cedbff013e28bb34072235e59be0`, section 0 third-round `r001` revision authority)

## 1. Outcome

- Observable result: this is the third `r001` revision of the existing Draft PR (same branch, same PR, same accepted base `2a3114290ab8d4f4f6933b88c036d9f02b48e826`). Every consolidated correction from the second `REVISION_REQUIRED` review (against `ec292ba6819a1aa2b0c3f2ab38dfb55379d6f3da`) is implemented, with RED-to-GREEN regressions for each case and fresh performance evidence from the new code head. The complete 0.2 test suite exits 0 on the mandated CPython 3.10.11 with branch coverage 94% (>= 90%).
- Scope completed (third-round revision):
  1. `project.py` — default compatibility dispatch now requires a manifest object before any version dispatch: a list returns `PROJECT_SCHEMA_INVALID` with `{"field": "$", "rule": "type"}` and a scalar such as JSON `"schemaVersion"` never leaks `TypeError`. An otherwise valid v1-shaped unsupported integer version (for example 99) returns `PROJECT_SCHEMA_VERSION_UNSUPPORTED` with `{"schemaVersion": value, "supported": [1, 2]}`; when another v1 schema defect sorts before the version error, the older deterministic first error is preserved (`invalid-project.json` keeps missing `logicalProjectId`/`required`, so `test_project.py` and `test_context.py` stay green).
  2. `project_model.py` — host-independent path rejection: Windows drive-qualified relative forms such as `D:outside.c` are rejected on every host (`_WINDOWS_ABSOLUTE_RE` covers drive-relative and drive-absolute forms); `..` traversal is detected under both `/` and `\` separator conventions via `PureWindowsPath`, so `..\outside.c` is rejected on Linux; `os.lstat` failures distinguish confirmed missing (`FileNotFoundError`) and non-directory (`NotADirectoryError`) components from every other inspection failure — `PermissionError` and other `OSError`s are rejected conservatively as `PROJECT_SCHEMA_INVALID`/`pathWithinProjectRoot` in both public loaders, never treated as safe or absent.
  3. `project_upgrade.py` — plan versions must be built-in integers exactly 1 and 2 (`type(...) is int`): `True`, `1.0`, `2.0`, strings, and int subclasses return `PROJECT_UPGRADE_PLAN_INVALID` with `{"fromVersion", "toVersion"}` without writing; a non-`Path` `manifest_path` returns `PROJECT_UPGRADE_PLAN_INVALID` with `{"field": "manifestPath", "rule": "canonicalProjectManifest"}` without leaking `AttributeError`.
  4. Tests — RED-to-GREEN regressions added for every case above (37 RED failures before the correction, all green after): list/scalar manifest dispatch, v1-shaped unsupported integer version, `invalid-project.json` precedence, drive-relative and backslash-traversal rejection in both loaders, injected `PermissionError`/generic `OSError` from component inspection in both loaders, boolean/float/string plan versions, and string `manifest_path`. `test_mcp_roots.py` untouched; no new skip/xfail.
  5. Performance — rerun on the new code head with a manifest of 159,175 bytes and exactly 1,000 source strings: `load_project_model` median 49.01 ms and `plan_project_upgrade` median 62.63 ms over 20 warm runs, both below the 100 ms budget.
  6. Report — truthful reconciliation: actual Draft PR URL, environment-separated evidence with the actual worker OS declared (no platform assumption repeated), Codex Windows evidence preserved as Codex evidence only, current-round Windows gate `DEFERRED_TO_CODEX`, and a `Deviations` field of `NONE` with no contradictory notes.
- Known limitations: `NONE` (real NTFS junction verification remains with Codex's named Windows gate by design; no OpenClaw gate is omitted).
- Deviations: `NONE`.

## 2. Complete changed-path inventory

Reconciled with `git diff 2a3114290ab8d4f4f6933b88c036d9f02b48e826..42372d3f5e42afe47a7329ee0feea22ec201fc49 --name-status`: exactly the ten product/test paths in work-order section 5, plus this report as the report-only addition after the code head.

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| A | `schemas/stm32-project-v1.schema.json` | 5 | frozen root Schema v1 snapshot (base schema JSON-equivalent except title/`$id` identifying `stm32-project-v1.schema.json`) |
| M | `schemas/stm32-project.schema.json` | 5 | canonical root Schema v2 per section 6.2 |
| M | `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` | 5 | bounded CPython 3.10 client-roots cancellation compatibility; preserves timeout and caller-cancellation semantics; public `asyncio` APIs only |
| M | `tools/stm32-toolkit/src/stm32_toolkit/project.py` | 5 | compatibility view: `ProjectManifest`/`ProjectManifestError` imports preserved, manifest-object-first default dispatch, unsupported-integer and precedence handling, complete post-schema path validation in both modes |
| A | `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` | 5 | frozen model types, schema dispatch, host-independent path validation (drive-relative, dual-convention traversal, conservative lstat failures, junction/reparse-point detection, NUL rejection), stable model errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py` | 5 | immutable upgrade plan, deterministic mapping, atomic digest-guarded apply with strict built-in-integer plan versions and forged-plan rejection |
| A | `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project-v1.schema.json` | 5 | packaged Schema v1; JSON-equivalent to root v1 |
| M | `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json` | 5 | packaged Schema v2; JSON-equivalent to root v2 |
| A | `tools/stm32-toolkit/tests/test_project_model.py` | 5 | model/schema/path/compatibility tests incl. third-round RED-to-GREEN regressions |
| A | `tools/stm32-toolkit/tests/test_project_upgrade.py` | 5 | read-only plan, mappings, digest, atomicity, forged-plan rejection, strict version/path regressions, cleanup, platform-correct assertions |
| A | `docs/openclaw/returns/STM32TK-0301-SCHEMA-V2/r001-implementation-report.md` | 9 | this report (report-only addition) |

No other path changed. `git diff --check 2a3114290ab8d4f4f6933b88c036d9f02b48e826..HEAD` exits 0 (no whitespace errors). `git status --short` is empty before the report commit.

## 3. Public contracts delivered

- Types/signatures (all `@dataclass(frozen=True)`, tuples not lists):
  - `ProjectInfo(name, origin)`, `TargetSpec(device, core, fpu, float_abi, device_pack)`, `FrameworkSpec(type, version)`, `BuildSpec(sources, include_paths, defines, compile_options, assembly_sources, presets, elf)`, `MemoryRegion(name, origin, length, attributes)`, `MemorySpec(source, regions)`, `DebugSpec(backend, target, svd)`, `GenerationSpec(tool, version, cube_mx_ioc, managed_manifest, generated_directories, user_directories)`, `ProjectModel(project_root, schema_version, logical_project_id, project, target, framework, build, memory, debug, generation)`
  - `load_project_model(project_root: Path) -> ProjectModel`
  - `UpgradePlan(manifest_path, source_sha256, from_version, to_version, proposed)` — `proposed` recursively immutable (`MappingProxyType` + tuples)
  - `ProjectUpgradeError(code, message, details)` with `__init__(code, message, details)`
  - `plan_project_upgrade(project_root: Path) -> UpgradePlan`
  - `apply_project_upgrade(plan: UpgradePlan) -> OperationResult[Mapping[str, object]]`
  - `ProjectManifest`, `ProjectManifest.load(project_root, schema_path=None)`, `ProjectManifestError` remain importable from `stm32_toolkit.project` with all existing fields and resolved-path behavior; both loader modes require a manifest object first; default dispatch returns `PROJECT_SCHEMA_VERSION_UNSUPPORTED` for otherwise valid v1-shaped unsupported integers and preserves the older deterministic first error when another v1 defect sorts first.
- Commands/events/configuration/schemas: `schemas/stm32-project-v1.schema.json` (Schema v1, JSON-equivalent to the base commit's schema except title/`$id`), `schemas/stm32-project.schema.json` (Schema v2, top-level required keys exactly `["schemaVersion","logicalProjectId","generatedBy","project","target","framework","build","memory","debug","generation"]`, `schemaVersion` const 2, closed objects everywhere, uniqueness on `build.presets`/`generatedDirectories`/`userDirectories`, region `origin >= 0`/`length >= 1`, `memory.source` enum `keil|cubemx|manual`). Root and packaged copies are JSON-equivalent (verified by tests).
- External interfaces: `NONE` added; no existing protocol version changes; the `mcp_server.py` correction changes no MCP interface or protocol output.

## 4. Environment-separated verification

Environment (all OpenClaw gates): Linux worker, actual OS declared: Ubuntu 26.04 LTS (kernel `7.0.0-22-generic`, x86_64); CPython 3.10.11 (uv-managed, `python3.10 -m venv` at `/home/openclaw/coding/venvs/stm32-toolkit-py310`, outside the repository); jsonschema 4.23.0, mcp 1.27.0, pytest 8.3.5, pytest-cov 6.0.0; package installed `pip install -e "tools/stm32-toolkit[test]"` (stm32-toolkit 0.2.0). All OpenClaw commands run from the repository root on branch `openclaw/STM32TK-0301-SCHEMA-V2/r001`.

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---:|---|---:|---|---|
| TDD RED (preserved from original r001, section 8.4): `python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q` before implementation | OpenClaw | Linux; CPython 3.10.11; exact deps | working tree at base (tests added, modules absent) | 2 | Collection interrupted: 2 errors. `ModuleNotFoundError: No module named 'stm32_toolkit.project_model'` / `'stm32_toolkit.project_upgrade'` (recorded in the previous r001 report, unchanged) | PASS |
| Third-round regression RED (section 8.4): focused command at reviewed head `ec292ba` with the new regressions added | OpenClaw | same | `ec292ba6819a1aa2b0c3f2ab38dfb55379d6f3da` + working-tree tests | 1 | `37 failed, 130 passed in 2.21s` — every third-round case reproduced RED: list manifest wrong required-field error; scalar `"schemaVersion"` leaked `TypeError: string indices must be integers`; v1-shaped version 99 returned `PROJECT_SCHEMA_INVALID`/`const`; `D:outside.c` and `..\outside.c` accepted by both loaders; injected `PermissionError`/`OSError` from `os.lstat` treated as safe; plan versions `True`/`1.0`/`2.0` passed equality and wrote; string `manifest_path` leaked `AttributeError` | PASS (regressions reproduced) |
| Focused GREEN: `python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q` | OpenClaw | same | `42372d3` | 0 | `167 passed in 1.27s`; zero failures; no new skip/xfail | PASS |
| CPython 3.10 cancellation regression: `python -m pytest tools/stm32-toolkit/tests/test_mcp_roots.py::test_client_roots_timeout_cancels_request_and_returns_stable_error tools/stm32-toolkit/tests/test_mcp_roots.py::test_inner_roots_cancellation_returns_stable_unavailable tools/stm32-toolkit/tests/test_mcp_roots.py::test_external_tool_cancellation_is_not_swallowed -q` | OpenClaw | same | `42372d3` | 0 | `3 passed`; all three pass (no `Task.cancelling()` usage) | PASS |
| Full Python suite and branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing` | OpenClaw | same | `42372d3` | 0 | `290 passed, 17 skipped in 2.74s`; zero failures/errors; branch coverage **94%** (fail_under 90 satisfied); the 17 skips are the pre-existing Windows cmd.exe/PowerShell platform skips in `test_plugin_layout.py`/`test_setup_runtime.py` | PASS |
| Syntax compilation: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `42372d3` | 0 | silent, no output | PASS |
| Diff scope and whitespace: `git diff --check 2a3114290ab8d4f4f6933b88c036d9f02b48e826..HEAD` and `git diff --name-status 2a3114290ab8d4f4f6933b88c036d9f02b48e826..HEAD` | OpenClaw | same | `42372d3` | 0 | silent; changed paths are exactly the ten implementation paths in section 5 (plus this report) | PASS |
| Manual upgrade and digest guard (section 8.6 steps 1-5) | OpenClaw | same | `42372d3` | 0 | all steps passed; SHA-256 evidence in section 5 | PASS |
| Performance (section 7.4) | OpenClaw | same | `42372d3` | 0 | 159,175-byte manifest, exactly 1,000 source strings; medians below 100 ms; evidence in section 5 | PASS |
| Windows compatibility review (focused + full pytest on returned code head, incl. real NTFS junction per section 8.6 step 6) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | returned head | — | not run by OpenClaw; current-round Windows gates remain with Codex's named review gate | DEFERRED_TO_CODEX |
| Visual/UI | N/A | N/A | — | — | `NOT_APPLICABLE` under section 7.5; no UI or visual asset created; no screenshot presented | PASS |

Codex evidence from the first review (recorded as Codex observations only, never attributed to OpenClaw; preserved per section 8.4): on Windows CPython 3.12.13 (NT 10.0.26200.0) Codex ran the focused suite (`128 passed`), the full suite (`251 passed, 3 skipped`, branch coverage 94%), and a real NTFS junction gate (`18/18`) against the then-returned head, and observed the second-round RED cases listed in section 8.4 against `ec292ba6819a1aa2b0c3f2ab38dfb55379d6f3da` (list/scalar dispatch errors, v1-shaped version 99 returning `PROJECT_SCHEMA_INVALID`/`const`, injected `PermissionError` treated as safe, `D:outside.c` accepted with the compatibility view returning `WindowsPath('D:outside.c')`, plan versions `True`/`1.0`/`2.0` passing equality checks and writing, and a string `manifest_path` leaking `AttributeError`). Every one of those RED cases is fixed and covered by the new Linux regressions in this round; the current code head `42372d3` still requires Codex's fresh Windows review.

Branch-coverage table (full-suite run with `--cov-branch --cov-report=term-missing` against `42372d3`):

| Module | Cover |
|---|---:|
| `stm32_toolkit/__init__.py` | 100% |
| `stm32_toolkit/cli.py` | 97% |
| `stm32_toolkit/context.py` | 91% |
| `stm32_toolkit/detection.py` | 100% |
| `stm32_toolkit/doctor.py` | 92% |
| `stm32_toolkit/identity.py` | 100% |
| `stm32_toolkit/mcp_server.py` | 92% |
| `stm32_toolkit/paths.py` | 98% |
| `stm32_toolkit/project.py` | 100% |
| `stm32_toolkit/project_model.py` | 94% |
| `stm32_toolkit/project_upgrade.py` | 93% |
| `stm32_toolkit/result.py` | 100% |
| TOTAL | **94%** |

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| §8.6 step 1: seed v1 fixture, record SHA-256/tree inventory | OpenClaw | source `sha256` = `674fb46168e6915bea319a7ff9c1d1161521f478407e548c43a31ac6aec656de`; inventory `.stm32-project.json`, `App`, `App/main.c`, `build-fw`, `build-fw/firmware.elf` | disposable `/tmp` project; recorded in section 5 |
| §8.6 step 2: plan read-only + exact proposed mapping | OpenClaw | bytes, mtimes, and recursive tree inventory identical before/after plan; `plan.source_sha256` matches; `memory.source=manual`, `memory.regions=[]`, `generation` defaults, `generatedBy` `{"tool": "stm32-toolkit", "version": "0.2.0"}` | PASS |
| §8.6 step 3: apply, reload both loaders, digests | OpenClaw | only manifest changed (tree inventory otherwise identical); one trailing LF; no BOM; `ProjectManifest.load` and `load_project_model` both reload as v2; `resultSha256` `fc5e214455bbc1f7b3b9a1d27bd5822a278c6b61242648784ac82dacc6b89490` equals the written file's digest; plan on the upgraded v2 returns `PROJECT_UPGRADE_NOT_REQUIRED` `{"schemaVersion": 2}` | PASS |
| §8.6 step 4: digest guard | OpenClaw | one byte changed between plan/apply → `PROJECT_CHANGED_SINCE_PLAN` with expected `674fb46168e6915bea319a7ff9c1d1161521f478407e548c43a31ac6aec656de` and observed `3c2037f000d9891f266a4da4f565c81917b19ee024ef71698022ff80faf124ca`; manifest untouched; no temp sibling | PASS |
| §8.6 step 5: forged plan on digest-matching non-manifest file | OpenClaw | `PROJECT_UPGRADE_PLAN_INVALID`, details `{"field": "manifestPath", "rule": "canonicalProjectManifest"}`; target file byte-for-byte preserved | PASS |
| §8.6 step 6: real NTFS junction (Windows gate) | Codex | not run by OpenClaw; Linux simulation test `test_reparse_point_junction_parent_cannot_escape_project_root` passes | DEFERRED_TO_CODEX |
| Visual acceptance (§7.5) | N/A | `NOT_APPLICABLE` | N/A |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| Schema v1 (root) | `schemas/stm32-project-v1.schema.json` | 2703 bytes |
| Schema v2 (root) | `schemas/stm32-project.schema.json` | 4675 bytes |
| Packaged v1/v2 | `tools/stm32-toolkit/src/stm32_toolkit/schemas/` | JSON-equivalent to root copies (asserted by tests) |
| Implementation report | `docs/openclaw/returns/STM32TK-0301-SCHEMA-V2/r001-implementation-report.md` | this file |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security checks:
  - Path containment: POSIX absolute, Windows drive-absolute (`C:\x`, `C:/x`), Windows drive-qualified relative (`D:outside.c`), UNC (`\\server\share`), and rooted backslash forms are rejected on every host before host-native parsing; `..` traversal is rejected under both `/` and `\` separator conventions (`..\outside.c` rejected on Linux via `PureWindowsPath`), so a manifest accepted on Linux cannot escape after relocation to Windows; existing file/directory symlink and Windows NTFS junction/reparse-point parent escapes are rejected (`st_file_attributes & 0x400` in addition to `stat.S_ISLNK`). Embedded-NUL and other inspection-raising path values produce the same stable error and never leak a raw host exception (both public loaders, both schema modes).
  - Conservative inspection failures: only confirmed missing (`FileNotFoundError`) and non-directory (`NotADirectoryError`) components use the lexical nonexistent-path fast path; `PermissionError` and every other `os.lstat` failure reject as `PROJECT_SCHEMA_INVALID`/`pathWithinProjectRoot` in both public loaders and never treat an uninspectable component as safe or absent.
  - Duplicate memory-region names → `PROJECT_SCHEMA_INVALID`, `{"field": "memory.regions", "rule": "uniqueRegionName"}`.
  - Forged-plan protection: `apply_project_upgrade` verifies, in order: plan versions are built-in integers exactly 1 and 2 (`True`, `1.0`, `2.0`, strings, and int subclasses are invalid); the target path is a `Path` and the canonical absolute `.stm32-project.json` (a public `UpgradePlan` constructor is not a write capability; a non-`Path` target never touches `Path` attributes, so no `AttributeError` leaks); the digest-matching current bytes form a valid Schema v1 manifest; the proposed payload is valid Schema v2; and the proposed payload is exactly the deterministic v1→v2 mapping of the digest-matching bytes. Any failure returns `PROJECT_UPGRADE_PLAN_INVALID` with the exact `field`/`rule` from section 6.3 and writes nothing.
  - Apply atomicity: temp file created with `O_CREAT|O_EXCL` and mode `0o600` in the manifest directory; content flushed and `fsync`ed; `os.replace` is the only manifest mutation; digest recheck and full revalidation happen before any write; temp removed on success and every handled failure. Directory `fsync` attempted on POSIX and best-effort where the platform does not support opening directories.
  - Digest guard: `PROJECT_CHANGED_SINCE_PLAN` on missing/changed bytes with `expectedSha256`/`observedSha256` (or `null`); `PROJECT_UPGRADE_IO_ERROR` with `stage` in `write|flush|replace|cleanup`.
  - Serialization: UTF-8 without BOM, two-space indent, `ensure_ascii=False`, exactly one trailing LF (asserted in tests and manual run).
- Privacy/redaction checks: failure messages and details contain only stable English text plus the canonical manifest path and stage/digest values; injected exception text never appears in `OperationResult` output; no traceback, source content, random temp name, or unrelated environment path enters any result. The leakage test asserts structured `to_dict()`/`details` fields directly (Windows path-escape safe).
- Performance measurements (method: `time.perf_counter`, 3 warm-up runs then 20 timed runs, median taken; same venv/CPython 3.10.11, code head `42372d3`): manifest byte size **159,175** (>= 102,400 required) with exactly **1,000** source strings; `load_project_model` median **49.01 ms** (min 48.22, max 51.40) and `plan_project_upgrade` median **62.63 ms** (min 61.56, max 64.45) — both below the 100 ms budget. No timing-fragile CI assertion added, per section 7.4. Processing is O(manifest size); no project-tree scan. The resolve-free lexical containment fast path with a per-document lstat cache and one-time cached `Draft202012Validator` instances per packaged schema are part of the delivered code (explicit caller-supplied schemas are still checked on every call).
- Accessibility/input checks: `NOT_APPLICABLE` for UI; deterministic English errors with structured `details` for AI/CLI adapters.
- Compatibility checks: drive-relative/backslash-traversal forms rejected host-independently on this POSIX host; junction detection implemented for Windows via `st_file_attributes` and verified on Linux with a clearly-labeled simulation; the real NTFS junction gate is Codex's. Python 3.10+ declared compatibility verified on CPython 3.10.11 (the full 0.2 suite, including the three `test_mcp_roots.py` cancellation tests, exits 0); Windows CPython 3.12.13 verification is deferred to Codex. Existing v1 `ProjectManifest` callers/tests remain source-compatible (all pre-existing `test_project.py` and `context.py` behaviors green, including the pinned `invalid-project.json` `logicalProjectId`/`required` precedence). No new runtime dependencies; allowed dependency direction respected.

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  1. Directory `fsync` after `os.replace` is attempted on POSIX and skipped best-effort on filesystems that reject opening/fsyncing directories (contract lists only `write|flush|replace|cleanup` stages; a post-replace directory-fsync failure is deliberately not mapped to an error stage to avoid reporting failure after a completed atomic replace). On this Linux worker it succeeds on standard filesystems.
  2. Junction behavior is verified on Linux via a labeled reparse-point simulation; the real NTFS junction gate (section 8.6 step 6, section 8.1 Windows row) remains with Codex on Windows CPython 3.12.13 and must not be satisfied by a skipped test.
  3. Rejecting every literal `..` component under either separator convention (including in-root forms such as `App/../main.c`) is a conservative superset of the escape-avoidance requirement; no existing test or caller relies on accepting such forms (full suite green).
- Follow-up recommendation: `NONE`.

## 7. Author checklist

- [x] Accepted base and code head are full SHAs (`2a3114290ab8d4f4f6933b88c036d9f02b48e826`, `42372d3f5e42afe47a7329ee0feea22ec201fc49`).
- [x] Final head will be returned out of band after this report commit.
- [x] Inventory matches the complete implementation diff and report addition (ten product/test paths + report path).
- [x] Every required OpenClaw gate has direct observed evidence (original RED, third-round regression RED 37 failed/130 passed, focused GREEN 167 passed, cancellation 3 passed, full suite 290 passed/17 skipped, coverage 94% table, compileall, diff checks, manual SHA-256 evidence, fresh performance medians).
- [x] Other-environment gates are accurately attributed or deferred (Codex first-review Windows evidence recorded as Codex evidence only; current-round Windows gate `DEFERRED_TO_CODEX`; visual gate `NOT_APPLICABLE`).
- [x] No credentials, private data, caches, build output, or unredacted diagnostics are committed (venv kept outside the repository; `.coverage`/`__pycache__`/`.pytest_cache`/`*.egg-info` ignored; no fixture or temp project committed).
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed (diff scope verified; `AGENTS.md`/`OPENCLAW_START_HERE.md`/work order untouched; `test_mcp_roots.py` untouched).
- [x] Every instructional value in this report is replaced with actual evidence.
- [x] Overall status `IMPLEMENTED`: complete 0.2 suite exits 0 on CPython 3.10.11 (290 passed, 17 skipped), branch coverage 94%, all third-round consolidated corrections delivered with RED-to-GREEN regressions, Windows gates `DEFERRED_TO_CODEX`.
