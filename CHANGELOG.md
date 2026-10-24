# Changelog

## [v1.3.0 local candidate]

- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to `1.3.0`. Recognize
  an existing `1.2.0` managed runtime and `1.2.0`-generated project as legacy inputs while
  retaining the older `1.1.2`/`1.0.1`/`1.0.0`/`0.9.0` compatibility. Recognition is
  read-only: advancing a runtime still needs an explicit authorized `Repair`, and existing
  `generatedBy` values are not rewritten. Exact current build, flash, import and export
  identities are unchanged.
- Bundle `normalize-source-comments` as the ninth discoverable Skill: an explicit,
  preview-first, per-file encoding helper that writes comment-only UTF-8 copies outside the
  project. It is not a migration step and adds no MCP tool.
- The declared final v1.3.0 inventory is 52 MCP tools and 9 Skills. The separately owned
  external-firmware slice supplies the remaining three MCP registrations and is not part of
  this version-preparation change; until it is integrated this branch exposes 49 tools.
  Offline imported-firmware admission is likewise separate from any authorized flashing.
- Known boundaries carried by this candidate: there is no native Keil UV4 build backend,
  no automated VS Code extension readiness probe (`vscodeExtensions` stays `not-probed`),
  and no migration-baseline comparison verdict (a discovered AXF/MAP baseline is not proof
  of toolchain, source or binary comparability). Migration remains one-way and Git-gated
  for plans, refuses unknown source encodings and arbitrary ARMCC assembly, and only
  generates startup for the bounded conventional ST/CMSIS Cortex-M3/M4/M7 case; scatter,
  memory and multi-RAM decisions require explicit reviewed input.
- **Not released.** This entry records a local source candidate only. There is no v1.3.0
  bundle, tag, GitHub Release, download link, installation or qualification. The
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
