# STM32 Toolkit

English | [简体中文](README_zh-CN.md)

STM32 Toolkit is a local, agent-neutral toolkit for STM32 projects. Its CLI and stdio MCP server share the same project, build, Probe Service, test, and Monitor contracts. The nine bundled Claude Code Skills are adapters to those public entry points; the core does not depend on an agent host.

**Current source candidate: v1.3.1 (local Release preparation, not published).** Use the version-matched v1.3.1 Windows ZIP with its `CHECKSUMS.sha256` only when both are actually available from a versioned Release listing them, or from a separately supplied local candidate whose checksum was verified. v1.2.0 remains the last observed dated public release (the frozen 48-tool, 8-Skill runtime), kept below as an explicit legacy route. [Release status](docs/release-status.md) records the current qualification status and release history. The distribution platform is Windows x86_64 with CPython `>=3.12,<3.13`.

## Download, verify, then set up the version-matched v1.3.1 package

The primary recipient path is a version-matched v1.3.1 installation, and it is conditional. Use v1.3.1 only when one of these two sources is actually available:

- a versioned v1.3.1 Release page that lists both `stm32-toolkit-1.3.1-windows-x86_64.zip` and `CHECKSUMS.sha256`. The intended conditional location is `https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1`; verify that the page and both assets actually exist before relying on it.
- a separately supplied local candidate (for example from the delivery evidence) that ships both files and whose ZIP matches its `CHECKSUMS.sha256` line.

If neither source is available, stop. Do not substitute the legacy v1.2.0 bundle, an earlier bundle, or GitHub's automatic source archive for a missing v1.3.1 asset, and do not mix files from different versions. Verify the ZIP before extraction; a missing or mismatched checksum is a stop. The bundle contains the matching source archive, release manifest and offline wheels. CPython 3.12 must be available to bootstrap the managed runtime.

```powershell
$Version = '1.3.1'
$Download = 'C:\Users\you\Downloads'
$Bundle = Join-Path $Download "stm32-toolkit-$Version-windows-x86_64.zip"
$Checksums = Join-Path $Download 'CHECKSUMS.sha256'
$Pattern = '^[0-9a-f]{64}  stm32-toolkit-' + [regex]::Escape($Version) + '-windows-x86_64\.zip$'
$ExpectedLine = @(Get-Content -LiteralPath $Checksums | Where-Object { $_ -match $Pattern })
if ($ExpectedLine.Count -ne 1) { throw "Missing or duplicate $Version bundle checksum" }
$Expected = ($ExpectedLine[0] -split '  ', 2)[0]
$Actual = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw 'Bundle SHA256 mismatch' }
$BundleRoot = 'C:\tools\stm32-toolkit-1.3.1-bundle'
if (Test-Path -LiteralPath $BundleRoot) { throw 'BundleRoot exists; choose a new path' }
Expand-Archive -LiteralPath $Bundle -DestinationPath $BundleRoot
```

Use a new, version-specific BundleRoot. If that path already exists, stop and choose another new directory; do not overwrite or delete it. The ZIP places `stm32-toolkit-1.3.1/` and an outer `release/` beside each other inside BundleRoot. ToolkitRoot is the former directory and has its own `release/release-manifest.json` for setup. Keep DataRoot durable and separate from BundleRoot, the project and disposable test directories. The setup script's `Check` is read-only and verifies the bundle/runtime contract. Inspect its result before explicitly choosing a missing-runtime `Bootstrap` or an authorized `Repair`; repeat `Check` afterward. The v1.3.1 CLI/MCP expects the managed interpreter in `DataRoot/runtime/1.3.1` and has no system-Python fallback. Existing v1.3.0, v1.2.0, v1.1.2, v1.0.1 and older approved runtimes can enter v1.3.1 only through authorized Repair, with the old runtime quarantined under the existing transaction recovery rules; see the [recorded rollback scope](docs/release-status.md).

