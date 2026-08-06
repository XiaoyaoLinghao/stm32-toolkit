# STM32TK-0305-BUILD-IDENTITY: Bounded Build, MAP Validation, and Firmware Identity

Status: `READY_FOR_OPENCLAW`
Accepted base commit: `e47eee0d374bd3a959fe555990b66a6163eb18b8`
Specification owner: Codex
Implementation owner: OpenClaw
Reviewer: Codex

## 0. r002 replacement order after r001 REWRITE_REQUIRED

- r001 reviewed final head: `bb747935eb002cad8b251ad7bd4ebae5467e08f7`; closed PR: `https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/5`.
- Verdict: `REWRITE_REQUIRED`, not a bounded revision. r002 starts again from accepted base `e47eee0d374bd3a959fe555990b66a6163eb18b8`; do not merge, rebase, or cherry-pick r001. It may be read only as negative evidence.
- r001 Windows focused gate failed with 23 failures. The exact rejected classes were CRLF output, POSIX-only `killpg`/`fcntl` tests executed on Windows, a shebang-only fake `cmake` that invoked the real CMake on Windows, and `chmod(0)` unreadability assumptions.
- r001 was also rejected independent of platform because it implemented a different public protocol and omitted the core safety boundary:
  - it used `clean_first`, nullable Git branch/target, percent memory, boolean ELF observations, `.stm32-toolkit/build/<preset>` evidence, and unapproved error codes instead of section 6/11/12;
  - it took only a post-build manifest/source snapshot, omitted headers and managed configuration, never compared a pre-build snapshot, and could identify source bytes that were not compiled;
  - configure/build failure published no failure record, so a previous success could remain fresh;
  - MAP LMA was discarded, out-of-region sections were clipped rather than rejected, model regions were not reconciled, and overflow was structurally impossible to detect;
  - missing/short vector, undefined non-weak symbols, Reset_Handler definition/vector mismatch, alloc-section escape, and fixed-section mismatch were recorded as booleans/lists rather than rejected;
  - release builds were labeled with `build/arm-debug/firmware.elf`; a real diagnostic built both outputs and observed the release success record point at the debug ELF;
  - `OperationResult.to_dict()` returned a live `BuildReport` object and was not JSON serializable;
  - raw process stdout/stderr were returned and published without the required root/privacy normalization.
- Codex's real toolchain gate also exposed one upstream STM32TK-0304 defect: generated link options omit the CPU/FPU/ABI flags and freestanding startup suppression. Both presets fail with VFP ABI mismatch and newlib/crt0 unresolved symbols. r002 is explicitly authorized to correct the exact CMake template/test paths added to section 5.
- r002 RED evidence must reproduce these safety failures against accepted base or isolated r001 code as appropriate. Passing rewritten assertions without demonstrating the rejected behavior is insufficient.

## 1. Objective and user-visible outcome

- Turn one validated Schema v2 project with the managed configuration from STM32TK-0304 into a bounded ARM GNU build and a trustworthy firmware identity.
- `run_build(BuildRequest) -> OperationResult[BuildReport]` runs exact CMake configure/build argv without a shell, rejects stale or malformed outputs, validates the GNU MAP and ELF, and publishes one current success or failure record.
- A successful result identifies the exact Git commit, dirty state, input snapshot, target, preset, Toolkit version, ELF/MAP bytes, entry point, vector table, `Reset_Handler`, memory use, and timestamps.
- A failed build never returns an old ELF as success. Existing output bytes may remain for diagnosis, but the new failure record makes them unambiguously stale to `build_project_context` and all later flash/debug consumers.

## 2. Scope

### 2.1 In scope

- Frozen build request/result/identity types and fresh JSON-safe serialization.
- A reusable bounded subprocess runner with concurrent stdout/stderr draining, byte and line limits, timeouts, child reaping, fixed argv, and no shell.
- Exact `cmake --preset <preset>` configure and `cmake --build --preset <preset>` build stages; `clean=True` adds `--clean-first` only to the build argv.
- Schema v2/model/configuration and build-input revalidation before invoking any process.
- Content and metadata snapshots for the manifest, declared C/C++ and assembly sources, recursively bounded declared include directories, and every file owned by `.stm32-toolkit/generated-files.json`.
- GNU linker MAP parsing, region/section accounting, overflow detection, and exact model-memory reconciliation.
- ELF parsing with pyelftools 0.33; exact hashes, entry point, `.isr_vector`, `Reset_Handler`, undefined-symbol rejection, and vector/reset consistency.
- Atomic publication of:
  - `artifacts/migration/build.log`;
  - `artifacts/migration/build-result.json`;
  - `build/<preset>/firmware-identity.json` beside the model-selected ELF basename.
