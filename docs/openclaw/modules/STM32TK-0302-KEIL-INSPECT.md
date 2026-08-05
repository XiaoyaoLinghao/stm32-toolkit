# STM32TK-0302-KEIL-INSPECT: Read-Only Keil Inspection and Baseline

Status: `READY_FOR_OPENCLAW`
Accepted base commit: `53321e8721cc479122c43285537dc108461a8e0e`
Default branch: `master`
Implementation branch: `openclaw/STM32TK-0302-KEIL-INSPECT/r001`
Specification owner: Codex
Implementer: OpenClaw
Reviewer: Codex

## 1. Objective and user-visible outcome

- Objective: add a deterministic, immutable, read-only inspection layer for one Keil MDK `.uvprojx` project and capture optional AXF/MAP baseline evidence without requiring Keil, ARM Compiler, a probe, or target hardware.
- User-visible outcome: callers can select one project and one target, inspect normalized build facts and ARMCC compatibility findings, and capture honest baseline evidence while the complete project tree remains byte-for-byte and metadata-equivalent.
- Success boundary: parsing, scanning, hashing, and baseline capture never write; ambiguous target/framework facts remain explicit; missing AXF/MAP artifacts are reported as unavailable rather than as zero measurements; all existing tests remain green with Python branch coverage at least 90%.

## 2. Scope

### 2.1 In scope

- Discover one root-level `.uvprojx`, or accept an explicit `.uvprojx` anywhere below the canonical project root, and select exactly one `<Target>`.
- Parse namespace-qualified and unqualified Keil XML with the standard library `xml.etree.ElementTree`.
- Extract target name, device, device pack, CPU/FPU/ABI facts, compiler family/version text, target/group/file options, sources, assembly sources, include paths, defines, linker inputs, scatter file, output paths, and IROM/IRAM regions.
- Normalize Keil Windows-style paths relative to the `.uvprojx` directory and return forward-slash paths relative to the canonical project root.
- Detect path escape, drive-qualified/UNC input, existing symlink/junction escape, malformed/unsafe XML, ambiguous project/target selection, unreadable sources, and bounded-resource violations with stable codes.
- Scan included C/C++/assembly files for the exact ARMCC constructs defined in section 6.3 without modifying source.
- Infer `spl`, `hal`, or `ll` only from at least two independent evidence categories; expose ambiguity/conflicts rather than guessing.
- Capture optional AXF ELF and Keil MAP evidence: hashes, sizes, entry point, allocatable sections, selected symbols, and program-size totals.
- Add `pyelftools>=0.33,<0.34` as the only new runtime dependency. Version 0.33 is the current Python 3.10+ release selected for this module.

### 2.2 Out of scope

- No source rewrite, ARMCC-to-GCC conversion, migration plan/apply, Git guard, `.stm32-project.json` write, CMake/VS Code generation, build, flash, debug, monitor, CLI command, MCP tool, or Skill.
- No `.uvproj`, `.uvmpw`, `.cprj`, IAR, STM32CubeIDE, ArmClang conversion, multi-project batch inspection, or all-device compatibility database.
- No invocation of Keil/UV4, compiler, linker, `fromelf`, CMake, Ninja, Git mutation, network service, probe, or hardware.
- No claim that the repository fixture is the user's final real Keil project; real-project/board acceptance remains a later gate.
- No new schema, collaboration automation, report validator, CI workflow, binary fixture, or generated artifact.

### 2.3 Prohibited shortcuts and unrelated changes

- Do not modify `.uvprojx`, source, AXF, MAP, `.stm32-project.json`, mtimes, permissions, Git index, or untracked project contents.
- Do not resolve ambiguity by selecting the first target, first project, or first framework candidate.
- Do not treat missing/unreadable/corrupt artifacts as valid zero-valued evidence.
- Do not parse XML with regex, enable external entities, follow paths outside the canonical root, or return host exception text/stack traces.
- Do not add fallback encodings for source files; UTF-8 and UTF-8 with BOM are accepted, and other encodings produce an explicit warning/blocker.
- Do not change files outside section 5 plus the required implementation report.

