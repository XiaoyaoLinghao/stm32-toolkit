# STM32TK-0303-ARMCC-CONVERT: Guarded ARMCC Conversion Plan and Apply

Status: `READY_FOR_OPENCLAW`
Accepted base commit: `c01a7d5a6bc669db30f65ea47d72357906d192e5`
Default branch: `master`
Implementation branch: `openclaw/STM32TK-0303-ARMCC-CONVERT/r001`
Specification owner: Codex
Implementer: OpenClaw
Reviewer: Codex

## 1. Objective and user-visible outcome

- Objective: turn one validated ARM Compiler 5 `KeilInspection` into a deterministic, reviewable conversion plan, then apply only approved GCC-compatibility source edits and a Schema v2 project manifest under Git and SHA-256 guards.
- User-visible outcome: planning is read-only and returns exact patches, blockers, absolute-placement linker requirements, the proposed `.stm32-project.json`, and a deterministic plan ID. Apply either performs the complete staged conversion and writes auditable migration artifacts, or leaves every pre-existing byte unchanged and returns one stable failure.
- Success boundary: no `.uvprojx` is ever written; unsupported or ambiguous ARMCC syntax blocks apply rather than being guessed; apply requires the same clean Git commit and exact input bytes observed by the plan; no staging residue or partial migration remains after success or a recoverable failure.

## 2. Scope

### 2.1 In scope

- Validate that `root` and `inspection.project_root` identify the same canonical Git worktree root.
- Revalidate every `KeilInspection.inputs` path, exact size, and SHA-256 before planning.
- Build a deterministic Schema v2 `.stm32-project.json` proposal from the selected Keil target.
- Plan token-aware rewrites for the exact supported ARMCC C/C++ constructs in section 6.3.
- Record unsupported C/C++/assembly/linker constructs as stable blockers with portable path, line, column, rule ID, and capped evidence.
- Record fixed-address declarations as named GCC section requirements for the later generation module.
- Produce immutable, JSON-safe plan models with portable `/` paths, deterministic ordering, deterministic UUID/plan ID, exact before/after digests, and unified diffs.
- Require an existing clean Git repository with a committed `HEAD`; capture the exact head without changing Git state.
- Apply through a private staging directory, revalidate plan integrity, Git state, path containment, input bytes, file type, and blockers, then replace files atomically with rollback on failure.
- Write `artifacts/migration/conversion.patch` and `artifacts/migration/conversion-report.json` only as part of a successful apply.
- Preserve source BOM, newline convention, unrelated whitespace, permissions, and every byte outside explicit replacement spans.

### 2.2 Out of scope

- No CMake, linker script, GCC startup, VS Code, build, flash, debug, monitor, CLI, MCP, Skill, release/version bump, or hardware work.
- No compilation, semantic C parser, Clang dependency, ARM assembler invocation, Keil invocation, network access, or device database.
- No SPL-to-HAL/LL conversion, library upgrade, API redesign, formatting pass, source-tree recursion, or batch-project migration.
- No automatic Git add, commit, branch creation, checkout, reset, clean, stash, merge, rebase, cherry-pick, or worktree mutation.
- No rewrite of `.uvprojx`, AXF, MAP, schema files, existing generated configuration, or unrelated source.
- No translation of arbitrary inline assembly, ARMASM source, scatter files, pragmas, compiler flags, or absolute-placement declarations outside the exact grammar in section 6.3.
- No attempt to make a blocked project build; blockers are an expected, explicit plan result.

### 2.3 Prohibited shortcuts

- Do not trust caller-constructed/frozen dataclasses merely because their types match; apply must recompute the canonical plan ID and validate every field.
- Do not use `shell=True`, command strings, environment-derived Git paths, or parse human-formatted Git output.
- Do not use regex over complete source text as the transformation engine. Comments, strings, character literals, raw strings, and preprocessor continuations must not be rewritten accidentally.
- Do not normalize all line endings, remove UTF-8 BOM, reformat the file, or decode with replacement characters.
- Do not accept a dirty/unborn/non-repository state, a changed `HEAD`, a changed input, an untracked collision, a symlink/reparse escape, or a non-regular destination.
- Do not create staging data during planning.
- Do not leave staging/backups after success or a successfully rolled-back failure.
- Do not change paths outside section 5 plus the required implementation report.