- `build_project_context` freshness based on the current successful build record, identity sidecar, hashes, target, preset, Git HEAD, and complete input snapshot rather than ELF mtime alone.
- One deterministic minimal ARM GNU fixture used by Codex's real Windows toolchain gate.

### 2.2 Out of scope

- No CLI, MCP tool, Skill, plugin/version bump, release packaging, flash, probe, debug, monitor, host/target tests, CubeMX, Keil invocation, network access, or dependency installation.
- No source/configuration generation or repair; consume STM32TK-0304 output and return a stable prerequisite failure when it is absent or stale.
- No parallel build scheduler, remote cache, container, compiler download, build-system discovery, arbitrary preset, arbitrary command, user-supplied environment, or shell command.
- No deletion of old ELF/MAP files on failure and no claim that byte-identical builds are bit-reproducible across different toolchain versions.
- No migration memory comparison against the Keil baseline; that is a later acceptance workflow. This module records GCC evidence only.

### 2.3 Prohibited shortcuts

- Do not use `shell=True`, command strings, `os.system`, `Popen.communicate()` without concurrent bounded drains, unbounded `read`/`read_text`, platform-default encoding/newlines, or host absolute paths in protocol/report JSON.
- Do not trust caller dataclasses, an existing ELF/MAP/identity, process exit 0, file mtimes alone, a prior build record, generated manifest ownership, or caller-provided digests.
- Do not scan outside the canonical project root, follow escaping symlinks/NTFS junctions, recursively scan the whole repository, read `.git` contents directly, or expose environment variables/credentials.
- Do not add skip/xfail for a required pure-code gate, lower coverage, weaken STM32TK-0301 through 0304 contracts, or modify paths outside section 5 plus the implementation report.

## 3. Prerequisites and fixed decisions

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Branch from the exact accepted product base `e47eee0d374bd3a959fe555990b66a6163eb18b8`. Fetch `origin/master`, but do not merge, rebase, or cherry-pick the specification commit into the implementation branch.
- Before implementation read `AGENTS.md`, `OPENCLAW_START_HERE.md`, this work order, the architecture, complete roadmap, 0.3 plan, and implementation reports for STM32TK-0301 through 0304.
- Runtime remains Toolkit `0.2.0`, protocol `stm32-toolkit/1`, Schema v2, CPython 3.10+, jsonschema 4.23, pyelftools 0.33, Jinja2 3.1.x, pytest 8.3.5, and pytest-cov 6.0.0. Add no dependency.
- Supported presets are exactly `arm-debug` and `arm-release`.
- Timestamps are UTC RFC 3339 with exactly six fractional digits and `Z`. Durations are non-negative integer milliseconds.
- Portable paths use `/`. Hashes are lowercase SHA-256 hex. Git HEAD is lowercase 40-hex.
- JSON is UTF-8 without BOM, `indent=2`, `ensure_ascii=False`, insertion order defined below, and exactly one final LF.
- Visual acceptance is `NOT_APPLICABLE`.

## 4. Architecture and dependency direction

```text
ProjectModel + managed generated-files manifest
  -> build.identity snapshot validation
  -> build.runner
       -> process.run_process (fixed argv, bounded output, timeout/reap)
       -> cmake configure
       -> cmake build
       -> build.map_file GNU MAP validation
       -> pyelftools ELF validation
  -> atomic build log/result/identity publication
  -> context reads and independently revalidates evidence
```

- `process.py` is generic stdlib-only process execution and imports no project/build module.
- `build/model.py` owns frozen public values and serialization only.
- `build/identity.py` owns snapshots, Git evidence, ELF validation, identity construction, schema validation, and atomic JSON helpers.
- `build/map_file.py` owns bounded GNU MAP parsing and interval accounting only.
- `build/runner.py` orchestrates prerequisites, lock, stages, evidence publication, and stable errors.
- `context.py` may consume read-only identity helpers; build modules must not import context, CLI, MCP, doctor, Keil, or migration.

## 5. Exact file plan

