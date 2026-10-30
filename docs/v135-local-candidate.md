# v1.3.5 local candidate guide

**Status: unpublished local candidate. Not published, not installed.**
Preparation checkpoint **2026-10-30**: documentation and identity wording only; no package, runtime
or test result is asserted on this page. The candidate source version is **1.3.5**; runtime
installation is a separate explicitly authorized step.
The maintained current build, integration and qualification records are
[release status](release-status.md) and the
[STM32TK-135 implementation report](codex/returns/STM32TK-135/implementation-report.md); read those
for the actual state instead of this page. There is **no** v1.3.5 release page, download, installer,
or remote artifact. The current latest published release is **v1.3.4**
([Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4)), and earlier
releases remain available; the v1.3.4 published recipe stays in the [user guide](user-guide.md). Do
not reuse published v1.3.4 asset names or checksums for this candidate, and do not describe the
candidate as downloadable, published, or installed.

This guide covers what a local candidate supports and which facts are *not yet* established. It
makes no firmware-correctness, ABI/CCM, target-execution, or hardware-acceptance claim.

## Identity checks (bundle, runtime, CLI, MCP)

Verify each layer separately; one layer never proves another.

1. **Bundle.** Confirm the extracted tree is the locally built 1.3.5 candidate itself: its setup
   helper belongs to that tree and reports the candidate runtime version `1.3.5`, and its manifest
   is the candidate's own, not the published v1.3.4 manifest. Use the candidate's own local
   checksums/manifest when the candidate package is built; do not fall back to v1.3.4 values.
2. **Runtime.** After any separately authorized Bootstrap/Repair, the managed runtime lives at
   `${CLAUDE_PLUGIN_DATA}/runtime/1.3.5`, and the single published generation in
   `runtime/runtime-state.json` reports version `1.3.5`. An installed `1.3.4`, `1.3.3`, `1.3.2`,
   `1.3.1`, `1.3.0`, `1.2.0`, `1.1.2`, `1.0.1`, `1.0.0`, `0.9.0`, `0.5.0` or `0.3.0` runtime is an
   upgrade input, not this candidate's runtime.
3. **CLI.** The candidate launcher reports the candidate version, and `doctor --json` returns
   `ok=true` with the expected bounded contract:

   ```powershell
   & '<DataRoot>\runtime\1.3.5\Scripts\stm32-toolkit.exe' version
   & '<DataRoot>\runtime\1.3.5\Scripts\stm32-toolkit.exe' --project-root '<ProjectRoot>' doctor --json
   ```

   Read the complete unfiltered JSON before checking `ok`; keep all `details.*` on failure.
4. **MCP.** Through the actual MCP client, call `stm32_doctor` and compare
   `data.runtime.toolkitVersion` (expected `1.3.5`) and `data.publicInventory` against the real
   tool list and input schemas the client exposes. Keep `stm32_project_context`
   `data.project.root` authoritative. A launcher/CLI version or inventory count alone does not
   prove the bound MCP server; after an upgrade restart the host once, then verify again.

## Inventory

The candidate carries the integrated **52-tool** MCP inventory and **9** bundled Skills (8 workflow
Skills plus the standalone `normalize-source-comments` copy helper), the same counts as published
v1.3.4. The authoritative names live in
`tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py`; do not infer the bound server from that
file or from this page.

## Offline Check before any separately authorized Bootstrap/Repair

Always start with the read-only, offline `Check`. It never creates files, installs anything, probes
hardware, or kills unrelated processes. It is not an installation and grants no hardware authority.

```powershell
& pwsh -NoProfile -File '<ToolkitRoot>\bin\setup-stm32-env.ps1' -Mode Check `
  -ToolkitRoot '<ToolkitRoot>' -DataRoot '<DataRoot>' -ProjectRoot '<ProjectRoot>'