## 3. Prerequisites and fixed decisions

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Accepted product base: `53321e8721cc479122c43285537dc108461a8e0e`; branch from this exact commit. Do not merge, rebase, or cherry-pick the specification commit into the implementation branch.
- Before implementation, fetch `origin/master`, read `AGENTS.md`, then `OPENCLAW_START_HERE.md`, this work order, the architecture, the complete roadmap, and the 0.3 plan.
- Runtime: CPython 3.10.11; `jsonschema==4.23.0`, `mcp==1.27.0`, `pyelftools==0.33`, `pytest==8.3.5`, and `pytest-cov==6.0.0` for evidence. Declare the actual OS; do not substitute an assumed distribution.
- Use only Python standard library plus the dependencies declared in `tools/stm32-toolkit/pyproject.toml`.
- Keil documents `.uvprojx` as the XML project file and ships `PROJECT_PROJX.XSD` with MDK; this module implements only the bounded fields in section 6, not a replacement for the complete XSD.
- Reference sources: `https://www.keil.com/support/man/docs/uv4/uv4_b_filetypes.asp` for the project-file/XSD contract and `https://pypi.org/project/pyelftools/0.33/` for the selected ELF parser release.
- The existing `load_project_model` contract is an upstream dependency but is not modified or called by this module.
- Visual acceptance does not apply.

## 4. Architecture and dependency direction

```text
canonical project root
  -> keil.uvprojx (bounded XML bytes, selection, path normalization)
  -> keil.model (frozen inspection contracts)
  -> keil.armcc_scan (read-only compatibility findings + framework evidence)
  -> KeilInspection
  -> keil.baseline (optional AXF/MAP evidence using pyelftools)
  -> KeilBaseline
```

- `model.py` contains public immutable values and stable exceptions only; it performs no I/O.
- `uvprojx.py` owns project discovery, XML parsing, target selection, option extraction, path validation, input hashing, and orchestration of the scanner.
- `armcc_scan.py` owns bounded source reads, ARMCC pattern classification, and framework evidence; it receives normalized paths and never discovers files itself.
- `baseline.py` owns AXF/MAP reads and parsing; it consumes only paths already validated in `KeilInspection`.
- Later migration code may consume `KeilInspection`; this module must not depend on future migration/generation/build layers.

## 5. Exact file plan

Only these implementation paths may differ from the accepted base:

| Status | Path | Responsibility |
|---|---|---|
| M | `tools/stm32-toolkit/pyproject.toml` | add only `pyelftools>=0.33,<0.34` |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/__init__.py` | re-export the public contracts/functions in section 6 |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/model.py` | frozen public models, JSON-safe `to_dict`, stable errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py` | safe XML parsing, selection, extraction, path normalization, inspection orchestration |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` | bounded source scan, compatibility findings, framework inference |
| A | `tools/stm32-toolkit/src/stm32_toolkit/keil/baseline.py` | AXF/MAP artifact parsing and baseline assembly |
| M | `tools/stm32-toolkit/tests/fixtures/keil-project/legacy.uvprojx` | representative single-target Keil MDK XML fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Common/common.c` | UTF-8 ARMCC scan fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Main/main.c` | framework/source fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Startup/startup_stm32f4xx.s` | assembly-path fixture |
| A | `tools/stm32-toolkit/tests/fixtures/keil-project/Objects/legacy.map` | text-only Keil MAP baseline fixture |
| A | `tools/stm32-toolkit/tests/test_keil_inspect.py` | discovery/XML/selection/path/scanner/framework/read-only tests |
| A | `tools/stm32-toolkit/tests/test_keil_baseline.py` | AXF/MAP/missing/corrupt/read-only baseline tests |

The implementation report is the only additional path:

- `docs/openclaw/returns/STM32TK-0302-KEIL-INSPECT/r001-implementation-report.md`

Do not change the 0.3 plan checkbox, roadmap, architecture, existing project model, CLI, MCP, schemas, Skills, setup scripts, or unrelated fixtures from the implementation branch.

## 6. Public contracts

All containers below are `@dataclass(frozen=True)` and use tuples rather than mutable lists. Every `to_dict()` returns a fresh JSON-safe mapping with repository-relative paths only.

### 6.1 Inspection contracts

```python
class KeilInspectionError(Exception):
    code: str
    message: str
    details: dict[str, object]

@dataclass(frozen=True)
class KeilInputDigest:
    path: str
    sha256: str
    size: int

@dataclass(frozen=True)
class KeilMemoryRegion:
    name: str              # IROM1, IROM2, IRAM1, IRAM2
    origin: int
    length: int
    attributes: str        # r-x for IROM, rwx for IRAM