```powershell
$BundleRoot = 'C:\tools\stm32-toolkit-1.3.1-bundle'
$ToolkitRoot = Join-Path $BundleRoot 'stm32-toolkit-1.3.1'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `missing` and installation is authorized, run **Bootstrap only**:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` instead reports an authorized repairable/broken state, run **Repair only**:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Repair `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

Run at most one mutation command, then repeat `Check`. For Claude Code, `/stm32-toolkit:setup-stm32-env` uses the same setup contract. For any MCP host, configure an **absolute launcher** at `bin/stm32-toolkit-mcp.cmd`, explicit project/data roots, and `"STM32_TOOLKIT_DATA_ROOT"` pointing to that DataRoot. A copyable [generic MCP configuration and public inventory](docs/user-guide.md) are in the user guide. `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` are Claude adapter placeholders, not required by the generic CLI. The CLI needs an explicit absolute `--project-root` for project-bound commands.

After that `Check` reports healthy for `runtime/1.3.1` (or a separately authorized `Bootstrap`/`Repair` has completed and a repeated `Check` is healthy), use the matching candidate launcher. This is the only route for v1.3.1-only behavior; the legacy v1.2.0 `$Cli` below is not a fallback.

```powershell
$CandidateCli = Join-Path $DataRoot "runtime\$Version\Scripts\stm32-toolkit.exe"
& $CandidateCli version
& $CandidateCli --project-root $ProjectRoot doctor --json
```

Confirm the launcher reports `1.3.1`; before relying on candidate-only behavior, verify the bound server's version, tool input schema and `data.project.root` as described in the [user guide](docs/user-guide.md). Read-only `keil inspect`/`preflight` do not require optional UV4/ARMCC tools, VS Code extensions or build tooling, so missing items like those do not by themselves block them. Judge each operation by its own response: `keil preflight` returns `data.analysis.blockers`, `data.planReadiness` and `data.applyReadiness`; a convert PLAN returns `data.plan_id`, `data.blockers` and `data.patches[]`. A diagnostic PLAN may carry blockers when Git/root prerequisites allow it; blockers prohibit APPLY, not read-only analysis. Stop when that operation's authorization, capability, identity or blocker guards fail. If the launcher version does not match, stop and resolve setup instead of switching launchers.

### Last observed public release: v1.2.0 (legacy route)

The [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) is the last observed dated public release; that page remains the authority for its asset availability, final qualification and limitations. It is an explicit legacy choice, not a fallback for an unavailable v1.3.1 package: v1.2.0 is the frozen 48-tool, 8-Skill runtime and does not contain the v1.3.1-only behavior described in this README.

For a v1.2.0 installation, confirm that the v1.2.0 Release lists both `stm32-toolkit-1.2.0-windows-x86_64.zip` and `CHECKSUMS.sha256`, then download them from that same page. If either asset is absent, stop; do not substitute another bundle or GitHub's automatic source archive. Verify the ZIP before extraction; a missing or mismatched checksum is a stop. The bundle contains the matching source archive, release manifest and offline wheels. Do not mix files from different versions. CPython 3.12 must be available to bootstrap the managed runtime.

```powershell
$Download = 'C:\Users\you\Downloads'
$Bundle = Join-Path $Download 'stm32-toolkit-1.2.0-windows-x86_64.zip'
$Checksums = Join-Path $Download 'CHECKSUMS.sha256'
$ExpectedLine = @(Get-Content -LiteralPath $Checksums | Where-Object {
  $_ -match '^[0-9a-f]{64}  stm32-toolkit-1\.2\.0-windows-x86_64\.zip$'
})
if ($ExpectedLine.Count -ne 1) { throw 'Missing or duplicate v1.2.0 bundle checksum' }
$Expected = ($ExpectedLine[0] -split '  ', 2)[0]
$Actual = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw 'Bundle SHA256 mismatch' }
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
if (Test-Path -LiteralPath $BundleRoot) { throw 'BundleRoot exists; choose a new path' }
Expand-Archive -LiteralPath $Bundle -DestinationPath $BundleRoot
```

Use a new, version-specific BundleRoot. If that path already exists, stop and choose another new directory; do not overwrite or delete it. The ZIP places `stm32-toolkit-1.2.0/` and an outer `release/` beside each other inside BundleRoot. ToolkitRoot is the former directory and has its own `release/release-manifest.json` for setup. Keep DataRoot durable and separate from BundleRoot, the project and disposable test directories. The setup script's `Check` is read-only and verifies the bundle/runtime contract. Inspect its result before explicitly choosing a missing-runtime `Bootstrap` or an authorized `Repair`; repeat `Check` afterward. The v1.2.0 CLI/MCP expects the managed interpreter in `DataRoot/runtime/1.2.0` and has no system-Python fallback. Existing v1.1.2, v1.0.1 and older approved runtimes can enter v1.2.0 only through authorized Repair, with the old runtime quarantined under the existing transaction recovery rules; see the [recorded rollback scope](docs/release-status.md).

```powershell
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
$ToolkitRoot = Join-Path $BundleRoot 'stm32-toolkit-1.2.0'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

