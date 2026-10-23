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

Keil inspection is read-only. Keil-to-GCC migration is one-way, uses deterministic plans and
digest-checked authorized apply, and never rewrites `.uvprojx` or synchronizes two build systems.
Preflight runs the same technical analysis as planning without requiring Git; blockers and apply
prerequisites stay separate, and preflight never creates a plan ID or mutates state. Missing Git,
unborn HEAD, and dirty work are diagnosable but remain explicit project-owner decisions before a
Git-bound plan. Only implemented compiler/source rules are supported. Non-UTF-8 sources and
unsupported ARMCC assembly require explicit project-owned adaptation; the Toolkit does not guess
encoding, silently transcode, or invent MCU startup/vector initialization. Keep compiler migration
separate from SPL/HAL conversion.

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

Snapshot provenance is build-only. Flash, debug, Target tests, Monitor, and acceptance protocols
still require Git-shaped firmware provenance. The shared firmware admission boundary validates the
snapshot identity and then returns `FIRMWARE_PROVENANCE_UNSUPPORTED` before any probe, lease, or
attach effect; outer wrappers may map that failure under their existing protocol (for example
acceptance recovery maps admission failure to `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID`), so the same
externally visible code is not promised from every entry. Context exposes this known blocker as
`blocked` in the affected hardware `capabilityDetails` for a fresh snapshot build, while legacy
false capability booleans remain conservative compatibility fields and read-only probe discovery
stays independent. Migration planning and apply continue to require their committed Git baseline.

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
Same-version source conflicts, downgrades and unknown future states remain refusals.

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
and [plan](superpowers/plans/2026-10-21-monitor-v120-delivery-plan.md). The
[v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)
is the source for asset availability, final qualification and limitations; [release status](release-status.md)
retains the dated pre-freeze candidate evidence. Architecture and source behavior alone
do not establish package installation, interactive browser, IDE or hardware qualification.
The earlier [v1.1.2 source delivery](superpowers/specs/2026-10-16-monitor-v112-source-delivery-design.md) remains a historical source record.
Older designs remain recoverable from Git history at `694c825d29a55a53052a148efa4cc6720c315a04`;
they are historical evidence rather than additional current workflow entry points.
