# Changelog

## [Unreleased]

- Migration/debug handoff guidance only; no new tool, option, schema or hardware behavior. A
  Keil delivery PLAN and a successful APPLY now expose the same derived
  `data.debugConfiguration` object the read-only preflight already reports (`phase`,
  `status`, `missingFields`, `diagnostics`, `nextSteps`, `targetSupport`,
  `hardwareVerified`, `blocking=false`), and the readable `data.followUp` string is derived
  from that same shared helper. The guidance binds the conversion's destination root
  (`data.outputRoot`), names the existing paired `project configure` PLAN with
  `--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json` followed by its
  exact-plan APPLY, and places that edit before build/flash identities are established. It
  also explains why the generated `.vscode/launch.json` stays empty: a live Cortex-Debug
  configuration exists only after an authorized handoff-begin, whose
  `data.cortexDebugLaunch.configuration` belongs to an independent external IDE workspace
  that must detach before handoff-end consumes the original ticket. The derived text never
  enters the hashed plan/content identity, adds no blocker, infers no backend/target and
  performs no hardware action.
- Implemented: preset-specific build evidence. Ordinary un-`clean` debug/release switching
  retains valid incremental evidence per preset; `arm-debug` keeps
  `artifacts/migration/build-result.json` and `artifacts/migration/build.log`, while
  `arm-release` publishes `artifacts/migration/arm-release/build-result.json` and
  `artifacts/migration/arm-release/build.log`. Identities stay at
  `build/<preset>/firmware-identity.json`, so no automatic clean is required, and
  malformed/failed/redirected canonical evidence is still refused rather than bypassed.
  A pre-fix release that already overwrote the global debug receipt cannot have that debug
  evidence reconstructed; one explicitly authorized `arm-debug --clean` rebuild may be
  needed once.
- Implemented: bounded CLI `--flash-regions` diagnostics. The accepted schema is exactly
  1..32 objects of `[{"start": <integer>, "length": <integer>}]`; `name` and `origin` are
  unsupported keys. Grammar failures keep exit code 2 with fixed messages that name the
  rejected aspect — bad JSON or wrong shape, missing or unsupported region fields,
  duplicate fields, and non-integer types where `bool` is not an integer — plus the
  1-based region index where applicable, without echoing caller payloads; `--help` shows
  the schema plus one example. Address-range, positive-length and other security checks
  remain existing workflow validation and are not part of this CLI diagnostic change.
- Implemented: controlled pre-program preparation for firmware programming. Managed
  `stm32_flash` and imported `stm32_flash_imported` now perform exactly one explicit
  `Target.ResetType.SYSRESETREQ` reset-and-halt after the existing service identity,
  immutable-image, MODIFY/action authorization and imported Flash-map admission checks, then
  read the target state and require `halted` before entering the programmer. Under-reset
  recovery reuses its connection-time reset instead of adding a second one and only
  re-verifies `halted`; the observe-preserve policy still refuses programming before any
  reset. The closed schema-1 program diagnostic gains two stages, `pre-program-reset` and
  `pre-program-halt`, alongside `driver-acquire`, `programmer-create` and `program-call`;
  every pre-program preparation failure is `PROBE_PROGRAM_FAILED` with bounded sanitised
  exceptions, and a failure in either new stage reaches no programmer, readback, success
  receipt or second program call, while the existing owned cleanup still runs.
  `details.flashOptions` additionally reports `preProgramReset`
  (`sysresetreq` normally, `under-reset-connect` for recovery) and
  `preProgramHaltRequired: true` as selected policy, not evidence that a reset or attach
  happened. No input option, schema/receipt version, erase/keep-unwritten
  behavior, automatic retry, target-state repair or post-flash run is added by
  this entry; the separately listed ordinary-flash default-frequency change
  does not alter any of them. The reset is
  part of the authorized flash operation and grants no later independent reset, resume,
  Monitor or handoff authority; offline success does not claim a physical HardFault fix.
