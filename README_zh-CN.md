# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 工程的本地工具。CLI 与 stdio MCP 共用工程、构建、Probe Service、测试和 Monitor 合同；八个 Claude Code Skill 只是这些公开入口的适配层，产品核心不依赖特定 Agent 宿主。

**版本状态：**[v1.0.0 已发布](docs/release-status.md)；当前源码候选标识为 **v1.0.1**，已包含获批补丁行为，尚待独立集成审查与发布资格验证，未发布、未安装。已安装使用请选已核验发行包及其匹配的 DataRoot。发行支持范围为 Windows x86_64、CPython `>=3.12,<3.13`。历史资格限制见[发布状态](docs/release-status.md)。

## 从已核验 runtime 开始

将已核验发行包解压到稳定的 ToolkitRoot。DataRoot 要长期保留，并与工程、一次性测试目录分开。setup 的 `Check` 只读；审阅结果后，仅在缺少 runtime 时选择已授权的 `Bootstrap`，或在受控升级/修复时选择已授权的 `Repair`，然后再次运行 `Check`。本候选的 CLI/MCP 使用 `DATA_ROOT/runtime/1.0.1`；已发布 v1.0.0 包使用 `runtime/1.0.0`，均不回退到系统 Python。已有 v1.0.0 runtime 只能经获授权的 Repair 进入新候选，旧目录隔离并保留失败回滚。

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit-1.0.1'
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

## 工程操作入口

在已核验 runtime 的 `Scripts` 目录可用的 shell 中执行。检测、检查及首次 configure plan 均只读；应用前审阅计划和 blocker。`.stm32-project.json` 是版本控制的工程意图，`.stm32-toolkit/` 中的 managed manifest 另行记录生成文件所有权。

```powershell
stm32-toolkit --project-root C:\work\blinky doctor --json
stm32-toolkit --project-root C:\work\blinky project detect --json
stm32-toolkit --project-root C:\work\blinky keil inspect --uvprojx Project\blinky.uvprojx --json
stm32-toolkit --project-root C:\work\blinky project configure --dry-run --json
stm32-toolkit --project-root C:\work\blinky build --preset arm-debug --json
```

Keil→GCC 是单向迁移，不改写 Keil 工程。当前候选可在受保护工程根内发现子目录 Keil 工程；多个候选仍须显式选择。非 UTF-8 源码、ARMCC 汇编需要工程自行适配；未跟踪文件也可能使 Git clean 检查阻断转换。configure 保留未托管的普通 `.vscode` 目标文件，已有托管文件改动保护不变；CubeMX regeneration 另有 inventory 规则。烧录/回读成功不证明程序正在运行。探针访问、handoff、读数与物理测试依照各自身份和授权合同执行。

Monitor 是观测 UI：组由用户创建，不自动连接探针。应从已核验启动器进入本次认证浏览器标签。允许的本地 Host 是 `127.0.0.1`；不要手输 `localhost` 或复制、记录 token 片段。[用户指南](docs/user-guide.md)含配置约束、22 项问题的处理和 Monitor 入口命令。

## 当前文档

- [用户指南与排障](docs/user-guide.md)：迁移、配置、构建、Probe Service、Monitor 和升级。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md)：最终 runtime 与调试器检查。
- [架构](docs/architecture.md)、[开发](docs/development.md)、[标准测试流程](docs/testing/standard-test-procedure.md)及[发布资格](docs/testing/release-qualification.md)。
- [变更记录](CHANGELOG.md)及[v1.0.1 补丁规格](docs/superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)。候选实现仍须独立审查与发布资格验证。

MCP inventory 有全部 48 个公开名称，覆盖工程、构建、探针、诊断、测试、验收。`VS09-B` 的当前发行构建仍使用 `tools/release/build_0900_artifacts.py` 和固定的 `release_0900_policy.json`；历史文件名不表示当前另有 0.9 runtime。退出当前树的旧计划与报告仍可用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>` 查阅。
