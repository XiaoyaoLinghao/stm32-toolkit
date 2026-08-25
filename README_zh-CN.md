# STM32 Toolkit 0.9

[English](README.md) | 简体中文

STM32 Toolkit 是本地、与 Agent 无关的 STM32 开发控制面。CLI 与 MCP 服务共享项目身份、
Keil→GCC 迁移、构建、探针工作流、Monitor、测试和证据诊断契约。Claude Code 只是该契约的
薄适配器。

## VS09-B 本地 candidate 与运行时边界

本仓库包含已验收的 **0.9.0 VS09-B candidate**，尚未打 tag、上传或 release。官方源码为
`https://github.com/XiaoyaoLinghao/stm32-toolkit.git`；candidate 构建绑定一个完整 40 位 Git
CodeHead 和封闭的 Windows CPython 3.12 wheelhouse。发布契约是 CPython `>=3.12,<3.13`；托管
解释器只能使用 `DATA_ROOT/runtime/0.9.0/Scripts/python.exe`。MCP 绝不回退到系统解释器。
setup helper 的 CHECK 模式只读；Bootstrap 和 Repair 必须得到明确授权，先校验解压后的离线
bundle，只安装 manifest 中的 wheel，运行 `pip check`，在本地 staging 后才可提升。

当前运行时是通用的：集成方可以选择任意绝对的 `TOOLKIT_ROOT`、`DATA_ROOT` 和
`PROJECT_ROOT`。启动器只读取 `STM32_TOOLKIT_DATA_ROOT`；所有项目命令都必须显式提供
`--project-root`。

```powershell
stm32-toolkit --project-root C:\work\blinky doctor --json
stm32-toolkit --project-root C:\work\blinky build --preset arm-debug --json
```

## 通用 MCP 模板

通用配置使用**绝对 launcher**、显式的 project/data 参数，并且 `env` 中只有
`STM32_TOOLKIT_DATA_ROOT`：

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit\\bin\\stm32-toolkit-mcp.cmd",
      "args": [
        "--project-root", "C:\\work\\blinky",
        "--data-root", "C:\\data\\stm32-toolkit"
      ],
      "env": {
        "STM32_TOOLKIT_DATA_ROOT": "C:\\data\\stm32-toolkit"
      }
    }
  }
}
```

Claude `.mcp.json` 只是同一契约的映射。它内联替换 `${CLAUDE_PLUGIN_ROOT}`、
`${CLAUDE_PROJECT_DIR}`、`${CLAUDE_PLUGIN_DATA}`，传递显式 project/data 参数，并且只把
`STM32_TOOLKIT_DATA_ROOT` 映射到 plugin data。它不添加第二个 server，也不回退到宿主 Python。

## CLI、setup 与隔离

先运行 `/stm32-toolkit:setup-stm32-env`。CHECK 返回 `missing`、`healthy` 或 `broken`，且不
修改项目。通用调用方式为：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

### 离线 candidate 构建与安装

在 pinned CodeHead 的干净 checkout 中，release owner 可以使用精确的 Windows CPython 3.12
wheelhouse 组装本地 candidate。utility 不从 index 解析、不上传、不 push，也不发布远程
release：

```powershell
py -3.12 tools/release/build_0900_artifacts.py build `
  --repo-root C:\src\stm32-toolkit `
  --code-head <40-位小写十六进制 commit> `
  --wheelhouse C:\tmp\p0902-wheelhouse `
  --output-root C:\tmp\p0902-candidate