Use the same authorized `Bootstrap`/`Repair` command forms shown above with this v1.2.0 `$ToolkitRoot`, `$DataRoot` and `$ProjectRoot`; run at most one mutation, then repeat `Check`.

### v1.3.1 candidate status and documented feature set

No installation qualification is recorded; a separate user session installed an earlier candidate, which this source slice does not verify or claim as qualified. Local candidate construction and validation are recorded in the delivery evidence; full qualification and publication remain pending. The candidate identifies as `1.3.1`, uses `DataRoot/runtime/1.3.1`, and treats an existing v1.3.0 or v1.2.0 runtime or generated project as a legacy input that requires an explicit authorized Repair or configure transaction; the same staged quarantine, final-path, source-conflict and downgrade guards apply. The v1.3.0 local candidate (source `1e6ea849`) was never a public release and remains historical delivery evidence. The v1.3.1 candidate keeps the 1.3.0 feature set — read-only Keil preflight, snapshot builds, bounded CMSIS startup generation, explicit multi-RAM layout, and the integrated external-firmware route (import an original ELF/AXF, Intel HEX or BIN into an immutable snapshot, admit it offline, then separately authorize flashing to one exact probe) — and adds the later diagnostic, extra-region and guidance behavior described below. It ships 52 MCP tools and 9 Skills; the published v1.2.0 runtime remains the frozen 48-tool, 8-Skill package. Do not describe any v1.3.1 asset as published unless the versioned Release page actually lists it, and do not reuse the v1.2.0 qualification exception.

#### AI invocation guidance (current source only)

Verify binding with existing evidence: repeat `stm32_doctor` and `stm32_project_context` through the actual MCP client, then compare `data.runtime.toolkitVersion` and `data.publicInventory` with the actual tool list/input schemas that client exposes, and keep `data.project.root` authoritative. A launcher/CLI process or inventory count does not prove what the MCP client registered. After an upgrade restart VS Code once and verify again; if expected tools or fields are missing or the root differs, preserve the full result and stop the dependent operation. Read and retain the complete `OperationResult` envelope, including `ok=false` `details` and `capabilityDetails`, before a concise summary; check `ok` before reading `data` and do not flatten it to legacy booleans.