## 3. Prerequisites and fixed decisions

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Accepted product base: `c01a7d5a6bc669db30f65ea47d72357906d192e5`. Branch from this exact commit. Do not merge, rebase, or cherry-pick the specification commit into the implementation branch.
- Before implementation, fetch `origin/master`; read `AGENTS.md`, `OPENCLAW_START_HERE.md`, this work order, the architecture, complete roadmap, 0.3 plan, and the implementation reports for `STM32TK-0301` and `STM32TK-0302`.
- Required upstream APIs are exactly `load_project_model(Path) -> ProjectModel`, `inspect_keil(...) -> KeilInspection`, the immutable types in `stm32_toolkit.keil`, and `OperationResult` in `stm32_toolkit.result`.
- Runtime evidence: CPython 3.10.11, `jsonschema==4.23.0`, `mcp==1.27.0`, `pyelftools==0.33`, `pytest==8.3.5`, and `pytest-cov==6.0.0`. Declare the actual OS; do not claim an assumed distribution.
- No new dependency is allowed. Use Python standard library (`dataclasses`, `difflib`, `hashlib`, `json`, `os`, `pathlib`, `shutil`, `stat`, `subprocess`, `tempfile`, `uuid`) plus existing package APIs.
- Git CLI must be available for the OpenClaw gates. Git 2.34+ behavior is sufficient; record the actual version.
- Planning is deterministic: identical root-relative bytes, inspection, Git head, and Toolkit version yield byte-identical serialized plan values.
- Apply is not automatically authorized by the presence of a plan. The library API accepts the explicit plan object; later CLI/MCP authorization is a separate module.
- Visual acceptance is not applicable.

## 4. Architecture and dependency direction

```text
canonical Git project root + KeilInspection
  -> migration.git_guard (read-only repo root/HEAD/status evidence)
  -> migration.rules (lexical ARMCC classification and exact edits)
  -> migration.planner (manifest proposal, immutable plan, blockers, plan ID)
  -> MigrationPlan                         # read-only boundary
  -> migration.apply (revalidation, staging, atomic replace, rollback)
  -> source edits + .stm32-project.json
  -> artifacts/migration/conversion.patch
  -> artifacts/migration/conversion-report.json
```

- `model.py` owns frozen public values, JSON-safe serialization, canonical hashing payloads, and stable exceptions; it performs no filesystem or subprocess I/O.
- `git_guard.py` owns only read-only Git discovery/status/head calls with fixed argv and bounded output.
- `rules.py` owns source decoding, lexical states, supported replacements, blocker classification, and fixed-address section requirements. It does not read paths itself.
- `planner.py` owns root/inspection validation, bounded reads, input revalidation, manifest mapping, deterministic ordering, UUID/plan ID, and orchestration.
- `apply.py` owns forged-plan rejection, second Git/digest/path checks, staging, fsync/replace, rollback, artifact writes, and `OperationResult` construction.
- This module may depend on `stm32_toolkit.keil`, `stm32_toolkit.project_model`, `stm32_toolkit.result`, and `stm32_toolkit.__version__`. Those upstream modules must not depend on migration.
- Later generation code consumes the Schema v2 manifest and the fixed-section requirements in `conversion-report.json`; this module must not depend on future generation/build code.

## 5. Exact file plan

Only these implementation paths may differ from the accepted base:

| Status | Path | Responsibility |
|---|---|---|
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/__init__.py` | re-export section 6 public contracts |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py` | frozen plan/patch/blocker/section models and stable errors |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/git_guard.py` | bounded read-only Git root/head/status evidence |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` | token-aware ARMCC transformation and blocker rules |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | inspection validation, manifest mapping, deterministic planning |
| A | `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py` | guarded staging, atomic apply, rollback, artifact emission |
| A | `tools/stm32-toolkit/tests/test_migration_plan.py` | read-only planning, rule, manifest, determinism, security tests |
| A | `tools/stm32-toolkit/tests/test_migration_apply.py` | Git/digest/forgery/atomicity/rollback/artifact tests |

The implementation report is the only additional path:

- `docs/openclaw/returns/STM32TK-0303-ARMCC-CONVERT/r001-implementation-report.md`

Tests must build disposable Git repositories below pytest temporary directories. Do not commit another project fixture, binary, patch, report, or migration artifact. Do not modify upstream Keil/model/result code, schemas, plan checkboxes, CLI/MCP, templates, Skills, dependencies, setup, roadmap, or architecture from the implementation branch.

## 6. Public contracts and exact behavior

All public containers are `@dataclass(frozen=True)` and recursively immutable. Tuples are used instead of lists. `to_dict()` returns a fresh JSON-safe mapping, omits `project_root` and raw before/after bytes, uses only portable paths, and never includes host exception text.

### 6.1 Public types and functions

```python
class MigrationPlanError(Exception):
    code: str
    message: str
    details: dict[str, object]

@dataclass(frozen=True)
class MigrationInput:
    path: str
    sha256: str
    size: int

@dataclass(frozen=True)
class MigrationBlocker:
    code: str
    rule_id: str
    path: str
    line: int
    column: int
    evidence: str
    message: str

@dataclass(frozen=True)
class FixedSectionRequirement:
    section: str
    address: int
    source_path: str
    line: int
    symbol: str

@dataclass(frozen=True)
class FilePatch:
    path: str
    before_sha256: str | None
    after_sha256: str
    before_size: int | None
    after_size: int
    rule_ids: tuple[str, ...]
    unified_diff: str
    before_bytes: bytes | None       # omitted from to_dict()
    after_bytes: bytes               # omitted from to_dict()

@dataclass(frozen=True)
class GitBaseline:
    head: str
    root_marker: str                 # always "."

@dataclass(frozen=True)
class MigrationPlan:
    project_root: Path               # omitted from to_dict()
    inspection: KeilInspection       # omitted from to_dict(); used for fresh re-inspection
    plan_version: int                # exactly 1
    plan_id: str                     # lowercase SHA-256 hex
    inspection_sha256: str
    git: GitBaseline
    inputs: tuple[MigrationInput, ...]
    patches: tuple[FilePatch, ...]
    fixed_sections: tuple[FixedSectionRequirement, ...]
    blockers: tuple[MigrationBlocker, ...]

def plan_keil_conversion(root: Path, inspection: KeilInspection) -> MigrationPlan: ...

def apply_keil_conversion(
    plan: MigrationPlan,
) -> OperationResult[Mapping[str, object]]: ...
```

