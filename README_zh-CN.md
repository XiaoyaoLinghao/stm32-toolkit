# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是一个在 VS Code 中使用、由 Agent 驱动的本地 STM32 开发控制面。通用 CLI/MCP 核心负责协调一次性 Keil→GCC 迁移、可复现 CubeCLT 构建、身份绑定的 PyOCD 探针工作流、Cortex-Debug 交接、项目隔离的 Monitor、测试和证据诊断。Claude Code 是当前已发布的薄客户端适配器，不是另一套产品运行时。

下文的 0.5.0 包装仍是当前可安装基线。本地 0.6 产品代码已经完成软件场景，具名物理证据后置；它尚未推送、合并、打 tag 或发布。批准后的 0.7–1.0 方向将增加 CubeMX 新工程创建、单一可恢复纵向验收、Windows/Python 3.12 发布收敛，以及最终一次统一的真实项目硬件活动。

## 产品工具边界

- **STM32CubeMX 6.18：** 为新工程生成 MCU pin/clock/peripheral、startup、HAL/LL 和原生 CMake 工程字节。
- **STM32CubeCLT 1.22.0：** 提供 ARM GCC、CMake、Ninja、CubeProgrammer/ST 工具、target 事实和 SVD 数据。Toolkit 使用 GCC/CMake/Ninja；随附的 ST 烧录/调试工具不是平行产品后端。
- **PyOCD：** 是烧录、观察、Target transport 和调试交接的唯一生产 Probe 后端。
- **Cortex-Debug：** 在一次性 PyOCD 交接后提供 VS Code 人工调试界面。
- **STM32 Toolkit：** 拥有项目身份、授权、编排、Monitor/Test/Diagnostic 契约和 Agent-neutral CLI/MCP 行为。

ST 官方 STM32 VS Code 扩展不是必需依赖。推荐的编辑器扩展仍是 C/C++、CMake Tools 和 Cortex-Debug。

## VS07-A 只读创建计划

在受支持的 Windows 与 CPython `>=3.12,<3.13` 环境中，可用以下命令检查新工程请求：

```powershell
stm32-toolkit project create-plan --project-root . --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --json
```

命令返回确定性的计划、工具/计划摘要和目标目录摘要，或封闭且可操作的阻断项。CubeMX 6.18 负责生成工程；CubeCLT 1.22.0 提供 GCC/CMake/Ninja，不能替代 CubeMX。`CUBEMX_MISSING` 表示必须安装 CubeMX，或通过可信 support profile 暴露它后再规划。VS07-A 不运行 CubeMX、不创建 staging、不写入目标目录，也不应用计划。Agent-neutral MCP 等价操作是 `stm32_project_create_plan`。

## VS07-B 授权创建与构建

在确认计划未变化后签发一次性、会过期的 capability，再严格消费一次：

```powershell
stm32-toolkit project create-prepare --project-root . --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --plan-id PLAN_ID --action-digest ACTION_DIGEST --json
stm32-toolkit project create-apply --project-root . --authorization-digest AUTHORIZATION_DIGEST --authorized --json
```

Prepare 不改变目标目录。Apply 在同卷 sibling staging 中运行 CubeMX，校验原生 CMake/IOC 事实，复用 Toolkit configure 以及 Debug/Release 构建，并在两次构建成功后才激活。重放、漂移、缺少 Cube firmware repository、协议/构建失败或激活失败都会返回 typed error，目标不会留下半工程。MCP 等价工具是 `stm32_project_create_prepare` 与 `stm32_project_create_apply`。已验证的本地主机具备 CubeMX 6.18.1-RC2、CubeCLT 1.22.0 与 `STM32Cube_FW_F4_V1.28.3` 离线 package。本地候选已完成 MCU 与 captured-IOC 原生软件场景，包括 configure、Debug/Release 构建、激活和残留检查。未执行硬件、安装、远程或 release 操作；Sol 的独立 review 仍是验收门槛。

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

### 仓库开发状态

本地 0.6 候选已经增加不可变 Host/Target 测试证据、四种 Target transport、诊断与修复验证生命周期、Monitor 比较/marker/bundle，以及公共 CLI/MCP 适配器。软件场景已经本地接受；历史 0.4 硬件检查和 0.6 物理场景明确保留到统一 1.0 活动。这不是已发布 0.6 的声明。

批准后的 0.7–1.0 设计与进度基线为：

- 0.7：只读创建计划、授权 CubeMX 生成/构建和安全重新生成；
- 0.8：面向 Keil 与 CubeMX 输入的一套可恢复、隔离纵向场景适配器；
- 0.9：Python 3.12 Windows runtime、Agent 适配、安装、升级、安全和发布产物；
- 1.0：在具名实体硬件上完成一个真实 legacy-Keil 场景和一个 new-CubeMX 场景。

Monitor 组和 UI 状态继续由用户创建并保持项目隔离；Toolkit 不附带虚构预设。Keil→GCC 迁移保持单向，不会写回 Keil 工程。
