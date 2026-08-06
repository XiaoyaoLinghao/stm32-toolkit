# STM32TK-0304-GCC-CONFIG: Managed GCC/CMake and VS Code Configuration

Status: `READY_FOR_OPENCLAW`
Accepted base commit: `8a627e95732bff069bef76e75c6b5f6fa992c6f4`
Default branch: `master`
Implementation branch: `openclaw/STM32TK-0304-GCC-CONFIG/r001`
Specification owner: Codex
Implementer: OpenClaw
Reviewer: Codex

## 1. Objective and user-visible outcome

- Objective: turn one validated Schema v2 `ProjectModel` into a deterministic, reviewable set of managed ARM GNU Toolchain, CMake, linker, and VS Code configuration files, then apply that set without overwriting user drift or touching any unplanned path.
- User-visible outcome: `plan_project_configuration(model)` is read-only and returns exact create/update/unchanged/drift decisions, byte digests, portable diffs, a deterministic plan ID, and blockers. `apply_project_configuration(plan)` either atomically installs the complete accepted configuration plus `.stm32-toolkit/generated-files.json`, or leaves all pre-existing bytes unchanged and returns one stable failure.
- Generated build configuration has exactly two presets, `arm-debug` and `arm-release`; consumes only facts already present in the model plus validated fixed-section evidence from the prior migration report; emits no guessed device startup code; and keeps every VS Code hardware action behind future Toolkit CLI commands rather than raw `pyocd` or shell snippets.
- Success boundary: an unowned collision or user-modified managed file is never overwritten; planning never writes; apply revalidates the model, inputs, target paths, prior manifest, plan integrity, and current bytes before its first write; recoverable failures leave no partial configuration or staging residue.

## 2. Scope

### 2.1 In scope

- Add a frozen generation plan/file/manifest model and stable error contract under `stm32_toolkit.generation`.
- Load Jinja templates only from packaged resources; root templates and packaged templates are byte-identical review copies.
- Generate deterministic UTF-8/LF files with exactly one final LF:
  - `CMakeLists.txt`;
  - `cmake/arm-none-eabi-gcc.cmake`;
  - `CMakePresets.json`;
  - `linker/stm32tk.ld`;
  - `.vscode/tasks.json`;
  - `.vscode/launch.json`;
  - `.vscode/c_cpp_properties.json`;
  - `.vscode/settings.json`;
  - `.vscode/extensions.json`;
  - the model-selected managed manifest, normally `.stm32-toolkit/generated-files.json`.
- Render project name, C/C++ and assembly sources, includes, defines, safe compile options, CPU/FPU/float ABI flags, memory regions, ELF/map/hex/bin outputs, and optional SVD using only validated model values.
- Consume `artifacts/migration/conversion-report.json` only when present. Validate and record its exact digest. Use only its `fixedSections` entries to generate `.stm32tk.abs.<ADDR8>` linker placements; ignore no malformed or conflicting entry.
- Treat absent migration evidence as valid when no `.stm32tk.abs.*` section is required. Never scan source text or infer fixed addresses.
- Record every generated file path, ownership, template version, and SHA-256 in the managed manifest.
- Classify targets as `create`, `unchanged`, `update-managed`, `user-drift`, or `unowned-collision` from exact bytes and the previous managed manifest.
- Preserve user drift: any `user-drift` or `unowned-collision` blocks the complete apply before staging.
- Stage, fsync, replace in sorted order, rollback byte/mode-exactly on recoverable failure, and retain recoverable backups only when rollback itself fails.
- Update `doctor` with bounded, read-only evidence for the three recommended VS Code extensions; update `setup-stm32-env` CHECK documentation only. Do not install or modify extensions/settings.
- Add `Jinja2>=3.1,<4` as the only new runtime dependency and package all runtime template resources.

### 2.2 Out of scope

- No compilation, CMake configure/build execution, firmware identity, MAP parsing, flash, probe, debug service, monitor, hardware, CLI/MCP adapter, release/version bump, or new Skill.
- No ARMCC conversion, source editing, framework conversion, `.uvprojx` editing, Keil invocation, CubeMX invocation, pack download, device database, network request, or tool installation.
- No generated chip startup/vector source. `build.assembly_sources` must already contain GCC-compatible assembly; missing target startup knowledge is never guessed.
- No automatic deletion of files that appear only in an older managed manifest. Such entries block with `GENERATION_ORPHANED_MANAGED_FILE` until a later explicit cleanup workflow exists.
- No change to `.stm32-project.json`, source/include/user directories, Git index/HEAD/config/remotes, unrelated `.vscode` files, or settings outside the exact generated settings keys.
- No recursive source discovery. Only model-declared paths are emitted.
- No raw `pyocd`, OpenOCD, GDB server, compiler, CMake, Ninja, PowerShell, Bash, or shell command in VS Code task configuration. Tasks call `stm32-toolkit` as a process with an argument array.
- No claimed operational debug handoff. Generated tasks are forward-compatible command declarations; the actual CLI/MCP and handoff state machine belong to later modules.