- Implemented: optional retained attach stage progress. Only the parent may add a closed
  `attachDiagnostic.progress` snapshot to an existing service attach timeout/cancellation
  diagnostic: `version=1`, `clock="parent-receipt"`, a bounded `elapsedMs`, and an ordered
  subsequence of the closed stage vocabulary beginning with a parent-created
  `worker-dispatch` at zero. Small stage frames use the existing owned worker connection,
  are accepted only for the matching `open_attach` request ID under the original absolute
  deadline, and never renew it. `PyOCDBackend` marks entry into its existing lazy driver
  acquisition, single enumeration, prior close, session create/open, target resolution,
  identity and the halt or resume branch through a private optional callback without adding
  target actions, warmup, retries or a second enumeration. The service attaches a validated
  snapshot only when its private per-attempt token matches, keeps it local and detached, and
  preserves it across the owned worker abort; raw child diagnostics carrying `progress` are
  rejected. Absent progress keeps the exact previous five-key envelope, successful attach
  results and all cleanup/control ordering are unchanged, and every timing marker is
  approximate observed IPC entry evidence — not a hardware duration, completion proof or
  target state.
- Implemented: ordinary flash default debug frequency. The shared production
  `ProbeWorkerConfig` and the direct `PyOCDBackend` constructor now default to
  exactly `100000` Hz (100 kHz), so an omitted `frequencyHz`/`--frequency` on
  managed flash, imported flash and normal Target programming reaches 100 kHz
  without selecting under-reset recovery or adding a reconnect, retry, warmup or
  extra enumeration/read/control. Omitted requests still forward `null` and an
  explicitly supplied private worker configuration is reused unchanged; the
  explicit frequency range `100000..50000000`, precedence, type/range/conflict
  errors and reset/halt, erase, keep-unwritten, identity, authorization, readback,
  cleanup and deadline behavior are unchanged. A supported faster value remains an
  optional explicit configuration, and 1 MHz is no longer a flash requirement or
  acceptance gate. CLI help, both registered MCP tool descriptions, the user guide
  and the flash Skill state this default and the optional override. The fixed
  100 kHz under-reset-recovery and observation/observe-preserve policies remain
  distinct from the ordinary default. Slower wire transfer may increase physical
  elapsed time; no hardware performance, frequency measurement or reset efficacy
  is claimed, and finite deadlines are unchanged.
- All entries above are local `Unreleased` corrections planned for `v1.3.5`; they are not
  part of the published v1.3.4 bytes, are not an accepted release, and packaging,
  installation and release qualification have not been performed for them. The controlled
  pre-program preparation entry is a real source-level hardware behavior change (one
  authorized `SYSRESETREQ` reset-and-halt on the managed and imported routes); the
  ordinary-flash 100 kHz default is likewise a source-level behavior change for any
  omitted frequency. Neither has
  hardware acceptance evidence until the change is installed and explicitly qualified on a
  board.

## [v1.3.4] - 2026-10-28

- Implemented: structurally balanced outer include guards allow independent nested
  conditionals, while true nested macro definitions remain rejected.
- Implemented: read-only preflight discovers potential quoted-header encoding blockers
  without transcoding. On an actual guarded UTF-8 project the zero-blocker `PLAN` was verified at
  the final full-core capture `e02d63605bccc1011712b1e458725c51ee51ab79` with 191 planned
  outputs; no apply, build or flash ran, so this is plan-level evidence only.
- Implemented: version alignment to `1.3.4` across the active Toolkit, Monitor, UI
  package/lock root, plugin, launchers, setup/release metadata, plus recognition of a
  `1.3.3` managed runtime and a `1.3.3`-generated project as supported legacy inputs while
  every older entry and guard is retained. Recognition is read-only: a `1.3.3` runtime
  advances only through an explicit authorized `Repair`, and an existing `generatedBy`
  value is not rewritten until an explicit configure transaction. Same-version source
  conflicts, downgrades, unknown future states and rollback rules are unchanged.
- Neither change alters ABI or floating-point ABI decisions, debug-address inference or
  transcoding behavior.
- Published as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4)
  from frozen source/tag target `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead`. The release
  (ID `426198381`) was observed public and Latest at `2026-10-28T02:39:44Z` with
  `draft=false` and `prerelease=false`; all 13 uploaded assets match the sizes and SHA-256
  of the two canonical builds. Anonymous download of all 13 files then returned HTTP 200
  with exact frozen bytes and matching SHA-256 (record
  `a1ee3e26f903c94d56f4967d8c0240189c264133f4f0d08d73e55ce218aa667a`).
  Documents inside the frozen package keep the build-time candidate wording they were
  built with; the current [release status](docs/release-status.md) and the Release notes
  record the observed publication. Published assets and tags are not rewritten.
