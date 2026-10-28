# Current product architecture

STM32 Toolkit is a local, agent-neutral Windows control plane for STM32 projects. CLI and stdio MCP
are thin adapters over the same Python workflows. Monitor consumes the same project, firmware and
Probe Service contracts. A host-specific skill must not create a second implementation or bypass
the public result, identity or authorization checks.

The supported release environment is Windows x86_64 and CPython `>=3.12,<3.13`. Dependencies and
offline artifacts are pinned by `tools/release/release_0900_policy.json`; the historical filename is
the current release engine's path, not a separate supported 0.9 runtime. See [release status](release-status.md)
for the distinction between published versions, local candidates, evidence and limitations.

## Ownership and data flow

```text
explicit project root + manifest
  -> deterministic inspect/plan
  -> authorized migration/configuration
  -> GCC/CMake build + immutable firmware identity
  -> explicit Probe Service lease + authorized flash/control
  -> typed reads / bounded sampling / controlled Fault / IDE handoff
  -> Monitor and immutable test/diagnostic evidence
```

| State | Single source of truth |
| --- | --- |
| Project intent | Versioned `.stm32-project.json` in the explicit project root |
| Generated-file ownership | The configured managed manifest, normally `.stm32-toolkit/generated-files.json` |
| Build identity | Validated build result and input snapshot; ELF content alone does not replace provenance |
| Installation | Verified release manifest plus managed runtime state under explicit DataRoot |
| Probe ownership | One Probe Service lease/ticket with the recorded workspace, session, probe and operation level |
| Flash evidence | Successful authorized programming and readback receipt; it does not imply that firmware is running |
| Monitor groups/history | Existing project-isolated data under DataRoot; no generated named presets |
| Test/diagnostic history | Immutable evidence envelopes and validated references; historical records retain their original identity |

DataRoot is a durable user-owned location. Project roots, runtime roots and run-scoped test output
are separate. Never restore a retired temporary path, borrow another session's action, or alter an
evidence hash to make a workflow pass. CLI project-bound commands require an explicit project root;
runtime launchers use the configured managed interpreter, with no system-Python fallback.

## Migration, generation and builds

Keil inspection and preflight are read-only. Keil-to-GCC migration is one-way independent delivery:
the Keil source is an immutable input and the deterministic plan publishes one complete, separately
buildable GCC/CMake project into an explicit absolute destination outside it. Planning binds the
complete source inventory, selected target, exact outputs/diffs, destination state and reviewed
options; apply revalidates all of them, stages in an owned sibling, verifies the complete staged
tree, and publishes only into an absent destination (an existing empty destination is verified and
replaced atomically). A nonempty destination is never overwritten, and public conversion has no
in-place fallback. The legacy in-place plan/apply engines remain available internally for historical
evidence, not as a public route. This destination contract is published v1.3.3 behavior; the
earlier v1.3.2 package still exposed the historical in-place `keil convert`.

Preflight runs the same technical analysis as planning without requiring Git. Technical blockers
alone determine technical readiness; Git is optional evidence and never a plan prerequisite. The
new output directory is a required next input whose absence/empty state preflight deliberately does
not evaluate, and apply readiness never follows from preflight. Only implemented compiler/source
rules are supported. Non-UTF-8 sources, needed quoted headers and unsupported ARMCC assembly
require explicit project-owned adaptation; the Toolkit does not guess encoding, silently
transcode, or invent MCU startup/vector initialization. A separate
`normalize-source-comments` companion skill may produce reviewed comment-only UTF-8 file copies in
a new external directory with explicit per-file charsets. Its output is a selected-file set, never
a project. Complete preparation is a separate explicit copy: inventory every project file, refuse
reparse/escaping/duplicate or unreadable paths, preserve all unselected sources, headers, startup
files, resources and licenses, overlay only reviewed copies whose source and output hashes match,
recheck the hashes and reparse the prepared root before planning. The original tree stays
unchanged; the prepared root is the migration input, and the delivered GCC output is an
independent tree whose build inputs never depend on the original or prepared tree. Bind the
prepared root for migration, then the returned output root for configuration/build. Preparation is
reversible and needs no Git. It does not remove startup, option, scatter/memory or
unsupported-assembly blockers. Keep compiler migration separate from SPL/HAL conversion.