- `__init__.py` re-exports every type and both functions above.
- Public paths use `/`, are relative to the canonical project root, contain no empty/`.`/`..` component, drive prefix, UNC prefix, NUL, or absolute form.
- `FilePatch.before_bytes` is `None` only for a newly created `.stm32-project.json`. Planning includes only manifest/source patches; apply derives artifact bytes from the canonical plan and result.
- `inputs` are sorted by path and include every `inspection.inputs` entry plus an existing `.stm32-project.json` when present. Hashes cover exact raw bytes.
- `patches` are sorted by path. A file with no byte change is omitted. `.stm32-project.json` sorts with ordinary lexical ordering.
- `fixed_sections` sort by `(address, section, source_path, line, symbol)`; blockers sort by `(path, line, column, code, rule_id)`.
- `inspection_sha256` is SHA-256 over canonical UTF-8 JSON of `inspection.to_dict()` using `sort_keys=True`, separators `(',', ':')`, and `ensure_ascii=False`.
- `plan_id` is SHA-256 over the canonical JSON-safe plan payload excluding `project_root`, `inspection`, `plan_id`, raw bytes, and unified diff. It includes plan version, inspection hash, Git head, all input and patch metadata/digests, fixed sections, blockers, Toolkit version, and the SHA-256 of the proposed concatenated patch content. It never includes self-referential report bytes. Repeated planning returns the same ID.

### 6.2 Root, inspection, input, and Git validation

- `root` and `inspection` must have the exact declared types. Bad values raise `MigrationPlanError`, never `AttributeError`/`TypeError` leakage.
- Canonical `root` must exist, be a directory, equal `inspection.project_root`, and equal `git rev-parse --show-toplevel` after canonicalization. A nested repository root or repository above the project root is rejected.
- Planning freshly calls `inspect_keil(root, uvprojx=root / inspection.project_file, target_name=inspection.target_name)` and requires its portable `to_dict()` to equal the supplied inspection exactly. A forged, partial, stale, or caller-invented inspection raises `MIGRATION_INSPECTION_INVALID`; migration rules never trust caller-supplied findings as the only syntax evidence.
- Git commands use fixed argument arrays, `cwd=root`, `stdin=DEVNULL`, `text=False`, a 10-second timeout, and at most 1 MiB combined stdout/stderr per invocation. Non-zero, timeout, overflow, invalid UTF-8, missing Git, unborn `HEAD`, or malformed full SHA returns stable planning error `MIGRATION_GIT_UNAVAILABLE` with `{"rule": <repository|head|status>}`.
- Planning runs `git status --porcelain=v1 -z --untracked-files=all`. Any byte of output creates blocker `MIGRATION_GIT_DIRTY`; planning remains read-only and returns the plan. Apply returns the more specific top-level `MIGRATION_GIT_DIRTY` during its status preflight, before generic blocker handling and before staging.
- Git ignored files do not make the baseline dirty. Git submodules are out of scope; a gitlink entry in the selected inputs creates `MIGRATION_INPUT_UNSUPPORTED`.
- Every inspection path is revalidated for canonical containment and existing symlink/reparse behavior. Redirects resolving inside root are permitted; escapes, loops, permission/inspection failures, non-regular files, or size beyond the inspection-recorded size return `MIGRATION_INPUT_INVALID`.
- Read at most recorded size + 1 for revalidation. Actual bytes must exactly match both recorded size and SHA-256; otherwise raise `MIGRATION_INSPECTION_CHANGED` with only `{"path": <portable path>}`.
- `inspection.compiler` must be `armcc`; otherwise add blocker `MIGRATION_COMPILER_UNSUPPORTED`.
- `inspection.framework` must be exactly one of `spl`, `hal`, `ll`, `cmsis`, or `bare-metal`; `None`/other adds blocker `MIGRATION_FRAMEWORK_SELECTION_REQUIRED`.
- An existing `.stm32-project.json` is read with an 8 MiB + 1 bounded read. If its bytes equal the proposal it is a no-op and becomes an input. Any different existing bytes add blocker `MIGRATION_MANIFEST_EXISTS`; never merge or overwrite it.

