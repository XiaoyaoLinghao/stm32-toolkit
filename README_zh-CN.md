# STM32 Toolkit

简体中文 | [English](README.md)

STM32 Toolkit 0.2.0 是面向未来 AI 辅助 STM32 编码、调试、测试与监控的只读项目检测和环境诊断基础。它将项目的共享意图保存在代码仓库中，同时为每个检出目录隔离由本机管理的运行时与会话状态。

## 直接从 GitHub 安装

本项目仅通过 GitHub 源代码分发，不提交到任何公开插件目录。先将该 GitHub 仓库注册为 Claude Code 插件源，再以用户级作用域安装一次：

```powershell
claude plugin marketplace add https://github.com/XiaoyaoLinghao/stm32-toolkit.git --scope user
claude plugin install stm32-toolkit@stm32-toolkit --scope user
```

在已经打开的 Claude Code 会话中运行 `/reload-plugins`，或重启 Claude Code。第一条命令中的 `marketplace` 是 Claude Code 固定的命令名称；实际安装源仍是本 GitHub 仓库，项目不会进入公开插件目录。

发布新的 Toolkit 版本后，可按以下方式更新已有安装：

```powershell
claude plugin marketplace update stm32-toolkit
claude plugin update stm32-toolkit@stm32-toolkit --scope user
```

Toolkit 使用 `.claude-plugin/plugin.json` 中的版本号作为 Claude Code 的更新标识，因此每次正式发布都必须提升该版本号。

请勿手动复制 Skills，也不要重复注册 MCP 服务器。Claude Code 会自动发现插件的标准 `skills/` 目录和随插件提供的 `.mcp.json`。0.2.0 版本仅公开 `/stm32-toolkit:setup-stm32-env`；尚未完成的 Skill 源文件保存在 `requirements/follow-on-skills/` 下，该目录不在 Claude 自动发现 Skill 的范围内。

安装后运行 `/stm32-toolkit:setup-stm32-env`。其中仅依赖 Skill 的 CHECK 在 MCP 启动前即可工作，并始终将托管运行时报告为 `missing`、`healthy` 或 `broken`。获得明确授权后，Bootstrap 或 Repair 会在唯一的插件数据暂存目录中构建运行时，验证 Toolkit 0.2.0 和 doctor，全部通过后才将其提升为正式运行时。Repair 会隔离失败的运行时以便恢复。宿主机 Python 3.10+ 仅作为有时间限制的引导前提，绝不会作为 MCP 的备用运行时。

## 自动项目绑定与隔离

启用插件后，随插件提供的 MCP 配置会自动启动托管运行时，并将服务器绑定到 `${CLAUDE_PROJECT_DIR}`。启动器始终使用 `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe`，绝不会选择系统解释器。

两类数据会被有意分开：

- `.stm32-project.json` 是共享且纳入版本控制的项目配置，其中 `logicalProjectId` 用于标识逻辑固件项目。
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` 保存单个规范化检出目录的隔离用户状态，包括会话、日志、诊断、缓存以及未来的监控状态。即使不同克隆共享同一个逻辑项目 ID，它们也会获得不同的 workspace ID。

MCP 进程只绑定到一个规范化项目根目录。尚未配置、仅包含 Keil 工程或无法识别的项目保持只读；在有效的 `.stm32-project.json` 出现之前，不会为其创建工作区。

## 故障排查

首选故障排查命令是 `stm32-toolkit doctor --json`。请通过托管运行时执行它，以确保诊断使用与 MCP 相同的环境：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

Doctor 会离线报告 ARM GCC/GDB、CMake、Ninja、PyOCD、CubeMX 和 VS Code 的环境证据，不会探测硬件或修改项目。`/stm32-toolkit:setup-stm32-env` 还会报告现有 VS Code 扩展和 CMSIS-Pack 清单中缺失的项目。缺失的硬件工具、扩展、驱动或软件包会交由用户处理；setup 不会安装它们。

如果 MCP 启动时提示运行时缺失，请重新运行 `/stm32-toolkit:setup-stm32-env`。随插件提供的 `.mcp.json` 是唯一权威配置，因此既不需要也不支持手动执行 `claude mcp add` 注册。失败的 setup 绝不会提升不完整的运行时；只有当 CHECK 报告 `broken` 时才应授权执行 `Repair`。

## 基础能力与后续能力

### 0.2.0 版本已交付的基础能力

- 带版本的 Python 包和稳定的 JSON 结果封装；
- STM32 项目检测和经过校验的 `.stm32-project.json` 加载；
- 确定性的逐检出目录 workspace ID 和隔离的插件数据路径；
- 离线 doctor、项目上下文、CLI 封装以及绑定到项目的 MCP 工具；
- 用户级插件布局、一次性托管运行时引导说明和自动 MCP 绑定。

### 后续工作

当前基础版本尚不宣称支持硬件烧录、调试探针租约、目标设备实时检查、断点调试、主机端/目标端测试执行、项目生成或监控 UI。这些能力需要后续实现，并建立能够感知硬件状态的安全约束。

Keil 到 GCC 的迁移是单向的：未来的迁移能力可以检查 Keil 输入并生成 GCC/CMake 配置，但不得回写或同步 Keil 工程。现有监控需求会继续保留，但当前基础版本尚未实现监控。需求约定所有监控组均由用户创建；Toolkit 不会随附或自行创建命名预设。
