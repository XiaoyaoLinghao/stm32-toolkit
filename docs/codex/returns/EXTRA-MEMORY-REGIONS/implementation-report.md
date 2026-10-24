# EXTRA-MEMORY-REGIONS implementation report

## Identity and ownership

- Accepted base: `e4c7314af220295037ed6d273127d9873ba3eedc`
- Branch: `codex/extra-memory-regions`
- CodeHead before this report commit: `540a62cbdf6d92de69b078736f8ffa5a9ec77477`
- Implementer: local Claude Code CLI using the existing `deepseek-v4.1-flash[1m]` provider/model configuration. No model change.
- Reviewer and evidence owner: primary Codex. This report is implementation evidence only; the author does not approve its own diff and records no acceptance verdict.
- Governance specification and plan (primary-owned): `docs/superpowers/specs/2026-10-24-extra-memory-regions-design.md` and `docs/superpowers/plans/2026-10-24-extra-memory-regions-plan.md`.
- Machine-readable evidence: [evidence.json](evidence.json) (primary places this adjacent file).

## Implemented behavior and boundaries

- Schema 2/3 manifests accept optional `memory.extraRegions`. Each entry supplies exactly `name`, `origin`, `length`, `attributes`; only `rw-`/`rwx` writable RAM is representable. At most 32 entries; names are 1-64 character ASCII linker identifiers with case-insensitive uniqueness; origins/lengths are exact JSON integers with bounded half-open ranges. Missing/unknown fields, duplicate/case-colliding names, overlap with base or other extras, zero length, booleans, strings, floats and unsafe names are rejected. Adjacency is allowed.
- One shared strict normalization/composition path (`extra_regions.py`) serves manifest loading and migration transport. The persisted manifest keeps inspect-derived base `memory.regions` and explicit `memory.extraRegions` separate. Loading normalizes once so `ProjectModel.memory.regions` is the ordered base-plus-extra tuple used by fixed-section admission, layout selection, linker rendering, ELF/MAP accounting, build identity and downstream consumers. `extra_region_names` is provenance for that same map, not a second interpretation.
- Omitted and empty extra-region options are the same request and produce the same migration proposal/plan bytes. For manifests differing only by an empty `extraRegions` array, the normalized model hash and rendered output remain equal. A raw manifest edit still changes input-snapshot/config-plan evidence and is not ignored; the report does not promise identical configuration hashes for different input files.
- Keil preflight, PLAN and APPLY accept MCP `extraRegions` (real `list[dict[str, Any]]`, preserving raw scalar types) and CLI `--extra-regions` JSON. CLI parsing rejects duplicate JSON keys, deep nesting via a bounded iterative depth guard, malformed/oversize input and repeated options; Toolkit failures use structured `EXTRA_REGIONS_INVALID` field/rule/remediation. Framework-level MCP rejection is distinguished from Toolkit validation.
- Preflight exposes `analysis.extraRegions`; PLAN exposes `extra_regions` and binds the immutable normalized request into plan identity; the conversion report records `extraRegions`. PLAN/APPLY replan with the same request. Omitted, shortened, changed or tampered requests are refused by plan-ID/fresh-plan/shape guards before any write.
- The proposal adds `memory.extraRegions` without modifying or re-claiming inspected Keil base regions or inspection evidence, and never updates `.uvprojx`.
- The combined map feeds migration fixed-address admission and layout candidates. Extra RAM adds RAM candidates only and is never a Flash candidate. Existing `memoryLayout` selection remains; managed `.data`/`.bss`/`.heap`/`.stack` are never placed in owner-supplied external RAM implicitly, while an explicit layout may name a valid extra RAM.
- Managed linker generation emits each normalized region once. Fixed sections remain address-bound `NOLOAD`; no copy/zero table, controller initialization, reset sequence or board timing is invented. The owner must initialize external memory before access; external stack use may require earlier bootstrap than `SystemInit`. Native linker ownership is unchanged and is not rewritten; native-linker projects cannot also declare managed `memoryLayout`.
- No startup or probe implementation changes, no Flash algorithm, and no hardware authorization. Offline link/ELF/MAP evidence is not runtime or board qualification.

## Changed file groups