Planning failures raise `MigrationPlanError` with these exact codes/details:

| Code | Required details |
|---|---|
| `MIGRATION_ROOT_INVALID` | `{"field": "projectRoot", "rule": <type|directory|canonicalRoot>}` |
| `MIGRATION_INSPECTION_INVALID` | `{"field": "inspection", "rule": <type|rootMatch|freshInspection>}` |
| `MIGRATION_GIT_UNAVAILABLE` | `{"rule": <repository|head|status>}` |
| `MIGRATION_INPUT_INVALID` | `{"path": <portable path>, "rule": <regularFile|withinProjectRoot|size>}` |
| `MIGRATION_INSPECTION_CHANGED` | `{"path": <portable path>}` |
| `MIGRATION_MANIFEST_INVALID` | `{"field": <schema/model field>, "rule": <stable validator rule>}` |
| `MIGRATION_LIMIT_EXCEEDED` | `{"scope": <git|file|aggregate|plan|patch|report>, "limitBytes": <int>}` |

### 6.3 Exact source transformation rules

Transform only included C/C++ files present in `inspection.inputs`. Header files, excluded files, libraries, linker inputs, assembly files, `.uvprojx`, scatter, AXF, and MAP are never rewritten.

The lexer must preserve exact byte spans and distinguish code, line/block comment, ordinary string, character literal, raw string, and preprocessor directive states. Identifiers require token boundaries. All supported source input is UTF-8 or UTF-8 BOM; decode failure adds `ARMCC_SOURCE_ENCODING_UNSUPPORTED`. Re-encoding preserves an existing BOM and every original newline sequence.

Supported transformations:

| Rule ID | Exact code-form behavior |
|---|---|
| `ARMCC_IRQ_QUALIFIER` | Remove a code token `__irq` plus only the immediately following horizontal whitespace. Do not remove newline or adjacent comments. |
| `ARMCC_INTRINSIC_NOP` | Rewrite the code identifier `__nop` to `__NOP` only when followed by optional horizontal whitespace and `(`. Preserve spacing and arguments. |
| `ARMCC_INTRINSIC_WFI` | Rewrite code identifier `__wfi` to `__WFI` only when followed by optional horizontal whitespace and `(`. Existing `__WFI` remains byte-identical. |
| `ARMCC_ABSOLUTE_PLACEMENT` | For the exact single-line declarations below, replace the placement attribute with `__attribute__((section(".stm32tk.abs.<ADDR8>"), used))`, where `<ADDR8>` is exactly eight lowercase hexadecimal digits without `0x`. Record one `FixedSectionRequirement`. |

Supported absolute declaration grammar:

```text
__attribute__((at(<integer>))) <type-and-qualifiers> <identifier>[<decimal-count>] ;
__at(<integer>) <type-and-qualifiers> <identifier>[<decimal-count>] ;
```

- `<integer>` is decimal or `0x` hexadecimal in unsigned 32-bit range.
- The declaration must occupy code on one physical line, contain exactly one identifier declarator, optional one-dimensional decimal array bound, and no initializer, pointer, function, comma, macro-expanded address, bit-field, or trailing code except a comment.
- `symbol` is the declared identifier. Duplicate `(address, symbol)`, reuse of one section address by different declarations, malformed/out-of-range values, or any other absolute-placement grammar adds blocker `ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED`; no partial rewrite occurs for that file.
- Existing GCC-compatible `__asm("...")` statement expressions and `__attribute__((section("...")))` remain byte-identical and are not blockers.
- Comments, strings, character literals, raw strings, and identifier substrings that resemble supported tokens remain byte-identical.

The following always create blockers and are never rewritten:

| Observation | Blocker code |
|---|---|
| `__asm` function declaration/body or brace-form inline assembly | `ARMCC_INLINE_ASSEMBLY_UNSUPPORTED` |
| included assembly source using ARMASM syntax or any non-empty included `asm` source | `ARMCC_ASSEMBLY_UNSUPPORTED` |
| `#pragma arm section`, `#pragma import`, `#pragma O...`, or another inspection `ARMCC_UNSUPPORTED_PRAGMA` | `ARMCC_PRAGMA_UNSUPPORTED` |
| non-empty scatter setting or ARMCC linker misc controls requiring translation | `ARMCC_LINKER_CONFIGURATION_UNSUPPORTED` |
| ARMCC target/group/file misc controls not proven empty | `ARMCC_OPTION_UNSUPPORTED` |
| any inspection finding with severity `blocker` not exactly resolved by a supported rule | `ARMCC_FINDING_UNSUPPORTED` |

- A blocker in one file prevents every patch from being applied, but the plan still reports all patches and all known blockers.
- A supported edit and an unsupported construct in the same file still produce a proposed full-file patch plus the blocker; apply remains prohibited.
- Unified diff uses labels `a/<path>` and `b/<path>`, three context lines, `lineterm="\n"`, deterministic path order, and no timestamp headers.

### 6.4 Schema v2 manifest proposal