| Status | Path | Responsibility |
|---|---|---|
| M | `.gitignore` | unignore only the mandated Python `stm32_toolkit/build/` package below the pre-existing global `build/` rule |
| A | `schemas/firmware-identity.schema.json` | review copy of identity schema |
| A | `tools/stm32-toolkit/src/stm32_toolkit/schemas/firmware-identity.schema.json` | byte-identical packaged runtime schema |
| A | `tools/stm32-toolkit/src/stm32_toolkit/process.py` | bounded fixed-argv subprocess execution |
| A | `tools/stm32-toolkit/src/stm32_toolkit/build/__init__.py` | public build exports |
| A | `tools/stm32-toolkit/src/stm32_toolkit/build/model.py` | frozen request/report/identity/memory types |
| A | `tools/stm32-toolkit/src/stm32_toolkit/build/map_file.py` | bounded GNU MAP parser and memory accounting |
| A | `tools/stm32-toolkit/src/stm32_toolkit/build/identity.py` | input snapshot, Git/ELF identity, schema, atomic evidence |
| A | `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py` | build orchestration, locking, stale-output defense |
| M | `tools/stm32-toolkit/src/stm32_toolkit/context.py` | evidence-backed ELF freshness |
| M | `tools/stm32-toolkit/src/stm32_toolkit/result.py` | preserve typed immutable data while snapshotting its explicit `to_dict()` representation for JSON serialization |
| M | `templates/cmake/CMakeLists.txt.j2` | root review template: architecture-correct freestanding link options |
| M | `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2` | byte-identical packaged template correction |
| A | `tools/stm32-toolkit/tests/test_process.py` | process limits/timeout/reaping contracts |
| A | `tools/stm32-toolkit/tests/test_build_runner.py` | build stages/failures/publication/atomicity |
| A | `tools/stm32-toolkit/tests/test_build_map.py` | MAP parsing/overflow/malformed evidence |
| A | `tools/stm32-toolkit/tests/test_firmware_identity.py` | snapshot/ELF/schema/context freshness |
| A | `tools/stm32-toolkit/tests/fixtures/minimal-gcc/.stm32-project.json` | exact Schema v2 real-toolchain fixture |
| A | `tools/stm32-toolkit/tests/fixtures/minimal-gcc/Src/main.c` | freestanding deterministic main |
| A | `tools/stm32-toolkit/tests/fixtures/minimal-gcc/Startup/startup.s` | Cortex-M vector and Reset_Handler fixture |
| M | `tools/stm32-toolkit/tests/test_context.py` | successful/failure/stale identity context tests |
| M | `tools/stm32-toolkit/tests/test_generation.py` | exact link-option snapshot and root/package template identity regression |
| M | `tools/stm32-toolkit/tests/test_result.py` | typed-data JSON snapshot and immutability regression |
| A | `docs/openclaw/returns/STM32TK-0305-BUILD-IDENTITY/r002-implementation-report.md` | report-only final commit |

No other path is approved. Existing `pyproject.toml` already packages `schemas/*.json`; do not change dependencies or package metadata. The `.gitignore` exception must be exactly `!tools/stm32-toolkit/src/stm32_toolkit/build/` and must not unignore project build outputs.

## 6. Public contracts

### 6.1 Types and functions

All values are `@dataclass(frozen=True)`. Container fields are tuples or recursively frozen mappings. Every `to_dict()` returns a fresh JSON-safe value and omits absolute roots and raw bytes.

```python
@dataclass(frozen=True)
class BuildRequest:
    project_root: Path
    preset: str
    clean: bool = False
    timeout_seconds: int = 300

@dataclass(frozen=True)
class MemoryUsage:
    name: str
    origin: int
    length: int
    used: int
    free: int

@dataclass(frozen=True)
class FirmwareIdentity:
    schema_version: int
    build_id: str
    logical_project_id: str
    toolkit_version: str
    git_head: str
    git_dirty: bool
    input_snapshot_sha256: str
    newest_input_mtime_ns: int
    target_device: str
    preset: str
    elf_path: str
    elf_sha256: str
    elf_size: int
    map_path: str
    map_sha256: str
    entry_point: int
    vector_address: int
    reset_handler_address: int
    built_at_utc: str

@dataclass(frozen=True)
class BuildReport:
    identity: FirmwareIdentity
    memory: tuple[MemoryUsage, ...]
    warnings: tuple[str, ...]
    build_log_path: str
    build_result_path: str
    identity_path: str
    configure_duration_ms: int
    build_duration_ms: int

def run_build(request: BuildRequest) -> OperationResult[BuildReport]: ...
```

`stm32_toolkit.build.__init__` exports exactly these four types and `run_build`. `OperationResult.operation` is `build`.

`result.data` remains the typed frozen `BuildReport`. `OperationResult` must capture a recursively frozen JSON representation at construction time when data provides the explicit Toolkit `to_dict()` contract; `OperationResult.to_dict()["data"]` returns a fresh ordinary mapping and `json.dumps(result.to_dict())` succeeds. Later mutation of a custom object's returned mapping cannot change the captured protocol payload. Existing mapping/list/scalar behavior and all foundation tests remain unchanged; do not invoke arbitrary properties, iterators, serializers, or `repr`.