- The user explicitly approved a candidate-only **USER_APPROVED_EXCEPTION** for this fixed
  package and its disclosed limits ([approval record](docs/codex/returns/STM32TK-134/authorization-2026-10-28.md)):
  Toolkit overall 82.7452% and risk 82.6335% remain below the 90% floors, Monitor risk
  92.3681% remains below its 95% floor, source-bound evidence reuse and original
  failures/skips are retained, and vendor-firmware, installation, VS Code and hardware
  limits are unchanged. Permanent gates and memberships are not lowered, and unmet values
  or skips do not become PASS. Final recipient installation and independent VS Code testing
  remain user-owned and pending; see [release status](docs/release-status.md).
- Later local corrections recorded under `[Unreleased]` are **not** part of the published
  v1.3.4 bytes; no build, CLI fix or documentation change in this source tree is claimed to
  have shipped in that release.

## [v1.3.3] - 2026-10-27

- Align the active Toolkit, Monitor, UI package metadata/lock root, plugin, launchers,
  setup, release utility/policy and release schema to `1.3.3`. Dependency versions and
  schema/template versions are unchanged. Recognize an existing `1.3.2` managed runtime
  and `1.3.2`-generated project as supported legacy inputs while retaining every older
  entry and guard. Recognition stays read-only: a `1.3.2` runtime advances only through an
  explicit authorized `Repair`, and an existing `generatedBy` value is not rewritten until
  an explicit configure transaction. Same-version source conflicts, downgrades, unknown
  future states and rollback rules are unchanged.
- Keil migration publishes one complete, independently buildable GCC/CMake project into a
  new absolute destination (`keil convert --destination`); the Keil source is read-only and
  public conversion has no in-place fallback. Complete source preparation preserves every
  ordinary project file while omitting Git metadata, and an explicit WFI normal-return
  intent records reviewed source behavior without claiming binary equivalence.
- Content identity is normal managed admission: Git remains optional traceability, and a
  schema-2 input-snapshot build of a new or migrated project uses the same normal managed
  GCC build, managed flash, debug handoff, Monitor and Target routes. New-project creation
  prepares a complete destination, and its apply both drops only its own staging CMake
  caches and initializes an empty durable lock only after native acquisition by the owner.
- Offline qualification at this source ran real GCC builds plus a simulated managed-flash
  journey; the new-project journey replaces only external CubeMX generation with a labeled
  synthetic adapter because no vendor firmware package is present. This is not vendor
  package generation, hardware, installation or IDE acceptance. Final installation and
  independent VS Code testing remain user-owned and pending. Detailed qualification stays
  in [release status](docs/release-status.md).
- Published as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3)
  on 2026-10-27 from frozen source `46ca09084bbe39f670714d19d7d55f9365ef06be`, with 13
  published assets matching the frozen package sizes and SHA-256. The user explicitly
  approved this candidate-specific exception and its disclosed coverage, reuse and platform
  limits ([approval record](docs/codex/returns/STM32TK-133/authorization-2026-10-27.md));
  the permanent coverage/risk gates remain unmet and unchanged. Final installation and
  independent VS Code testing remain user-owned and pending. Frozen package documentation
  keeps its build-time candidate status; this entry supersedes that status.

## [v1.3.2] - 2026-10-26

- Align the active Toolkit, Monitor, UI package metadata/lock root, plugin, launchers,
  setup, release utility/policy and release schema to `1.3.2`. Dependency versions are
  unchanged, including the existing `lark`/`pyusb` 1.3.1 pins; template content, schema
  versions, authorization and ownership/drift rules are unchanged.
- Recognize an existing `1.3.1` managed runtime and `1.3.1`-generated project as supported
  legacy inputs while retaining every older entry and guard. Recognition is read-only: an
  existing runtime still advances only through an explicit authorized `Repair`, and the
  project `generatedBy` value is not rewritten until an explicit configure transaction.
  Same-version source conflicts, downgrades, unknown future states and rollback rules are
  unchanged.