### 2.3 Prohibited shortcuts

- Do not overwrite an existing target merely because its bytes happen to equal the new proposal when it is not owned by the previous manifest.
- Do not trust caller-created frozen dataclasses, manifest hashes, plan IDs, prior ownership, or before/after bytes without recomputation at apply.
- Do not use `Path.write_text`, platform-default encoding/newlines, `shell=True`, command strings, `eval`, permissive Jinja undefined values, or ambient paths to locate templates.
- Do not accept absolute, drive-relative, UNC, NUL, `.`/`..`, empty-component, mixed-separator traversal, casefold-colliding, symlink, or NTFS-junction escaping paths.
- Do not interpolate unvalidated model strings into CMake, linker, JSON, or VS Code files.
- Do not use a generic recursive merge for user settings. The generated settings file is a complete owned file or a drift blocker.
- Do not add skip/xfail for a required pure-code gate, lower coverage, commit generated test output, or change paths outside section 5 plus the implementation report.

## 3. Prerequisites and fixed decisions

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Accepted product base: `8a627e95732bff069bef76e75c6b5f6fa992c6f4`. Branch from this exact commit. Do not merge, rebase, or cherry-pick the specification commit into the implementation branch.
- Before implementation, fetch `origin/master`; read `AGENTS.md`, `OPENCLAW_START_HERE.md`, this work order, the architecture, complete roadmap, 0.3 plan, and the implementation reports for `STM32TK-0301`, `0302`, and `0303`.
- Required upstream APIs are `load_project_model(Path) -> ProjectModel`, the frozen types in `stm32_toolkit.project_model`, `FixedSectionRequirement` semantics from `stm32_toolkit.migration`, `OperationResult`, and `stm32_toolkit.__version__`.
- Runtime baseline: CPython 3.10.11, `jsonschema==4.23.0`, `mcp==1.27.0`, `pyelftools==0.33`, `pytest==8.3.5`, and `pytest-cov==6.0.0`. Install one compatible Jinja2 3.1.x release and record the actual version. Declare the actual OS; do not claim an assumed distribution.
- Toolkit and template version remain `0.2.0` and `1` respectively. The unified 0.3.0 version bump belongs to Task 6.
- JSON output uses `indent=2`, `ensure_ascii=False`, insertion order defined below, UTF-8 without BOM, and one final LF.
- Portable paths always use `/`. Generated content uses `/` in CMake and JSON even on Windows.
- Visual acceptance is `NOT_APPLICABLE`; generated JSON/text is validated structurally and by exact snapshots.

## 4. Architecture and dependency direction

```text
ProjectModel + optional validated migration conversion report
  -> generation.managed_files (frozen values, ownership manifest, hashes)
  -> packaged StrictUndefined Jinja templates
  -> generation.configure (validation, rendering, deterministic plan)
  -> GenerationPlan                         # read-only boundary
  -> generation.configure.apply (fresh replan + atomic staging/rollback)
  -> managed CMake/linker/VS Code files + generated-files.json

doctor -> bounded `code --list-extensions --show-versions` evidence only
setup Skill -> describes CHECK evidence and manual remediation only
```

- `managed_files.py` owns frozen public values, portable path validation, canonical JSON/hashing, prior-manifest parsing, plan-ID computation, and stable exceptions. It performs no subprocess or network I/O.
- `configure.py` owns root/model revalidation, bounded input reads, fixed-section evidence validation, template loading/rendering, classification, fresh replan, staging, atomic replace, and rollback.
- Root template files are human-reviewable sources. Packaged copies are runtime resources and must be byte-identical. Runtime code uses `importlib.resources`, never repository-relative `__file__.parents[...]` discovery.
- `doctor.py` remains read-only and may invoke only bounded fixed-argv probes. Generation must not import doctor; doctor must not import generation.
- Upstream project/migration/result modules must not import generation. Later build/CLI/MCP modules may consume generation.

## 5. Exact file plan

Only the following implementation paths may differ from the accepted base:

| Status | Path | Responsibility |
|---|---|---|
| M | `tools/stm32-toolkit/pyproject.toml` | add Jinja2 range and package template JSON/Jinja/linker resources |
| A | `tools/stm32-toolkit/src/stm32_toolkit/generation/__init__.py` | re-export section 6 public contracts |
| A | `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py` | frozen values, hashes, portable paths, manifest and error validation |
| A | `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` | plan/render/classify/apply/stage/rollback orchestration |
| A | `templates/cmake/CMakeLists.txt.j2` | review copy of root CMake template |
| A | `templates/cmake/arm-none-eabi-gcc.cmake` | review copy of toolchain template |
| A | `templates/cmake/CMakePresets.json.j2` | review copy of preset template |
| A | `templates/cmake/linker.ld.j2` | review copy of linker template |
| A | `templates/vscode/tasks.json.j2` | review copy of Toolkit task template |
| A | `templates/vscode/launch.json.j2` | review copy of Cortex-Debug handoff template |
| A | `templates/vscode/c_cpp_properties.json.j2` | review copy of IntelliSense template |
| A | `templates/vscode/settings.json.j2` | review copy of owned VS Code settings |
| A | `templates/vscode/extensions.json` | exact three-extension recommendations |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/arm-none-eabi-gcc.cmake` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakePresets.json.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/linker.ld.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/vscode/tasks.json.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/vscode/launch.json.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/vscode/c_cpp_properties.json.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/vscode/settings.json.j2` | packaged byte-identical runtime resource |
| A | `tools/stm32-toolkit/src/stm32_toolkit/templates/vscode/extensions.json` | packaged byte-identical runtime resource |
| M | `tools/stm32-toolkit/src/stm32_toolkit/doctor.py` | bounded VS Code extension evidence |
| M | `skills/setup-stm32-env/SKILL.md` | document extension CHECK/manual remediation without mutation |
| A | `tools/stm32-toolkit/tests/test_generation.py` | all generation/model/template/security/atomicity tests |
| M | `tools/stm32-toolkit/tests/test_doctor.py` | extension evidence and bounded probe tests |

The implementation report is the only additional path:

- `docs/openclaw/returns/STM32TK-0304-GCC-CONFIG/r001-implementation-report.md`

Tests create disposable projects below pytest temporary directories. Do not commit fixture projects, rendered outputs, staging data, build trees, `.coverage`, caches, or generated manifests. Do not modify schemas, project/migration code, CLI/MCP, plugin version/runtime scripts, roadmap, architecture, or other Skills.

## 6. Public contracts

All public containers are `@dataclass(frozen=True)` and recursively immutable. Tuples replace lists. `to_dict()` returns a fresh JSON-safe mapping, uses portable paths, and omits `project_root`, `model`, and raw bytes.

### 6.1 Types and functions

```python
class GenerationError(Exception):
    code: str
    message: str
    details: dict[str, object]

@dataclass(frozen=True)
class GenerationInput:
    path: str
    sha256: str
    size: int

@dataclass(frozen=True)
class ManagedFileRecord:
    path: str
    ownership: str       # exactly "managed"
    template_version: int
    sha256: str

@dataclass(frozen=True)
class GeneratedFile:
    path: str
    status: str          # create|unchanged|update-managed|user-drift|unowned-collision
    template_name: str
    template_version: int
    before_sha256: str | None
    after_sha256: str
    before_size: int | None
    after_size: int
    unified_diff: str
    before_bytes: bytes | None   # omitted from to_dict()
    after_bytes: bytes           # omitted from to_dict()

@dataclass(frozen=True)
class GenerationBlocker:
    code: str
    path: str
    message: str

@dataclass(frozen=True)
class GenerationPlan:
    project_root: Path           # omitted from to_dict()
    model: ProjectModel          # omitted from to_dict()
    plan_version: int            # exactly 1
    plan_id: str                 # lowercase SHA-256
    model_sha256: str
    inputs: tuple[GenerationInput, ...]
    files: tuple[GeneratedFile, ...]
    blockers: tuple[GenerationBlocker, ...]
    managed_manifest_path: str
    managed_manifest_bytes: bytes  # omitted from to_dict()

def plan_project_configuration(model: ProjectModel) -> GenerationPlan: ...
def apply_project_configuration(plan: GenerationPlan) -> OperationResult[dict[str, object]]: ...
```

`generation.__init__` exports only the types and two functions above.

### 6.2 Serialization and plan identity

- `model_sha256` is SHA-256 over canonical JSON of every serializable ProjectModel field except `project_root`; UUID is stringified and tuples become arrays.
- `GenerationPlan.to_dict()` key order is `plan_version`, `plan_id`, `model_sha256`, `inputs`, `files`, `blockers`, `managed_manifest_path`.
- Generated file serialization includes metadata/digests/diff but not raw bytes.
- `plan_id` hashes canonical compact sorted-key JSON containing plan version, model hash, Toolkit version, template version, every input, every file metadata/status/digest, blockers, managed manifest path, and SHA-256 of the proposed manifest bytes. It excludes itself, absolute paths, raw bytes, and unified diffs.
- Ordering is bytewise portable path order for inputs/files/blockers. Duplicate or Unicode-casefold-colliding paths are invalid.
- All SHA values are lowercase 64-hex. Every serialized plan/report is bounded to 64 MiB.

## 7. Planning behavior

### 7.1 Model and project-root validation