Canonical JSON is UTF-8 without BOM, `indent=2`, `ensure_ascii=False`, keys inserted in the order below, arrays in upstream first-seen order, and exactly one final LF.

```json
{
  "schemaVersion": 2,
  "logicalProjectId": "<deterministic UUIDv5>",
  "generatedBy": {"tool": "stm32-toolkit", "version": "<package version>"},
  "project": {"name": "<output name or uvprojx stem>", "origin": "keil-migration"},
  "target": {
    "device": "<inspection.device>",
    "core": "<lowercase inspection.cpu>",
    "fpu": "<omit when null>",
    "floatAbi": "<omit when null>",
    "devicePack": "<omit when null>"
  },
  "framework": {"type": "<selected framework>", "version": null},
  "build": {
    "sources": ["<included c/cxx sources>"],
    "includePaths": ["<inspection includes>"],
    "defines": ["<inspection defines>"],
    "compileOptions": [],
    "assemblySources": ["<included asm sources>"],
    "presets": ["arm-debug", "arm-release"],
    "elf": "build/arm-debug/<sanitized output name>.elf"
  },
  "memory": {"source": "keil", "regions": ["<inspection regions verbatim>"]},
  "debug": {},
  "generation": {
    "cubeMxIoc": null,
    "managedManifest": ".stm32-toolkit/generated-files.json",
    "generatedDirectories": [],
    "userDirectories": []
  }
}
```

- UUID namespace is the fixed UUID `a2e9f523-3c9e-5cb2-bf50-5cf9ff5d16a8`; UUIDv5 name is `<project_file>\n<target_name>\n<device>` using portable exact strings.
- Project name uses trimmed `inspection.output.output_name`, else the `.uvprojx` filename stem. It must be non-empty.
- ELF basename replaces every character outside `[A-Za-z0-9._-]` with `_`, collapses repeated `_`, strips leading/trailing `._-`, and falls back to `firmware`.
- Core is `inspection.cpu.strip().lower()` with whitespace runs replaced by `-`; it must be non-empty.
- Only included sources are emitted. C/C++ go to `sources`; assembly goes to `assemblySources`; headers, libraries, and `other` are omitted. Libraries remain represented only in the conversion report for the later generation module.
- Memory fields copy name/origin/length/attributes in inspection order and require at least one executable region and one writable region; otherwise add `MIGRATION_MEMORY_INCOMPLETE`.
- Before adding the patch, load the packaged Schema v2 JSON through `importlib.resources`, validate it with the existing `first_schema_error`, and call `project_model.validate_model_document(root, payload, 2)`. Do not create a temporary manifest or write anywhere during planning. Validation failure is `MIGRATION_MANIFEST_INVALID`, never a guessed repair.
- If framework selection is blocked, serialize no manifest patch because Schema v2 requires a concrete framework; all other plan evidence remains available.

### 6.5 Apply, atomicity, rollback, and artifacts

Apply performs these checks before its first write, in this order:

1. Exact `MigrationPlan` type, `plan_version == 1`, field/container/scalar types, canonical portable paths, unique paths, digest formats, sorted order, and recomputed `inspection_sha256`/`plan_id`.
2. Canonical `project_root`, exact repository root, and full committed `HEAD` equal to `plan.git.head`; do not check porcelain status yet.
3. Every patch target resolves inside root; `.uvprojx`, `.git`, artifact outputs, and staging paths cannot appear as caller-supplied patches. Every existing target is a regular file and exact `before_bytes`/digest/size match. Every creation target and both artifact targets are absent. Every recorded input still matches exact bytes. This ordering guarantees a changed inspected input returns `MIGRATION_INPUT_CHANGED`, not the less specific dirty-worktree error.
4. Require clean porcelain status. An unrelated tracked/staged/untracked change returns `MIGRATION_GIT_DIRTY`.
5. Freshly run `inspect_keil` from the stored inspection's project/target selectors, require an exact portable inspection match, run `plan_keil_conversion` again, and require every canonical field and raw patch byte to equal the supplied plan. This is the forged-plan and removed-blocker defense.
6. No blocker exists.

Failures before writing return `OperationResult.failure("keil-conversion-apply", <code>, <stable message>, details)` with one of:

| Code | Required details |
|---|---|
| `MIGRATION_PLAN_INVALID` | `{"rule": <stable rule>}` |
| `MIGRATION_BLOCKED` | `{"blockerCodes": [<sorted unique codes>]}` |
| `MIGRATION_GIT_UNAVAILABLE` | `{"rule": <repository|head|status>}` |
| `MIGRATION_GIT_HEAD_CHANGED` | `{"expected": <sha>, "actual": <sha>}` |
| `MIGRATION_GIT_DIRTY` | `{"rule": "cleanWorktree"}` |
| `MIGRATION_INPUT_CHANGED` | `{"path": <portable path>}` |
| `MIGRATION_PATH_INVALID` | `{"path": <portable path>, "rule": "withinProjectRoot"}` |
| `MIGRATION_TARGET_EXISTS` | `{"path": <portable path>}` |