Published v1.3.4 adds two bounded analysis changes to that read-only preflight contract,
without changing any public command and still without transcoding. Structural outer include-guard
recognition accepts a balanced, independent nested conditional inside the guard, while real nested
macro definitions or includes are still read as conditional evidence and cannot be used as
unconditional constant evidence of the guarded content. Preflight also
exposes `analysis.encodingDiscovery`: a read-only inventory of potential project-contained
dependency headers reached through ASCII quoted includes from the selected sources. A known
non-UTF-8 header becomes a header blocker alongside source blockers even when earlier invalid C or
header bytes stop that file's own parse. Excluded paths, unrelated files and angle or system
headers are never scanned. An unresolved quoted standard-library name, non-ASCII or dynamic
include, multiline raw-string edge or scan limit reports `discovery.complete=false` with explicit
diagnostics: incomplete discovery is not proof that every dependency was checked, and those
discovery diagnostics are not a new semantic blocker by themselves. On the actual original project,
v1.3.4 selected 36 non-UTF-8 C files and reached 24 non-UTF-8 headers, with two further
non-UTF-8 headers inside excluded paths. UTF-8 preparation stays an explicit per-file charset
conversion outside the original tree with stable source hashes and a reviewed destination PLAN, and
explicit WFI, memory-region, startup and layout selections keep their existing meaning; Git remains
optional traceability on the normal managed flow. Independent destination delivery, explicit WFI
normal-return intent and the no-Git managed flow were introduced by published v1.3.3 and are not
new v1.3.4 claims. v1.3.4 was published as Latest from frozen source `a7db6a8c` under an explicitly
approved candidate-specific exception: Toolkit overall/risk 82.7452%/82.6335% remain below
90% and Monitor risk 92.3681% remains below 95%, with exact-source reuse, retained original
failures, platform/historical-data skips, the synthetic external vendor adapter and final
recipient installation/VS Code validation still disclosed. This section claims no
physical-target or ABI verification.

One bounded migration opt-in recognizes and generates a GNU replacement for the
conventional ST/CMSIS Cortex-M3/M4/M7 ARMCC5 startup. It is selected only by
explicit `startupStrategy: "generate-cmsis-gcc"` plus, when the choice is
ambiguous, the exact project-relative `startupSource`; omitted options preserve
the existing arbitrary-assembly blockers. The recognizer validates the whole
active ARMASM file (including physical line continuations and the conventional
Microlib/`__user_initial_stackheap` boilerplate), rejects unknown or custom
logic with portable line diagnostics, and never executes input. Planning emits
`Startup/stm32tk_startup_gcc.S` as a reviewed create-only patch, never edits or
deletes the original startup, and binds the selected source and options into
the plan digest. Apply replans with the plan-bound options, so a caller-edited
or omitted strategy/source cannot be accepted after review; an existing
different destination is a collision, never an overwrite.

The generated startup keeps the original vector order and reserved zero slots,
exports weak core handlers and weak IRQ aliases (strong C definitions override),
and implements `SystemInit` followed by `.data` copy, `.bss` clear, the newlib
constructor path and `main`, with a deterministic return loop. The
`cmsis-gcc-v1` linker contract aligns `_sidata`, `_sdata`, `_edata`, `_sbss`
and `_ebss` to four bytes and asserts that alignment at link time, because the
generated copy/clear loop transfers whole words. It records the
source-derived `memory.stackSize`/`memory.heapSize` and the sole
`generation.runtimeInitialization: "cmsis-gcc-v1"` contract. That contract is
valid only with the managed linker template, which then emits the constructor
arrays and initial-stack/heap compatibility symbols; a native linker is
rejected rather than silently ignored. Existing manifests without the optional
fields keep their model hash and default 4 KiB heap/1 KiB stack bytes. This is a
reviewed GCC runtime replacement, not ARMCC, ABI or Microlib equivalence; it
does not claim device/IRQ fabrication, binary equivalence or board-level memory
behavior.