`process.py` exposes frozen `ProcessRequest`, `ProcessResult`, and `run_process(request)`. `ProcessRequest.argv` is a non-empty tuple of strings, `cwd` is a canonical existing directory, timeout is `1..3600`, and output cap is `1..8 MiB` per stream.

### 6.2 Identity and build ID

- `input_snapshot_sha256` hashes canonical compact sorted-key JSON of sorted entries `{path, size, sha256}`. It excludes mtimes and absolute paths.
- `newest_input_mtime_ns` is the maximum captured input mtime and is evidence only.
- `build_id` hashes canonical compact sorted-key JSON of every identity field except `schemaVersion`, `buildId`, and `builtAtUtc`. Repeated builds of the same exact inputs and binary therefore share a build ID even though timestamps differ.
- Firmware identity key order is: `schemaVersion`, `buildId`, `logicalProjectId`, `toolkitVersion`, `gitHead`, `gitDirty`, `inputSnapshotSha256`, `newestInputMtimeNs`, `targetDevice`, `preset`, `elfPath`, `elfSha256`, `elfSize`, `mapPath`, `mapSha256`, `entryPoint`, `vectorAddress`, `resetHandlerAddress`, `builtAtUtc`.
- The root and packaged schemas are byte-identical and require exactly those fields, no additional properties, bounded strings/integers, portable paths, lowercase hashes, and RFC 3339 UTC time.

### 6.3 Required STM32TK-0304 link correction

- The generated CMake target must pass the exact validated architecture flags to both compile and link: `-mcpu=<core flag>`, `-mthumb`, and optional paired `-mfpu=<fpu>` / `-mfloat-abi=<abi>`.
- Add `-nostartfiles` and `-Wl,--gc-sections` to `target_link_options`. Do not add guessed startup objects, host libraries, `--specs`, or `-nostdlib`; GCC may still supply required compiler runtime helpers while the project-owned `Reset_Handler` remains the entry.
- Preserve `-T...` and deterministic MAP options. Root and packaged templates remain byte-identical.
- Exact generation snapshots cover hard-FPU and no-FPU targets and prove link flags match their compile architecture flags. The real r002 fixture must link without VFP ABI mismatch, crt0, newlib syscall, or undefined-symbol errors.

## 7. Build prerequisites and input snapshot

- Require `type(request) is BuildRequest`, `type(project_root) is Path`, canonical existing directory root, supported preset, `type(clean) is bool`, and `type(timeout_seconds) is int` in range `1..3600`; booleans are not integers.
- Load a fresh Schema v2 `ProjectModel`. Require `generation.tool/version/managedManifest` contracts from STM32TK-0304 and exactly `CMakeLists.txt`, `CMakePresets.json`, the toolchain, linker script, and valid managed manifest ownership.
- The model ELF must be `build/arm-debug/<basename>.elf`; release uses the same basename under `build/arm-release`. MAP is the same directory and basename with `.map`.
- Centralize this mapping in one validated helper. Every debug/release pre-state check, process result, MAP/ELF validation, identity, context comparison, and artifact path uses the preset-specific path. A release result pointing to a debug artifact is an unconditional failure.
- Snapshot exact bytes for `.stm32-project.json`, declared sources, assembly sources, and all currently owned generated files listed by the managed manifest.
- Recursively snapshot only declared include directories. Walk lexically sorted portable relative paths; accept regular files only; reject escaping redirects, loops, special files, unreadable entries, duplicate/casefold collisions, and inspection failures.
- Bounds: 8 MiB per input file, 10,000 files, and 256 MiB aggregate. Read `limit + 1`. Hash exact disk bytes. Directories themselves contribute their portable path but no host metadata.
- Revalidate the snapshot immediately before configure and again after successful build. Any change returns `BUILD_INPUT_CHANGED`; do not publish success.
- Obtain Git evidence only through fixed argv `git rev-parse --verify HEAD` and `git status --porcelain=v1 -z --untracked-files=all`, with bounded output and no shell. A non-repository or invalid HEAD returns `BUILD_GIT_INVALID`. Dirty builds are allowed and recorded truthfully.
- Build outputs and `artifacts/migration` are excluded from the dirty-input interpretation and input recursion; declared sources/includes may never point into those directories.

## 8. Process contract