Write protocol:

- Create `.stm32-toolkit/migration-staging/<plan_id>/` only after every preflight check passes. Refuse if that exact directory already exists.
- Write each proposed destination to the staging directory using exclusive creation, exact after bytes, flush, `fsync`, and the original mode for replacements (default `0o644` for new files).
- Stage canonical `conversion.patch` and `conversion-report.json` bytes with the same protocol.
- Preserve backups of existing destination bytes and modes inside staging. Replace destinations in sorted path order with sibling temporary files and `os.replace`; fsync each containing directory where supported.
- If any write/replace/fsync fails, restore every already-replaced original in reverse order, remove every created destination and newly created empty parent directory, and remove staging. A successful rollback returns `MIGRATION_APPLY_FAILED` with only `{"phase": <stage|replace|fsync>}`.
- If rollback itself fails, return `MIGRATION_ROLLBACK_FAILED` with portable `{"paths": [<sorted paths>]}` and leave staging/backups for manual recovery. This is the only failure allowed to retain staging.
- On success, remove staging and prune empty `.stm32-toolkit/migration-staging` only; never remove `.stm32-toolkit` or unrelated contents.
- Success operation is `keil-conversion-apply`, code `OK`, and data is a JSON-safe mapping containing `planId`, `gitHead`, sorted `changedPaths`, `createdPaths`, `fixedSections`, `patchPath`, `patchSha256`, `reportPath`, and `reportSha256`.

`artifacts/migration/conversion.patch` is the concatenation of plan unified diffs in patch order. `conversion-report.json` uses canonical JSON and contains:

- `schemaVersion: 1`, Toolkit version, plan ID, Git head, inspection SHA-256;
- input path/hash/size inventory;
- patch path/before/after hash/size/rule IDs inventory;
- fixed-section requirements;
- ignored compatible observations (`__asm("...")`, GCC section attributes);
- omitted headers/libraries/other sources and included assembly sources;
- blocker list (necessarily empty on successful apply);
- artifact paths and the patch SHA-256. The report never contains its own SHA-256; the apply success data contains both `patchSha256` and `reportSha256` after the report bytes are finalized.

The report contains no absolute root, username, environment value, timestamp, raw source, Git remote, credential, or host exception.

## 7. Determinism, security, performance, and compatibility

### 7.1 Determinism and read-only planning

- Repeated plans over unchanged bytes serialize identically and have equal `plan_id`, patches, diffs, blockers, UUID, and manifest bytes.
- Planning leaves recursive names, bytes, SHA-256, mtimes, modes, Git index/status, ignored files, and untracked contents unchanged.
- Planning opens only `.git` through Git CLI, exact inspection inputs, and an existing manifest. It does not recursively enumerate source directories.
- Apply success changes exactly the planned source/manifest paths plus the two artifact paths.

### 7.2 Security and privacy

- Reject foreign POSIX/Windows absolute, drive-relative, UNC, mixed traversal, NUL, symlink/junction escape, forged raw path, duplicate/case-colliding Windows path, and non-regular target on every host.
- Detect case-insensitive path collisions using Unicode `casefold()` before apply so one plan cannot target two Windows-equivalent names.
- Only `FileNotFoundError`/`NotADirectoryError` can establish absence. Permission and generic inspection failures reject conservatively.
- Git output, file reads, diffs, and report generation are bounded. Source input inherits the 8 MiB/file and 64 MiB aggregate limits from inspection; manifest is 8 MiB; Git output is 1 MiB; serialized plan/report/patch each must not exceed 64 MiB.
- No log/error/details value contains raw Git stderr/stdout, source bytes, absolute path, temporary path, environment, stack trace, username, or credential.
- Apply never follows a replacement target outside the root and repeats containment immediately before each replace.

### 7.3 Performance and compatibility

- Generated performance fixture: a disposable clean Git repo with 100 included UTF-8 C sources of exactly 64 KiB each, 25 supported edits per file, and no blockers.
- Measure 3 warm-ups and 20 runs of planning without apply; median must be below 2,000 ms on the declared OpenClaw environment.
- Measure 10 independent disposable repos for apply; median must be below 2,000 ms. Recreate the clean repo for every apply run; do not reuse a dirty result.
- Record min/median/max, fixture byte counts, edit count, Git version, filesystem, OS, and Python version. Do not add timing assertions to normal CI tests.
- Compatible hosts: Windows 10/11 and Linux; CPython 3.10+; Git worktrees where `.git` is a file; LF/CRLF/mixed untouched spans; UTF-8 BOM.
- Accessibility/UI: `NOT_APPLICABLE`; no UI or rendered artifact.

## 8. Tests and environment evidence

### 8.1 Required environment matrix