Explicit WFI normal-return intent is a separate reviewed source choice, not a binary-equivalence
claim and not an assembly translator. Public MCP `wfiReturns` (a real array of exactly
`{path, function}` objects) and repeatable CLI `--wfi-return PATH:FUNCTION` bind one or more plain
file-scope zero-argument ARMCC `__asm void name(void)`/`name()` definitions whose body is exactly
one WFI, with an optional trailing semicolon and lexical comments, and no explicit return. The
same selection must be used for preflight, PLAN and APPLY; a nonempty selection participates in
plan identity and source-change previews, while omission or change is a different request that
fails with `DELIVERY_BLOCKED` or `PLAN_CHANGED` before any write. The selected wrapper becomes
ordinary non-naked C executing `__asm volatile ("wfi" ::: "memory");` and returning normally,
preserving its name, prototype, comments, BOM/newline convention and adjacent functions; the
patch carries rule `ARMCC_WFI_RETURN_INTENT`. Wrappers with an explicit `BX LR`/`BX R14` keep the
existing naked rewrite. Storage or prefix tokens, conditional/macro/nested definitions, multiple
definitions, extra instructions and every other unsupported assembly stay project-owned ports,
with unused or ambiguous selections reported rather than silently accepted.
Keil disassembly, AXF or a binary baseline is not a prerequisite, and the choice does not prove
the original binary behavior.

Managed multi-RAM placement is an explicit, reviewed choice. The optional
`memory.layout` object (MCP `memoryLayout`, CLI `--memory-layout` JSON) has
exactly `flash`, `data`, `bss`, `heap` and `stack`, and every value names an
existing region. Flash must be readable, executable and non-writable;
data/bss/heap/stack must be readable and writable. The managed linker places
each section in its selected region and keeps the `.data` load address in the
selected Flash with the existing `_sidata`/`_sdata`/`_edata`/`_sbss`/`_ebss`
runtime contract. A missing layout is accepted only for an unambiguous single
non-writable Flash plus single readable/writable RAM topology, which preserves
the historical generated bytes and model hash. Multiple managed Flash/RAM
candidates produce `MEMORY_LAYOUT_REQUIRED` with actual candidates and leave
every other blocker in place; configuration refuses rather than choosing the
first RAM. A writable executable RAM is never inferred as Flash, and CCM or
external SRAM is never selected automatically. An explicit all-main-RAM
mapping is valid and intentionally leaves other RAM unused. Native
linker-script projects keep their own placement and may not also declare
`memory.layout`. Fixed absolute sections remain address-bound `NOLOAD`
placements or their existing blocker; additional initialized/zero regions
still require a separate startup table contract. This is offline link/ELF
evidence, not proof that CCM, external memory or a physical board initializes
or runs correctly.

Explicit external RAM is a separate bounded input. Schema 2/3 manifests may
carry `memory.extraRegions`, and Keil preflight/PLAN/APPLY accept the same
explicit list as MCP `extraRegions` or CLI `--extra-regions` JSON. Every entry
has exactly `name`, `origin`, `length` and `attributes`; only `rw-`/`rwx`
writable RAM is representable, with at most 32 entries, linker-safe ASCII
names of 1-64 characters, exact integer ranges, no overlap with the declared
base or another extra region, and no inferred default. The persisted manifest
keeps the inspected base `memory.regions` and `memory.extraRegions` separate;
the typed `ProjectModel.memory.regions` is normalized once to the ordered
base-plus-extra tuple, which is the only map used by fixed-section admission,
managed layout selection, linker rendering, ELF/MAP accounting and build
identity. Omitted or empty extras preserve historical bytes, model hashes and
plan identities. A non-empty request is bound into migration plan identity,
exposed in preflight/PLAN/report evidence, and revalidated on apply against
the complete map, so a changed, shortened or omitted request refuses rather
than reusing an approved plan.

Extra regions add RAM candidates only, never Flash candidates. The existing
`memory.layout`/`memoryLayout` selection requirement remains when the combined
map is ambiguous, and managed `.data`/`.bss`/`.heap`/`.stack` are never placed
in an owner-supplied region implicitly: an explicit mapping must name it.
Fixed absolute sections remain address-bound `NOLOAD` placements and are not
promised initialized. The owner must arrange external-memory initialization
before access; external stack use can require earlier bootstrap than
`SystemInit`. A native linker script stays user-owned and is never rewritten.
This is offline source/link evidence, not hardware qualification.

