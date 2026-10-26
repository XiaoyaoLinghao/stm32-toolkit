# v1.3.2 diagnostic clarity and IDE binding guidance

Accepted base: `cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`.
Module: STM32TK-132; branch `codex/v132-guidance`, no PR.
The user's 2026-10-26 instruction approves these three improvements and v1.3.2
build/release. Primary owns specification, orchestration, independent review and
release; local Claude Code CLI with the existing provider owns implementation
and tests. No ownership override. Original firmware project, hardware, installed
user runtimes, global settings and Skills are excluded. Independent final IDE
and user installation testing remains user-owned. No code/tool inventory expansion.

## Diagnostic contract

Preserve all existing doctor fields and their semantics. `data.tools.pyocd` is
PATH executable evidence, while `data.probeCore.dependencies.pyocd` is installed
distribution metadata in this interpreter. Collect both once per doctor call.
Add `data.probeCore.pyocdResolution`, with `status` equal to
`runtime-package-present` or `runtime-package-unconfirmed`, `runtimeAvailable`,
`runtimeVersion`, `pathCommandAvailable`, `pathCommandStatus`,
`evidenceBasis: distribution-metadata`, `hardwareVerified: false`, `message`,
and `remediation`. A metadata observation is neither importability nor physical
readiness. A failed metadata lookup is unconfirmed, not proof of uninstall.

When runtime metadata is present but PATH lookup is missing, include an additive
top-level `data.diagnostics` entry with component `pyocd`, code
`PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT`, severity `info`, and clear message/remediation.
Explain that internal Probe backend imports pyOCD from its runtime and that a
missing PATH command alone does not establish a missing runtime dependency.
When runtime metadata is unavailable, emit `PYOCD_RUNTIME_PACKAGE_UNCONFIRMED`
with severity `warning` even if a separate PATH command exists. Direct the caller
to the matching managed interpreter/setup Check; never suggest global pip or
PATH edits as the default remedy. Preserve CLI timeout/nonzero/unknown evidence
without converting it to runtime failure or success. Do not import pyOCD, start a
worker, enumerate probes or perform extra process/network discovery.

## Configure PLAN/APPLY guidance

Add a derived `data.vscodeGuidance` object to public configure PLAN and every
successful APPLY result (including unchanged/idempotent apply):

- `bindingMode`: `user-settings` when both optional bindings are absent, otherwise
  `explicit-paths` after the existing paired validation.
- `requiredUserSettings`: the two existing `stm32-toolkit.executablePath` and
  `stm32-toolkit.compilerPath` keys for defaults; empty for explicit bindings.
- `userSettingsChecked: false`; this offline call never reads VS Code user settings
  and must not assert they are actually unbound.
- `preservedPaths`: exactly the plan files with status `preserved-unowned`.
- `diagnostics`: additive structured explanatory entries.

Default bindings produce `VSCODE_EXECUTABLE_SETTINGS_REQUIRED` (severity `info`):
the generated command/IntelliSense values require those User Settings to contain
reviewed absolute native paths. Offer the existing paired CLI/MCP arguments on
both PLAN/APPLY as the alternative. Never imply PATH installation is required.
An explicit pair must not receive the default-settings-required diagnostic.

If `.vscode/tasks.json` is preserved-unowned, additionally produce
`VSCODE_TASKS_PRESERVED` (severity `warning`, path `.vscode/tasks.json`). Explain
that existing tasks were retained, requested bindings/new tasks were not applied
to that file, contents were not inspected and old bare commands may remain.
Give manual review instructions using the absolute managed runtime executable or
the documented User Settings, and the exact PLAN/APPLY fields to inspect.
Do not claim to have found a bare command. Other preserved editor paths remain
reported and existing warnings stay compatible.

This metadata is derived only from the validated configuration and existing file
statuses. Do not open/hash/parse/adopt user-owned preserved files, read global
settings, alter rendered task bytes, add generation inputs, change plan hashing,
weaken revalidation/ownership/drift rules, repair hashes by hand or add an auto-run.
Plan output is advisory, not an authorization or proof of installation/IDE use.

## Documentation, version and verification

Update the VS Code/AI user guide and relevant setup/configure Skills to read both
pyOCD evidence fields and the new guidance, including preserved paths. Keep
machine-specific paths as examples and never edit the original project.
Implement behavior first, review, then separately align active product/package/
plugin/launcher/setup/version identities to 1.3.2 while retaining 1.3.1 as an
explicit legacy runtime/generation producer. Historical evidence is immutable.

Author owns unit/public CLI/MCP regression tests; primary independently reviews
the complete diff and runs focused integration checks from a clean exact-head
worktree. Cover present/missing runtime and PATH combinations, metadata errors,
CLI nonzero, default/explicit bindings, preserved tasks with unread contents,
unchanged and writing APPLY, byte preservation and plan identity stability.
No hardware, original project edits, runtime installation or GUI operations.

Release qualification is bounded to this patch's affected software layers and
source-bound reusable baseline evidence; no unrelated coverage expansion loop.
Permanent gates remain unchanged; the v1.3.1-only exception does not transfer.
Prepare exact frozen source, double reproducible 13-asset builds, concrete
qualification/notes and independent hashes before any required exception decision.
Publish only the new v1.3.2 tag/assets, never replace v1.3.1. User's release request
authorizes the necessary new source push/tag/Release actions; final qualified
status and any unmet gates must remain truthful and explicitly disposed.