| Gate | Exact command/action | Required environment | Evidence owner | Expected result | Deferred owner if unavailable |
|---|---|---|---|---|---|
| TDD RED | section 8.3 focused command before implementation | OpenClaw, CPython 3.10.11, exact deps/Git | OpenClaw | collection fails only because migration APIs do not exist | none |
| Focused GREEN | same command after implementation | same | OpenClaw | exit 0, no new skip/xfail | none |
| Full + branch coverage | section 8.4 | same | OpenClaw | exit 0, branch coverage >=90% | none |
| Compile | section 8.4 | same | OpenClaw | exit 0, silent | none |
| Dependency | installed metadata/diff | same | OpenClaw | no dependency change | none |
| Read-only plan | section 8.5 | same | OpenClaw | complete tree/Git snapshot identical | none |
| Atomic apply/rollback | section 8.5 | same | OpenClaw | exact write set; injected failure restores bytes/modes/status | none |
| Performance | section 7.3 | same | OpenClaw | both medians <2,000 ms | none |
| Windows | focused/full plus real NTFS junction and replace/rollback | Windows NT 10.0.26200.0, CPython 3.12.13, Git | Codex | exit 0; no skip; exact behavior | may be `DEFERRED_TO_CODEX` only |
| Visual/UI | no action | N/A | N/A | `NOT_APPLICABLE` | none |

`PASS` means that owner ran the gate against the returned code head. OpenClaw must not claim Codex Windows evidence. A pure code failure is never deferred.

### 8.2 Required focused coverage

`test_migration_plan.py` must cover:

- malformed root/inspection values and root mismatch without host exceptions;
- non-repository, nested repository, missing/unborn Git head, dirty tracked/untracked state, bounded/malformed Git output, and Git timeout;
- exact inspection input revalidation for missing, changed, oversized, unreadable, non-regular, redirect-in-root, redirect-escape, and path forms on Windows/POSIX semantics;
- deterministic inspection hash, UUID, plan ID, ordering, frozen values, fresh JSON-safe `to_dict`, and no absolute path;
- comments/strings/chars/raw strings/identifier substrings untouched;
- exact `__irq`, `__nop`, `__wfi`, already-compatible `__WFI`, string-form `__asm`, GCC section attribute behavior;
- both supported absolute-placement spellings, decimal/hex addresses, array declarator, section naming, and every unsupported grammar branch;
- all blocker classes in section 6.3, aggregation across files, capped evidence, and no first-blocker early return;
- UTF-8, BOM, LF, CRLF, mixed newline preservation, invalid encoding, per-file/aggregate/plan output caps;
- exact Schema v2 mapping, deterministic UUID/project/ELF names, memory completeness, concrete framework requirement, existing-identical manifest no-op, different manifest blocker, and packaged schema/model validation;
- read-only recursive names/bytes/hash/mtime/mode/Git snapshot and repeated-plan equality.

`test_migration_apply.py` must cover:

- success in a disposable clean repository at a committed `HEAD`, exact source/manifest/artifact bytes, preserved modes, clean staging removal, and expected dirty status after apply;
- blocker refusal before any write;
- changed head, staged/unstaged/untracked dirt, changed/deleted/replaced input, target collision, casefold collision, symlink/reparse escape, NUL/absolute/traversal, non-regular target, and inspection failure;
- forged plan version, plan ID, root, Git head, input, patch path, before/after bytes/digest/size, duplicate/unsorted fields, blocker removal, fixed section, and artifact hash/content;
- existing staging collision and exclusive creation;
- injected failure at every stage/open/fsync/replace point with exact rollback; injected rollback failure with retained recoverable staging and portable paths;
- no `.uvprojx`, Git index, branch, HEAD, config, remote, ignored file, unrelated tracked/untracked file, or external target change;
- deterministic patch/report bytes and `OperationResult.to_dict()` JSON serialization.

Tests may invoke only a local Git executable and disposable repositories. They require no network, compiler, Keil, CMake, Ninja, probe, administrator privilege, or hardware. Linux real symlink tests run without skip. Simulated Windows reparse tests supplement but do not replace Codex's real NTFS junction gate.

### 8.3 TDD evidence

Create both test files first, then run:

```powershell
python -m pytest tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py -q
```

Expected RED: collection fails only because `stm32_toolkit.migration` modules/public names are missing. Record verbatim output and exit code. After implementation, the identical command exits 0 with no new skip/xfail.

### 8.4 Required verification commands

Run from repository root in this order:

```powershell
$baseCommit = "c01a7d5a6bc669db30f65ea47d72357906d192e5"
python -m pip install -e "tools/stm32-toolkit[test]"
python -c "from importlib.metadata import requires; r = requires('stm32-toolkit') or []; assert not any('jinja' in x.lower() for x in r)"
git --version
python -m pytest tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term-missing
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check "$baseCommit..HEAD"
git diff --name-status "$baseCommit..HEAD"
git status --short
```

Expected: all commands exit 0; no new dependency; focused/full have no failures/errors; branch coverage >=90%; compile/diff/status are silent; diff paths are exactly section 5 plus the report.

### 8.5 Manual verification