- Configure argv is exactly `("cmake", "--preset", preset)`.
- Build argv is exactly `("cmake", "--build", "--preset", preset)` plus final `"--clean-first"` only when `clean=True`.
- Use `cwd=project_root`, `shell=False`, stdin disconnected, no user-provided environment, no command interpolation, and no PATH resolution persisted in results.
- Concurrently drain stdout and stderr as bytes while the child runs. Retain at most 1 MiB and 20,000 LF-delimited lines per stream; continue draining discarded overflow to prevent deadlock. Mark truncation deterministically.
- On timeout terminate the process group/tree created for this invocation, wait up to two seconds, force-kill only that tree if needed, reap it, and return a timeout result. POSIX uses a new session/process group; Windows uses `CREATE_NEW_PROCESS_GROUP` and bounded child-tree termination without killing unrelated processes.
- Decode retained output as UTF-8 with replacement only for the log. Protocol details never contain raw output, exception text, executable paths, cwd, environment, username, or stack traces.
- Normalize captured CRLF and bare CR to LF before constructing `ProcessResult`; exact Windows and Linux subprocess output is therefore portable.
- Log serialization uses stable stage headers, normalized LF, and replaces all canonical project-root spellings with `<PROJECT_ROOT>`. It records argv as JSON arrays, exit code, timeout/truncation flags, and retained output.

## 9. MAP and ELF validation

### 9.1 GNU MAP

- Read the MAP as at most 32 MiB plus one byte and decode strict UTF-8/ASCII-compatible text.
- Parse GNU ld `Memory Configuration` rows and output-section rows with optional `load address` using anchored, bounded regexes. Reject duplicate region names, malformed/overflowing integers, overlapping declared intervals, duplicate/conflicting sections, and ambiguous rows.
- MAP region names, origins, and lengths must exactly equal the model memory regions in model order. GNU ld attribute order is not identity evidence and is ignored.
- Account non-empty output-section VMA intervals to the containing region. When an explicit load address differs, also account the LMA interval to its containing region. Compute used bytes as interval union, not sum, so overlaps cannot double-count.
- Every allocatable address interval must fit completely in one model region. `used <= length`; return `FLASH_OVERFLOW` for the selected executable region, `RAM_OVERFLOW` for the selected writable region, and `MEMORY_OVERFLOW` for any other region, with only `{region, used, length, overflow}`.

### 9.2 ELF

- Require regular non-empty ELF32 little-endian ARM bytes, bounded to 64 MiB, parsed by pyelftools 0.33 from an already bounded byte buffer.
- Require `.isr_vector` with at least eight bytes in an executable memory region; require a defined `Reset_Handler` symbol in a symbol table; require `e_entry & ~1 == reset_handler_address & ~1`.
- Decode the second 32-bit little-endian vector word and require `word & ~1 == reset_handler_address & ~1`.
- Reject every named undefined global symbol. Undefined weak symbols may remain only when their binding is `STB_WEAK`; list no symbol names in protocol errors.
- Require every `SHF_ALLOC` section with nonzero size to fit one model region. Verify the fixed `.stm32tk.abs.<ADDR8>` sections, when present, start at the encoded address.
- Hash exact ELF and MAP bytes only after all validation succeeds.

## 10. Freshness and stale-output defense

- Capture pre-run ELF/MAP existence, size, mtime, and digest before configure.
- Exit 0 is insufficient. Success requires valid current ELF/MAP and one of:
  1. output metadata changed during this invocation; or
  2. an existing valid successful build-result and identity match the exact current input snapshot, Git HEAD, target, preset, ELF hash, and MAP hash (legitimate no-op rebuild).
- A configure/build timeout or nonzero exit returns failure with `data=None`, writes the new failure build-result/log atomically, and never rewrites the identity sidecar.
- A post-build validation/input-race/publication failure also returns `data=None`; it must not leave a partially written JSON file. The failure build-result supersedes an older success for context freshness.
- `build_project_context` reports `elfFresh=True` only when build-result status is `success`, identity schema/build ID are valid, identity and record agree, current Git HEAD/target/preset/input snapshot/ELF/MAP hashes agree, and every path remains contained and regular. Missing, malformed, failure, unreadable, mismatched, or oversized evidence yields `elfFresh=False` without trusting mtime.
- The context implementation validates the complete packaged identity schema and independently recomputes `buildId`; it must not search another preset and accept it as evidence for the model-selected debug ELF.
- Context adds `buildId`, `elfSha256`, `preset`, `gitHead`, and portable evidence paths when fresh; otherwise those values are `None`. Do not expose absolute ELF paths newly through these fields; preserve existing context compatibility outside this bounded change.

## 11. Evidence publication and locking