- Require `type(model) is ProjectModel`, `schema_version == 2`, an existing canonical directory root, and a fresh `load_project_model(model.project_root)` whose canonical serialized model exactly equals the supplied model.
- Require `generation.tool == "stm32-toolkit"`, `generation.version == stm32_toolkit.__version__`, and `generation.managed_manifest == ".stm32-toolkit/generated-files.json"`. Other values return `GENERATION_MODEL_INVALID` with `{"field": ..., "rule": ...}`.
- Revalidate every model-declared source, assembly source, include directory, optional SVD, optional CubeMX IOC, and `.stm32-project.json` using portable lexical paths, canonical containment, `lstat`, and Windows reparse attributes. Source/assembly/SVD/IOC must be regular files; includes must be directories.
- Inputs include `.stm32-project.json`, all source/assembly files, optional SVD/IOC, optional prior managed manifest, and optional conversion report. Include directories are state-validated but not recursively hashed.
- Each file read is bounded to 8 MiB; aggregate inputs to 64 MiB. Read `limit + 1`. Only `FileNotFoundError`/`NotADirectoryError` establishes absence; permission and generic inspection failures reject conservatively.
- No error/details/to_dict value contains an absolute path, source bytes, environment value, username, stack trace, or host exception text.

### 7.2 Target and option validation

- Project name for CMake identifier is sanitized by replacing every non-ASCII `[A-Za-z0-9_]` with `_`, collapsing `_`, stripping `_`, prefixing `stm32_` if the result begins with a digit, and falling back to `stm32_firmware`. The original project name remains only a JSON string value.
- Supported cores and exact GCC CPU flags are:

| `target.core` | flag |
|---|---|
| `cortex-m0` | `-mcpu=cortex-m0` |
| `cortex-m0plus` | `-mcpu=cortex-m0plus` |
| `cortex-m3` | `-mcpu=cortex-m3` |
| `cortex-m4` | `-mcpu=cortex-m4` |
| `cortex-m7` | `-mcpu=cortex-m7` |
| `cortex-m23` | `-mcpu=cortex-m23` |
| `cortex-m33` | `-mcpu=cortex-m33` |

- Always add `-mthumb`, `-ffunction-sections`, and `-fdata-sections`. Debug adds `-Og -g3`; release adds `-O2 -g0` through preset build type/template logic.
- `fpu` and `float_abi` must be both absent or both present. Allowed ABI values are `soft`, `softfp`, `hard`. FPU must match ASCII `[A-Za-z0-9_.+-]+`. Emit `-mfpu=<fpu>` and `-mfloat-abi=<abi>` only when both exist.
- Defines must match `[A-Za-z_][A-Za-z0-9_]*(=.*)?`, contain no CR/LF/NUL/semicolon, and remain single CMake list atoms. Include/source paths are quoted as CMake arguments after escaping only `\`, `"`, and `;` in the controlled renderer.
- `compile_options` entries must start with `-`, be one token, and contain no whitespace, CR/LF/NUL, semicolon, quote, backslash, `$`, backtick, `@`, `SHELL:`, or generator expression. Reject rather than reinterpret unsafe options.
- Presets must be exactly `("arm-debug", "arm-release")` in this order. `build.elf` must equal `build/arm-debug/<basename>.elf`, where basename is one portable filename component ending `.elf`. Generation produces the release ELF with the same basename below `build/arm-release/`.
- Memory region names match `[A-Za-z_][A-Za-z0-9_]*`, ranges are non-overlapping unsigned 32-bit intervals, and at least one executable and one writable region exist. The first executable region is FLASH; the first writable region is RAM. Preserve model region order in the linker `MEMORY` block.

### 7.3 Fixed-section evidence

- If `artifacts/migration/conversion-report.json` is absent, fixed sections are empty.
- If present, it must be UTF-8 JSON object with `schemaVersion == 1`, `planId` and `gitHead` in their documented formats, and a `fixedSections` array. Ignore unrelated keys but never accept duplicate JSON keys.
- Each fixed section has exactly `section`, `address`, `sourcePath`, `line`, `symbol`; section must equal `.stm32tk.abs.<address:08x>`, address is `0..0xffffffff`, source path is a declared C/C++ source, line is positive, and symbol is a non-empty safe C identifier.
- Duplicate identical entries collapse deterministically. Conflicting section/address/symbol reuse returns `GENERATION_FIXED_SECTION_INVALID`.
- Each address must lie completely within one declared memory region. Linker output emits an absolute-address output section with `KEEP(*(<section>))` assigned to that region. No address or region is inferred from source text.

### 7.4 Exact generated contracts