1. Create a disposable Git repository containing a minimal ARMCC-inspected project; commit it and capture recursive paths, exact bytes/SHA-256, mtimes, modes, `HEAD`, index, porcelain status, and ignored/untracked inventory.
2. Run planning twice; compare complete portable `to_dict`, plan ID, UUID, patches, blockers, and confirm the snapshot is unchanged.
3. Use a blocker-free project containing all supported edits; inspect the unified diff and manifest; apply; verify exact changed/created path set, source byte spans, modes, artifacts, report hashes, staging absence, unchanged `.uvprojx`, unchanged Git index/HEAD, and expected porcelain paths.
4. Reset only the disposable repository through a fresh copy, change one inspected input after planning, and confirm `MIGRATION_INPUT_CHANGED` with no writes.
5. Repeat with dirty tracked, staged, and untracked state; confirm refusal before staging.
6. Inject replace failure after at least one destination changes; confirm every original byte/mode and pre-apply status is restored and staging is absent.
7. Forge a digest-matching-looking plan with a changed patch path/after bytes/blocker tuple; confirm `MIGRATION_PLAN_INVALID` and no writes.
8. On Codex Windows, use real NTFS junctions for one in-root source and one escaping source, then inject a Windows replace failure; confirm in-root behavior, escape rejection, rollback, and no skip.

## 9. Artifacts and return evidence

OpenClaw must return:

- branch `openclaw/STM32TK-0303-ARMCC-CONVERT/r001`, accepted base, code head before report commit, final remote head out of band, and one Draft PR targeting `master`;
- report `docs/openclaw/returns/STM32TK-0303-ARMCC-CONVERT/r001-implementation-report.md` copied from the repository template;
- accepted-base-to-code-head inventory plus report-only addition;
- exact RED/GREEN/full/coverage/compile/dependency/Git/read-only/atomicity/rollback/performance evidence with actor, actual OS, runtime/dependency/Git versions, command, commit, exit, and observed result;
- manual plan/apply SHA-256 evidence, failure injection results, performance fixture dimensions/timings, and known limitations;
- Windows gate marked `DEFERRED_TO_CODEX` only if unavailable;
- proof local HEAD equals remote implementation branch equals Draft PR head and `git status --short` is empty.

The tracked report records accepted base and code head before its report commit. It must not contain its own final SHA or moving commit totals.

## 10. Acceptance checklist

- [ ] Only section 5 paths plus the report changed.
- [ ] Public frozen models, signatures, deterministic hashes, and JSON-safe serialization match section 6.
- [ ] Planning is byte/metadata/Git read-only and deterministic.
- [ ] Supported transforms change only exact code tokens/spans and preserve BOM/newlines/permissions.
- [ ] Every unsupported construct is an explicit blocker; apply cannot bypass blockers.
- [ ] Schema v2 proposal is deterministic, validated, and never overwrites a different manifest.
- [ ] Apply rejects forged/stale/dirty/escaping/colliding plans before writes.
- [ ] Success is exact and atomic; injected recoverable failures restore all pre-existing state.
- [ ] `.uvprojx`, Git index/HEAD/config/remotes, unrelated files, and external targets never change.
- [ ] Patch/report are deterministic, bounded, portable, and contain no private host data.
- [ ] Focused/full suites pass with branch coverage >=90%; performance budgets pass.
- [ ] Evidence ownership and report/remote identity are truthful.

## 11. Explicit rejection conditions

- Planning writes, creates staging, mutates Git, or produces nondeterministic output.
- Apply accepts blockers, a forged plan, stale Git/input state, dirt, a path escape/collision, a different manifest, or a non-regular target.
- A comment/string/literal/identifier substring is rewritten, an unrelated byte/newline/BOM/mode changes, or a supported exact construct is omitted.
- Unsupported inline assembly/ARMASM/pragma/linker/option syntax is guessed or silently dropped.
- `.uvprojx`, Git index/HEAD/config/remote, ignored/unrelated file, or out-of-root target changes.
- Recoverable failure leaves a partial conversion or staging residue; rollback failure lacks recoverable backups.
- Report/patch leaks host paths/source contents beyond unified diff/credentials or exceeds bounds.
- Any required pure-code gate fails, coverage is below 90%, dependency/scope differs, or report evidence is inaccurate.
- Correctable failures remain on the same branch/PR as `REVISION_REQUIRED`; fundamental safety/scope/architecture failures become `REWRITE_REQUIRED` only by Codex verdict.

## 12. Dispatch readiness

This work order is `READY_FOR_OPENCLAW` only after the specification commit containing it is pushed and verified on remote `master`. OpenClaw must branch from accepted base `c01a7d5a6bc669db30f65ea47d72357906d192e5`, not from the later specification commit. It reads this work order from the dispatch-supplied specification commit, implements on `openclaw/STM32TK-0303-ARMCC-CONVERT/r001`, pushes only that branch, opens one Draft PR targeting `master`, and stops as `BLOCKED` rather than guessing if a contract, path, Git behavior, or gate is unavailable or contradictory.
