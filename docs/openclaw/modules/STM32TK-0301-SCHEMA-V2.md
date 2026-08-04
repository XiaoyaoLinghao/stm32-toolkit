# STM32TK-0301-SCHEMA-V2: Project Schema v2 and Explicit Upgrade

Status: `READY_FOR_OPENCLAW`
Owner: OpenClaw implementation agent
Reviewer: Codex
Target branch: `master`
Base rule: fetched `master` commit containing this ready work order; record its full hash before branch creation
Implementation branch: `openclaw/STM32TK-0301-SCHEMA-V2/r001`

## 1. Objective and user-visible outcome

- Objective: add a version-dispatched immutable project model that reads Schema v1 and v2, and add a read-only-plan/digest-guarded v1→v2 upgrade API.
- User-visible outcome: existing v1 projects continue to load unchanged; callers can inspect a deterministic v2 upgrade plan and apply it only while the original manifest digest still matches.
- Success boundary: both schema copies remain byte-for-byte JSON-equivalent, all existing tests pass, new focused tests cover v1/v2/loading/upgrading/security, and no CLI/MCP or migration behavior is added in this module.

## 2. Scope

### 2.1 In scope

- Preserve the current Schema v1 as a separately addressable root and packaged schema.
- Make `stm32-project.schema.json` Schema v2.
- Add immutable public model types and `load_project_model(Path) -> ProjectModel`.
- Keep `ProjectManifest.load(project_root, schema_path=None)` source-compatible while allowing v1 and v2 default-schema dispatch.
- Add immutable `UpgradePlan`, `plan_project_upgrade(Path)`, and `apply_project_upgrade(UpgradePlan)`.
- Validate every project-relative path against the canonical project root, including existing symlink/junction parents.
- Add focused unit tests and keep the complete 0.2 test suite green with branch coverage at least 90%.

### 2.2 Out of scope

- Keil parsing, ARMCC conversion, CMake/VS Code generation, project creation, build, flash, probe, monitor, test runner, or diagnostic features.
- CLI or MCP commands for project upgrade; those belong to a later module.
- Package/plugin version bump from 0.2.0 to 0.3.0.
- Batch migration, an MCU database, Schema v3, or support for versions other than v1 and v2.
- Editing roadmap checkboxes or this work order.

### 2.3 Prohibited shortcuts and unrelated changes

- Do not silently rewrite a manifest while loading it.
- Do not accept unknown schema versions, unknown object properties, absolute project paths, or paths escaping the canonical root.
- Do not infer memory regions, presets, CubeMX files, SVD files, or generated directories from the filesystem.
- Do not weaken current deterministic error details or remove current v1 tests.
- Do not use Pydantic, a database, shell commands, external services, or new runtime dependencies.
- Do not modify agent instructions, approved plans/work orders, CI, packaging metadata, credentials, or remote policy.

## 3. Prerequisites and fixed decisions