```

Pass three explicit absolute paths (extracted `ToolkitRoot`, long-lived `DataRoot`, existing
`ProjectRoot`). Do not add `-ExecutionPolicy` overrides; a machine-policy denial is a boundary, not
a reason to switch shells or retry.

- If `Check` reports `missing`, review its evidence and obtain **explicit authorization for the
  absent-runtime install** before running the separate `Bootstrap` command.
- If `Check` reports `repairable` for an approved legacy upgrade (including 1.3.4) or `broken` for an
  existing runtime, review its source/downgrade guards and obtain **separate explicit
  authorization** before running the separate `Repair` command. Repair quarantines the old runtime
  before atomically promoting the candidate and publishing one `runtime/runtime-state.json`
  generation.
- Run at most **one** mutation for the decision, then repeat `Check`. Toolchain gaps do not
  invalidate a healthy runtime.

## pyOCD 0.46.0

The 1.3.5 candidate pins the isolated `pyocd` distribution to **`0.46.0`** (bounded
`>=0.46.0,<0.47`). The published 1.3.4 helper and runtime keep `pyocd==0.45.1`. Use the helper that
belongs to the bundle you actually extracted; never apply the candidate range retroactively to a
published 1.3.4 runtime. `pyocd` presence is distribution metadata, not importability, a working
Probe backend, or hardware evidence.

## Flash default and recovery

- Ordinary managed and imported flash default to **100000 Hz (100 kHz)**, including the shared
  worker/backend defaults. A faster value (up to 50000000 Hz) is an **optional explicit** choice;
  there is **no required 1 MHz gate**, and no 1 MHz physical-success claim.
- Frequency is selected configuration, not a measured clock.
- **No automatic recovery or retry.** A failure stops the route and returns its diagnostic; a
  `recoverySuggestion`, when present, is informational only and needs fresh explicit authorization.
  Under-reset recovery is a separately selected, explicitly authorized managed policy only; it is
  never inferred after a failure and is unavailable to the imported route.
- A normal confirmed flash includes one pre-program `SYSRESETREQ` reset-and-halt with a HALTED
  check; that reset belongs to the single authorized operation. A successful flash still reports
  `details.postFlash.targetState=unknown` and `runVerified=false`.

## Current limitations

- **Build and qualification state is recorded, not asserted here.** As of the 2026-10-30
  preparation checkpoint no v1.3.5 package build or qualification result was recorded, and no
  runtime from this candidate has been installed. Build, integration and qualification state is
  maintained in [release status](release-status.md) and the
  [STM32TK-135 implementation report](codex/returns/STM32TK-135/implementation-report.md).
- **Preparation edits are not acceptance.** Documentation and identity wording changed for this
  candidate on 2026-10-30; that is not integration, coverage reconciliation or package
  qualification, and none of those may be inferred from it.
- **No acceptance claim.** This candidate is not installed/final 1.3.5 acceptance, not a universal
  repair, and not application-run verification. A prior isolated one-shot 100 kHz managed flash run
  on candidate source is a scoped prior candidate-source/original-pair case only; see
  [release status](release-status.md) and
  [the normal-flash evidence](codex/returns/FLASH-FAILURE-EVIDENCE/normal-flash-2026-10-30.md).
  It does not prove firmware correctness or final acceptance.
- **No invented facts.** Do not state checksums, source commits, build dates, or future results for
  this candidate until an actual build/qualification/installation produces them.

## Identity scope: generated projects vs firmware evidence

Recognizing a project with `generatedBy.version=1.3.4` means that its declared producer is a
supported input. It does not prove original binary compatibility: recognizing the marker, metadata
or output layout is a statement about declaration support, not proof that the tool verified who
generated the project. It does **not** validate old 1.3.4 firmware, build or flash
evidence under the 1.3.5 runtime. Exact-version admission is preserved: where a step needs it, use
the existing explicitly authorized configure/rebuild/flash steps. Never rewrite receipts, and never
operate hardware automatically.

## Related

- [User guide](user-guide.md) — the published v1.3.4 installation and upgrade recipe.
- [Release status](release-status.md) — publication evidence, candidate checkpoints and retained
  limitations.
- [Changelog](../CHANGELOG.md) — version history and the v1.3.5 local-candidate section.
- [setup-stm32-env Skill](../skills/setup-stm32-env/SKILL.md) — the authoritative Check/Bootstrap/
  Repair contract.