An owner-supplied linker fragment is a separate, optional configuration input.
Schema 2/3 `generation.linkerFragment` names one project-relative UTF-8 file
that configuration reads under a bounded grammar: at most 32 custom writable-RAM
`NOLOAD` output sections, 64 KiB of raw bytes, `ALIGN`/selector/`KEEP` statements
only, and selectors confined to each output section's own family. Every region
name resolves against the same canonical base-plus-extra map used by fixed
sections, linker rendering, ELF/MAP accounting and build identity; only writable
regions are accepted, no region or capacity is inferred, and explicit addresses
must start inside their region. Managed and standard GNU families (vector, text,
rodata, data, bss, small-data, TLS, dynamic metadata, constructors/unwind,
heap/stack, `.stm32tk.abs.*`) are rejected case-insensitively. The fragment is
user-owned and is never rewritten or recorded as a managed file. Its path and
exact raw-byte SHA-256 participate in model identity, managed-manifest
provenance and build input snapshots; path/content edits, deletion and option
removal invalidate prior configuration and refuse the build before any compiler
spawn. Configuration renders validated sections after fixed sections and before
managed data/bss, and the generated CMake gains a conditional `LINK_DEPENDS` on
the merged linker only for this route. `NOLOAD` sections are never copied or
zeroed: initialized objects and external-memory availability remain the owner's
responsibility, and this is offline link evidence rather than behavioral or
hardware qualification.

Generation retains prior ownership and hash checks. Existing user files never become writable merely
because they occupy a generator target or have identical bytes. The implemented v1.0.1
editor-preservation behavior is described in its
[specification](superpowers/specs/2026-10-10-stm32tk-101-patch-design.md).
CubeMX regeneration has its own closed source inventory and refuses unknown paths.

Builds use the pinned external GCC/CMake/Ninja tools. Input snapshots include project configuration;
changed debug metadata can therefore require configure/build and a new physical receipt even when
the ELF bytes match. Stale or unverifiable output remains a refusal, not permission to refresh IDs.
Memory reports describe linker allocation/reservation, not runtime high-water usage. For accurate
Flash accounting, file-backed load ranges and NOBITS runtime ranges must remain distinct.

Git is a provenance source, not a build prerequisite. A committed HEAD produces the unchanged
schema-1 identity/record and build-ID semantics. When Git is missing, unborn, or unreadable, the
Toolkit emits schema 2 with `sourceBaseline: "input-snapshot-v1"`, null `gitHead`/`gitDirty`, and
bounded `gitEvidence` (`status: "unavailable"`, `code: "BUILD_GIT_INVALID"`, rule `head` or
`status`); it never initializes, commits, or fabricates a hash. Schema-1 validation stays strict and
does not accept nullable Git fields. Context freshness for schema 2 proves the exact current input
snapshot, model/target/preset, the actual `toolkitVersion`, and ELF/MAP digests without spawning Git, and
reports `sourceBaseline`, `gitDirty`, and `gitEvidence` explicitly. No-op reuse requires a compatible
current prior success record in the same provenance mode; unknown, tampered, cross-schema, stale, or
failed records are refused.

Snapshot provenance is a normal managed source, not a build-only form. One shared firmware
admission boundary decodes both provenance forms strictly and derives the same firmware facts for
managed flash, debug handoff, register/Fault reads, Target tests, Monitor and other
diagnostic/acceptance consumers: declared inputs, model/debug target, exact ELF/MAP bytes, build ID
and the successful build record must still match. Git commit and dirty state are optional
traceability for schema 1; schema 2 records explicit nulls plus bounded unavailable evidence. Null
is never clean, and no route initializes or fabricates Git state. Outer wrappers keep their own
protocol and may report or map a shared admission failure differently. Context still reports
`available`/`blocked`/`not-evaluated` honestly: `not-evaluated` means it did not inspect hardware,
not that the route is ready or blocked, and probe discovery stays independent. Missing probes,
stale builds, target/ELF mismatch, absent authorization and lease/ownership failures still stop
before effects. Migration planning and apply remain Git-independent: they bind the complete source
snapshot and destination instead of a committed HEAD.

External firmware import is a separate, source-only route for projects without
a managed model. It parses exactly one ELF/AXF (AXF is ELF), Intel HEX, or BIN
source into deterministic PT_LOAD segments, then emits a minimal ARM ELF32
programming image whose SHA-256 is distinct from the original source SHA-256.
The import store lives under a deterministic external workspace
(`projects/external-<key>/firmware-imports/<importId>`) derived from both the
canonical project and data roots; the deterministic import identity binds the
Toolkit version, both root digests, portable source path, format, source
SHA-256/size, base address, target, reviewed Flash-region declaration, image
SHA-256/size, segment summaries, and entry metadata. No timestamp participates
in identity. Admission is read-only and offline: it re-reads the stored source,
re-parses it with the recorded parameters, rebuilds the normalized image, and
compares bytes, segment summaries, entry metadata, and the canonical identity
before reporting `offlineReady=true`/`hardwareVerified=false`; it is not an
authorization token. Every store ancestor is revalidated for redirects before
reads, publication, programming, and receipt writes.

