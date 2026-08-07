# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 0.3.0 将一个 Keil uVision 工程转变为可复现的 ARM GNU/GCC 构建：只读 Keil 检查、受保护的 ARMCC→GCC 转换计划、托管 GCC/CMake 与 VS Code 配置，以及带固件身份的受约束构建。它是面向未来 AI 辅助 STM32 编码、调试、测试与监控的基础。它将项目的共享意图保存在代码仓库中，同时为每个检出目录隔离由本机管理的运行时与会话状态。

## 直接从 GitHub 安装

本项目直接从 GitHub 分发，不提交到公开插件目录。将仓库注册为 Claude Code 插件源，然后在 user scope 安装一次插件：

```powershell
claude plugin marketplace add https://github.com/XiaoyaoLinghao/stm32-toolkit.git --scope user
claude plugin install stm32-toolkit@stm32-toolkit --scope user
```

在活跃的 Claude Code 会话中运行 `/reload-plugins`，或重启 Claude Code。第一条命令中的 `marketplace` 是 Claude Code 的固定命令名；本仓库仍然是安装源，不会出现在公开目录中。

发布新 Toolkit 版本后更新现有安装：

```powershell
claude plugin marketplace update stm32-toolkit
claude plugin update stm32-toolkit@stm32-toolkit --scope user
```

Toolkit 使用 `.claude-plugin/plugin.json` 中的版本作为 Claude Code 的更新键，因此每个发布版本都必须提升该版本。从 0.2.0 升级到 0.3.0 会把托管运行时路径从 `runtime/0.2.0` 更新为 `runtime/0.3.0`；CHECK 会把已有的 0.2.0 运行时报告为 `broken`，`recommendedMode` 为 `Repair`，Repair 会在提升 0.3.0 运行时之前将其隔离。

请勿手动复制 Skills，也不要重复注册 MCP 服务器。Claude Code 会自动发现插件的标准 `skills/` 目录和随插件提供的 `.mcp.json`。0.3.0 版本恰好公开四个 Skill：`/stm32-toolkit:setup-stm32-env`、`/stm32-toolkit:migrate-keil`、`/stm32-toolkit:configure-stm32-project` 和 `/stm32-toolkit:build-firmware`。尚未完成的 Skill 源文件保存在 `requirements/follow-on-skills/` 下，该目录不在 Claude 自动发现 Skill 的范围内。

安装后运行 `/stm32-toolkit:setup-stm32-env`。其中仅依赖 Skill 的 CHECK 在 MCP 启动前即可工作，并始终将托管运行时报告为 `missing`、`healthy` 或 `broken`。获得明确授权后，Bootstrap 或 Repair 会在唯一的插件数据暂存目录中构建运行时，验证 Toolkit 0.3.0 和 doctor，全部通过后才将其提升为正式运行时。Repair 会隔离失败的运行时以便恢复。宿主机 Python 3.10+ 仅作为有时间限制的引导前提，绝不会作为 MCP 的备用运行时。

## 自动项目绑定与隔离

启用插件后，随插件提供的 MCP 配置会自动启动托管运行时，并将服务器绑定到 `${CLAUDE_PROJECT_DIR}`。启动器始终使用 `${CLAUDE_PLUGIN_DATA}/runtime/0.3.0/Scripts/python.exe`，绝不会选择系统解释器。

两类数据保持严格分离：

