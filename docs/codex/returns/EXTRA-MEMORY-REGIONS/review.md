# EXTRA-MEMORY-REGIONS independent review

2026-10-24 verdict: **ACCEPTED_WITH_FIXES**, for the bounded offline source slice.

Accepted base `e4c7314af220295037ed6d273127d9873ba3eedc`; final CodeHead `540a62cbdf6d92de69b078736f8ffa5a9ec77477`; branch `codex/extra-memory-regions`. Primary Codex owns specification, plan, orchestration, complete-diff review and acceptance. Local Claude Code CLI using the existing `deepseek-v4.1-flash[1m]` configuration authored every product, test, user-guide and skill change. No ownership exception or remote authority is used.

Governing [design](../../../superpowers/specs/2026-10-24-extra-memory-regions-design.md) and [plan](../../../superpowers/plans/2026-10-24-extra-memory-regions-plan.md). Independent review used clean `build-snapshot-final/STM32-Toolkit` at the exact CodeHead. Complete binary diff SHA256 `6580dd494ad7e69400d31a4ca3c0ec5eccd06d7d688f08b7e635d3ae71cdb2f2`, retained at `D:/codex-tmp/er24/reviewed.diff`. Exact commands, JUnit counts, native tool events and source identities are in [evidence.json](evidence.json).

## Accepted behavior

Schema 2/3 `memory.extraRegions` accepts up to 32 explicit writable RAM entries containing exactly name, origin, length and attributes. Names are bounded linker-safe ASCII identifiers, origins/lengths exact integers within a 32-bit address space, and attributes only `rw-`/`rwx`. Missing values, coercible but invalid scalar types, zero/overflow capacity, unknown fields, case-colliding names and overlaps with base/extra regions are refused; adjacency is valid. CLI JSON is byte/depth bounded and refuses duplicate object keys; MCP preserves scalar types for shared validation. No capacity is inferred from the device, source address or board.

The persisted base region list is unchanged and extras remain explicit. Shared validation/composition produces one canonical ordered base-plus-extra `ProjectModel.memory.regions` tuple. Fixed-section admission, managed configuration/linker rendering, actual ELF/MAP validation and build identity consume that map. Existing linker/build/probe code required no alternate maps or implementation changes. The small `memory_layout.py` provenance extension implements the approved no-implicit-external-placement behavior; it is not a new layout algorithm. Nonempty provenance participates in model identity, and external RAM must be explicitly selected for data/bss/heap/stack even when it is the only writable RAM.

Keil preflight, PLAN and APPLY carry the exact normalized request through MCP `extraRegions`, CLI `--extra-regions`, immutable plan identity, fresh replan and conversion-report evidence. Inspect/uvprojx base evidence is not falsified. Responses distinguish preflight `analysis.extraRegions`, PLAN `extra_regions`, report `extraRegions`, and manifest `memory.extraRegions`. Changed/omitted requests or tampered plans refuse before writes. Git-free analysis remains available; Git, authorization, input/managed drift and transactional apply guards remain intact. Omitted/empty migration requests preserve historical output/identity. Explicitly editing a raw manifest still changes its input snapshot; equality of normalized model hashes does not erase raw-file evidence.

External SRAM is never a programmable Flash candidate, including `rwx`. A real linked ELF with its copied PT_LOAD physical destination retargeted to synthetic external SRAM is rejected by the pure Flash-segment parser while the original Flash image is accepted. No probe or device is involved.

Fixed sections remain NOLOAD and are not promised initialized. There is no controller initialization, copy/zero-table invention or automatic external placement. The owner must initialize external memory before access; an external initial stack may require earlier bootstrap than SystemInit. Native linker scripts remain user-owned and cannot also claim a managed layout. Offline compilation/linking does not establish board, timing, DMA, ARMCC ABI or runtime equivalence.

VS Code/MCP guide and migrate-keil skill now document actual parameters, diagnostic fields, unchanged request routing and initialization limits. They explicitly state that frozen/installed1.3.0 also lacks this source-only patch; restarting VS Code alone does not install it. Paired schemas match byte-for-byte; no tool count/version/dependency/CI changes were introduced.

## Review corrections and failure evidence