@dataclass(frozen=True)
class KeilScopedOptions:
    scope: str             # target, group, or file
    owner: str             # target/group name or source path
    include_in_build: bool
    defines: tuple[str, ...]
    include_paths: tuple[str, ...]
    misc_controls: tuple[str, ...]

@dataclass(frozen=True)
class KeilSource:
    path: str
    group: str
    language: str          # c, cxx, asm, header, library, or other
    included: bool

@dataclass(frozen=True)
class KeilOutputSpec:
    object_directory: str | None
    listing_directory: str | None
    output_name: str | None
    axf: str | None
    map_file: str | None
    scatter_file: str | None

@dataclass(frozen=True)
class KeilEvidence:
    category: str          # define, include, or path
    value: str
    framework: str         # spl, hal, or ll

@dataclass(frozen=True)
class KeilFinding:
    rule_id: str
    severity: str          # info, warning, or blocker
    path: str
    line: int
    column: int
    evidence: str          # trimmed to at most 200 Unicode code points
    message: str

@dataclass(frozen=True)
class KeilWarning:
    code: str
    message: str
    details: tuple[tuple[str, object], ...]

@dataclass(frozen=True)
class KeilInspection:
    project_root: Path
    project_file: str
    project_sha256: str
    target_name: str
    device: str
    device_pack: str | None
    cpu: str
    fpu: str | None
    float_abi: str | None
    compiler: str          # armcc, armclang, or unknown
    compiler_version: str | None
    defines: tuple[str, ...]
    include_paths: tuple[str, ...]
    sources: tuple[KeilSource, ...]
    scoped_options: tuple[KeilScopedOptions, ...]
    linker_inputs: tuple[str, ...]
    memory_regions: tuple[KeilMemoryRegion, ...]
    output: KeilOutputSpec
    framework: str | None
    framework_candidates: tuple[str, ...]
    framework_evidence: tuple[KeilEvidence, ...]
    findings: tuple[KeilFinding, ...]
    warnings: tuple[KeilWarning, ...]
    inputs: tuple[KeilInputDigest, ...]

