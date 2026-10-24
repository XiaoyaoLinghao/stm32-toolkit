# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 工程的本地工具。CLI 与 stdio MCP 共用工程、构建、Probe Service、测试和 Monitor 合同；九个随插件提供的 Claude Code Skill 只是这些公开入口的适配层，产品核心不依赖特定 Agent 宿主。

**当前源码候选：v1.3.0（本地 Release 准备，尚未发布）。**公开下载仍是 **v1.2.0**：资产是否可用、最终资格与限制以 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) 页面为准。发行平台为 Windows x86_64、CPython `>=3.12,<3.13`。[发布状态](docs/release-status.md)保留有日期的历史断点，并单独记录 v1.3.0 候选。

## 下载、校验并安装已发布的 v1.2.0

安装 v1.2.0 时，先确认 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) 页面同时列出 `stm32-toolkit-1.2.0-windows-x86_64.zip` 与 `CHECKSUMS.sha256`，再从同一页面下载；任一资产缺失就停止，不借用旧版包或 GitHub 自动生成的源码归档。先核对 ZIP 哈希，再解压；缺少校验行或哈希不符即停止。发行包内含匹配的源码归档、发行清单与离线 wheels，不要混用其它版本文件。Bootstrap 前本机需要可用的 CPython 3.12。

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

使用全新的每版专用 BundleRoot；若该路径已存在，停止并另选新目录，不覆盖也不删除。ZIP 在 BundleRoot 下并列放置 `stm32-toolkit-1.2.0/` 和外层 `release/`。前者是 ToolkitRoot，其内部也有供 setup 使用的 `release/release-manifest.json`。DataRoot 要长期保留，并与 BundleRoot、工程、一次性测试目录分开。setup 的 `Check` 只读，核对发行包与 runtime 合同；审阅结果后，仅在缺少 runtime 时选择已授权的 `Bootstrap`，或在受控升级/修复时选择已授权的 `Repair`，然后再次运行 `Check`。v1.2.0 的 CLI/MCP 预期 `DataRoot/runtime/1.2.0`，不回退到系统 Python。已有 v1.1.2、v1.0.1 及更早获批 runtime 只能经获授权的 Repair 进入 v1.2.0，旧目录按既有事务规则隔离；恢复保证以[已记录的回滚范围](docs/release-status.md)为限。

```powershell
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
$ToolkitRoot = Join-Path $BundleRoot 'stm32-toolkit-1.2.0'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

若 `Check` 返回 `missing` 且已获安装授权，**仅执行 Bootstrap**：

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

若 `Check` 表明可进行已授权修复，**改为仅执行 Repair**：

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Repair `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

每次至多执行一个修改动作，再重复 `Check`。Claude Code 可用 `/stm32-toolkit:setup-stm32-env`，其底层仍是同一 setup 合同。其它 MCP 宿主使用 `bin/stm32-toolkit-mcp.cmd` 的绝对路径、显式工程/DataRoot 参数，环境变量 `STM32_TOOLKIT_DATA_ROOT` 指向该 DataRoot。[通用 MCP 配置示例和公开入口](docs/user-guide.md)见用户指南。`${CLAUDE_PROJECT_DIR}` 和 `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` 是 Claude 适配占位符，不是通用 CLI 的依赖。所有工程 CLI 命令都要显式给出绝对 `--project-root`。

### v1.3.0 本地候选

v1.3.0 本地候选不是 GitHub Release，也没有公开下载链接、tag、安装或资格结论；本地候选的构建与验证记录在交付证据中，完整资格验证与发布仍待完成。候选标识为 `1.3.0`，使用 `DataRoot/runtime/1.3.0`，并把已有的 v1.2.0 runtime 或生成工程视为旧版输入，只能经显式授权的 Repair 或 configure 事务推进。候选包含只读 Keil preflight、snapshot 构建、受控 CMSIS startup 生成、显式多 RAM 布局，以及已集成的外部固件路线：把原始 ELF/AXF、Intel HEX 或 BIN 导入不可变快照，离线准入，再对单个精确探针单独授权烧录。候选提供 52 个 MCP 工具和 9 个 Skill；已发布的 v1.2.0 runtime 仍是冻结的 48 工具、8 Skill 包。不要把任何 v1.3.0 资产描述为 GitHub 公开下载，也不要沿用 v1.2.0 的资格例外。

#### 本地 v1.3.0 发行包

当本地构建的 v1.3.0 ZIP 与 `CHECKSUMS.sha256` 已交付（例如来自交付证据）时，使用下面的参数化流程。它不是公开下载，不能指向未经核验的资产。`Check`、获授权的 `Bootstrap` 或获授权的 `Repair` 顺序与上文相同。