```

先验证外置的 `CHECKSUMS.sha256`，再解压 `stm32-toolkit-0.9.0-windows-x86_64.zip`。generic
setup 使用解压后的 `ToolkitRoot`、明确的 `DataRoot` 与 `ProjectRoot`。CHECK 会报告 bundle 和
`runtime-state.json` 证据；Bootstrap/Repair 只用 `release/wheels/` 中 manifest 列出的 wheel，
并使用 `--no-index`、`--no-deps`。授权 Repair 会隔离 0.3.0/0.5.0 legacy runtime；记录过更高
版本时返回 `downgrade-refused`，同版本但 manifest/source 不同时返回 `source-conflict`，未来
state 永不被猜测或重写。Project 与 Monitor 数据仍由既有的显式事务负责。

candidate 只承诺 Windows x86_64，并包含确定性的 source/archive/SBOM/license/
compatibility/troubleshooting 材料；不包含硬件或远程 release 的 acceptance 声明。

`.stm32-project.json` 是版本控制的项目配置。机器状态保存在
`${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>`（或等价的通用 `DATA_ROOT`）下，因此不同
clone 拥有不同 workspace 和 session。Monitor 组仍由用户创建，Toolkit 不附带虚构预设；
Monitor Skill 只在调用启动器期间临时设置通用 data-root 环境，并恢复进程原值。

## Skill（恰好八个）

- `/stm32-toolkit:setup-stm32-env`
- `/stm32-toolkit:migrate-keil`
- `/stm32-toolkit:configure-stm32-project`
- `/stm32-toolkit:build-firmware`
- `/stm32-toolkit:flash-firmware`
- `/stm32-toolkit:debug-firmware`
- `/stm32-toolkit:read-var`
- `/stm32-toolkit:stm32-monitor`

每个 Skill 都只是对同一 CLI/MCP 行为的薄交接。硬件 Skill 先建立 project context，并展示
精确固件/探针身份；模拟、跳过、延期或失败的硬件证据绝不描述为真实物理成功。Keil→GCC
迁移是单向的，不会写回 Keil 工程。

## MCP inventory（全部 48 个名称）

公开 inventory 按职责分组：

### Project

`stm32_doctor`、`stm32_project_detect`、`stm32_project_context`、`stm32_project_create_plan`、
`stm32_project_create_prepare`、`stm32_project_create_apply`、`stm32_project_regenerate_plan`、
`stm32_project_regenerate_prepare`、`stm32_project_regenerate_apply`、`stm32_keil_inspect`、
`stm32_keil_convert`、`stm32_project_configure`

### Build

`stm32_build`

### Probe

`stm32_probe_list`、`stm32_flash`、`stm32_debug_handoff_begin`、`stm32_debug_handoff_end`、
`stm32_variable_read`、`stm32_variable_sample`、`stm32_register_read`、`stm32_fault_analyze`

### Diagnostic

`stm32_diagnostic_start`、`stm32_diagnostic_show`、`stm32_diagnostic_begin`、
`stm32_diagnostic_hypothesis_add`、`stm32_diagnostic_hypothesis_assess`、
`stm32_diagnostic_plan_add`、`stm32_diagnostic_plan_run`、`stm32_test_target_replay`、
`stm32_diagnostic_source_change_declare`、`stm32_diagnostic_verification_plan_add`、
`stm32_diagnostic_verification_start`、`stm32_diagnostic_marker_attach`、
`stm32_diagnostic_verification_complete`、`stm32_diagnostic_verification_show`

### Test

`stm32_test_host_discover`、`stm32_test_host_run`、`stm32_test_show`、
`stm32_test_target_prepare`、`stm32_test_target_execute`

### Acceptance

`stm32_acceptance_scenario_describe`、`stm32_acceptance_scenario_record`、
`stm32_acceptance_scenario_show`、`stm32_acceptance_attempt_begin`、
`stm32_acceptance_attempt_checkpoint`、`stm32_acceptance_attempt_authorize_source_change`、
`stm32_acceptance_attempt_show`、`stm32_acceptance_attempt_resume`

服务恰好注册上述 48 个名称，顺序和 schema 也是 Agent-neutral 契约的一部分。项目操作不能
通过参数偷偷替换 project root、环境、target、ELF、SVD、地址或服务凭据。

## Target 测试与实体资格

Target frame v1 保持 replay 兼容：旧项目的 v1 fixture、字节和回放语义继续保持不变。
Target frame v2 是 host-bound 的。项目在显式 project root 的 `testing.target.protocol` 中
选择 v2；host 会把完整的 project、固件、Probe、target、session、revision identity 与
case-inventory digest 绑定，并且只有在受保护的 flash、readback 和 transport identity 检查
完成后才发布实体结果。CLI 与 MCP 的 target prepare/execute 入口读取该项目配置，不接受调用
方注入的 identity、ELF、target 或 address。

VS10-A 的参考 transport 只有一个 `memory-mailbox` 路径。RTT、UART 和 semihosting 仍保留
软件 adapter 及 replay 兼容协议选项，但尚未在指定参考硬件上进行实体资格化。

## 产品工具边界

STM32CubeMX 负责生成新工程的 MCU、pin、clock、peripheral、startup、HAL/LL 和原生 CMake
字节。STM32CubeCLT 提供 ARM GCC、CMake、Ninja、ST 工具、target 事实与 SVD。PyOCD 是生产
探针后端，Cortex-Debug 是明确交接后的 VS Code 人工 UI。外部工具、扩展、驱动和
CMSIS-Pack 检查均有界且只读；缺少的工具仍由操作者处理。

## VS09-B 边界

VS09-B 负责 pinned-source 安装、安全升级/降级、恶意名称测试、checksums、archives、SBOM、
licenses、compatibility 和 troubleshooting。本地 candidate 可复现且可审计，但本仓库不执行
远程 release、PR、merge、tag、上传、签名或硬件操作。

历史 0.5 证据继续保存在有明确标记的 release-controller 与 replay fixture 中，只作为历史，
不作为当前 runtime 或 inventory。