def inspect_keil(
    root: Path,
    uvprojx: Path | None = None,
    target_name: str | None = None,
) -> KeilInspection: ...
```

- `project_root` is the canonical absolute root for internal identity; every serialized path is relative and uses `/`.
- Dataclass container fields, including `KeilWarning.details`, are recursively immutable. `KeilInspectionError` copies caller details on construction. Serialized representations use only JSON scalars, mappings, and arrays.
- `sources` preserves target/group/file order. Exact duplicate paths keep their first occurrence and produce `KEIL_DUPLICATE_SOURCE` warning evidence for later occurrences.
- `defines`, `include_paths`, `linker_inputs`, and evidence preserve first-seen order with stable deduplication.
- `inputs` contains the `.uvprojx` and each readable included C/C++/assembly/scatter input, sorted by normalized path. Hashes use SHA-256 over exact bytes.
- `__init__.py` re-exports every type above, `KeilBaseline` types below, `inspect_keil`, and `capture_keil_baseline`.

### 6.2 XML extraction and normalization

- Accept XML with or without namespaces by comparing expanded-element local names; never assume a fixed namespace prefix.
- Read at most 8 MiB of `.uvprojx` bytes. Reject case-insensitive `<!DOCTYPE` or `<!ENTITY` before parsing. Parse bytes so a valid XML encoding declaration is honored.
- Project discovery with `uvprojx=None` examines only `root/*.uvprojx`, sorted by case-folded repository-relative name. Zero matches returns `KEIL_PROJECT_NOT_FOUND`; more than one returns `KEIL_PROJECT_SELECTION_REQUIRED` with only the sorted relative candidates.
- `root` must be a `Path` naming an existing canonical directory. Other types, missing paths, files, NUL values, and canonicalization/inspection failures return `KEIL_PROJECT_PATH_INVALID` without a raw host exception.
- An explicit `uvprojx` must be a `Path`, must name a `.uvprojx` file within the canonical root, and may be absolute or root-relative. Missing/unreadable input returns a stable error.
- Target selection uses `<Targets>/<Target>/<TargetName>`. Zero valid targets returns `KEIL_TARGET_INVALID`. Multiple targets without `target_name` returns `KEIL_TARGET_SELECTION_REQUIRED` with sorted names. A missing requested name returns `KEIL_TARGET_NOT_FOUND`. Matching is exact and case-sensitive.
- Required selected-target facts are non-empty `<Device>` and a parseable `CPUTYPE("...")` from `<Cpu>`; missing values return `KEIL_TARGET_INVALID` with `field` set to `device` or `cpu`.
- Record `<PackID>` when present. Record the compiler/version from `<pCCUsed>`/toolchain fields without inventing a version. Recognize ARM Compiler 5 as `armcc` and Arm Compiler 6 as `armclang`; otherwise use `unknown` plus `KEIL_COMPILER_UNKNOWN`.
- Parse `IROM`, `IROM2`, `IRAM`, and `IRAM2` from the `<Cpu>` expression and/or target memory fields. Integer values accept decimal or `0x` hexadecimal. Omit a region with length zero. Conflicting duplicate definitions return `KEIL_MEMORY_CONFLICT`; malformed non-empty values return `KEIL_TARGET_INVALID`.
- Target options come from `TargetArmAds/Cads/VariousControls` and linker options from `LDads`. Record group/file option blocks separately in `scoped_options`; do not silently flatten overrides into target options.
- Parse defines separated by comma or semicolon after trimming. Parse include paths separated by semicolon. Preserve a non-empty misc-control string as one tuple item; do not shell-split it.
- Determine language by `FileType` when recognized and otherwise by case-insensitive suffix: `.c`, `.cc/.cpp/.cxx`, `.s/.asm`, `.h/.hpp`, `.a/.lib`, or `other`. `IncludeInBuild=0` marks the source excluded.
- Derive output candidates from `OutputDirectory`, `OutputName`, `ListingPath`, and scatter-file settings. `.axf` and `.map` candidates remain optional and are never required by inspection.
- Convert both `\` and `/` separators. Keil paths are relative to the `.uvprojx` directory; normalize `.` and `..`, then require containment in the canonical root. Reject POSIX absolute, UNC, drive-absolute, and drive-relative forms on every host.
- Existing symlink or Windows reparse-point traversal must resolve within the canonical root. `PermissionError` or another non-missing inspection failure rejects conservatively. Missing in-root source/include paths are retained with warnings and are never created.

### 6.3 ARMCC scan and framework inference

Scan only readable, included C/C++/assembly files named by the selected target. Limit each file to 8 MiB and all scanned bytes to 64 MiB. Decode only UTF-8/UTF-8-BOM. Findings are sorted by `(path, line, column, rule_id)`.

| Rule ID | Detection | Severity |
|---|---|---|
| `ARMCC_IRQ_QUALIFIER` | token `__irq` | warning |
| `ARMCC_INTRINSIC_NOP` | call `__nop(...)` | warning |
| `ARMCC_INTRINSIC_WFI` | call `__WFI(...)` or `__wfi(...)` | warning |
| `ARMCC_INLINE_ASSEMBLY_FUNCTION` | `__asm` used as a function declaration/body, not a string literal | blocker |
| `ARMCC_ABSOLUTE_PLACEMENT` | `__attribute__((at(...)))`, `__at(...)`, or equivalent ARMCC absolute placement | blocker |
| `ARMCC_SCATTER_FILE` | non-empty scatter-file linker setting | warning at the scatter path, line/column zero |
| `ARMCC_CUSTOM_SECTION` | `section(...)`, `#pragma arm section`, or named section linker input | warning |
| `ARMCC_UNSUPPORTED_PRAGMA` | `#pragma` beginning with `arm`, `import`, or `O` that is not classified above | blocker |

- Matching must ignore comments and ordinary string/character literal contents for token rules. A lightweight lexical state machine is required; raw regex over the complete file is not sufficient.
- Evidence is the source line with leading/trailing whitespace removed and capped at 200 code points. Never include absolute paths or exception text.
- Missing source: warning `KEIL_SOURCE_MISSING`; unreadable source: warning `KEIL_SOURCE_UNAVAILABLE`; unsupported encoding: blocker finding `ARMCC_SOURCE_ENCODING_UNSUPPORTED` with empty evidence; resource cap: `KEIL_SCAN_LIMIT_EXCEEDED` error.
- Framework evidence categories are independent: `define`, `include`, and `path`. Recognize only:
  - SPL: `USE_STDPERIPH_DRIVER`, `STM32F*_StdPeriph_Driver`, or a path component `Libraries/STM32*_StdPeriph_Driver`.
  - HAL: `USE_HAL_DRIVER`, include basename `stm32*_hal.h`, or path component `Drivers/STM32*_HAL_Driver`.
  - LL: define matching `USE_FULL_LL_DRIVER`, include basename `stm32*_ll_*.h`, or path component `Drivers/STM32*_HAL_Driver` together with an `_ll_` source/include basename.
- Select `framework` only when exactly one candidate has evidence from at least two distinct categories. Otherwise set it to `None`, populate sorted `framework_candidates`, and append `KEIL_FRAMEWORK_SELECTION_REQUIRED`. Never infer from the device family alone.

### 6.4 Baseline contracts

```python
@dataclass(frozen=True)
class KeilArtifactEvidence:
    path: str | None
    available: bool
    sha256: str | None
    size: int | None

@dataclass(frozen=True)
class KeilSectionEvidence:
    name: str
    address: int
    size: int
    flags: int

@dataclass(frozen=True)
class KeilSymbolEvidence:
    name: str
    address: int
    size: int | None
    section: str | None

@dataclass(frozen=True)
class KeilProgramSize:
    code: int
    ro_data: int
    rw_data: int
    zi_data: int
    flash: int             # code + ro_data + rw_data
    ram: int               # rw_data + zi_data

@dataclass(frozen=True)
class KeilBaseline:
    available: bool
    axf: KeilArtifactEvidence
    map_file: KeilArtifactEvidence
    entry_point: int | None
    sections: tuple[KeilSectionEvidence, ...]
    symbols: tuple[KeilSymbolEvidence, ...]
    program_size: KeilProgramSize | None
    warnings: tuple[KeilWarning, ...]

def capture_keil_baseline(root: Path, inspection: KeilInspection) -> KeilBaseline: ...
```

- Require `root` to canonicalize to `inspection.project_root`; otherwise raise `KEIL_INSPECTION_ROOT_MISMATCH` before reading artifacts.
- Accept only the validated relative AXF/MAP candidates recorded in `inspection.output`; revalidate containment and existing-link behavior before every read.
- Hash exact artifact bytes with SHA-256. Limit AXF to 256 MiB and MAP to 32 MiB.
- Parse ELF with `elftools.elf.elffile.ELFFile`. Record `e_entry`, all non-empty `SHF_ALLOC` sections sorted by `(address, name)`, and these symbols when present: `__Vectors`, `Reset_Handler`, `SystemInit`, `main`, `HardFault_Handler`.
- Parse the Keil MAP line `Program Size: Code=<n> RO-data=<n> RW-data=<n> ZI-data=<n>` with arbitrary horizontal whitespace and decimal values. More than one conflicting summary or overflow beyond unsigned 64-bit returns `KEIL_MAP_INVALID`.
- Missing AXF or MAP yields an unavailable artifact and `KEIL_BASELINE_ARTIFACT_MISSING`; the baseline may still be partially available. `available` is true when at least one artifact parsed successfully.
- An existing malformed/truncated/non-ELF AXF returns `KEIL_AXF_INVALID`; an unreadable existing artifact returns `KEIL_BASELINE_ARTIFACT_UNAVAILABLE`. Do not downgrade corrupt evidence to missing.
- `capture_keil_baseline` performs no directory discovery and never invokes external processes.

### 6.5 Stable errors

All raised errors are `KeilInspectionError(code, message, details)`. Details contain only stable fields, relative paths, sizes, limits, requested names, or candidate names.

| Code | Required details |
|---|---|
| `KEIL_PROJECT_NOT_FOUND` | `{"pattern": "*.uvprojx"}` |
| `KEIL_PROJECT_SELECTION_REQUIRED` | `{"candidates": [...]}` |
| `KEIL_PROJECT_PATH_INVALID` | `{"field": "projectRoot", "rule": "directory"}` for a bad root, or `{"field": "uvprojx", "rule": "withinProjectRoot"}` for a bad explicit project path |
| `KEIL_PROJECT_UNAVAILABLE` | `{"path": <relative-or-name>}` |
| `KEIL_XML_UNSAFE` | `{"rule": "doctypeOrEntity"}` |
| `KEIL_XML_LIMIT_EXCEEDED` | `{"limitBytes": 8388608}` |
| `KEIL_XML_INVALID` | `{"path": <relative>, "line": <int>, "column": <int>}` when available |
| `KEIL_TARGET_SELECTION_REQUIRED` | `{"targets": [...]}` |
| `KEIL_TARGET_NOT_FOUND` | `{"targetName": <requested>, "targets": [...]}` |
| `KEIL_TARGET_INVALID` | `{"field": <stable-field>, "rule": <stable-rule>}` |
| `KEIL_MEMORY_CONFLICT` | `{"region": <name>}` |
| `KEIL_PATH_OUTSIDE_PROJECT` | `{"field": <XML logical field>, "rule": "withinProjectRoot"}` |
| `KEIL_SCAN_LIMIT_EXCEEDED` | `{"limitBytes": <int>, "scope": "file" or "inspection"}` |
| `KEIL_INSPECTION_ROOT_MISMATCH` | `{"field": "projectRoot"}` |
| `KEIL_BASELINE_ARTIFACT_UNAVAILABLE` | `{"artifact": "axf" or "map", "path": <relative>}` |
| `KEIL_AXF_INVALID` | `{"path": <relative>, "rule": "elf"}` |
| `KEIL_MAP_INVALID` | `{"path": <relative>, "rule": <stable-rule>}` |

## 7. Behavior, security, and performance

### 7.1 State and determinism

| Operation | Before | Result | Writes |
|---|---|---|---|
| inspect valid project/target | project tree exists | frozen `KeilInspection` | none |
| ambiguous discovery/target | multiple candidates | stable selection error | none |
| scan missing source | selected target references missing file | inspection plus warning | none |
| capture with no artifacts | output candidates absent | `available=false` plus warnings | none |
| capture partial artifacts | one valid artifact exists | partial baseline, `available=true` | none |
| malformed existing AXF/MAP | corrupt evidence exists | stable error | none |

- Repeated calls over unchanged bytes return equal serialized values except `project_root`, which is a stable canonical path and is omitted from portable serialized evidence.
- No timestamps are generated in this module.
- Planning/capture must leave bytes, file names, directory entries, mtimes, and permissions unchanged.

### 7.2 Security and privacy

- Reject DTD/entity declarations before XML parse; never fetch external resources.
- Reject path escape under both Windows and POSIX syntax on every host, including drive-relative `D:file.c`, UNC, mixed separators, symlinks, and NTFS junctions.
- Only confirmed `FileNotFoundError`/`NotADirectoryError` may be treated as missing. Permission and inspection failures are not safe fast paths.
- Do not recursively scan source trees; read only files referenced by the selected target and the two output artifact candidates.
- Do not read `.git`, environment variables, credentials, user configuration, unrelated source files, or file contents beyond the declared caps.
- `to_dict`, warnings, findings, and errors contain no host exception string, stack trace, source content beyond capped evidence, credential, unrelated absolute path, or temporary-directory path.

### 7.3 Performance and compatibility

- For a generated 1 MiB `.uvprojx` with exactly 1,000 file nodes and 100 referenced UTF-8 source files of 1 KiB each, median `inspect_keil` time over 20 warm runs must be below 500 ms on the declared OpenClaw environment.
- For a generated 2 MiB valid ELF plus 2 MiB MAP, median `capture_keil_baseline` time over 20 warm runs must be below 500 ms on the declared environment.
- Record fixture sizes, warm-up count, run count, medians, and min/max values; do not add timing-fragile CI assertions.
- Memory use is O(XML + referenced inputs + artifact size within caps); do not load unrelated project data.
- Compatibility: Windows 10/11 and Linux path forms; CPython 3.10+; namespace-qualified Keil MDK 5 XML; ARM Compiler 5 inspection. ArmClang is identified but conversion support is not claimed.
- Accessibility/input: no UI; stable English messages and structured fields are required for later CLI/MCP adapters.

### 7.4 Visual acceptance gate

- Applies: `NO`.
- Fixture/route/viewport: `N/A`.
- Evidence owner: `N/A`.
- Expected result: no UI, visual asset, or rendered output is created; screenshots are not implementation evidence.

## 8. Tests and environment evidence

### 8.1 Required environment evidence matrix

| Gate | Exact command/action | Required environment | Evidence owner | Expected result | Deferred owner if unavailable |
|---|---|---|---|---|---|
| TDD RED | focused pytest command before implementation | OpenClaw; CPython 3.10.11; exact deps | OpenClaw | collection fails only because `stm32_toolkit.keil` APIs do not exist | none |
| Focused GREEN | focused pytest command after implementation | same | OpenClaw | exit 0; no new skip/xfail | none |
| Full suite + branch coverage | full command in 8.4 | same | OpenClaw | exit 0; branch coverage >=90% | none |
| Compile | compileall command | same | OpenClaw | exit 0, silent | none |
| Dependency | pip metadata/import check | same | OpenClaw | pyelftools 0.33, no other dependency change | none |
| Read-only tree | manual step 8.5 | same | OpenClaw | bytes/names/mtimes/permissions identical | none |
| Performance | section 7.3 fixtures | same | OpenClaw | both medians <500 ms | none |
| Windows compatibility | focused/full tests plus real NTFS junction source path | Windows NT 10.0.26200.0; CPython 3.12.13 | Codex | exit 0; junction escape rejected without skip | may be `DEFERRED_TO_CODEX` only |
| Visual/UI | no action | N/A | N/A | `NOT_APPLICABLE` | none |

`PASS` means the named owner ran the gate against the returned code head. A pure code failure is never deferred. OpenClaw must not attribute Codex Windows evidence to itself.

### 8.2 Required focused tests

`test_keil_inspect.py` must cover:

- representative namespace-qualified single-target fixture exact extraction and frozen/tuple immutability;
- exact `to_dict()` shape without absolute paths;
- no project, multiple projects, explicit project, malformed/non-object `Path`, missing file, unsafe DTD/entity, malformed XML, and 8 MiB cap;
- zero/one/multiple targets, exact selection, missing requested target, missing device/CPU, namespace variants;
- target/group/file option separation, exclusion from build, stable deduplication/order, compiler family/version, IROM/IRAM parsing/conflict/zero-length behavior;
- Windows/POSIX/mixed path normalization from a nested `.uvprojx` directory;
- POSIX absolute, drive absolute, drive relative, UNC, escaping `..`, symlink, simulated Windows reparse point, NUL, `PermissionError`, and generic `OSError` rejection;
- missing in-root source warning and no creation;
- lexical scanner ignores comments/string literals and detects every rule in 6.3 with exact positions/order/evidence cap;
- invalid encoding and per-file/aggregate scan caps;
- SPL/HAL/LL positive inference from two categories, single-category ambiguity, and conflicting evidence;
- exact input SHA-256 inventory and complete bytes/names/mtimes/permissions read-only snapshot.

`test_keil_baseline.py` must cover:

- dynamically generated minimal ELF32 parsed by pyelftools for exact entry point, alloc sections, and selected symbols; do not commit a binary fixture;
- exact MAP program-size parsing and derived flash/RAM totals;
- missing both, AXF-only, MAP-only, and both-valid availability;
- corrupt/truncated/non-ELF AXF, malformed/conflicting/overflow MAP, unreadable artifact, size caps, root mismatch;
- path revalidation, symlink/reparse escape, digest over exact bytes, stable ordering, immutable values, portable `to_dict`, and read-only snapshot.

No test may require Keil, ARM Compiler, GCC, a probe, network, administrator privileges, or hardware. Linux symlink tests must run rather than skip. A simulated reparse test complements but does not replace Codex's real Windows junction gate.

### 8.3 TDD evidence

Before implementation, add both test files and run:

```powershell
python -m pytest tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_keil_baseline.py -q
```

Expected RED: collection fails only with missing `stm32_toolkit.keil` modules/public names. Record exact exit/output. After implementation the identical command exits 0 with no new skip/xfail.

### 8.4 Required verification commands

Run from repository root in this order:

```powershell
$baseCommit = "53321e8721cc479122c43285537dc108461a8e0e"
python -m pip install -e "tools/stm32-toolkit[test]"
python -c "from importlib.metadata import version; assert version('pyelftools') == '0.33'"
python -m pytest tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_keil_baseline.py -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check "$baseCommit..HEAD"
git diff --name-status "$baseCommit..HEAD"
git status --short
```

Expected: every command exits 0; focused/full tests have no failure/error; branch coverage >=90%; compileall/diff check/status are silent; diff paths are exactly section 5 plus the report.

### 8.5 Manual verification

1. Copy the committed Keil fixture to a disposable Git working tree and record recursive relative paths, exact bytes/SHA-256, mtimes, modes, and Git status.
2. Run `inspect_keil`; inspect target/device/compiler/memory/source/options/findings/framework/input digests; repeat and confirm equal portable `to_dict()`.
3. Run `capture_keil_baseline`; verify MAP facts and honest AXF absence, then confirm the complete snapshot and Git status are unchanged.
4. Add a disposable generated minimal ELF32 at the inspection's AXF candidate, capture again, and verify its entry point/sections/symbols/hash. Remove only disposable data after evidence capture.
5. Create multiple targets and multiple `.uvprojx` candidates; confirm selection errors contain sorted relative names and make no writes.
6. Place a referenced source through an existing symlink to a sibling outside root; confirm `KEIL_PATH_OUTSIDE_PROJECT` and no external content in error details.
7. On Codex Windows, replace that symlink case with a real NTFS junction and confirm the same stable rejection without skipping.
8. Inject `PermissionError` during path inspection and artifact read; confirm conservative stable errors without exception text or absolute-path leakage.

## 9. Artifacts and return evidence

OpenClaw must return:

- branch `openclaw/STM32TK-0302-KEIL-INSPECT/r001`, accepted base, code head before report commit, final remote head out of band, and one Draft PR/compare URL targeting `master`;
- report `docs/openclaw/returns/STM32TK-0302-KEIL-INSPECT/r001-implementation-report.md` copied from the repository template;
- exact accepted-base-to-code-head path inventory plus the report-only addition;
- environment-separated RED/GREEN/full/compile/dependency/read-only/performance evidence with owner, OS/runtime/dependency versions, commit, command, exit, and observed result;
- focused/full counts, coverage table, exact performance fixture sizes/runs/timings, and manual SHA-256/read-only evidence;
- known limitations/deviations, with the current-round Windows real-junction gate marked `DEFERRED_TO_CODEX` if not run;
- clean status and proof that local HEAD, remote implementation branch, and PR head are identical.

The tracked report records the accepted base and code head before the report commit. It must not contain its own final SHA or moving commit totals.

## 10. Acceptance checklist

- [ ] Only section 5 paths plus the report changed.
- [ ] Public frozen types/signatures and stable errors match section 6.
- [ ] Inspection and baseline capture are provably read-only and deterministic.
- [ ] Project/target/framework ambiguity is explicit; no first-candidate guessing.
- [ ] XML/resource/path/source/artifact security requirements pass.
- [ ] Missing baseline artifacts are honest unavailable evidence, not zeros.
- [ ] Focused/full suites pass with branch coverage >=90%.
- [ ] OpenClaw evidence and Codex Windows evidence are correctly separated.
- [ ] Report matches complete diff and direct command evidence.
- [ ] No credentials, caches, binary fixtures, build outputs, temp projects, or unrelated changes are committed.

## 11. Explicit rejection conditions

- Any inspect/baseline path writes or changes project metadata.
- Any ambiguous project/target/framework is silently chosen.
- XML entities/DTD, out-of-root path, junction/symlink escape, raw host exception, or unbounded input is accepted.
- Scanner reports constructs found only in comments/string literals or omits a required rule.
- Missing/corrupt AXF/MAP becomes fabricated zero evidence.
- Public types are mutable, paths serialize as host absolute paths, ordering varies, or digests are not exact-byte SHA-256.
- A required pure-code gate fails, a required command is omitted, or branch coverage is below 90%.
- Dependency scope differs from pyelftools 0.33, or any path outside section 5/report changes.
- Correctable failures produce `REVISION_REQUIRED` on the same branch/PR; fundamental safety/scope/architecture failure produces `REWRITE_REQUIRED`.

## 12. Dispatch readiness

This work order is `READY_FOR_OPENCLAW` only after the specification commit containing it is pushed and verified on remote `master`. OpenClaw must branch from accepted product base `53321e8721cc479122c43285537dc108461a8e0e`, read the remotely visible work order from the specification commit supplied in dispatch, implement on `openclaw/STM32TK-0302-KEIL-INSPECT/r001`, push only that branch, open one Draft PR targeting `master`, and stop as `BLOCKED` rather than guess if any contract, dependency, path, or gate is unavailable or contradictory.