Successful context adds `data.firmwareRoutes`. `managed` mirrors `capabilityDetails.flash` and uses `stm32_flash` with `buildId`/`elfSha256` plus Git-shaped provenance; only this managed route carries the provenance stop rule. `imported` is always `not-evaluated` in context: `stm32_firmware_import` -> `stm32_firmware_admit` -> `stm32_flash_imported`, with no Git or managed-model requirement, separate authorizations for the immutable copy and hardware, and no managed debug/Monitor/Target/recovery eligibility. Debug/Monitor/Target guidance never offers an imported receipt as a remedy. Tool presence is not image readiness; a managed blocker does not block the separately selected imported route, and no route switches automatically. A context model error preserves its own diagnostics and does not prove the imported endpoint absent, but invalid roots, binding errors, and errors from that endpoint still stop it. `stm32_keil_preflight` adds per-blocker `remediation` (`needs-user-input` or `unsupported`) plus `blockerSummary.byRemediation`; the optional `tool` key names only a real MCP tool, and the optional `skill` key separately names the `normalize-source-comments` Skill. `uvprojx`/`targetName` are the base selection parameters; the only supplementary options relevant to remediation are `memoryLayout` (and the separate startup options). There is no FPU, framework, or ABI override parameter. A comment-only encoding copy applies only when every affected file's charset is explicitly declared; other bytes remain unsupported. Framework/FPU/ABI/option guidance must inspect and retain actual toolchain/build semantics, not alter evidence or remove controls merely to clear a blocker. No blocker is auto-fixable.

This guidance describes the v1.3.1 source candidate. The frozen `1e6ea849` v1.3.0 local artifacts already contain `stm32_keil_preflight` with `analysis.blockers`, the additive blocker summary, `planReadiness`/`applyReadiness`, and the `startupStrategy`/`startupSource`/`memoryLayout` options. They do not contain the later additions named on this page: `firmwareRoutes`, per-blocker `remediation`/`blockerSummary.byRemediation`, and the `extraRegions` option and `analysis.extraRegions`. Those newer fields/options require this matching source or a later build, and their absence from the 1.3.0 package is expected, not proof that the MCP server is stale; do not infer the whole preflight tool or payload from a version string or inventory count. Restarting VS Code refreshes an installed server; it does not install this patch. The sample version/doctor/context PowerShell and MCP route examples are in the [user guide](docs/user-guide.md).

## Work with a project

After a healthy `Check`, the examples below use the version-matched v1.3.1 console launcher (`$CandidateCli` from the recipe above, `runtime\1.3.1`). If you deliberately installed the legacy v1.2.0 release, use its own `$Cli` example instead; never mix launchers. Detection, inspection, and the first configure call are read-only. Review the returned plan and blockers before any authorized apply. `.stm32-project.json` is the versioned project intent; managed generated-file ownership is tracked separately under `.stm32-toolkit/`.

**v1.3.1 candidate runtime example (requires the verified, installed package and a healthy `Check` for `runtime/1.3.1`):**

```powershell
$CandidateCli = Join-Path $DataRoot 'runtime\1.3.1\Scripts\stm32-toolkit.exe'
& $CandidateCli --project-root $ProjectRoot doctor --json
& $CandidateCli --project-root $ProjectRoot project detect --json
& $CandidateCli --project-root $ProjectRoot keil inspect --uvprojx Project/blinky.uvprojx --json
& $CandidateCli --project-root $ProjectRoot project configure --dry-run --json
& $CandidateCli --project-root $ProjectRoot build --preset arm-debug --json
```

**Legacy v1.2.0 public-runtime example (last observed dated public release):**