- `CMakeLists.txt` starts with `cmake_minimum_required(VERSION 3.22)`, declares `project(<sanitized> LANGUAGES C CXX ASM)`, creates one ELF target, lists exact sources/assembly sources, includes/defines/options, links `linker/stm32tk.ld`, emits `<basename>.map`, and adds deterministic `.hex`/`.bin` post-build commands through `${CMAKE_OBJCOPY}`. No globbing or recursive discovery.
- `cmake/arm-none-eabi-gcc.cmake` sets `CMAKE_SYSTEM_NAME Generic`, `CMAKE_SYSTEM_PROCESSOR arm`, `CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY`, and exact compiler/binutil program names: `arm-none-eabi-gcc`, `g++`, `objcopy`, `size`. It contains no host absolute path.
- `CMakePresets.json` uses schema version 3 and contains exactly two configure presets plus matching build presets. Both use Ninja, `${sourceDir}/build/${presetName}`, the generated toolchain file, and `CMAKE_BUILD_TYPE` of `Debug` or `Release`. No environment values or host paths.
- `linker/stm32tk.ld` contains deterministic `MEMORY`, entry `Reset_Handler`, `.isr_vector`, `.text`, `.ARM.extab`, `.ARM.exidx`, `.data`, `.bss`, heap/stack symbols, and validated fixed sections. FLASH/RAM selections follow section 7.2. Do not invent vector contents or startup code.
- `.vscode/tasks.json` contains exact process tasks named `STM32 Toolkit: Build Debug`, `Build Release`, `Flash`, `Debug Handoff Begin`, and `Debug Handoff End`. Every task command is `stm32-toolkit`; args are arrays using `${workspaceFolder}`. No task contains `pyocd`, `cmake`, compiler commands, shell quoting, or `type: shell`.
- `.vscode/launch.json` contains one `cortex-debug` configuration named `STM32 Toolkit: Debug`, `request: launch`, `servertype: pyocd`, the model debug target, debug ELF, optional SVD, `preLaunchTask` equal to the handoff-begin task, and `postDebugTask` equal to handoff-end. If debug backend/target is absent or backend is not `pyocd`, return `GENERATION_MODEL_INVALID`; do not guess.
- `.vscode/c_cpp_properties.json` has one `arm-debug` configuration, compiler command `arm-none-eabi-gcc`, exact includes/defines, IntelliSense mode `gcc-arm`, and C/C++ standards `c11`/`c++17`.
- `.vscode/settings.json` is exactly the owned mapping `{"cmake.configureOnOpen": false, "cmake.useCMakePresets": "always"}`.
- `.vscode/extensions.json` recommends exactly and only `ms-vscode.cpptools`, `ms-vscode.cmake-tools`, and `marus25.cortex-debug`, in this order.
- JSON templates render native JSON booleans/null and arrays through a JSON filter; never build JSON by manual quoting.

## 8. Managed ownership and drift

### 8.1 Manifest format

The generated manifest is exactly:

```json
{
  "schemaVersion": 1,
  "tool": "stm32-toolkit",
  "toolVersion": "0.2.0",
  "templateVersion": 1,
  "projectManifestSha256": "<sha256>",
  "files": [
    {
      "path": "CMakeLists.txt",
      "ownership": "managed",
      "templateVersion": 1,
      "sha256": "<sha256>"
    }
  ]
}
```

- `files` contains the nine generated targets, sorted by portable path. It never contains the managed manifest itself.
- Reject unknown top-level/file keys, wrong types/versions/tool, duplicates, casefold collisions, unsafe paths, non-managed ownership, invalid hashes, or non-canonical ordering with `GENERATION_MANIFEST_INVALID` and portable details.
- The previous manifest is evidence only; planning never repairs it silently.

### 8.2 Classification

For each proposed target:

| Prior record | Current target | Classification |
|---|---|---|
| absent | absent | `create` |
| absent | exists | `unowned-collision` |
| present; current SHA = proposed SHA | exists | `unchanged` |
| present; current SHA = prior SHA; proposed differs | exists | `update-managed` |
| present; current SHA differs from prior SHA | exists | `user-drift` |
| present | absent | `update-managed` (recreate) |

- A prior manifest record absent from the new nine-target set adds `GENERATION_ORPHANED_MANAGED_FILE`; no deletion is proposed.
- Drift/collision/orphan blockers are all collected and sorted; apply returns `GENERATED_FILE_DRIFT` for any drift, otherwise `GENERATION_BLOCKED` for collision/orphan.
- The proposed new manifest is deterministic even when apply is blocked, so the user can review the intended ownership state.

## 9. Apply, forged-plan defense, and atomicity

- Apply accepts only the exact `GenerationPlan` type and validates every scalar, tuple, nested type, path, order, digest, raw byte size/hash, template name/version, status, blocker, managed manifest bytes, model hash, and recomputed plan ID.
- Re-resolve the canonical project root; reload the fresh model; re-read all inputs; re-render every template; re-read prior ownership/current targets; and require the fresh plan metadata and raw after bytes to match exactly.
- Repeat containment immediately before staging and each destination replace. Validate every existing destination with `lstat`; reject non-regular files and reparse escapes. Validate every absent destination conservatively.
- Staging is `.stm32-toolkit/configuration-staging/<plan_id>`. Reject any existing exact staging path and any intermediate symlink/junction/reparse escape before the first write.
- If blockers exist, return before staging. Apply writes the nine generated targets and managed manifest in portable sorted order.
- For each replacement, back up exact bytes and mode; for every new file, record it. Stage with exclusive creation, flush and `fsync`; create a sibling temporary file, flush/fsync, then `os.replace` and directory fsync where supported.
- On any stage/replace/fsync failure, restore replacements in reverse order, remove created targets and newly created empty parents, and remove staging. Return `GENERATION_APPLY_FAILED` with only `{"phase": "stage"|"replace"|"fsync"}`.
- If rollback cannot restore all targets, return `GENERATION_ROLLBACK_FAILED` with sorted portable `{"paths": [...]}` and retain recoverable staging/backups. This is the only failure allowed to retain staging.
- On success, remove staging and prune empty `configuration-staging` only; never remove `.stm32-toolkit` or unrelated contents.
- Success operation is `project-configuration-apply`, code `OK`, with JSON-safe data: `planId`, `modelSha256`, sorted `createdPaths`, `updatedPaths`, `unchangedPaths`, `managedManifestPath`, `managedManifestSha256`, and `templateVersion`.

