# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 开发的本地工具：检查现有 Keil 工程，迁移到 ARM GCC/CMake 构建，完成编译，通过真实探针烧录并调试目标，并在浏览器 Monitor 中观察变量。CLI 与 MCP 服务器共用同一后端和同一工程模型，因此终端、支持 MCP 的 AI 宿主和 VS Code 都能执行相同操作。

## 主要能力

- **检查并迁移 Keil 工程** —— 先只读检查，再执行受控的单向 Keil/ARMCC → GCC + CMake 转换；Keil 工程本身不会被改写。
- **构建固件** —— 配置一次工程，之后用 ARM GCC、CMake 与 Ninja 构建。
- **操作真实硬件** —— 列出探针，烧录受管构建产物或导入的 ELF/AXF/HEX/BIN 镜像，交接给 GDB，读取变量与寄存器，并分析 Fault。
- **观察运行中的目标** —— 本地 Monitor UI，监视组由用户创建，绝不自行连接探针。
- **同一后端，多处可用** —— CLI 与 MCP 服务器提供相同操作；VS Code 使用 MCP 服务器和可选的生成任务，随附的 Claude Code 技能只是同一入口的轻量适配层。

## 环境要求

Windows x86_64、受管 runtime 所需的 CPython 3.12（`>=3.12,<3.13`），以及原生 PowerShell 7（`pwsh`）。runtime 不会回退到系统 Python。构建固件还需要 ARM GNU 工具链、CMake 与 Ninja；`doctor` 会报告它们的可用性，只读 Keil 检查不需要这些工具。

## 安装当前版本

当前公开发布的最新版本为 **v1.3.2**（2026-10-26）。请从同一个 [v1.3.2 Release 页面](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2) 下载两个文件：

- [stm32-toolkit-1.3.2-windows-x86_64.zip](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.2/stm32-toolkit-1.3.2-windows-x86_64.zip)
- [CHECKSUMS.sha256](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.2/CHECKSUMS.sha256)

用 `CHECKSUMS.sha256` 中该 ZIP 对应的一行核对 ZIP 的 SHA-256，然后把 ZIP 解压到一个全新的空目录。其中包含 `stm32-toolkit-1.3.2/` 目录（即 ToolkitRoot）和同级的 `release/` 目录。

自行选择三个绝对路径——解压得到的 ToolkitRoot、位于其之外且长期保留的 DataRoot、以及工程根目录——然后运行只读的 `Check`：

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit\stm32-toolkit-1.3.2'
$DataRoot    = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

& pwsh -NoProfile -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

若 `Check` 报告受管 runtime 缺失且你希望安装它，执行一次 `Bootstrap`：

```powershell
& pwsh -NoProfile -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

随后重复 `Check`，仅在其对 `runtime/1.3.2` 报告 healthy 后再继续。升级或修复现有安装同样使用该脚本，具体路径见[用户指南](docs/user-guide.md)。若机器执行策略阻止该脚本，请与机器所有者解决，而不要添加 `-ExecutionPolicy` 覆盖。

## 使用 CLI

`Check` healthy 后，用绝对路径调用已安装的启动器。`doctor` 可用于诊断；构建示例假定工程已经完成 GCC/CMake 配置或迁移：

```powershell
$Cli = Join-Path $DataRoot 'runtime\1.3.2\Scripts\stm32-toolkit.exe'
& $Cli version
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

每条与工程相关的命令都要显式给出自己的绝对 `--project-root`。这些示例以绝对路径调用可执行文件，因此无需修改 `PATH`。

## 在 AI 宿主或 VS Code 中使用

MCP 宿主以绝对路径启动 `bin\stm32-toolkit-mcp.cmd`，并显式传入工程根与数据根，同时将 `STM32_TOOLKIT_DATA_ROOT` 指向同一个 DataRoot；Claude Code 使用随附技能与 `.mcp.json`。VS Code 使用同一个 MCP 服务器，并可添加工具生成的构建与调试任务。可复制配置与完整设置见[用户指南](docs/user-guide.md)。

## 文档

- [用户指南](docs/user-guide.md) —— 安装与升级细节、Keil 迁移、工程配置、构建、探针、Monitor、MCP 服务器、VS Code 与排障。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md) —— runtime、调试器与扩展检查。
- [变更记录](CHANGELOG.md) —— 版本历史；上文 v1.3.2 Release 页面记录该版本的说明与保留限制。