```powershell
$Version = '1.3.0'
$Download = 'C:\Users\you\Downloads'
$Bundle = Join-Path $Download "stm32-toolkit-$Version-windows-x86_64.zip"
$Checksums = Join-Path $Download 'CHECKSUMS.sha256'
$Pattern = '^[0-9a-f]{64}  stm32-toolkit-' + [regex]::Escape($Version) + '-windows-x86_64\.zip$'
$ExpectedLine = @(Get-Content -LiteralPath $Checksums | Where-Object { $_ -match $Pattern })
if ($ExpectedLine.Count -ne 1) { throw "Missing or duplicate $Version bundle checksum" }
$Expected = ($ExpectedLine[0] -split '  ', 2)[0]
$Actual = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw 'Bundle SHA256 mismatch' }
$BundleRoot = 'C:\tools\stm32-toolkit-1.3.0-bundle'
if (Test-Path -LiteralPath $BundleRoot) { throw 'BundleRoot exists; choose a new path' }
Expand-Archive -LiteralPath $Bundle -DestinationPath $BundleRoot
$ToolkitRoot = Join-Path $BundleRoot "stm32-toolkit-$Version"
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

该 `Check` 对 `runtime/1.3.0` 返回 healthy（或已单独授权完成 `Bootstrap`/`Repair` 并再次 `Check` 为 healthy）后，使用与本版本匹配的候选启动器。v1.3.0 专属行为只走这条路线；下文的已发布 v1.2.0 `$Cli` 不是回退路径。

```powershell
$CandidateCli = Join-Path $DataRoot "runtime\$Version\Scripts\stm32-toolkit.exe"
& $CandidateCli version
& $CandidateCli --project-root $ProjectRoot doctor --json
```

确认启动器报出的版本为 `1.3.0` 且 `doctor` healthy 后，再使用 `keil preflight`、`--startup-strategy`、`--memory-layout` 或外部固件命令。版本或健康检查不符就停止并先解决 setup，不要改换启动器。

## 工程操作入口

以下示例使用已发布的 v1.2.0 控制台启动器，属于公开 runtime 示例。本地 v1.3.0 候选必须使用上面对应配方中的 `$CandidateCli`（`runtime\1.3.0`），不得沿用旧的 `$Cli`。检测、检查及首次 configure plan 均只读；应用前审阅计划和 blocker。`.stm32-project.json` 是版本控制的工程意图，`.stm32-toolkit/` 中的 managed manifest 另行记录生成文件所有权。

**已发布 v1.2.0 runtime 示例：**

```powershell
$Cli = Join-Path $DataRoot 'runtime\1.2.0\Scripts\stm32-toolkit.exe'
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot project detect --json
& $Cli --project-root $ProjectRoot keil inspect --uvprojx Project\blinky.uvprojx --json
& $Cli --project-root $ProjectRoot project configure --dry-run --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

Keil→GCC 是单向迁移，不改写 Keil 工程。v1.2.0 可在受保护工程根内发现子目录 Keil 工程；多个候选仍须显式选择。非 UTF-8 源码、ARMCC 汇编需要工程自行适配；未跟踪文件也可能使 Git clean 检查阻断转换。configure 保留未托管的普通 `.vscode` 目标文件，已有托管文件改动保护不变；CubeMX regeneration 另有 inventory 规则。烧录/回读成功不证明程序正在运行。探针访问、handoff、读数与物理测试依照各自身份和授权合同执行。

Monitor 是观测 UI：组由用户创建，不自动连接探针。`Check` 确认 healthy 后，在前台终端运行已核验的 v1.2.0 启动器：

```powershell
$env:STM32_TOOLKIT_DATA_ROOT = $DataRoot
& (Join-Path $ToolkitRoot 'bin\stm32-monitor.cmd') open --project $ProjectRoot --data-root $DataRoot --port 8765
```

进入本次认证浏览器标签。允许的本地 Host 是 `127.0.0.1`；不要手输 `localhost` 或复制、记录 token 片段。用前台终端的 Ctrl-C 正常停服。[用户指南](docs/user-guide.md)含配置约束、22 项问题的处理和会话恢复。

## 当前文档

- [用户指南与排障](docs/user-guide.md)：迁移、配置、构建、Probe Service、Monitor 和升级。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md)：最终 runtime 与调试器检查。
- [架构](docs/architecture.md)、[开发](docs/development.md)、[标准测试流程](docs/testing/standard-test-procedure.md)及[发布资格](docs/testing/release-qualification.md)。
- [变更记录](CHANGELOG.md)及[v1.2.0 源码交付规范](docs/superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)。[v1.0.1 执行记录](docs/codex/returns/STM32TK-101/execution.md)保留其历史资格事实。

当前源码 inventory 有 52 个公开 MCP 名称，包含 `stm32_keil_preflight`、`stm32_firmware_import`、`stm32_firmware_admit` 与 `stm32_flash_imported`，覆盖工程、构建、探针、外部固件、诊断、测试、验收；另有九个随插件提供的 Skill（八个工作流 Skill 加 `normalize-source-comments`）。已发布的 v1.2.0 runtime 仍是冻结的 48 工具、8 Skill 包，不包含这些源码新增入口。请先核对启动器版本，再对实际绑定服务器执行 `doctor --json`，读取 `data.publicInventory` 与真实工具 input schema；不要依据本页或源码清单推断可用工具。外部固件路线只导入原始 ELF/AXF、Intel HEX 或 BIN 快照并离线准入，再单独授权烧录；它不需要托管 manifest、Git、构建 receipt 或 SVD。计划中的 `data.source.sha256` 与 `data.image.sha256` 是两个独立字段；准入与烧录结果中的 `sourceSha256`/`imageSha256` 是扁平字段。导入 receipt 不会解锁 debug、Monitor、Target 测试或伪造的 build identity。`VS09-B` 的当前发行构建仍使用 `tools/release/build_0900_artifacts.py` 和固定的 `release_0900_policy.json`；历史文件名与冻结策略是现行打包输入，不代表该源码候选已发布。退出当前树的旧计划与报告仍可用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>` 查阅。
