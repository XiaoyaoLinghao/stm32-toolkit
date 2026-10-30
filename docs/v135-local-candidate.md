# v1.3.5 receiving guide

**Status: published as Latest on 2026-10-30. Not installed on a recipient machine.**
The maintained build, publication, integration and qualification records are
[release status](release-status.md), the
[STM32TK-135 implementation report](codex/returns/STM32TK-135/implementation-report.md) and the
[publication evidence](codex/returns/STM32TK-135/publication-2026-10-30.md); read those for the
actual state. This page restates the release identity checks, the Check-first receiving order and
the retained limits. It makes no firmware-correctness, ABI/CCM, target-execution, or
hardware-acceptance claim.

## Published identity

[v1.3.5 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5) is public and
**Latest**, release `428722744`, published `2026-10-30T06:42:28Z` (14:42:28 Asia/Shanghai) with
`draft=false` and `prerelease=false`, from frozen source
`eac81a00a9c0cb0f78dcc0b423945605897b4806`. All 13 attached files were anonymously downloaded with
HTTP 200 and matched the two canonical builds. The Windows package is
`stm32-toolkit-1.3.5-windows-x86_64.zip`, 119000802 bytes, SHA-256
`19d317d4ddd5838d2902ca7bbc3b41b58fce63f357df16a2d829e1ee2a6d469d`; the source archive is
`stm32-toolkit-1.3.5-source.zip`.

Public download is **not** installation proof. Documents inside the frozen package keep the
build-time candidate wording they were built with; current guidance for the published release is
this page and [release status](release-status.md). Recipient installation, upgrade/rollback,
VS Code/MCP and interactive validation remain user-owned and **pending**.

## Identity checks (bundle, runtime, CLI, MCP)

Verify each layer separately; one layer never proves another.

1. **Bundle.** Confirm the extracted tree is the published 1.3.5 release itself: its setup helper
   belongs to that tree, its package manifest and `CHECKSUMS.sha256` belong to the v1.3.5 Release,
   and the Windows ZIP matches the size/SHA-256 above. Do not fall back to published v1.3.4
   asset names, values or checksums.
2. **Runtime.** After any separately authorized Bootstrap/Repair, the managed runtime lives at
   `${CLAUDE_PLUGIN_DATA}/runtime/1.3.5`, and the single published generation in
   `runtime/runtime-state.json` reports version `1.3.5`. An installed `1.3.4`, `1.3.3`, `1.3.2`,
   `1.3.1`, `1.3.0`, `1.2.0`, `1.1.2`, `1.0.1`, `1.0.0`, `0.9.0`, `0.5.0` or `0.3.0` runtime is an
   explicit upgrade input, not this release's runtime; its historical SDK, old flash default and
   preparation behavior is not promoted by restarting the host alone.
3. **CLI.** The launcher reports `1.3.5`, and `doctor --json` returns `ok=true` with the expected
   bounded contract:

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

v1.3.5 carries the integrated **52-tool** MCP inventory and **9** bundled Skills (8 workflow Skills
plus the standalone `normalize-source-comments` copy helper), the same counts as published v1.3.4.
The authoritative names live in
`tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py`; do not infer the bound server from that
file or from this page.

## Offline Check before any separately authorized Bootstrap/Repair

Always start with the read-only, offline `Check` from the release bundle you actually extracted. It
never creates files, installs anything, probes hardware, or kills unrelated processes. It is not an
installation and grants no hardware authority.

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
  before atomically promoting the new one and publishing one `runtime/runtime-state.json`
  generation.
- Run at most **one** mutation for the decision, then repeat `Check`. Toolchain gaps do not
  invalidate a healthy runtime.

## pyOCD 0.46.0

The published 1.3.5 release pins the isolated `pyocd` distribution to **`0.46.0`** (bounded
`>=0.46.0,<0.47`). The published v1.3.4 helper and runtime keep `pyocd==0.45.1` as their historical
component; use the helper that belongs to the bundle you actually extracted, and never apply the
1.3.5 range retroactively to a published 1.3.4 runtime. `pyocd` presence is distribution metadata,
not importability, a working Probe backend, or hardware evidence.

