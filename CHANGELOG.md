# Changelog

## [Unreleased] — v1.2.0 source candidate

- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to 1.2.0. Recognize 1.1.2 managed runtimes and generated projects as legacy inputs while preserving older supported inputs, user-edited files, and exact-version export checks. An explicit Repair or configure transaction is required to advance current artifacts.
- Include the accepted Monitor workbench, source catalog, preserved-state connection, u16 composition and consistent-read behavior, including the accepted schema 3 observation-group storage migration. This version-alignment change introduces no further protocol, storage-schema or wire-schema change.
- This is source delivery only. No 1.2.0 bundle, installation, browser or hardware qualification, tag, or GitHub Release is implied. The latest published release remains v1.0.1.

## [v1.1.2 source delivery]

- Deliver the accepted Monitor workbench source update: fixed local entry and session recovery, Chinese interface and accessible group workflow, live connection and data freshness, shared-time chart inspection, and history/export range clarity. Preserve the existing API, protocol and data schema versions.
- Align Toolkit, Monitor, UI, plugin, launchers and release metadata to 1.1.2. The published 1.0.1 runtime and generated projects remain identifiable as legacy inputs; only an explicit Repair or configure transaction advances current artifacts. Existing export manifests still require exact runtime versions, so create a new export under 1.1.2 rather than reusing a 1.0.1 export as a current artifact.
- This entry records the earlier source-branch delivery only. No 1.1.2 bundle, installation, browser or hardware qualification, tag, or GitHub Release was implied. The latest published release remains v1.0.1.

## [v1.0.1] — 2026-10-10

- Published behavior: guarded nested Keil discovery and clearer migration blockers; preserved unowned editor files during configure; corrected linker stack symbols and NOBITS accounting; clearer Probe, SVD, flash, context, doctor and Monitor diagnostics. The release has a consistent v1.0.1 product identity and a controlled 1.0.0 runtime Repair path. Old 1.0.0/0.9.0 project producer identities remain readable, and user-edited managed files remain protected.
- Current source-tree maintenance: concise English and Chinese README entry points, a user guide covering the 22 reported issues, and a current Windows deployment/IDE preflight. Obsolete plans, reports, progress snapshots, and their retired release tools/tests leave the current tree; Git history remains available by commit and path.
- Review, qualification, installation, hardware scope and published asset identities are recorded in [release status](docs/release-status.md) and the [execution ledger](docs/codex/returns/STM32TK-101/execution.md). The v1.0.0 tag and published assets are unchanged.

## [v1.0.0] — 2026-10-08

- Published Windows x86_64 local toolkit release with CLI/MCP, managed runtime, Keil migration, CMake builds, Probe Service, Monitor, tests and diagnostic evidence.
- Acceptance used a candidate-specific user-approved coverage exception; it does not change future release thresholds. See [release status](docs/release-status.md) for the fixed identity, hashes and retained limitations.