- Base repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`; use the fetched `master` commit that contains this ready work order and record its full hash before branch creation.
- Runtime used for evidence: CPython 3.10.11.
- Exact test environment: `jsonschema==4.23.0`, `mcp==1.27.0`, `pytest==8.3.5`, `pytest-cov==6.0.0`.
- Declared compatibility remains Python 3.10 or newer, jsonschema in `[4.23, 5.0)`, mcp in `[1.27, 2.0)`, pytest in `[8.0, 9.0)`, and pytest-cov in `[5.0, 7.0)`.
- Prerequisite module: 0.2 foundation on the recorded base commit; no other OpenClaw module.
- Schema standard: JSON Schema Draft 2020-12.
- Serialization: UTF-8 without BOM, two-space JSON indentation, `ensure_ascii=False`, and exactly one trailing LF.
- Paths stored in `ProjectModel` remain project-relative strings for relocatability; loading validates them but does not require referenced files to exist.
- `ProjectManifest` remains the resolved-`Path` compatibility view used by current context code.
- Existing `OperationResult` from `stm32_toolkit.result` is the only apply-result envelope. A failure is asserted through `.code`/`.to_dict()`, not a new `.error` property.

## 4. Architecture and dependency direction

- Architecture position: project-schema/model layer below CLI, MCP, context, migration, generation, build, and hardware layers.
- Allowed dependencies: Python standard library, `jsonschema`, `stm32_toolkit.identity.canonical_project_root`, `stm32_toolkit.result.OperationResult`, and `stm32_toolkit.__version__`.
- Forbidden dependencies: CLI, MCP server, context, detection, hardware/probe code, monitor code, Jinja2, CMake, Git, network, or subprocesses.
- Data flow for load: canonical root → read JSON once → inspect integer `schemaVersion` → select packaged v1/v2 schema → validate → validate project-relative paths → construct frozen model.
- Data flow for upgrade plan: load raw v1 bytes → validate v1 → compute SHA-256 → add only defined v2 fields/defaults → validate proposed v2 → return a recursively immutable `UpgradePlan`; no filesystem writes.
- Data flow for apply: reread bytes → compare SHA-256 → revalidate proposed v2 → serialize → write sibling temporary file → flush and `fsync` file → `os.replace` manifest → return immutable result evidence. Directory `fsync` is required where the platform supports opening directories and is best-effort on Windows.

## 5. Exact file plan

| Path | Action | Responsibility | Allowed dependencies |
|---|---|---|---|
| `schemas/stm32-project-v1.schema.json` | create | frozen root Schema v1 snapshot | none |
| `schemas/stm32-project.schema.json` | modify | canonical root Schema v2 | none |
| `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project-v1.schema.json` | create | packaged Schema v1; JSON-equivalent to root v1 | none |
| `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json` | modify | packaged Schema v2; JSON-equivalent to root v2 | none |
| `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` | create | frozen model types, schema dispatch, path validation, stable model errors | stdlib, jsonschema, identity |
| `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py` | create | immutable upgrade plan, deterministic mapping, atomic digest-guarded apply | stdlib, project_model, result, package version |
| `tools/stm32-toolkit/src/stm32_toolkit/project.py` | modify | preserve `ProjectManifest`/`ProjectManifestError` imports and adapt v1/v2 models to resolved paths | project_model |
| `tools/stm32-toolkit/tests/test_project_model.py` | create | model/schema/path/compatibility tests | pytest, package APIs |
| `tools/stm32-toolkit/tests/test_project_upgrade.py` | create | read-only plan, mappings, digest, atomicity, errors, cleanup tests | pytest, package APIs |

No other path may change. If an exact-path contradiction is found, return `BLOCKED` in the implementation report; do not broaden the diff.

## 6. Public contracts

### 6.1 Frozen model types

All types use `@dataclass(frozen=True)` and tuples rather than mutable collections.

```python
@dataclass(frozen=True)
class ProjectInfo:
    name: str
    origin: str

@dataclass(frozen=True)
class TargetSpec:
    device: str
    core: str
    fpu: str | None
    float_abi: str | None
    device_pack: str | None

@dataclass(frozen=True)
class FrameworkSpec:
    type: str
    version: str | None

@dataclass(frozen=True)
class BuildSpec:
    sources: tuple[str, ...]
    include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    compile_options: tuple[str, ...]
    assembly_sources: tuple[str, ...]
    presets: tuple[str, ...]
    elf: str | None

@dataclass(frozen=True)
class MemoryRegion:
    name: str
    origin: int
    length: int
    attributes: str

@dataclass(frozen=True)
class MemorySpec:
    source: str
    regions: tuple[MemoryRegion, ...]

@dataclass(frozen=True)
class DebugSpec:
    backend: str | None
    target: str | None
    svd: str | None

@dataclass(frozen=True)
class GenerationSpec:
    tool: str
    version: str
    cube_mx_ioc: str | None
    managed_manifest: str
    generated_directories: tuple[str, ...]
    user_directories: tuple[str, ...]

@dataclass(frozen=True)
class ProjectModel:
    project_root: Path
    schema_version: int
    logical_project_id: UUID
    project: ProjectInfo
    target: TargetSpec
    framework: FrameworkSpec
    build: BuildSpec
    memory: MemorySpec
    debug: DebugSpec
    generation: GenerationSpec