## 10. Stable failures

Use exactly these public codes and bounded details:

| Code | Required use/details |
|---|---|
| `GENERATION_MODEL_INVALID` | wrong/stale/unsupported model; `field`, `rule` |
| `GENERATION_INPUT_INVALID` | missing/unreadable/non-regular/oversized model input; `path`, `rule` |
| `GENERATION_FIXED_SECTION_INVALID` | malformed/conflicting/out-of-region migration evidence; `path`, `rule` |
| `GENERATION_TEMPLATE_INVALID` | missing, mismatched, oversized, undefined, or invalid rendered resource; `template`, `rule` |
| `GENERATION_MANIFEST_INVALID` | malformed prior managed manifest; `path`, `rule` |
| `GENERATION_PATH_INVALID` | target/staging path escape or inspection failure; `path`, `rule: withinProjectRoot` |
| `GENERATED_FILE_DRIFT` | at least one user-drift target; `paths` sorted |
| `GENERATION_BLOCKED` | unowned collision or orphaned prior entry; `codes`, `paths` sorted |
| `GENERATION_PLAN_INVALID` | forged/inconsistent plan; `rule` |
| `GENERATION_INPUT_CHANGED` | model/input/current target changed since plan; `path` |
| `GENERATION_TARGET_EXISTS` | staging collision or creation race; `path` |
| `GENERATION_APPLY_FAILED` | recoverable mutation failure; only `phase` |
| `GENERATION_ROLLBACK_FAILED` | incomplete rollback; only sorted portable `paths` |

Messages are stable English summaries. Details never include exception text, absolute/temp paths, rendered content, source bytes, Git/config/environment output, or credentials.

## 11. Doctor and setup Skill

- `run_doctor` keeps existing `platform`, `project`, `tools`, and `mutated: false` fields and adds `vscodeExtensions`.
- When `code` exists, invoke exactly `[resolved_code, "--list-extensions", "--show-versions"]` through the existing bounded process machinery. Parse UTF-8 lines of `publisher.extension@version` case-insensitively, cap retained output at 8 KiB, and ignore malformed/unrelated lines.
- `vscodeExtensions` has exactly the three IDs as keys. Each value is `{"installed": bool, "version": str|null, "status": "ok"|"missing"|"unavailable"|"nonzero"|"timeout"|"error"}`.
- Missing `code` yields `unavailable` for all three. A failed probe never claims missing; it reports its failure status. Do not reveal the extensions directory or scan home/AppData directly.
- Doctor remains offline/read-only, launches no GUI, installs nothing, and never changes settings.
- `setup-stm32-env/SKILL.md` CHECK describes these exact three recommendations and tells the operator to install/remove extensions manually. Bootstrap/Repair boundaries and runtime version remain unchanged.

## 12. Security, limits, performance, and compatibility

- Template resource: 1 MiB each; generated file: 8 MiB each; all generated bytes plus manifest: 64 MiB; prior manifest/conversion report: 8 MiB; serialized plan: 64 MiB.
- Jinja environment uses `StrictUndefined`, no autoescape, no filesystem loader, and only explicit scalar/list context plus a deterministic JSON filter. Templates cannot access model objects, globals, environment, imports, attributes, callables, or host paths.
- Root/package template copies are byte-identical and SHA-256 checked by tests. Missing or mismatched resources fail closed.
- Planning and apply perform no network access and do not invoke compiler/CMake/Ninja/code. Only doctor invokes bounded `code` evidence.
- Plan performance fixture: 1,000 declared source paths and 100 fixed sections, 20 warm runs; plan median below 500 ms. Apply fixture: nine files, 10 fresh disposable projects; median below 1,000 ms. Record min/median/max, bytes, OS/filesystem/Python/Jinja versions. Do not add timing assertions to normal tests.
- Compatible hosts: Windows 10/11 and Linux, CPython 3.10+. Tests write exact bytes, use portable path component matching, and require no administrator privileges.
- Real NTFS junction escape and Windows atomic replace/rollback are Codex gates. Linux real symlink tests run without skip; simulated reparse tests supplement but do not replace the real Windows gate.

## 13. Required tests

### 13.1 TDD RED and focused command

Create `test_generation.py` first and run:

