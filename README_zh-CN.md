# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 开发的本地工具。CLI 与 MCP 服务器共用同一后端和同一工程模型，因此终端、支持 MCP 的 AI 宿主和 VS Code 都能执行相同操作。

## 两条核心产品路线

1. **新建 STM32 工程** —— 创建工程、配置受管 ARM GCC/CMake 构建，再通过正常的授权路线编译和烧录。
2. **现有 Keil 工程** —— 先只读 inspect 与 preflight，审阅确定性交付计划，再用 `keil convert --destination <绝对新输出目录>` **应用到一个新的独立输出目录**。Keil 源工程绝不被改写，交付出的工程可独立构建；随后绑定其 `outputRoot`，走同一套 configure、build、flash 路线。

两条路线都不以 Git 为使用条件，Git 只是可选追溯信息。硬件操作需要明确选择设备并授权；本源码树不声称已完成硬件验收。

## 发布状态

当前最新已发布版本：**v1.3.5**，于 2026-10-30 发布为 [Latest](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5)，共 13 个可下载资产。上一已发布版本是 [v1.3.4](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4)，更早的版本仍可获取。发布身份核对、先 Check 的接收与升级步骤以及当前限制见 [v1.3.5 接收指南](docs/v135-local-candidate.md)；[用户指南](docs/user-guide.md) 已更新为当前 v1.3.5 的安装与升级配方与通用工作流，并保留 v1.3.4 作为上一公开版本的历史配方，发布证据与保留限制见[发布状态](docs/release-status.md)。

v1.3.5 保持 52 个 MCP 工具与 9 个随附 Skill，并将隔离的 pyOCD 发行版固定为 `0.46.0`。普通受管与导入烧录默认使用 `100000 Hz`（100 kHz），这是所选配置而非实测时钟；更高频率是可选显式设置，不再有 1 MHz 门槛。一次正常确认的烧录会执行一次获授权的 `SYSRESETREQ` 复位并停机，编程前要求 `HALTED`；失败即停止该路线，不自动重试或恢复，成功烧录仍报告 `targetState=unknown` 与 `runVerified=false`。已有的 v1.3.4 及更早 runtime 都是显式升级输入，不会仅因重启而升级。各分组非回归条件已通过，永久 Toolkit/Monitor 覆盖率门槛仍未满足。公开下载不等于安装：最终接收者安装/升级/回滚、VS Code/MCP 与交互验证仍归用户所有且尚待完成；本源码树不声称已完成硬件验收。

v1.3.4（上一已发布版本）接受结构平衡且允许相互独立嵌套条件编译的外层 include 保护，而真正的嵌套宏定义仍被拒绝；只读前置检查还会发现潜在的引号头文件编码阻塞，不做转码。这两项改动都不改变 ABI 判定、调试地址推断或转码行为。在仅针对本候选的用户批准例外下，永久覆盖率/风险门槛仍未满足；最终安装与 VS Code 验证仍归用户所有且尚待完成。更早的 [v1.3.3](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3) 发布仍可获取。

## 环境要求

Windows x86_64、受管 runtime 所需的 CPython 3.12（`>=3.12,<3.13`），以及原生 PowerShell 7（`pwsh`）。runtime 不会回退到系统 Python。构建固件还需要 ARM GNU 工具链、CMake 与 Ninja；`doctor` 会报告它们的可用性，只读 Keil 检查不需要这些工具。

## 文档

- [用户指南](docs/user-guide.md) —— 安装与升级、Keil 迁移、工程配置、构建、探针、Monitor、MCP 服务器、VS Code 与排障。
- [v1.3.5 接收指南](docs/v135-local-candidate.md) —— 发布身份核对、先 Check 的接收与升级步骤，以及当前限制。
- Claude Code：先使用随附的 `/stm32-toolkit:setup-stm32-env` 技能，再执行其它工作流。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md) —— runtime、调试器与扩展检查。
- [变更记录](CHANGELOG.md) —— 版本历史与保留限制。