def load_project_model(project_root: Path) -> ProjectModel: raise NotImplementedError
```

For a valid v1 manifest, `load_project_model` returns a normalized compatibility model without changing the file: `build.presets=()`, `memory.source` follows the mapping in section 6.3, `memory.regions=()`, and generation defaults match section 6.3. `generation.tool/version` for v1 compatibility are `stm32-toolkit` and the current imported package version.

`ProjectManifest`, `ProjectManifest.load`, and `ProjectManifestError` remain importable from `stm32_toolkit.project`. `ProjectManifest.load(project_root, schema_path=None)` retains all current fields and resolved-path behavior. With no explicit schema, it accepts v1 or v2. With an explicit schema path, it validates only against that supplied schema and then constructs the corresponding supported model; existing stable errors remain unchanged.

### 6.2 Schema v2

Schema v2 has these exact top-level required keys and rejects all others:

```json
[
  "schemaVersion", "logicalProjectId", "generatedBy", "project",
  "target", "framework", "build", "memory", "debug", "generation"
]
```

- `schemaVersion`: integer constant `2`.
- `logicalProjectId`: UUID-formatted string.
- `generatedBy`: closed object; required `tool` and `version`, both non-empty strings.
- `project`: existing closed object; required `name` and `origin`, both non-empty strings.
- `target`: existing closed object; required `device` and `core`; optional non-empty `fpu`, `floatAbi`, and `devicePack`.
- `framework`: existing closed object; required `type` enum `spl|hal|ll|cmsis|bare-metal`; required nullable `version`. A v1 document that omitted it upgrades to `null`.
- `build`: closed object; required `sources`, `includePaths`, `defines`, `compileOptions`, `assemblySources`, and `presets`; optional nullable `elf`. Arrays contain non-empty strings; `presets` is unique.
- `memory`: closed object; required `source` enum `keil|cubemx|manual` and `regions`. Each closed region requires non-empty `name`, integer `origin >= 0`, integer `length >= 1`, and `attributes` enum `r--|rw-|r-x|rwx`; region names are unique at model-validation time.
- `debug`: closed object; optional non-empty `backend`, optional non-empty `target`, and optional nullable non-empty `svd`. Missing v1 debug facts remain `null` in the model and are not invented during upgrade.
- `generation`: closed object; required nullable non-empty `cubeMxIoc`, required non-empty `managedManifest`, and required `generatedDirectories`/`userDirectories` arrays of unique non-empty strings.

Both v1 schemas must be JSON-equivalent to the base commit's current schema except for title/`$id` naming that identifies `stm32-project-v1.schema.json`. Both v2 schemas must be JSON-equivalent to each other.

### 6.3 Upgrade contracts

```python
@dataclass(frozen=True)
class UpgradePlan:
    manifest_path: Path
    source_sha256: str
    from_version: int
    to_version: int
    proposed: Mapping[str, object]

class ProjectUpgradeError(Exception):
    code: str
    message: str
    details: Mapping[str, object]

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object],
    ) -> None: raise NotImplementedError

def plan_project_upgrade(project_root: Path) -> UpgradePlan: raise NotImplementedError