```powershell
python -m pytest tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_doctor.py -q
```

RED must fail only because generation APIs/resources and doctor extension evidence do not exist. Record exact command, exit, and collection/failure summary before implementation.

### 13.2 Generation coverage

Tests must cover:

- exact frozen public types, recursive immutability, fresh JSON-safe `to_dict`, deterministic model hash/plan ID/order, no absolute path/raw byte leakage;
- missing/wrong/stale Schema v2 model, wrong tool/version/manifest path, malformed target/core/FPU/ABI/preset/ELF/memory/define/option/path values;
- source/assembly/include/SVD/IOC missing, changed, oversized, unreadable, non-regular, NUL/traversal/drive/UNC, in-root redirect, redirect escape, `lstat`/resolve failures;
- duplicate/casefold-colliding paths and target names on POSIX and Windows semantics;
- root/package template identity, missing/corrupt/oversized template, StrictUndefined, escaping/JSON correctness, LF/final-newline determinism;
- exact CMake/toolchain/preset/linker snapshots for no-FPU and hard-FPU targets, paths with spaces, C++ and ASM sources, multiple memory regions, optional SVD, and absent CCM region;
- fixed-section report absent/valid, duplicate-identical, malformed JSON/UTF-8/duplicate keys, wrong types/schema/path/symbol/address, conflict, undeclared source, and out-of-region address;
- exact VS Code task names/process commands/args, no raw hardware/build commands, handoff pairing, optional SVD, exact settings and extension IDs;
- first plan read-only complete tree/mtime/mode snapshot; create classifications; apply exact bytes/modes/write set/manifest; second identical plan all unchanged and deterministic;
- managed template upgrade, missing managed target recreation, user drift, unowned equal/different collision, malformed manifest, orphan entry, and complete blocker aggregation;
- forged plan/model hash/ID/status/path/template/digest/bytes/diff/manifest/blocker/order/duplicate/casefold values rejected before writes;
- apply changed model/input/prior manifest/target/collision race, staging collision, target non-regular, target/staging symlink/reparse escape, and permission/inspection failures;
- exclusive create, file/directory fsync, replace failure at every destination position, exact reverse rollback, rollback failure with recoverable staging, cleanup, unrelated files, `.stm32-project.json`, Git state, and external targets untouched;
- `OperationResult.to_dict()` JSON serialization and absence of credentials/host paths in every failure;
- doctor exact extension parse, case/version/malformed/unrelated lines, missing/nonzero/timeout/error/overflow, fixed argv, no mutation, and unchanged existing evidence.

No new skip/xfail. Platform-adaptive tests must not depend on developer-mode symlink privileges.

### 13.3 Full gates

```powershell
python -m pytest tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_doctor.py -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check 8a627e95732bff069bef76e75c6b5f6fa992c6f4..HEAD
git diff --name-status 8a627e95732bff069bef76e75c6b5f6fa992c6f4..HEAD
git status --short
```

Expected: focused/full exit 0 with no failures/errors/new skips; total branch coverage at least 90%; compile/diff/status silent; only section 5 plus report changed; Jinja2 is the only dependency delta.

### 13.4 Environment evidence matrix

| Gate | Required environment | Owner | Expected | Deferred owner |
|---|---|---|---|---|
| TDD RED, focused GREEN | OpenClaw CPython 3.10.11 + exact deps/Jinja/Git | OpenClaw | expected RED then exit 0 | none |
| Full + branch coverage, compile, dependency, scope | same | OpenClaw | exit 0, branch >=90%, exact scope | none |
| Read-only plan, drift, atomicity, rollback, performance | same | OpenClaw | exact behavior and budgets | none |
| Root/package resource identity and installed-wheel resource load | fresh OpenClaw venv | OpenClaw | byte-identical; load succeeds outside repository | none |
| Windows focused/full, real NTFS junction, replace/rollback | Windows NT 10.0.26200.0, CPython 3.12.13 | Codex | exit 0, no new skip, exact behavior | `DEFERRED_TO_CODEX` only |
| Real CMake/GCC generated-fixture configure | Codex Windows; CMake 4.3.1, Ninja 1.13.2, installed ARM GNU toolchain | Codex | `cmake --preset arm-debug` exits 0 without host paths | `DEFERRED_TO_CODEX` only |
| VS Code GUI/extension installation | N/A | N/A | `NOT_APPLICABLE`; doctor is evidence only | none |

`PASS` means the named owner ran the gate against the returned code head. OpenClaw must not claim Codex Windows/toolchain evidence. A pure-code failure is never deferred.

## 14. Manual verification

OpenClaw must perform and report:

1. Snapshot every project entry's portable name, type, exact bytes/SHA-256, mode, and mtime plus Git HEAD/index/status/config/remotes. Run plan and prove the snapshot is identical.
2. Apply a first configuration and list the exact ten written paths; verify every byte/digest, preserved replacement mode, managed manifest, no staging, and no other state change.
3. Replan without edits and prove all nine targets are `unchanged`, plan/manifest bytes are deterministic, and apply performs no target replacement.
4. Modify one managed file after planning; prove `GENERATION_INPUT_CHANGED` or `GENERATED_FILE_DRIFT` as appropriate, with no write. Modify before planning; prove `user-drift` and complete refusal.
5. Place an unowned file whose bytes equal the proposal; prove `unowned-collision` still blocks.
6. Inject replace failure after at least one replacement and one creation; prove exact bytes/modes/status restored and staging absent. Inject rollback failure; prove portable paths and recoverable backup retention.
7. Forge a digest-consistent-looking plan with changed target/after bytes/status/blockers/manifest; prove `GENERATION_PLAN_INVALID` and no write.
8. Build/install a wheel in a fresh external venv, change cwd outside the repository, import generation, and produce a plan using packaged templates; record installed Jinja version and resource hashes.
9. Measure performance using section 12 fixtures and record dimensions and min/median/max.

Codex later performs Windows real junction/rollback and real CMake/GCC configure on the exact returned remote head.

## 15. Implementation sequence and commits

Use TDD and keep one branch/PR:

1. Commit RED tests/resources expectations: `test(STM32TK-0304): define managed generation contracts`.
2. Implement frozen values, templates, rendering, and plan: `feat(STM32TK-0304): plan deterministic GCC configuration`.
3. Implement ownership/drift and atomic apply: `feat(STM32TK-0304): apply managed configuration safely`.
4. Implement doctor/Skill evidence and close coverage: `feat(STM32TK-0304): report VS Code extension readiness`.
5. Commit the completed report separately after the code head: `docs(STM32TK-0304-GCC-CONFIG): r001 implementation report`.

Do not combine the tracked report with the code-head commit. The report records accepted base and code head before its own commit, but never its own final SHA or moving commit totals.

## 16. Return contract

Return exactly:

- Status: `IMPLEMENTED` or `BLOCKED`.
- Branch: `openclaw/STM32TK-0304-GCC-CONFIG/r001`.
- Base commit: `8a627e95732bff069bef76e75c6b5f6fa992c6f4`.
- Code head: full SHA before report commit.
- Final remote head: full out-of-band SHA.
- Draft PR or compare URL targeting `master`.
- Report path: `docs/openclaw/returns/STM32TK-0304-GCC-CONFIG/r001-implementation-report.md`.
- Accepted-base inventory and report-only addition.
- Actual environment/dependency versions, commands, exits, counts, branch coverage, resource hashes, manual/atomicity/performance evidence, and named deferred gates.
- Proof local HEAD equals remote implementation branch equals PR head; clean `git status --short`.

Push only the implementation branch. Do not push `master`, force-push, merge, approve, close, delete a branch, or create another attempt/PR without Codex direction.

## 17. Rejection conditions

Return `REVISION_REQUIRED` or `REWRITE_REQUIRED` when any applies:

- Planning writes, apply overwrites drift/collision, or any recoverable failure leaves partial output/staging.
- Runtime templates cannot load from an installed wheel outside the repository, or root/package copies differ.
- Generated content includes host absolute paths, unsafe model interpolation, raw `pyocd`/compiler/CMake task commands, shell tasks, guessed startup/vector/device data, or files outside the exact targets.
- Linker memory/fixed-section placement is guessed, conflicting, incomplete, or outside declared regions.
- Prior manifest, plan ID/digests/statuses, fresh model/input/target bytes, containment, or forged-plan defenses are not revalidated.
- `.stm32-project.json`, sources, `.uvprojx`, Git state, unrelated files/settings, extension installation, external targets, or user directories change.
- Doctor scans user directories, launches GUI, installs/modifies extensions, exposes private paths, or relabels a failed probe as missing.
- Dependency/scope differs, Jinja is not bounded/StrictUndefined, limits are absent, full tests fail, branch coverage is below 90%, or evidence/report ownership is inaccurate.

## 18. Completion checklist

- [ ] Exact accepted base, branch, scope, dependency, and ownership rules followed.
- [ ] Plan is deterministic/read-only and all public values are frozen/JSON-safe/portable.
- [ ] Templates are packaged, byte-identical, StrictUndefined, bounded, and render exact contracts.
- [ ] Model, input, option, memory, fixed-section, path, and target validation fail closed.
- [ ] Managed manifest classification preserves drift and blocks unowned/orphaned files.
- [ ] Apply freshly replans, rejects forgery/races, stages atomically, and rolls back exactly.
- [ ] VS Code files use only Toolkit process tasks and exact extension recommendations.
- [ ] Doctor/Skill report extension readiness without mutation or private path scanning.
- [ ] Focused/full/coverage/compile/dependency/scope/resource/manual/performance gates pass.
- [ ] Windows/toolchain evidence is truthfully assigned to Codex or deferred.
- [ ] Report contains accepted base and code head, not its own final SHA.
- [ ] Remote branch, PR head, local HEAD, and clean status are proven.