- Serialize success/failure evidence completely in memory, validate success identity against the packaged schema, then write with unique sibling temporary files, flush, `fsync`, `os.replace`, and directory `fsync`.
- Publish the sanitized log first, identity second, and build-result last. The last replacement is the freshness commit point.
- `build-result.json` key order is `schemaVersion`, `status`, `stage`, `code`, `buildId`, `gitHead`, `gitDirty`, `inputSnapshotSha256`, `targetDevice`, `preset`, `startedAtUtc`, `finishedAtUtc`, `durationMs`, `artifacts`, `memory`, `warnings`. Failure uses `buildId: null`, empty memory, and stable code/stage.
- Artifact paths are portable project-relative paths only. No raw stdout/stderr is embedded in JSON.
- Serialize builds per project with a nonblocking cross-platform advisory lock on `.stm32-toolkit/build.lock`. An already held lock returns `BUILD_BUSY`; a lock file may remain, but an unlocked stale file must not block. Never delete or break another process's held lock.
- Publication failure returns `BUILD_EVIDENCE_FAILED`; clean up only this invocation's temporary files. Never claim success without the final build-result commit point.

## 12. Stable failures

| Code | Meaning and bounded details |
|---|---|
| `BUILD_REQUEST_INVALID` | invalid request; `{field, rule}` |
| `BUILD_PROJECT_INVALID` | model/configuration/manifest invalid; `{field, rule}` or `{path, rule}` |
| `BUILD_INPUT_INVALID` | input missing/unreadable/non-regular/oversized/escaping; `{path, rule}` |
| `BUILD_INPUT_CHANGED` | snapshot changed during build; `{path}` when one safe path is known, otherwise `{rule: inputSnapshot}` |
| `BUILD_GIT_INVALID` | Git evidence unavailable/malformed/oversized; `{rule}` |
| `BUILD_BUSY` | project build lock held; `{path: .stm32-toolkit/build.lock}` |
| `BUILD_CONFIGURE_FAILED` | configure nonzero; `{stage, exitCode, log}` |
| `BUILD_FAILED` | build nonzero; `{stage, exitCode, log}` |
| `BUILD_TIMEOUT` | bounded timeout; `{stage, timeoutSeconds, log}` |
| `BUILD_OUTPUT_STALE` | exit 0 returned unverifiable prior outputs; `{path, rule}` |
| `BUILD_MAP_INVALID` | malformed/mismatched MAP; `{path, rule}` |
| `BUILD_ARTIFACT_INVALID` | ELF/entry/vector/symbol/section invalid; `{path, rule}` |
| `FLASH_OVERFLOW` / `RAM_OVERFLOW` / `MEMORY_OVERFLOW` | `{region, used, length, overflow}` |
| `BUILD_EVIDENCE_FAILED` | atomic evidence publication failed; `{path, phase}` |

Messages are stable English summaries. Details and `to_dict()` never contain host exception text, absolute/temp paths, process output, source bytes, environment values, usernames, or credentials.

## 13. Security, limits, performance, and compatibility

- Planning/snapshot reads no network and invokes only the fixed Git commands. Building invokes only fixed CMake argv; compiler/Ninja subprocesses are descendants of CMake.
- Reject NUL, drive-relative, UNC, absolute, `.`/`..`, empty-component, mixed-separator traversal, casefold collisions, escaping symlinks, and NTFS reparse escapes for every consumed and published path.
- No committed build output, coverage file, cache, log, temporary project, virtualenv, ELF, MAP, or identity from tests.
- Unit fixture with 1,000 source/header inputs and a 4 MiB MAP: input snapshot median below 500 ms and MAP+ELF identity median below 500 ms over 20 warm runs on OpenClaw's declared environment. Do not add timing assertions to normal tests.
- Compatible with Windows 10/11 and Linux, CPython 3.10+. Tests use exact bytes, portable path components, injected permission failures, and no administrator privileges.
- Root/package schema identity and installed-wheel schema loading outside the repository are mandatory.

## 14. Required tests

### 14.1 TDD RED and focused command

Commit tests before implementation. Record a RED run proving imports/contracts are absent or the stale-artifact behavior fails for the intended reason, not syntax/fixture errors.

```powershell
python -m pytest tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_build_map.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_context.py -q
```

### 14.2 Coverage requirements

Tests cover:

- frozen exact public types, recursive immutability, key order, fresh serialization, canonical build ID, no root/raw-byte leakage;
- request type/range/preset/root validation and booleans-not-integers;
- process concurrent stdout/stderr flood, no deadlock, byte/line truncation, invalid UTF-8, timeout, graceful/forced termination, child reaping, fixed argv/cwd, no shell/environment leakage;
- exact CRLF/bare-CR normalization; POSIX-only killpg tests run through injected callable seams on Windows rather than touching absent `os.killpg`; Windows tests exercise the real `_WINDOWS=True` branch;
- missing/stale/malformed managed configuration, manifest drift, source/header/config missing/change/race, limits, permission/lstat/resolve failures, redirects and junction escapes;
- Git clean/dirty/non-repository/detached/malformed/nonzero/timeout/overflow results;
- configure/build success, nonzero, timeout, launch failure, clean argv, stage order, lock contention, and lock release on every exit;
- platform-adaptive fake CMake uses an explicit `sys.executable` wrapper or Windows `.cmd` launcher and proves the fake was hit; it must never fall through to ambient real CMake. Lock tests use the product lock abstraction and real `msvcrt`/`fcntl` according to host, never unconditional `import fcntl`;
- stale ELF/MAP before a failed build, fake exit 0 without outputs, legitimate no-op rebuild with matching evidence, and changed outputs;
- GNU MAP valid Flash/RAM/LMA, interval union, region mismatch, malformed/duplicate/conflict, unknown/out-of-range section, overflow, limits, and CRLF/LF exact-byte behavior;
- ELF wrong class/endian/machine, truncated/malformed, missing/short vector, missing/mismatched Reset_Handler/entry/vector word, undefined global versus allowed weak, alloc section escape, fixed-section address, and size limit;
- atomic log/identity/result order, write/flush/fsync/replace failures at every point, no partial JSON, previous success invalidated by failure, and no unrelated write;
- context success, build failure, changed source/header/config/Git HEAD/ELF/MAP/identity, malformed/oversized/unreadable evidence, portable fields, and backward-compatible unconfigured context;
- unreadability uses deterministic `PermissionError` injection on Windows; no `chmod(0)` assumption, skip, or xfail;
- typed `BuildReport` remains accessible as `result.data`, while `json.dumps(result.to_dict())` succeeds and uses a construction-time immutable snapshot;
- schema identity, installed-wheel loading, deterministic fixture, privacy/error serialization, and performance evidence.

No new skip/xfail. Platform-adaptive tests must not require Windows developer mode.

### 14.3 Full gates

```powershell
python -m pytest tools/stm32-toolkit/tests -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check e47eee0d374bd3a959fe555990b66a6163eb18b8..HEAD
git diff --name-status e47eee0d374bd3a959fe555990b66a6163eb18b8..HEAD
```

Branch coverage must remain at least 90% overall and at least 90% for every new build/process module.

### 14.4 Environment evidence matrix

| Gate | Required environment | Owner | Expected | Deferred owner |
|---|---|---|---|---|
| TDD RED, focused GREEN | OpenClaw CPython 3.10.11 + exact pinned deps/Git | OpenClaw | expected RED then exit 0 | none |
| Full + branch coverage, compile, dependency, scope | same | OpenClaw | exit 0, branch >=90%, exact scope, no dependency change | none |
| Process limits/timeouts, fake builds, MAP/ELF, stale defense, atomic publication, performance | same | OpenClaw | exact behavior and budgets | none |
| Root/package schema and installed-wheel load | fresh external OpenClaw venv | OpenClaw | byte-identical and repository-independent | none |
| Windows focused/full, process-tree timeout, advisory lock, replace/fsync publication | Windows NT 10.0.26200.0, CPython 3.12.13 | Codex | exit 0, no new skip, exact behavior | `DEFERRED_TO_CODEX` only |
| Real minimal generated configure/build/MAP/ELF identity | Codex Windows; CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1/binutils 2.44 | Codex | debug and release success; exact identity and no host paths | `DEFERRED_TO_CODEX` only |
| Visual/hardware | N/A | N/A | `NOT_APPLICABLE` | none |

`PASS` means the named owner ran the gate against the returned code head. A pure-code failure is never deferred and OpenClaw must not claim Codex evidence.

## 15. Minimal real-toolchain fixture

- `.stm32-project.json` uses logical ID `12345678-1234-5678-1234-567812345678`, target `STM32F407VGTx`, cortex-m4 hard-float, sources `Src/main.c`, assembly `Startup/startup.s`, no include paths, exact debug/release presets, ELF `build/arm-debug/firmware.elf`, FLASH `0x08000000/0x00100000/r-x`, RAM `0x20000000/0x00020000/rwx`, pyocd target `stm32f407vg`, and standard generation metadata.
- `startup.s` emits a non-empty `.isr_vector` whose first word is `0x20020000`, second word is `Reset_Handler`, and a Thumb `Reset_Handler` that calls `main` then loops. It contains no guessed production device startup logic and is test-only.
- `main.c` is freestanding and returns zero without libc.
- The Codex gate copies the fixture, calls STM32TK-0304 plan/apply, then calls `run_build` for `arm-debug` and `arm-release`. Both must produce valid MAP/ELF/identity; no fixture build artifact is committed.
- The two builds use fresh fixture copies or prove preset isolation explicitly. Debug identity must reference only `build/arm-debug/*`; release identity must reference only `build/arm-release/*`. Independently inspect both ELF files with pyelftools/objdump.

