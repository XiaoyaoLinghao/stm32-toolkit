# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 0.5.0 将 Keil uVision 工程转换为可复现的 ARM GNU/GCC 构建，并提供与固件身份严格绑定的探针及调试工作流。功能包括只读 Keil 检查、受保护的 ARMCC→GCC 转换、托管 GCC/CMake 与 VS Code 配置、受约束构建、显式授权烧录、一次性调试器交接、DWARF/SVD 类型化读取、有限采样、Fault 分析，以及一个离线、项目隔离的 Monitor UI。它仍是后续 AI 辅助 STM32 编码、调试、测试与监控的基础。

## 从 GitHub 安装

本插件直接从 GitHub 分发，不进入公开目录。以 user scope 安装一次：

```powershell
claude plugin marketplace add https://github.com/XiaoyaoLinghao/stm32-toolkit.git --scope user
claude plugin install stm32-toolkit@stm32-toolkit --scope user
```

运行 `/reload-plugins` 或重启 Claude Code。更新命令：

```powershell
claude plugin marketplace update stm32-toolkit
claude plugin update stm32-toolkit@stm32-toolkit --scope user
```

Claude Code 会自动发现标准 `skills/` 目录和随插件提供的 `.mcp.json`。不要手工复制 Skill，也不要注册第二个 MCP。0.5.0 恰好提供八个 Skill：

- `/stm32-toolkit:setup-stm32-env`
- `/stm32-toolkit:migrate-keil`
- `/stm32-toolkit:configure-stm32-project`
- `/stm32-toolkit:build-firmware`
- `/stm32-toolkit:flash-firmware`
- `/stm32-toolkit:debug-firmware`
- `/stm32-toolkit:read-var`
- `/stm32-toolkit:stm32-monitor`

安装后运行 `/stm32-toolkit:setup-stm32-env`。CHECK 将托管运行时报告为 `missing`、`healthy` 或 `broken`。已有 0.3.0 runtime 会报告 `broken` 和 `recommendedMode: Repair`；得到明确授权后，Repair 先将旧 runtime 隔离，再原子提升 0.5.0。宿主 Python 3.10+ 只用于有界引导，绝不是 MCP 备用解释器。

## 自动项目绑定与隔离

随插件提供的 MCP 配置会自动把唯一服务绑定到 `${CLAUDE_PROJECT_DIR}`。启动器只使用 `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0/Scripts/python.exe`，绝不选择系统解释器。

- `.stm32-project.json` 是受版本控制的共享项目配置。
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` 保存单个规范检出目录的本机状态；不同 clone 拥有不同 workspace 和 session。

服务恰好公开 15 个项目绑定工具：`stm32_doctor`、`stm32_project_detect`、`stm32_project_context`、`stm32_keil_inspect`、`stm32_keil_convert`、`stm32_project_configure`、`stm32_build`、`stm32_probe_list`、`stm32_flash`、`stm32_debug_handoff_begin`、`stm32_debug_handoff_end`、`stm32_variable_read`、`stm32_variable_sample`、`stm32_register_read` 和 `stm32_fault_analyze`。硬件工具不接受项目根、数据根、命令、环境、服务凭据、目标覆盖、SVD 覆盖、ELF 路径或内存地址。

## Monitor UI

`/stm32-toolkit:stm32-monitor` 是打开项目隔离 Monitor UI 的显式人工路径。它先取得 project context，说明 UI 只读、零预设，只有用户明确要求打开本项目 UI 后才调用 human launcher：

```powershell
& '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
```

启动器在前台启动一个 loopback `127.0.0.1` Monitor 服务，并在默认浏览器中恰好打开一次带 fragment token 的 URL。它绝不打印、持久化、复制或记录该 access URL。页面以零监控组启动，绝不自动连接探针或自动开始采样；连接、组创建、导入/导出以及采样 start/pause/resume/stop 都是页面上的显式操作。`serve --json` 是机器命令，绝不打开浏览器。

## 工作流与授权

转换与配置仍采用两阶段协议：只读计划返回确定性 `plan_id`，修改必须带回该 ID 和明确授权。构建、烧录与调试交接严格绑定固件身份；目标与可选 SVD 只能来自 Schema-v2 项目模型。

- 探针枚举不打开目标会话，也不隐式选择第一只探针。
- 烧录需要精确探针、build ID、ELF SHA-256 和明确授权。
- handoff begin 需要明确授权并返回一次性秘密 ticket；end 负责重新获取、验证、消费并释放所有权。
- 变量、寄存器、有限采样与 Fault 分析均为只读且绑定固件身份。

每个硬件 Skill 都先调用 `stm32_project_context`，展示精确探针和固件身份，绝不从之前的只读调用推断授权。模拟、跳过、延期或失败的硬件证据绝不会被描述为真实物理成功。

## 故障排查

运行 setup Skill 使用的同一条有界 CHECK：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

首选包命令是 `stm32-toolkit doctor --json`。Doctor 会离线报告 ARM GCC/GDB、CMake、Ninja、PyOCD、CubeMX、VS Code 和 CMSIS-Pack 证据，不探测硬件，也不修改项目。缺失的外部工具、扩展、驱动或包由操作者处理。

## 已交付与后续范围

### 0.5.0 已交付

- Schema-v2 项目、逐检出目录隔离、Keil 检查、转换、生成、构建与固件身份；
- 跨进程探针租约、身份绑定烧录、一次性外部调试器交接、DWARF/SVD 类型化读取、有限采样与 Fault 分析；
- 严格 JSON CLI、恰好 15 个 MCP 工具、八个薄 Skill 和一个托管 0.5.0 runtime；
- 由同一 loopback 进程服务的离线 Monitor UI、显式人工 `stm32-monitor open`、已验证的 CSV/JSONL 历史导出，以及用户组 schema JSON 导入/导出。

### 后续工作

0.5 软件表面已完成，但真实探针/开发板结论只能由具名物理门禁产生。未实际运行的 Linux 或物理门禁继续标记延期，不得虚构通过。

监控组、历史、保留策略、存储、HTTP/WebSocket 服务和 UI 均由用户创建且项目隔离；本工具不附带或发明预设。Keil→GCC 迁移保持单向，不会写回 Keil 工程。

### 延后到 0.6.0

以下功能保持延后，0.5.0 不实现：AI 可读快照或诊断会话导出及 "AI Analyze"；多 run/group/firmware 历史叠加、diff、brush 或跨会话比较；完整质量时间线、分布、分阶段或 halt 影响面板；注释、书签和诊断标记；host/target 测试自动化。0.6 实现不会在 0.5.0 验收前开始。