A separately authorized imported flash uses the existing owned Probe Service
one-shot lifecycle. Its session carries a private programming root containing
only the validated immutable import; the general project-root jail and legacy
`flash.program` behavior are unchanged, and legacy programming is refused in
an imported session. Before the first driver call the backend parses the
normalized image and requires every byte to be covered by the union of the
attached target's declared contiguous Flash intervals (gaps, non-Flash
intervals, and ambiguous overlapping maps are rejected). This native map is
support metadata, not a physical-capacity measurement. Normalized sector erase,
`trustCrc=false`, `keepUnwritten=true`, and failure cleanup are reused; the
workflow verifies every planned byte by bounded readback, revalidates the store
after attach, before the program RPC, and after readback, and commits a
distinct external-flash receipt only after readback, final integrity, and owned
cleanup. That receipt records no build, Git, or input-snapshot identity and
does not admit debug, Monitor, Target tests, or legacy flash evidence.

## Probe, debugging and Monitor

One physical probe has one owner. All attach/control uses the same Probe Service; no competing
backend, automatic probe selection, lease stealing, chip erase, Option Bytes or arbitrary writes.
Operation levels, exact identities and fresh authorization are checked before effects. Probe
enumeration is a separate read-only discovery path: it requires no project manifest, build,
backend, target, or SVD, creates no lease or project state, and establishes neither target identity
nor flash readiness. A valid configured project preserves its workspace ID; otherwise discovery is
explicitly unbound rather than inventing one. Hardware-capability booleans in project context are
not-evaluated snapshots, not evidence that the tools do not exist.

OBSERVE attach must meet its running-state postcondition. Sampling does not implicitly halt/reset/
resume the target. Full Fault analysis requires a separately authorized controlled snapshot when
halted core-register stability is needed. A recovery request does not authorize retry/fallback or
turn an OBSERVE operation into MODIFY. Recovery prepare remains static; execute consumes its action
once, proves physical identity, then performs only its authorized operation sequence.

Queueing and backend work consume the original absolute request deadline. An attach candidate is
published only on validated, in-deadline success; cancellation/failure abandons it before recovery.
Cleanup must prove owned worker exit and lease disposition rather than treating a terminate signal
or timeout as success. IDE handoff transfers ownership to the external debugger until normal detach
and successful end/reacquire; Toolkit must not access the probe during that interval.

SVD selection is exact, project-contained and bound to its identity and trusted readable regions.
The current contract validates every parsed register in the selected SVD, then separately validates
each requested read. An out-of-range register is a diagnostic, not permission to trust all addresses.
Debug binding compares the complete flash/build/probe/project identity; matching ELF hashes alone
do not authorize reuse of a different receipt.

Monitor binds `127.0.0.1` with a dynamic port and random token. Host, Origin and session checks protect
the local service. Use the authenticated tab opened by the current `open` invocation; do not publish
fragment URLs or tokens. `open` owns a foreground process; closing the tab or stopping sampling is
not service shutdown. The owning terminal's Ctrl-C invokes the existing cleanup path.

## Compatibility, evidence and current changes

Toolkit, Monitor, UI and plugin ship one release version. Schema/protocol compatibility must be
explicit; upgrades never silently rewrite project intent or historical evidence. Check is read-only;
Bootstrap/Repair use verified offline artifacts, staging, validation, promotion and bounded rollback.
Same-version source conflicts, downgrades and unknown future states remain refusals. The published
v1.3.4 release aligns the product authorities to 1.3.4 and adds 1.3.3 to the recognized legacy
managed-runtime and generation-producer versions while retaining the older entries. Like the
earlier recognitions it is read-only, so an existing 1.3.3 runtime still requires an explicit
authorized Repair, and a 1.3.3-generated project keeps its historical `generatedBy` value until an
explicit configure transaction. The previously published
v1.3.3 release aligned the product authorities to 1.3.3 and added 1.3.2 to the recognized
legacy managed-runtime and generation-producer versions while retaining the older entries. That
recognition is read-only: an existing 1.3.2, 1.3.1, 1.3.0 or 1.2.0 runtime still requires an
explicit authorized Repair, and a project generated by any of those versions keeps its historical
`generatedBy` value until an explicit configure transaction. The v1.3.2 diagnostic-clarity patch
aligned the authorities to 1.3.2 and was published on 2026-10-26; the v1.3.1 integration was
published on 2026-10-26; the earlier v1.3.0 local candidate (source `1e6ea849`) aligned the
authorities to 1.3.0, added 1.2.0 recognition, and was never published. Exact current build, flash,
import and export identities are not relaxed. The v1.3.4, v1.3.3, v1.3.2 and v1.3.1 packages ship 9
bundled Skills and the integrated 52-tool inventory, while the published v1.2.0 package remains
48 tools and 8 Skills.