def apply_project_upgrade(
    plan: UpgradePlan,
) -> OperationResult[Mapping[str, object]]: raise NotImplementedError
```

The v1→v2 proposed document preserves every existing v1 value and performs these exact field assignments:

| Field | Assigned value |
|---|---|
| `schemaVersion` | integer `2` |
| `generatedBy.tool` | string `stm32-toolkit` |
| `generatedBy.version` | imported `stm32_toolkit.__version__` |
| `framework.version` | existing v1 value, or JSON `null` when omitted |
| `build.presets` | empty array |
| `memory.source` | source mapping below |
| `memory.regions` | empty array |
| `generation.cubeMxIoc` | JSON `null` |
| `generation.managedManifest` | string `.stm32-toolkit/generated-files.json` |
| `generation.generatedDirectories` | empty array |
| `generation.userDirectories` | empty array |

Source mapping is exact: `project.origin == "keil-migration"` maps to `keil`; `project.origin == "cubemx"` maps to `cubemx`; every other accepted origin maps to `manual`.

`UpgradePlan.proposed` and nested containers are recursively immutable. Planning v2 returns `ProjectUpgradeError(code="PROJECT_UPGRADE_NOT_REQUIRED", details={"schemaVersion": 2})`. Missing/invalid manifests retain `ProjectManifestError`. Any other integer schema version returns `PROJECT_SCHEMA_VERSION_UNSUPPORTED` with `{"schemaVersion": value, "supported": [1, 2]}`.

Apply success uses operation `project.upgrade` and data:

```json
{
  "path": "ABSOLUTE_MANIFEST_PATH",
  "fromVersion": 1,
  "toVersion": 2,
  "sourceSha256": "SHA256_64_LOWERCASE_HEX",
  "resultSha256": "SHA256_64_LOWERCASE_HEX"
}
```

The uppercase values in the success example are runtime values and are never emitted literally. Apply never raises for expected operational failures:

| Condition | `OperationResult.code` | Details |
|---|---|---|
| manifest bytes changed/missing after plan | `PROJECT_CHANGED_SINCE_PLAN` | `path`, `expectedSha256`, and actual `observedSha256` or `null` |
| plan versions are not exactly 1→2 | `PROJECT_UPGRADE_PLAN_INVALID` | `fromVersion`, `toVersion` |
| proposed payload is not valid v2 | `PROJECT_UPGRADE_PLAN_INVALID` | `field`, `rule` |
| temporary write, flush, replace, or cleanup fails | `PROJECT_UPGRADE_IO_ERROR` | `path`, `stage` (`write|flush|replace|cleanup`) |

Messages are stable English summaries and must not expose exception text, temporary random names, home directories unrelated to the project, or file contents.

### 6.4 External interfaces

- No CLI, MCP, network, subprocess, hardware, environment-variable, or UI interface is added.
- No existing protocol version changes.

## 7. Behavior

### 7.1 State transitions

| Current state | Input/event | Next state | Side effects |
|---|---|---|---|
| valid v1 on disk | load model | valid v1 compatibility model | none |
| valid v2 on disk | load model | valid v2 model | none |
| valid v1 on disk | plan upgrade | immutable 1→2 plan | none |
| unchanged valid v1 + valid plan | apply | valid v2 on disk | one atomic manifest replacement |
| changed/deleted v1 + valid plan | apply | unchanged changed/deleted state | none; failure result |
| any manifest | invalid/tampered plan | unchanged manifest | none; failure result |
| v2 on disk | plan upgrade | not-required error | none |

Planning must leave the complete project tree byte-for-byte and metadata-equivalent. Apply may change only `.stm32-project.json`. Temporary siblings must be removed on success and every handled failure.

### 7.2 Validation and error handling

- `schemaVersion` must be an integer and exactly 1 or 2; booleans are not accepted as integers.
- Malformed JSON/UTF-8, missing manifests, unavailable schemas, and JSON Schema errors retain the existing stable error contract from `stm32_toolkit.project`.
- Every path field listed below is non-absolute and resolves within `canonical_project_root`: build sources/include paths/assembly sources/elf, debug SVD, generation CubeMX IOC/managed manifest/generated directories/user directories.
- Windows drive/UNC absolute forms and POSIX absolute forms must be rejected on both Windows and POSIX hosts, even when the host-native `Path` parser would treat the foreign form as relative.
- Duplicate memory-region names return `PROJECT_SCHEMA_INVALID`, field `memory.regions`, rule `uniqueRegionName`.
- Do not dereference target files or require them to exist; only canonical containment and existing-parent symlink/junction escape are checked.

### 7.3 Security and privacy

- Digest comparison uses SHA-256 over the exact original bytes.
- The upgrade plan contains only manifest-derived project facts and package version; it must not read source files, Git configuration, environment variables, probes, credentials, or plugin data.
- Temporary files use exclusive creation in the manifest directory with user-only permissions where supported.
- No exception `repr`, stack trace, source content, token, or unrelated absolute path enters `OperationResult`.

### 7.4 Performance, accessibility, and compatibility

- Performance budget: for a 100 KiB manifest with 1,000 source strings, median `load_project_model` and `plan_project_upgrade` time over 20 warm runs must each be below 100 ms on the declared test environment; record the measurements, but do not add a timing-fragile CI assertion.
- Memory budget: processing is O(manifest size); do not recursively scan the project tree.
- Accessibility/input behavior: no UI is present; deterministic English errors and structured details are required for AI and CLI adapters.
- Compatibility: Windows 10/11 and Linux path forms; Python 3.10+; existing v1 `ProjectManifest` callers and tests remain source-compatible.

## 8. Tests

### 8.1 Fixtures

Tests create manifests and project trees with `tmp_path`; no committed binary fixture is required. Use the current `tools/stm32-toolkit/tests/fixtures/valid-project.json` only as read-only v1 source data.

### 8.2 Required focused tests

`tools/stm32-toolkit/tests/test_project_model.py` must cover:

- exact frozen v1 compatibility model and zero writes;
- exact v2 model including memory regions, presets, ELF, SVD, generation metadata/directories;
- mutation attempts against every model tuple/dataclass fail;
- v1/v2 root and packaged schema equivalence;
- unsupported, missing, boolean, and malformed `schemaVersion` errors;
- unknown properties and duplicate memory region names;
- POSIX, Windows drive, UNC, `..`, symlink, and junction escape rejection;
- safe nonexistent in-root paths;
- existing `ProjectManifest.load` behavior for v1 and v2, including explicit schema-path tests.

`tools/stm32-toolkit/tests/test_project_upgrade.py` must cover:

- plan is read-only for bytes, names, mtimes, and tree inventory;
- exact origin mapping and all v2 defaults;
- proposed mapping is recursively immutable and valid against v2;
- v2 not-required and unsupported-version behavior;
- changed bytes, deletion, invalid plan versions, and invalid proposed payload fail without writes;
- successful atomic replacement, one trailing LF, expected digests, and reload as v2;
- injected write/flush/replace/cleanup failures return the specified code/stage, preserve or clearly retain the last valid manifest, and leave no temporary sibling;
- failure details do not contain injected exception text or unrelated environment paths.

### 8.3 TDD evidence

Before implementation, add the focused tests and run:

```powershell
python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q
```

Expected RED: collection fails because `stm32_toolkit.project_model` and `stm32_toolkit.project_upgrade` do not exist. Record the exact observed output in the implementation report. After implementation the same command must exit 0 with all collected tests passing and no new skip/xfail.

### 8.4 Required verification commands

Run from repository root in this order:

```powershell
python -m pip install -e "tools/stm32-toolkit[test]"
python -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_upgrade.py -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check "$baseCommit..HEAD"
git diff --name-status "$baseCommit..HEAD"
```

Expected: every command exits 0; focused/full suites have zero failures/errors; branch coverage is at least 90%; compileall is silent; diff check is silent; changed paths are exactly the nine paths in section 5 plus the required implementation report.

### 8.5 Manual verification

1. Copy `tools/stm32-toolkit/tests/fixtures/valid-project.json` into a disposable project as `.stm32-project.json` and record its SHA-256/tree inventory.
2. Call `plan_project_upgrade`; confirm no byte, path, or mtime changes and inspect the exact proposed v2 mapping.
3. Call `apply_project_upgrade`; confirm only the manifest changed, reload it through both public loaders, and verify the success evidence digests.
4. Repeat after changing one byte between plan/apply; confirm `PROJECT_CHANGED_SINCE_PLAN` and no upgrade write.

## 9. Artifacts and return evidence

OpenClaw must return:

- branch `openclaw/STM32TK-0301-SCHEMA-V2/r001`, full base/head commits, and PR/compare URL targeting `master`;
- report `docs/openclaw/returns/STM32TK-0301-SCHEMA-V2/r001-implementation-report.md` copied from `docs/openclaw/returns/implementation-report-template.md`;
- complete changed-path inventory reconciled with the base-to-head diff;
- exact dependency versions and OS used;
- RED test command/output summary and subsequent GREEN focused/full command results;
- branch-coverage percentage and missing-line output;
- performance measurement method and 20-run medians;
- SHA-256 values from the manual successful and digest-mismatch checks;
- known limitations/deviations, with no silent substitutions.

Do not commit `.coverage`, `htmlcov`, `__pycache__`, `.pytest_cache`, wheels, editable-install metadata, temporary manifests, or manual-test projects.

## 10. Acceptance checklist

- [ ] All nine product/test paths in section 5 have exactly the assigned responsibility.
- [ ] Schema v1 remains supported and frozen; Schema v2 matches section 6.2.
- [ ] Model types/signatures and compatibility view match section 6.1.
- [ ] Upgrade mapping/result/errors and atomicity match section 6.3.
- [ ] All validation, security, privacy, performance, and compatibility requirements pass.
- [ ] Focused and complete suites pass with branch coverage at least 90%.
- [ ] Implementation report matches the complete diff and evidence.
- [ ] No out-of-scope product, workflow, plan, or agent file changed.

## 11. Explicit rejection conditions

- Any required command fails, is omitted, or uses stale/unreconciled evidence.
- Any load/plan operation writes project state.
- Apply can overwrite a digest-mismatched manifest, leave a corrupt manifest, or silently accept an invalid plan.
- Schema copies diverge, v1 compatibility breaks, public contracts differ, or path escape validation is host-dependent.
- Mutable model/plan containers, new runtime dependencies, filesystem inference, project-tree scanning, or exception-detail leakage is introduced.
- Any path outside section 5 and the required implementation report changes.
- Credentials, private data, caches, build outputs, or unredacted diagnostics are committed.
- Correctable bounded failures produce `REVISION_REQUIRED`; OpenClaw updates the same `r001` branch and report.
- Fundamental architecture, safety, scope, or coverage violations produce `REWRITE_REQUIRED`; do not start `r002` until Codex issues a replacement instruction.

## 12. Dispatch readiness

This work order is `READY_FOR_OPENCLAW`: repository, base, branch, versions, paths, public contracts, defaults, errors, tests, evidence, and rejection conditions are resolved. OpenClaw must stop as `BLOCKED` rather than guess if the recorded base is unavailable or an exact-path contradiction exists.