Product:
- `tools/stm32-toolkit/src/stm32_toolkit/extra_regions.py` (new)
- `tools/stm32-toolkit/src/stm32_toolkit/memory_layout.py`
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json`
- `schemas/stm32-project.schema.json` (paired byte-identical copy)
- `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`
- `tools/stm32-toolkit/src/stm32_toolkit/workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`
- `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py`

Tests:
- `tools/stm32-toolkit/tests/test_extra_memory_regions.py` (new)
- `tools/stm32-toolkit/tests/test_extra_memory_regions_migration.py` (new)
- `tools/stm32-toolkit/tests/test_extra_memory_regions_compiler.py` (new)
- `tools/stm32-toolkit/tests/test_mcp_migration_build.py` (exact registered schema expectations)

Documentation and Skill:
- `docs/user-guide.md`
- `docs/architecture.md`
- `skills/migrate-keil/SKILL.md`

## Test and review evidence

Author native verification (PowerShell tool inventory and bound working directory confirmed before test dispatch):

| Run | Head | Result |
| --- | --- | --- |
| initial | `a2e6837f4d791b87437ecb7697e0b2bcc355c98d` | 51 tests, 48 passed, 3 failed, 0 skipped |
| final-new | `540a62cb...` | 56 passed, 0 failed/skipped |
| migration | `540a62cb...` | 296 passed |
| build | `540a62cb...` | 142 total, 141 passed, 1 symlink skip |
| Skill `quick_validate` | `540a62cb...` | `Skill is valid!` |

The initial three failures are retained, not erased:

- Overlapping boundary fixture (`TOP` inside `WHOLE`) was a contradictory test, not a validator defect; the boundary values were split into separate valid requests.
- Nesting diagnostic depended on interpreter recursion; a bounded iterative JSON depth guard now gives deterministic `nesting` rejection.
- GNU ld returned 0 with a warning for an undeclared `EXT_SRAM` reference; removal is now rejected through the actual model/ELF/MAP product guards, while genuine shortened-region link overflow and section-crossing-end evidence remain.

Primary independent evidence in the clean review tree (`build-snapshot-final`):

- `model-review` at `a2e6837f`: 568 total, 566 passed, 2 real-symlink skips.
- `artifact-review` at `a2e6837f`: 158 passed.
- These two groups are reused deliberately: the only product delta from `a2e6837f` to `540a62cb` is the bounded CLI JSON depth guard in `extra_regions.py`; model/generation/artifact implementation and old tests are byte-identical and old no-extra regressions do not enter that parser. This report claims no final-head combined full matrix.
- `final-review` at final full CodeHead `540a62cb`: 71 passed (56 new + 15 legacy layout), process exit 0. This is primary independent verification, not author evidence.
- Entire accepted-base-to-CodeHead diff was independently reviewed in the clean exact-head review tree. Primary evidence/review placement and acceptance remain outside this report.

Aggregate: 1217 unique passing cases across the required groups. The remaining 3 real-symlink cases are **PLATFORM DEFERRED** to primary release qualification on a capable Windows/Linux environment:

- `tests.test_project_model::test_file_symlink_cannot_escape_project_root`
- `tests.test_project_model::test_directory_symlink_parent_cannot_escape_project_root`
- `tests.test_regeneration::test_destination_symlink_is_rejected_before_resolution`

Real GNU Arm GCC compile/link with the generated linker, actual `validate_elf` acceptance of the combined model, `parse_map` accounting from that ELF evidence, removed/shortened/cross-end rejection, and the pure flash-segment parser's refusal of writable executable external RAM were exercised by the new tests. This is offline software evidence only.

## Limitations and boundaries

- No full release matrix, board run, hardware access, CMake/Keil behavioral equivalence or external-memory runtime claim is made. No startup/probe implementation was changed.
- The frozen/installed 1.3.0 runtime still lacks this source-only patch, as does v1.2.0. Users must verify the bound server's actual tools and input schema; a version number is not proof.
- Three symlink cases remain platform-deferred as named above. No pure-code failure was deferred.
- No remote action, PR mutation, tag, package, installation, release-asset change, original-project access, installed-runtime change, global Skill change, or hardware operation occurred. Normal configured CLI authentication was used; no credential exposure or authentication-setting change occurred.
- Implementation/verification split was preserved: file-only authoring and exact native PowerShell commands were separate calls. The author/continue/continue2 invocations hit the 65-turn budget and retained their logs; no permission bypass or boundary violation occurred. The initial CLI final prose misstated 49 passed; JUnit is authoritative at 48.
