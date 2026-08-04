# STM32TK-0301-SCHEMA-V2 r001 Implementation Report

Status: `IMPLEMENTED`
Branch: `openclaw/STM32TK-0301-SCHEMA-V2/r001`
Accepted base commit: `2a3114290ab8d4f4f6933b88c036d9f02b48e826`
Code head before report commit: `22cf3339149b7af8b39e777ab666c8e0ea7b431a`
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: `https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/1`
Work order: `docs/openclaw/modules/STM32TK-0301-SCHEMA-V2.md` (specification commit `d11c1d04c29bbe9d2852879bf7fd1380d810c892`, section 0 `r001` revision authority)

## 1. Outcome

- Observable result: this is the `r001` revision of the existing Draft PR (same branch, same PR, same accepted base). All consolidated corrections in work-order section 0 are implemented and verified: CPython 3.10 cancellation compatibility, Windows junction containment, complete compatibility-loader validation and version dispatch, tampered-plan write prevention, platform-correct result assertions, and a truthful final report. The complete 0.2 test suite now exits 0 on the mandated CPython 3.10.11 with branch coverage 94% (>= 90%).
- Scope completed (revision):
  1. `mcp_server.py` — replaced the Python 3.11+-only `Task.cancelling()` check in `_client_roots_failure` with a public-API `asyncio` restructure (`ensure_future` + `wait` with timeout): an inner client-roots cancellation returns the stable `MCP_ROOTS_UNAVAILABLE` result, cancellation of the outer tool task propagates `CancelledError`, and a timeout cancels/awaits the in-flight request before returning the stable result. No private task attributes, no version checks, no protocol output change. The three `test_mcp_roots.py` cancellation tests now pass on CPython 3.10.11 (previously two failed with `AttributeError: '_asyncio.Task' object has no attribute 'cancelling'`).
  2. `project_model.py` — junction/reparse-point containment: existing Windows NTFS junction/reparse-point parents are detected through `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT (0x400)` in addition to `stat.S_ISLNK`, forcing the full resolved containment check; embedded-NUL and other inspection-raising path values produce the stable `PROJECT_SCHEMA_INVALID`/`pathWithinProjectRoot` error instead of leaking a raw host exception, in both public loaders.
  3. `project.py` — `ProjectManifest.load` now runs complete post-schema path validation (`validate_model_document`) in both default and explicit-schema modes, so escaping `generation.managedManifest` and every other listed path field is rejected in both modes; default dispatch keeps the pre-existing stable v1-schema error contract for unsupported integer versions while rejecting non-integer (boolean/float/string) `schemaVersion` values with the stable type error; explicit-schema mode enforces integer `schemaVersion` exactly 1 or 2 with the model loader's stable errors.
  4. `project_upgrade.py` — `apply_project_upgrade` rejects a forged public `UpgradePlan` before any write: the target must be the canonical absolute `.stm32-project.json` (`PROJECT_UPGRADE_PLAN_INVALID`, `manifestPath`/`canonicalProjectManifest`), the digest-matching current bytes must be a valid Schema v1 manifest (`source`/`validSchemaVersion1`), the proposed payload must be valid v2, and it must be exactly the deterministic v1-to-v2 mapping of the digest-matching bytes (`proposed`/`deterministicUpgrade`).
  5. `test_project_upgrade.py` — the assertion in `test_apply_result_never_leaks_exception_or_environment_details` now inspects structured `OperationResult.to_dict()`/`details` fields directly instead of comparing an unescaped path with `str(dict)` (the Windows CPython 3.12.13 failure observed by Codex); forged-plan regression tests added (arbitrary digest-matching file, non-v1 digest-matching source, non-object source, valid-v2 nondeterministic proposal).
  6. `test_project_model.py` — added junction (simulated reparse point, clearly labeled; the Codex Windows gate exercises a real NTFS junction), embedded-NUL, explicit-schema complete path validation, default escaping-generation-path, and unsupported/boolean version behavior tests.
  7. Report — truthful reconciliation: actual Draft PR URL, no "no remote branch/PR exists" statement, no unsubstantiated Ubuntu 22.04 dispatch assumption (actual worker OS declared in section 4), Windows gate explicitly `DEFERRED_TO_CODEX`.