| Path | Finding and correction | Verification |
| --- | --- | --- |
| `migration/apply.py` | Initial draft checked explicit layout against base regions only. Validate extras first and check the complete map. | Public core/CLI/MCP PLAN/APPLY with external layout roles. |
| `project_model.py`, `generation/configure.py`, `generation/managed_files.py` | Preserve normalized tuple through layout validation, carry provenance to prevent implicit external-only RAM selection, bind nonempty provenance into identity. | Schema2/3, external-only layout, model/config and historical layout tests. |
| `extra_regions.py` | Bound unknown-key diagnostic text and make CLI depth rejection deterministic instead of relying on interpreter recursion thresholds. | Invalid input, oversized/nested JSON, duplicate keys and raw MCP scalar checks. |
| New tests | Boundary fixture accidentally overlapped TOP with WHOLE. Separate valid requests; retain overlap rejection. | Final56 new cases pass. |
| New compiler tests | GNU ld may only warn for an undeclared MEMORY region, so link exit alone is not an adequate refusal assertion. Use real product ELF/MAP checks against removed/shortened maps; retain genuine linker overflow evidence. | Real GNU image, actual validate_elf/parse_map, range-end refusal. |
| New compiler tests | Place compiler output inside the synthetic project to satisfy validate_elf containment. Refuse an actual copied ELF destination at0x68000000 rather than only relabeling Flash in a model. | Actual product validation and pure Flash parser test. |
| Guide/skill | Correct overlapping example address, reuse the same explicit layout in examples, preserve structured-error precedence and installed-source distinction. | Complete guide/skill delta review; native skill validation. |

## Verification

Windows CPython3.12.14 / GNU Arm GCC14.3.1. Same-worktree Toolkit/Monitor source, installed1.3.0 packages used only as read-only dependency donor. All temporary fixtures/cache/compiler products/evidence reside under `D:/codex-tmp/er24`; no original project was used.

| Owner / exact source | Result |
| --- | --- |
| Claude / `a2e6837f4d791b87437ecb7697e0b2bcc355c98d` initial new tests | 51 total:48 pass,3 fail. Retained original failures; not counted as acceptance. |
| Primary / clean `a2e6837f` model/generation/layout | 568 total:566 pass,2 platform skips; process exit0. |
| Primary / clean `a2e6837f` MAP/build-snapshot/pure Flash regressions | 158 pass; process exit0. |
| Claude / final `540a62cbdf6d92de69b078736f8ffa5a9ec77477` | 56 new tests pass;296 migration/routing/ARMCC/include/guide regressions pass;142 build/regeneration/compiler cases:141 pass,1 platform skip. |
| Primary / clean final CodeHead | 71 pass, including all56 new cases and15 historical layout checks; process exit0. |
| Claude / final CodeHead | migrate-keil quick_validate: `Skill is valid!`. |

There are **1217 unique passing cases**:56 new and1161 related regressions. Counts come from JUnit, not estimated progress dots or a Claude process exit. The initial CLI summary incorrectly estimated49 passes (JUnit48), and the build summary incorrectly estimated144 total (JUnit142); the machine ledger uses actual XML counts. Native tool execution, generated JUnit and independent exit codes are retained without inventing an unreported native subprocess exit code.

The only product delta after a2e6837f is the new option's bounded JSON-depth guard; old model/generation/artifact code and regression test bytes are identical, and these no-extra checks do not enter that JSON parser. Their evidence is explicitly reused. The final source reran the new option/public/compiler cases and15 legacy layout cases; this is not a claim of a final-head combined full matrix.

Three existing real-symlink cases are PLATFORM DEFERRED to primary-owned release qualification in a capable Windows/Linux environment: project-model file escape, directory-parent escape, and regeneration destination-link refusal. The unchanged dependency lifespan warning is nonfatal. No pure code failure remains deferred.

Real GNU compile/link evidence uses generated startup/linker output and an explicit synthetic0x68000000/64KiB range. Actual ELF validation feeds MAP accounting; fixed NOLOAD VMA, explicit layout, external capacity, removed/shortened/cross-end refusals and writable-SRAM programming refusal are verified. This is not a full CMake invocation, Keil baseline comparison, IDE UI exercise or physical qualification.

Native PowerShell registration/inventory and actual Get-Location were verified; process-only flags respected existing execution policy. File-only implementation and exact-command verification used separate invocations with empty MCP configuration. The three65-turn budget exits retained logs/edits; no absent/denied-tool anomaly or permission bypass occurred in this slice. No Codex implementation subagent was used. Primary planning/review still uses Codex conversation usage.

No blocking finding remains for the approved offline source slice. Original project, installed runtime, global skills, frozen release assets and hardware remain untouched. No packaging, installation, remote push/PR/tag or publication occurred. This verdict grants no hardware or release acceptance.