- `.stm32-project.json` 是共享的、受版本控制的项目配置。其 `logicalProjectId` 标识逻辑固件项目。
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` 包含单个规范检出目录的隔离用户状态，包括会话、日志、诊断、缓存以及未来的监控状态。即使共享同一个逻辑项目 ID，不同的克隆也会获得不同的工作区 ID。

MCP 进程绑定到一个规范项目根目录，并恰好公开七个工具：`stm32_doctor`、`stm32_project_detect`、`stm32_project_context`、`stm32_keil_inspect`、`stm32_keil_convert`、`stm32_project_configure` 和 `stm32_build`。任何工具都不接受项目根目录、命令或环境参数。未配置的仅 Keil 或未知项目保持只读，在存在有效 `.stm32-project.json` 之前不会获得工作区。

## 工作流与授权

每个转换和配置工作流都是两阶段操作。只读计划返回确定性的 `plan_id`；变更操作要求调用方返回该确切 ID 并显式授权。核心随后根据当前磁盘状态独立重新规划，并在第一次写入前重新检查所有摘要、Git 和漂移保护。使用缺失、格式错误或过期的计划 ID 执行 apply 会无写入地失败关闭（`AUTHORIZATION_REQUIRED` / `PLAN_CHANGED`）。

- **检查**：`stm32-toolkit keil inspect --project <path> [--uvprojx <rel>] [--target-name <name>] [--no-baseline] --json` 返回只读的 `inspection` 和可选的 `baseline` 证据。
- **转换计划**：`stm32-toolkit keil convert --project <path> --dry-run --json` 显示阻塞项、精确变更路径、差异和计划 ID。
- **转换应用**：`stm32-toolkit keil convert --project <path> --apply --plan-id <sha256> --authorized --json` 只应用确切计划。
- **配置计划**：`stm32-toolkit project configure --project <path> --dry-run --json` 显示文件状态、差异、阻塞项和计划 ID。
- **配置应用**：`stm32-toolkit project configure --project <path> --apply --plan-id <sha256> --authorized --json` 安装托管文件。
- **构建**：`stm32-toolkit build --project <path> --preset {arm-debug,arm-release} [--clean] [--timeout-seconds 300] [--json]` 运行受约束的 CMake/Ninja 构建，并发布构建日志、构建结果和固件身份。CLI 调用本身就是用户的显式操作；MCP `stm32_build` 工具另外要求 `authorized=true`。

Claude Code 可通过 MCP 工具和三个工作流 Skill 使用相同操作。这些 Skill 始终以 `stm32_project_context` 开始，展示只读计划和证据，并在变更边界请求授权。Skill 绝不会从之前的只读调用推断同意。

为已配置项目生成的 VS Code 任务只调用受支持的 `stm32-toolkit build --preset ... --project ${workspaceFolder}` 契约；本版本不公开烧录和调试交接命令。

## 故障排查

第一条故障排查命令是 `stm32-toolkit doctor --json`。请通过托管运行时执行它，使诊断使用与 MCP 相同的环境：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

Doctor 在不探测硬件或不改动项目的情况下报告 ARM GCC/GDB、CMake、Ninja、PyOCD、CubeMX 和 VS Code 的离线证据。`/stm32-toolkit:setup-stm32-env` 还会报告现有 VS Code 扩展和 CMSIS-Pack 清单缺口。缺失的硬件工具、扩展、驱动或包会报告给用户解决；setup 不会安装它们。

如果 MCP 启动提示运行时缺失，请重新运行 `/stm32-toolkit:setup-stm32-env`。随插件提供的 `.mcp.json` 是权威配置，因此既不需要也不支持手动 `claude mcp add` 注册。失败的 setup 绝不会提升不完整的运行时；仅在 CHECK 报告 `broken` 时授权 `Repair`。

## 基础与后续能力

### 0.3.0 版本已交付

- 版本化 Python 包与稳定 JSON 结果信封（`stm32-toolkit/1`）；
- STM32 项目检测与受验证的 Schema v1/v2 `.stm32-project.json` 加载；
- 确定性的逐检出工作区 ID 与隔离的插件数据路径；
- 只读 Keil 检查与 AXF/MAP 基线证据；
- 带精确补丁、阻塞项和确定性计划 ID 的受保护 ARMCC→GCC 转换计划；
- 带漂移保护的托管 GCC/CMake、链接器与 VS Code 配置；
- 带 MAP 验证、ELF 身份和失败记录的受约束 CMake/Ninja 构建；
- 离线 doctor、项目上下文、CLI 包装器与七个项目绑定 MCP 工具；
- user scope 插件布局、一次性托管运行时引导指引与自动 MCP 绑定。

### 后续工作

工具包尚不宣称硬件烧录、探针租约、实时目标检查、断点调试、主机/目标测试执行或监控 UI。这些能力需要后续实现与硬件感知的安全契约。

Keil→GCC 迁移是单向的：迁移检查 Keil 输入并生成 GCC/CMake 配置，但绝不会写回或同步 Keil 工程。现有监控需求得到保留，但本版本不实现监控。契约要求用户创建监控组；工具包不随附或发明命名预设。