## Flash default and recovery

- Ordinary managed and imported flash default to **100000 Hz (100 kHz)**, including the shared
  worker/backend defaults. A faster value (up to 50000000 Hz) is an **optional explicit** choice;
  there is **no required 1 MHz gate**, and no 1 MHz physical-success claim.
- Frequency is selected configuration, not a measured clock.
- **No automatic recovery or retry.** A failure stops the route and returns its diagnostic; a
  `recoverySuggestion`, when present, is informational only and needs fresh explicit authorization.
  Under-reset recovery is a separately selected, explicitly authorized managed policy only; it is
  never inferred after a failure and is unavailable to the imported route.
- A normal confirmed flash includes one pre-program `SYSRESETREQ` reset-and-halt with a `HALTED`
  check; that reset belongs to the single authorized operation, and a failure there stops before any
  programmer, readback or success receipt. A successful flash still reports
  `details.postFlash.targetState=unknown` and `runVerified=false`.

## Current limitations

- **Publication is not qualification.** The per-group non-regression condition passed: Toolkit
  15530/18734 overall and 14399/17394 risk; Monitor 3292/3564 for both overall and risk; UI
  2938/3147 by exact-source reuse. The permanent Toolkit overall/risk 90% and Monitor risk 95% gates
  remain **unmet**. 3,204 distinct cases passed with 3 real-symlink capability skips, and prior
  failures, rechecks and source-bound reuse remain disclosed; this is not a final-head
  whole-repository rerun.
- **No installation or hardware claim.** Final recipient installation/upgrade/rollback, VS Code/MCP
  and interactive validation are **USER_VALIDATION_PENDING**, owned by the user. No installed
  runtime, IDE result or hardware acceptance is asserted, and this release is not a universal
  repair.
- **Prior physical run scope.** One narrowly scoped prior candidate-source run is recorded: a single
  100 kHz managed flash at source `e8e3c5f8d77490eaa0fae3e8ab8586237f30935c` / CodeHead
  `bfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d` returned `OK` (exit 0, 19656 ms, 61516 verified
  bytes, lease released). That is a prior candidate-source/isolated-SDK/original-pair case only: it
  is not installed/final 1.3.5 acceptance, not a universal repair, and not application-run
  verification, its target state stays `unknown` and `runVerified=false`, and it establishes no
  automatic retry or recovery. See
  [the normal-flash evidence](codex/returns/FLASH-FAILURE-EVIDENCE/normal-flash-2026-10-30.md).
- **Firmware ABI/CCM is out of scope.** Nothing here infers firmware correctness or reopens ABI/CCM
  diagnostics.

## Identity scope: generated projects vs firmware evidence

Recognizing a project with `generatedBy.version=1.3.4` means that its declared producer is a
supported input. It does not prove original binary compatibility: recognizing the marker, metadata
or output layout is a statement about declaration support, not proof that the tool verified who
generated the project. It does **not** validate old 1.3.4 firmware, build or flash evidence under
the 1.3.5 runtime. Exact-version admission is preserved: where a step needs it, use the existing
explicitly authorized configure/rebuild/flash steps. Never rewrite receipts, and never operate
hardware automatically.

## Related

- [v1.3.5 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5) — the
  published Latest assets.
- [User guide](user-guide.md) — the current v1.3.5 installation and upgrade recipe plus general
  workflows; the v1.3.4 release recipe stays as previous published guidance.
- [Release status](release-status.md) — publication evidence, checkpoints and retained limitations.
- [Changelog](../CHANGELOG.md) — version history and the v1.3.5 section.
- [setup-stm32-env Skill](../skills/setup-stm32-env/SKILL.md) — the authoritative Check/Bootstrap/
  Repair contract.