- Known limitations: `NONE` (the two pre-existing CPython 3.10 full-suite failures that blocked r001 are fixed in this revision and the full suite now exits 0; Windows junction verification remains with Codex's named gate by design).
- Deviations: `NONE` — two documented, non-silent reconciliation notes: (a) the default compatibility loader keeps the pre-existing stable v1-schema error contract for unsupported integer versions (pinned by `tests/test_project.py::test_invalid_project_returns_schema_error` and `tests/test_context.py`), while the model loader and explicit-schema mode raise `PROJECT_SCHEMA_VERSION_UNSUPPORTED` per work-order section 7.2; (b) the worker OS is Ubuntu 26.04 LTS, not the Ubuntu 22.04 assumed by the dispatch — declared truthfully in section 4; runtime CPython 3.10.11 and the exact pinned dependencies match the work order.

## 2. Complete changed-path inventory

Reconciled with `git diff 2a3114290ab8d4f4f6933b88c036d9f02b48e826..22cf3339149b7af8b39e777ab666c8e0ea7b431a --name-status`: exactly the ten product/test paths in work-order section 5, plus this report as the report-only addition after the code head.

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| A | `schemas/stm32-project-v1.schema.json` | 5 | frozen root Schema v1 snapshot (base schema JSON-equivalent except title/`$id` identifying `stm32-project-v1.schema.json`) |
| M | `schemas/stm32-project.schema.json` | 5 | canonical root Schema v2 per section 6.2 |
| M | `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` | 5 | bounded CPython 3.10 client-roots cancellation compatibility; preserves timeout and caller-cancellation semantics; public `asyncio` APIs only |
| M | `tools/stm32-toolkit/src/stm32_toolkit/project.py` | 5 | compatibility view: preserves `ProjectManifest`/`ProjectManifestError` imports, v1/v2 dispatch, complete post-schema path validation in both modes, resolved-path behavior, stable errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` | 5 | frozen model types, schema dispatch, canonical path validation incl. junction/reparse-point detection and NUL rejection, stable model errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py` | 5 | immutable upgrade plan, deterministic mapping, atomic digest-guarded apply with canonical-path/valid-v1/deterministic-proposal rejection of forged plans |
| A | `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project-v1.schema.json` | 5 | packaged Schema v1; JSON-equivalent to root v1 |
| M | `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json` | 5 | packaged Schema v2; JSON-equivalent to root v2 |
| A | `tools/stm32-toolkit/tests/test_project_model.py` | 5 | model/schema/path/compatibility tests incl. junction simulation, embedded NUL, explicit-schema validation, version behavior |
| A | `tools/stm32-toolkit/tests/test_project_upgrade.py` | 5 | read-only plan, mappings, digest, atomicity, forged-plan rejection, errors, cleanup, platform-correct assertions |
| A | `docs/openclaw/returns/STM32TK-0301-SCHEMA-V2/r001-implementation-report.md` | 9 | this report (report-only addition) |

No other path changed. `git diff --check 2a3114290ab8d4f4f6933b88c036d9f02b48e826..22cf3339149b7af8b39e777ab666c8e0ea7b431a` exits 0 (no whitespace errors). `git status --short` is empty before the report commit.

## 3. Public contracts delivered

- Types/signatures (all `@dataclass(frozen=True)`, tuples not lists):
  - `ProjectInfo(name, origin)`, `TargetSpec(device, core, fpu, float_abi, device_pack)`, `FrameworkSpec(type, version)`, `BuildSpec(sources, include_paths, defines, compile_options, assembly_sources, presets, elf)`, `MemoryRegion(name, origin, length, attributes)`, `MemorySpec(source, regions)`, `DebugSpec(backend, target, svd)`, `GenerationSpec(tool, version, cube_mx_ioc, managed_manifest, generated_directories, user_directories)`, `ProjectModel(project_root, schema_version, logical_project_id, project, target, framework, build, memory, debug, generation)`
  - `load_project_model(project_root: Path) -> ProjectModel`
  - `UpgradePlan(manifest_path, source_sha256, from_version, to_version, proposed)` — `proposed` recursively immutable (`MappingProxyType` + tuples)
  - `ProjectUpgradeError(code, message, details)` with `__init__(code, message, details)`
  - `plan_project_upgrade(project_root: Path) -> UpgradePlan`
  - `apply_project_upgrade(plan: UpgradePlan) -> OperationResult[Mapping[str, object]]`
  - `ProjectManifest`, `ProjectManifest.load(project_root, schema_path=None)`, `ProjectManifestError` remain importable from `stm32_toolkit.project` with all existing fields and resolved-path behavior; default dispatch accepts v1 and v2; explicit schema validates against that schema only; both modes run complete post-schema path validation; unsupported integer versions keep the pre-existing v1-schema stable errors in default mode.
- Commands/events/configuration/schemas: `schemas/stm32-project-v1.schema.json` (Schema v1, JSON-equivalent to the base commit's schema except title/`$id`), `schemas/stm32-project.schema.json` (Schema v2, top-level required keys exactly `["schemaVersion","logicalProjectId","generatedBy","project","target","framework","build","memory","debug","generation"]`, `schemaVersion` const 2, closed objects everywhere, uniqueness on `build.presets`/`generatedDirectories`/`userDirectories`, region `origin >= 0`/`length >= 1`, `memory.source` enum `keil|cubemx|manual`). Root and packaged copies are JSON-equivalent (verified by tests).
- External interfaces: `NONE` added; no existing protocol version changes; the `mcp_server.py` correction changes no MCP interface or protocol output.

## 4. Environment-separated verification

Environment (all OpenClaw gates): Linux (Ubuntu 26.04 LTS, kernel `7.0.0-22-generic`, x86_64) — the dispatch's Ubuntu 22.04 assumption is not restated; the actual worker OS is declared here; CPython 3.10.11 (uv-managed, `python3.10 -m venv` at `/home/openclaw/coding/venvs/stm32-toolkit-py310`, outside the repository); jsonschema 4.23.0, mcp 1.27.0, pytest 8.3.5, pytest-cov 6.0.0; package installed `pip install -e "tools/stm32-toolkit[test]"` (stm32-toolkit 0.2.0). All OpenClaw commands run from the repository root on branch `openclaw/STM32TK-0301-SCHEMA-V2/r001` against code head `22cf3339149b7af8b39e777ab666c8e0ea7b431a`.

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---:|---|---:|---|---|
| TDD RED (preserved from original r001, section 8.4): `python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q` before implementation | OpenClaw | Linux; CPython 3.10.11; exact deps | working tree at base (tests added, modules absent) | 2 | Collection interrupted: 2 errors. `ModuleNotFoundError: No module named 'stm32_toolkit.project_model'` / `'stm32_toolkit.project_upgrade'` (recorded in the previous r001 report, unchanged) | PASS |
| Pre-fix CPython 3.10 cancellation regression (section 8.4): `python -m pytest tools/stm32-toolkit/tests/test_mcp_roots.py::test_client_roots_timeout_cancels_request_and_returns_stable_error tools/stm32-toolkit/tests/test_mcp_roots.py::test_inner_roots_cancellation_returns_stable_unavailable tools/stm32-toolkit/tests/test_mcp_roots.py::test_external_tool_cancellation_is_not_swallowed -q` at reviewed head `c19d53f` | OpenClaw | same | `c19d53ffe40026251ed10a7ec01b19b6c9edaca0` | 1 | `2 failed`: `test_inner_roots_cancellation_returns_stable_unavailable` and `test_external_tool_cancellation_is_not_swallowed` both fail with `AttributeError: '_asyncio.Task' object has no attribute 'cancelling'` at `mcp_server.py:161` (the two `Task.cancelling()` failures named in section 8.4) | PASS (regression reproduced) |
| Focused GREEN: `python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q` | OpenClaw | same | `22cf333` | 0 | `128 passed in 1.24s`; zero failures; no new skip/xfail | PASS |
| CPython 3.10 cancellation regression (post-fix): the three-test command above | OpenClaw | same | `22cf333` | 0 | `3 passed in 0.69s`; all three pass | PASS |
| Full Python suite and branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing` | OpenClaw | same | `22cf333` | 0 | `251 passed, 17 skipped in 4.62s`; zero failures/errors; branch coverage **94%** (fail_under 90 satisfied) | PASS |
| Syntax compilation: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `22cf333` | 0 | silent, no output | PASS |
| Diff scope and whitespace: `git diff --check 2a3114290ab8d4f4f6933b88c036d9f02b48e826..HEAD` and `git diff --name-status 2a3114290ab8d4f4f6933b88c036d9f02b48e826..HEAD` | OpenClaw | same | `22cf333` | 0 | silent; changed paths are exactly the ten implementation paths in section 5 (plus this report) | PASS |
| Manual upgrade and digest guard (section 8.6 steps 1-5) | OpenClaw | same | `22cf333` | 0 | all steps passed; SHA-256 evidence in section 5 | PASS |
| Performance (section 7.4) | OpenClaw | same | `22cf333` | 0 | medians below 100 ms; evidence in section 5 | PASS |
| Windows compatibility review (focused + full pytest on returned code head, incl. real NTFS junction per section 8.6 step 6) | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | returned head | — | not run by OpenClaw; the Codex-observed focused-suite failure in `test_apply_result_never_leaks_exception_or_environment_details` and the junction/loader/forged-plan regressions are fixed and covered by new Linux tests, but the Windows gates themselves remain with Codex | DEFERRED_TO_CODEX |
| Visual/UI | N/A | N/A | — | — | `NOT_APPLICABLE` under section 7.5; no UI or visual asset created; no screenshot presented | PASS |

Codex-observed regressions at reviewed head `c19d53f` (section 8.4, recorded as Codex observations, not OpenClaw evidence) and their fixes: (1) Windows CPython 3.12.13 focused suite: one failure in `test_apply_result_never_leaks_exception_or_environment_details` — fixed by inspecting structured `to_dict()`/`details` fields directly (assertions remain valid on Windows path escaping); (2) a real NTFS junction escape was accepted — fixed by reparse-point detection in `project_model.py`; the Codex gate must exercise a real NTFS junction and must not skip it; (3) `ProjectManifest.load` accepted an escaping `generation.managedManifest` — fixed by complete post-schema path validation in both loader modes (regression tests added); (4) a forged `UpgradePlan` overwrote a digest-matching arbitrary file — fixed by canonical-manifest-path, valid-v1-source, and deterministic-proposal rejection in `apply_project_upgrade` (regression tests added).

Branch-coverage table (full-suite run with `--cov-branch --cov-report=term-missing` against `22cf333`):

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
| §8.6 step 2: plan read-only + exact proposed mapping | OpenClaw | bytes, mtimes, and recursive tree inventory identical before/after plan; `plan.source_sha256` matches; `memory.source=manual`, `memory.regions=()`, `generation` defaults, `generatedBy` `{"tool": "stm32-toolkit", "version": "0.2.0"}` | PASS |
| §8.6 step 3: apply, reload both loaders, digests | OpenClaw | only manifest changed (asserted by `test_apply_success_replaces_atomically_with_expected_digests` and manual run); one trailing LF; no BOM; `ProjectManifest.load` and `load_project_model` both reload as v2; `resultSha256` equals the written file's digest | PASS |
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
  - Path containment: POSIX absolute, Windows drive (`C:\`/`C:/`), UNC (`\\server\share`), and rooted backslash forms are rejected on this POSIX host before host-native parsing; `..` traversal and existing file/directory symlink parent escapes are rejected; Windows NTFS junction/reparse-point parents are detected via `st_file_attributes & 0x400` in addition to `stat.S_ISLNK` (a junction is a directory + reparse point, so `S_ISLNK` alone misses it) and an escaping junction is rejected as `PROJECT_SCHEMA_INVALID`/`pathWithinProjectRoot`. Embedded-NUL and other inspection-raising path values produce the same stable error and never leak a raw host exception (both public loaders, both schema modes).
  - Duplicate memory-region names → `PROJECT_SCHEMA_INVALID`, `{"field": "memory.regions", "rule": "uniqueRegionName"}`.
  - Forged-plan protection: `apply_project_upgrade` verifies, in order: plan versions are exactly 1→2; the target path is the canonical absolute `.stm32-project.json` (a public `UpgradePlan` constructor is not a write capability); the digest-matching current bytes form a valid Schema v1 manifest (object, integer `schemaVersion` 1, schema + model valid); the proposed payload is valid Schema v2; and the proposed payload is exactly the deterministic v1→v2 mapping of the digest-matching bytes. Any failure returns `PROJECT_UPGRADE_PLAN_INVALID` with the exact `field`/`rule` from section 6.3 and writes nothing.
  - Apply atomicity: temp file created with `O_CREAT|O_EXCL` and mode `0o600` in the manifest directory; content flushed and `fsync`ed; `os.replace` is the only manifest mutation; digest recheck and full revalidation happen before any write; temp removed on success and every handled failure. Directory `fsync` attempted on POSIX and best-effort where the platform does not support opening directories.
  - Digest guard: `PROJECT_CHANGED_SINCE_PLAN` on missing/changed bytes with `expectedSha256`/`observedSha256` (or `null`); `PROJECT_UPGRADE_IO_ERROR` with `stage` in `write|flush|replace|cleanup`.
  - Serialization: UTF-8 without BOM, two-space indent, `ensure_ascii=False`, exactly one trailing LF (asserted in tests and manual run).
- Privacy/redaction checks: failure messages and details contain only stable English text plus the canonical manifest path and stage/digest values; injected exception text ("injected write/flush/replace/cleanup failure") never appears in `OperationResult` output; no traceback, source content, random temp name, or unrelated environment path enters any result. The leakage test now asserts structured fields directly (Windows-safe).
- Performance measurements (method: `time.perf_counter`, 20 warm runs on a 100,000-byte v1 manifest with 1,000 source strings, median taken; same venv/CPython 3.10.11, code head `22cf333`):
  - `load_project_model` median: **43.80 ms** (min 42.79, max 46.53) — below the 100 ms budget — PASS
  - `plan_project_upgrade` median: **59.68 ms** (min 59.08, max 61.61) — below the 100 ms budget — PASS
  - No timing-fragile CI assertion added, per section 7.4. Processing is O(manifest size); no project-tree scan. The resolve-free lexical containment fast path with a per-document lstat cache and one-time cached `Draft202012Validator` instances per packaged schema are part of the delivered code (explicit caller-supplied schemas are still checked on every call).
- Accessibility/input checks: `NOT_APPLICABLE` for UI; deterministic English errors with structured `details` for AI/CLI adapters.
- Compatibility checks: Windows drive/UNC/POSIX absolute forms rejected on POSIX hosts; junction detection implemented for Windows via `st_file_attributes` and verified on Linux with a clearly-labeled simulation; the real NTFS junction gate is Codex's. Python 3.10+ declared compatibility verified on CPython 3.10.11 (the full 0.2 suite, including the three `test_mcp_roots.py` cancellation tests, exits 0); CPython 3.12.13 Windows verification is deferred to Codex. Existing v1 `ProjectManifest` callers/tests remain source-compatible (all pre-existing `test_project.py` and `context.py` behaviors green, including the pinned unsupported-integer stable error). No new runtime dependencies; allowed dependency direction respected.

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  1. Directory `fsync` after `os.replace` is attempted on POSIX and skipped best-effort on filesystems that reject opening/fsyncing directories (contract lists only `write|flush|replace|cleanup` stages; a post-replace directory-fsync failure is deliberately not mapped to an error stage to avoid reporting failure after a completed atomic replace). On Linux this succeeds on standard filesystems.
  2. Junction behavior is verified on Linux via a labeled reparse-point simulation; the real NTFS junction gate (section 8.6 step 6, section 8.1 Windows row) remains with Codex on Windows CPython 3.12.13 and must not be satisfied by a skipped test.
  3. The worker OS is Ubuntu 26.04 LTS rather than the Ubuntu 22.04 assumed by the dispatch; runtime CPython 3.10.11 and the exact pinned dependencies match the work order. Declared truthfully; no gate depends on the Ubuntu minor version.
- Follow-up recommendation: `NONE`.

## 7. Author checklist

- [x] Accepted base and code head are full SHAs (`2a3114290ab8d4f4f6933b88c036d9f02b48e826`, `22cf3339149b7af8b39e777ab666c8e0ea7b431a`).
- [x] Final head will be returned out of band after this report commit.
- [x] Inventory matches the complete implementation diff and report addition (ten product/test paths + report path).
- [x] Every required OpenClaw gate has direct observed evidence (RED, pre-fix cancellation regression, focused/full suite, coverage table, compileall, diff checks, manual SHA-256 evidence, performance medians).
- [x] Other-environment gates are accurately attributed or deferred (Windows gate deferred to Codex; Codex observations recorded as such; visual gate `NOT_APPLICABLE`).
- [x] No credentials, private data, caches, build output, or unredacted diagnostics are committed (venv kept outside the repository; `.coverage`/`__pycache__`/`.pytest_cache`/`*.egg-info` ignored; no fixture or temp project committed).
- [x] No unrelated file, agent instruction, approved work order, or remote policy changed (diff scope verified; `AGENTS.md`/`OPENCLAW_START_HERE.md`/work order untouched; `test_mcp_roots.py` untouched).
- [x] Every instructional value in this report is replaced with actual evidence.
- [x] Overall status `IMPLEMENTED`: complete 0.2 suite exits 0 on CPython 3.10.11 (251 passed, 17 skipped), branch coverage 94%, all consolidated revision corrections delivered, Windows gates `DEFERRED_TO_CODEX`.