Replay Acceptance `diagnosticSessionId` identifies 128 bits without RFC UUID version/variant
semantics. Public replay inputs accept lowercase compact 32-hex or grouped `8-4-4-4-12` spelling;
persisted replay records require the grouped spelling. Normalize before comparison, digest,
authorization or publication without changing any identity bits. Diagnostic storage lookup removes
only hyphens. Other UUID fields and physical compact-only IDs keep their own domains. Version 1.0
reads existing 0.9 records unchanged; a 0.9 reader is not a supported consumer of new 1.0 identities
outside its narrower UUID domain. Repair/rollback preserves original data and never translates IDs.

Physical repair evidence normally keeps a common EvidenceIdentity session across failed-before,
Diagnostic and fixed-after. A supported explicit continuation proof can bind original different
sessions without rewriting them. It grants no source-change or hardware authority. Valid lineage,
immutable historical references and current revision checks remain mandatory. Monitor analysis uses
canonical JSON; register comparison requires its explicit versioned scalar and time-alignment
contract. `OK` alone does not prove `quality=VALID`, `conclusion=COMPLETED` and the required change.

Fake/replay/internal-component checks establish only their named software properties. Real transport,
physical target, native Windows resources and published artifacts need their own evidence. A prior
PASS may be reused only when the relevant source, environment, dependencies and contract still apply.
See the [standard test procedure](testing/standard-test-procedure.md) and
[development rules](development.md) for acceptance and execution ownership.

The published v1.0.1 contract and schedule remain in its [specification](superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)
and [implementation plan](superpowers/plans/2026-10-10-stm32tk-101-patch-plan.md).
The accepted v1.2.0 source-delivery slice follows its
[specification](superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)
and [plan](superpowers/plans/2026-10-21-monitor-v120-delivery-plan.md). The v1.3.1
integration followed the
[integration design](superpowers/specs/2026-10-25-v131-integration-design.md) and
[plan](superpowers/plans/2026-10-25-v131-integration-plan.md); it was published on
2026-10-26. The v1.3.2 diagnostic-clarity patch follows the
[v1.3.2 design](superpowers/specs/2026-10-26-v132-diagnostics-design.md) and
[plan](superpowers/plans/2026-10-26-v132-diagnostics-plan.md); it was published on
2026-10-26 with its separately approved candidate-specific limitations. The v1.3.3 release
follows the [v1.3.3 plan](superpowers/plans/2026-10-27-v133-release-plan.md) and was published
on 2026-10-27 under an explicitly approved candidate-specific exception. The v1.3.4
release follows the
[v1.3.4 specification](superpowers/specs/2026-10-27-v134-migration-readiness.md) and
[plan](superpowers/plans/2026-10-27-v134-migration-readiness.md) and is the current
[Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4) release, published
2026-10-28 from frozen source `a7db6a8c` under an explicitly approved candidate-specific
exception; its permanent unmet coverage gates and disclosed limits did not become PASS. The
earlier v1.3.0
local Release preparation remains historical evidence
([design](superpowers/specs/2026-10-24-v130-local-release-design.md),
[plan](superpowers/plans/2026-10-24-v130-local-release-plan.md)). The
[v1.3.3 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3)
is the previous public version and the source for its asset availability, final
qualification and limitations; the
[v1.3.2 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2)
is the version before it, and the
[v1.3.1 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1) and
[v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)
remain earlier public releases. [Release status](release-status.md) retains the dated
historical evidence, checkpoints and limitations; the Release pages remain the authority for
asset availability and final qualification. Architecture and source behavior alone do not
establish package installation, interactive browser, IDE or hardware qualification.
The earlier [v1.1.2 source delivery](superpowers/specs/2026-10-16-monitor-v112-source-delivery-design.md) remains a historical source record.
Older designs remain recoverable from Git history at `694c825d29a55a53052a148efa4cc6720c315a04`;
they are historical evidence rather than additional current workflow entry points.