## 16. Manual verification

1. Place an old ELF/MAP and valid old success record, inject configure and build failures separately, and prove `data=None`, a new failure record, old identity not returned, and context `elfFresh=False`.
2. Flood stdout and stderr concurrently beyond both limits; prove no deadlock, deterministic truncation, child reaped, and bounded sanitized log.
3. Change a header during build after configure; prove `BUILD_INPUT_CHANGED` and no success commit point.
4. Inject atomic publication failure at log, identity, and final result replacement; prove no partial JSON and no false freshness.
5. Hold the project advisory lock from another process; prove `BUILD_BUSY`, then release it and prove the unchanged stale lock file does not block.
6. Parse a 4 MiB synthetic MAP with overlapping section intervals and `.data` LMA; prove interval-union Flash/RAM accounting and performance budget.
7. Build/install a wheel in a fresh external venv, change cwd outside the repository, load the packaged identity schema, and validate a generated identity.
8. On Codex Windows, build both fixture presets and independently recompute ELF/MAP hashes and inspect entry/vector/Reset_Handler addresses with pyelftools/objdump.

## 17. Implementation sequence and commits

1. Commit focused RED tests and exact fixture bytes. Include r001 rejected-head regression evidence without copying r001 implementation commits.
2. Implement process/model foundations and make process tests green; commit.
3. Implement snapshots, MAP/ELF identity, and schema; commit.
4. Implement runner, atomic evidence, locking, and context freshness; commit.
5. Run all OpenClaw gates and performance/wheel checks.
6. Reconcile the report and commit it separately after the code head.

Use small coherent commits; do not amend, rebase, or force-push after the branch becomes reviewable.

## 18. Return contract

- Branch: `openclaw/STM32TK-0305-BUILD-IDENTITY/r002` from the exact accepted base.
- Report: `docs/openclaw/returns/STM32TK-0305-BUILD-IDENTITY/r002-implementation-report.md`.
- The tracked report records the accepted base and full code head before the report commit. It must not contain its own final commit SHA or moving commit totals.
- Push only the implementation branch and create/update one Draft PR targeting `master`.
- Return status, branch, accepted base, code head, final remote head, PR URL, report path, exact changed-path inventory, environment-separated tests/coverage/performance/wheel evidence, deferred Codex gates, and proof local HEAD equals remote branch equals PR head with clean status.
- Do not push master, force-push, merge, approve, close, delete a branch, or create another attempt/PR without Codex direction.

## 19. Rejection conditions

- A failed/timeout/malformed build returns or makes context trust a previous ELF.
- Process output can deadlock, grow without bound, survive timeout, invoke a shell, accept arbitrary argv/environment, or leak private host state.
- Build trusts exit 0, mtimes alone, stale records, caller hashes, managed-manifest claims, escaping paths, malformed MAP/ELF, unresolved globals, missing vector/Reset_Handler, or overflowing memory.
- Evidence publication can leave partial JSON, publish result before identity, claim success after failure, overwrite unrelated files, or expose absolute/temp paths, output, environment, username, or credentials.
- Context freshness remains mtime-only or accepts mismatched Git/input/ELF/MAP/identity evidence.
- Root/package schema differs, installed-wheel loading depends on repository cwd, dependency/scope differs, required tests fail, or coverage falls below the thresholds.
- OpenClaw claims a deferred Windows/toolchain gate it did not run.

## 20. Completion checklist

- [ ] Exact accepted base, ownership, branch, scope, and dependency rules followed.
- [ ] Frozen build/process/identity contracts are deterministic, bounded, portable, and JSON-safe.
- [ ] Inputs, managed configuration, Git evidence, paths, MAP, ELF, vector, symbols, fixed sections, and memory fail closed.
- [ ] Configure/build execution is fixed-argv, shell-free, concurrently drained, bounded, timed out, and reaped.
- [ ] Failure never returns stale output; success requires exact current evidence.
- [ ] Log, identity, and build result publish atomically with the result as commit point.
- [ ] Context freshness independently revalidates the complete evidence chain.
- [ ] Focused/full/coverage/compile/scope/schema/wheel/manual/performance gates pass.
- [ ] Codex-only Windows and real-toolchain gates are truthfully deferred.
- [ ] Report contains accepted base and code head, not its own final SHA.
- [ ] Remote branch, PR head, local HEAD, and clean status are proven.