- Separate pyOCD evidence: `data.tools.pyocd` remains PATH command evidence while
  `data.probeCore.dependencies.pyocd` is installed-distribution metadata and
  `data.probeCore.pyocdResolution` combines them as metadata-only evidence. Add inclusive
  `PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT` (`severity="info"`) when metadata is present but
  the PATH command is missing, and `PYOCD_RUNTIME_PACKAGE_UNCONFIRMED`
  (`severity="warning"`) when metadata cannot be confirmed, even if a PATH command exists.
  These fields do not verify importability, a working Probe backend or hardware, and a
  missing PATH command alone does not establish a missing runtime dependency. CLI
  nonzero/timeout evidence is preserved unchanged.
- Add advisory `data.vscodeGuidance` to configure PLAN and every successful APPLY result,
  including unchanged/idempotent apply: `bindingMode`, `requiredUserSettings`,
  `userSettingsChecked=false`, `preservedPaths` and explanatory
  `VSCODE_EXECUTABLE_SETTINGS_REQUIRED`/`VSCODE_TASKS_PRESERVED` diagnostics. Explicit
  bindings receive no default-settings diagnostic. It never reads preserved-unowned editor
  contents or evaluates effective VS Code settings for binding readiness, never changes
  generated bytes or plan identity, and is not proof of installation or IDE use.
- Published as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2)
  on 2026-10-26 from frozen source `acb71b9f39e8ae4799179b0cab088245c0a5ea5b`, with 13
  verified assets. The user explicitly approved this candidate's disclosed coverage, reuse
  and platform limitations and its publication as Latest; this is a new exception, not a
  transfer of v1.3.1's, and it does not mean the numerical coverage/risk gates passed. Final
  installation and independent VS Code testing remain user-owned and pending. Frozen package
  documentation keeps its build-time candidate status; this entry supersedes that status.

## [v1.3.1] - 2026-10-26

- Published as [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1)
  from frozen source `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`, with 13 verified assets.
- Include the v1.3.0 candidate's Git-free preflight/build and external-firmware routes,
  plus safe scoped includes, bounded common ARMCC migration, explicit extra memory
  regions/linker fragments, PyOCD configuration and reviewed comment replacement.
- Improve floating-point ABI decisions, stale-build diagnostics, VS Code tasks,
  doctor readiness, flash-frequency guidance and memory-margin warnings.
- Retain the approved candidate-specific coverage/reuse limits. The user explicitly
  requested publication before their final installation and VS Code independent
  testing; that testing remains pending. See [release status](docs/release-status.md).

## [v1.3.0 local candidate]

- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to `1.3.0`. Recognize
  an existing `1.2.0` managed runtime and `1.2.0`-generated project as legacy inputs while
  retaining the older `1.1.2`/`1.0.1`/`1.0.0`/`0.9.0` compatibility. Recognition is
  read-only: advancing a runtime still needs an explicit authorized `Repair`, and existing
  `generatedBy` values are not rewritten. Existing exact build, flash, import and export
  identity checks are not relaxed.
- Add a read-only, Git-free Keil preflight (`keil preflight` / `stm32_keil_preflight`):
  it reports structured capability diagnostics and separates `planReadiness` from
  `applyReadiness` without writing files or emitting a plan ID, and `keil inspect`
  remains available without a migration baseline. Read-only probe discovery
  (`probe list` / `stm32_probe_list`) is decoupled from preflight, manifest and build
  facts, and does not grant hardware authority.
- Support a content-snapshot managed build for projects without a usable Git identity:
  `schemaVersion: 2` records `sourceBaseline: "input-snapshot-v1"`, explicit null Git
  fields and bounded `gitEvidence`, and freshness depends on the exact input snapshot,
  target/preset/model and ELF/MAP hashes. The hardware-managed flash, debug, Target and
  Monitor route still requires a Git-verified build identity.
- Add explicit opt-in bounded CMSIS GCC startup generation for conventional ST/CMSIS
  Cortex-M3/M4/M7 ARMCC5 startup, and an explicit `memoryLayout` that maps the five
  roles `flash`, `data`, `bss`, `heap` and `stack` to declared regions. Multiple RAM
  candidates require an explicit reviewed selection; no RAM is chosen by default.
- Add the accepted external-firmware route: import an original ELF/AXF, Intel HEX or BIN
  file into an immutable project-bound snapshot, admit it offline, and only then offer a
  separately authorized flash to one exact probe. The imported source SHA-256 and the
  normalized programming-image SHA-256 are distinct fields. The route needs no managed
  manifest, Git baseline, build receipt or SVD, and an imported receipt does not unlock
  debug, Monitor, Target tests, a managed build identity or legacy flash evidence.