```powershell
$Cli = Join-Path $DataRoot 'runtime\1.2.0\Scripts\stm32-toolkit.exe'
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot project detect --json
& $Cli --project-root $ProjectRoot keil inspect --uvprojx Project\blinky.uvprojx --json
& $Cli --project-root $ProjectRoot project configure --dry-run --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

Keil-to-GCC migration is **one-way** and does not rewrite the Keil project. The last observed v1.2.0 release discovers nested Keil projects within the guarded root; multiple candidates require an explicit choice, and the version you installed must be checked for the same behavior. In the v1.3.1 candidate, the matching `keil preflight` reports its supported bounded remediation paths — CMSIS startup generation for regular ST/CMSIS ARMCC5 startup, the supported common-ARMCC construct handling, and comment-only copies only when every affected file's charset is explicitly declared. Unknown or unsupported constructs still block; charset is never guessed, and no implicit transcoding or generic ARMCC converter is provided. The legacy v1.2.0 runtime has no such preflight, so there, unsupported source encodings and ARMCC assembly remain project-owned adaptation. Git changes, including untracked files, can block conversion. Configure preserves existing unowned regular `.vscode` target files while retaining managed-file drift protection; CubeMX regeneration has a separate inventory rule. Flash programming/readback does not establish that firmware is running. Probe access, handoff, reads, and physical tests require their explicit identity and authorization contracts.

Monitor is an observation UI with user-created monitor groups and no automatic probe connection. After a healthy `Check`, open it from the installed version's verified `bin\stm32-monitor.cmd` in a foreground terminal — the v1.3.1 recipe's `$ToolkitRoot` by default, or the legacy v1.2.0 ToolkitRoot if you chose that release. A launcher uses only its own version's managed runtime; do not mix interpreters, `PYTHONPATH` overrides or wheels from another version.

```powershell
$env:STM32_TOOLKIT_DATA_ROOT = $DataRoot
& (Join-Path $ToolkitRoot 'bin\stm32-monitor.cmd') open --project $ProjectRoot --data-root $DataRoot --port 8765
```

Use the current authenticated browser tab. The allowed local Host is `127.0.0.1`, not a hand-entered `localhost` URL; never copy or log its token fragment. Stop the foreground service with Ctrl-C. See the [user guide](docs/user-guide.md) for configuration constraints, all 22 issue remedies, and session recovery.

## Current documentation

- [User guide and troubleshooting](docs/user-guide.md): migration, generation, builds, Probe Service, Monitor, and upgrade decisions.
- [Windows deployment and IDE preflight](docs/testing/windows-deployment-and-ide-preflight.md): final runtime and debugger checks.
- [Architecture](docs/architecture.md), [development](docs/development.md), [standard test procedure](docs/testing/standard-test-procedure.md), and [release qualification](docs/testing/release-qualification.md).
- [Changelog](CHANGELOG.md) and [v1.2.0 source-delivery specification](docs/superpowers/specs/2026-10-21-monitor-v120-delivery-design.md). The [v1.0.1 execution ledger](docs/codex/returns/STM32TK-101/execution.md) retains its historical qualification record.

The current source inventory has 52 public MCP names, including `stm32_keil_preflight`, `stm32_firmware_import`, `stm32_firmware_admit`, and `stm32_flash_imported`, organized by project, build, probe, external-firmware, diagnostic, test, and acceptance workflows, plus nine bundled Skills (the eight workflow Skills and `normalize-source-comments`). The published v1.2.0 runtime remains the frozen 48-tool, 8-Skill package and does not contain these source-only entries. Check the actually installed server with `doctor --json` and read `data.publicInventory` (and the real tool input schema) instead of inferring availability from this page; the launcher version and the server inventory must match. `VS09-B` release construction uses the existing `tools/release/build_0900_artifacts.py` and pinned `release_0900_policy.json`; these historical filenames and the policy pinned to the current candidate remain the packaging inputs, not evidence that the source candidate is published. Old plans and reports removed from the current tree remain retrievable with `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`.

The external-firmware route imports an original ELF/AXF, Intel HEX, or BIN file into an immutable project-bound snapshot, admits it offline, and only then offers a separately authorized flash to one exact probe. It needs no managed manifest, Git repository, build receipt, or SVD. `capabilities.flash` in project context describes only the managed build route; an unmanaged project can use the imported route when the bound server actually exposes these tools. The original source SHA-256 (`data.source.sha256` in a plan) and the normalized programming-image SHA-256 (`data.image.sha256` in a plan; flat `sourceSha256`/`imageSha256` in admission and flash results) are distinct fields, and an imported receipt never unlocks debug, Monitor, Target tests, or a fabricated build identity. See the [user guide](docs/user-guide.md).