- Bundle `normalize-source-comments` as the ninth discoverable Skill: an explicit,
  preview-first, per-file encoding helper that writes comment-only UTF-8 copies outside the
  project. It is not a migration step and adds no MCP tool.
- The integrated v1.3.0 inventory is 52 MCP tools and 9 Skills, including the external
  registrations `stm32_firmware_import`, `stm32_firmware_admit` and
  `stm32_flash_imported`. The published v1.2.0 package remains 48 tools and 8 Skills.
  Offline import/admission is separate from any authorized hardware flash.
- Known boundaries carried by this candidate: there is no native Keil UV4 build backend,
  no automated VS Code extension readiness probe (`vscodeExtensions` stays `not-probed`),
  and no migration-baseline comparison verdict (a discovered AXF/MAP baseline is not proof
  of toolchain, source or binary comparability). Migration remains one-way and Git-gated
  for plans, refuses unknown source encodings and arbitrary ARMCC assembly, and only
  generates startup for the bounded conventional ST/CMSIS Cortex-M3/M4/M7 case; scatter,
  memory and multi-RAM decisions require explicit reviewed input.
- **Not released as a GitHub Release.** This entry records a local v1.3.0 candidate. There
  is no v1.3.0 tag, GitHub Release, public download link, installation or qualification.
  Local candidate construction and validation are recorded in the delivery evidence; full
  qualification and publication remain pending. The
  [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)
  remains the current public download, and its one-time qualification exception does not
  transfer. See [release status](docs/release-status.md).

## [v1.2.0]

- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to 1.2.0. Recognize 1.1.2 managed runtimes and generated projects as legacy inputs while preserving older supported inputs, user-edited files, and exact-version export checks. An explicit Repair or configure transaction is required to advance current artifacts.
- Include the accepted Monitor workbench, source catalog, preserved-state connection, u16 composition and consistent-read behavior, including the accepted schema 3 observation-group storage migration. This version-alignment change introduces no further protocol, storage-schema or wire-schema change.
- The [release status](docs/release-status.md) preserves a dated pre-freeze qualification checkpoint. Consult the [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) for asset availability, final qualification and limitations.

## [v1.1.2 source delivery]

- Deliver the accepted Monitor workbench source update: fixed local entry and session recovery, Chinese interface and accessible group workflow, live connection and data freshness, shared-time chart inspection, and history/export range clarity. Preserve the existing API, protocol and data schema versions.
- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to 1.1.2. The published 1.0.1 runtime and generated projects remain identifiable as legacy inputs; only an explicit Repair or configure transaction advances current artifacts. Existing export manifests still require exact runtime versions, so create a new export under 1.1.2 rather than reusing a 1.0.1 export as a current artifact.
- This entry records the earlier source-branch delivery only. No 1.1.2 bundle, installation, browser or hardware qualification, tag, or GitHub Release was implied. At that source delivery, the latest published release was v1.0.1.

## [v1.0.1] — 2026-10-10

- Published behavior: guarded nested Keil discovery and clearer migration blockers; preserved unowned editor files during configure; corrected linker stack symbols and NOBITS accounting; clearer Probe, SVD, flash, context, doctor and Monitor diagnostics. The release has a consistent v1.0.1 product identity and a controlled 1.0.0 runtime Repair path. Old 1.0.0/0.9.0 project producer identities remain readable, and user-edited managed files remain protected.
- Current source-tree maintenance: concise English and Chinese README entry points, a user guide covering the 22 reported issues, and a current Windows deployment/IDE preflight. Obsolete plans, reports, progress snapshots, and their retired release tools/tests leave the current tree; Git history remains available by commit and path.
- Review, qualification, installation, hardware scope and published asset identities are recorded in [release status](docs/release-status.md) and the [execution ledger](docs/codex/returns/STM32TK-101/execution.md). The v1.0.0 tag and published assets are unchanged.

## [v1.0.0] — 2026-10-08

- Published Windows x86_64 local toolkit release with CLI/MCP, managed runtime, Keil migration, CMake builds, Probe Service, Monitor, tests and diagnostic evidence.
- Acceptance used a candidate-specific user-approved coverage exception; it does not change future release thresholds. See [release status](docs/release-status.md) for the fixed identity, hashes and retained limitations.
