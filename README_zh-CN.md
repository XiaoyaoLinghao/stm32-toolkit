# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 开发的本地工具。CLI 与 MCP 服务器共用同一后端和同一工程模型，因此终端、支持 MCP 的 AI 宿主和 VS Code 都能执行相同操作。

## 两条核心产品路线

1. **新建 STM32 工程** —— 创建工程、配置受管 ARM GCC/CMake 构建，再通过正常的授权路线编译和烧录。
2. **现有 Keil 工程** —— 先只读 inspect 与 preflight，审阅确定性交付计划，再用 `keil convert --destination <绝对新输出目录>` **应用到一个新的独立输出目录**。Keil 源工程绝不被改写，交付出的工程可独立构建；随后绑定其 `outputRoot`，走同一套 configure、build、flash 路线。

两条路线都不以 Git 为使用条件，Git 只是可选追溯信息。硬件操作需要明确选择设备并授权；本源码树不声称已完成硬件验收。

## 发布状态

当前源码：**v1.3.3 发布候选（尚未发布）**。公开发行版：[v1.3.2](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2)。安装、升级、迁移差异与验证限制见[用户指南](docs/user-guide.md)。

## 环境要求

Windows x86_64、受管 runtime 所需的 CPython 3.12（`>=3.12,<3.13`），以及原生 PowerShell 7（`pwsh`）。runtime 不会回退到系统 Python。构建固件还需要 ARM GNU 工具链、CMake 与 Ninja；`doctor` 会报告它们的可用性，只读 Keil 检查不需要这些工具。

## 文档

- [用户指南](docs/user-guide.md) —— 安装与升级、Keil 迁移、工程配置、构建、探针、Monitor、MCP 服务器、VS Code 与排障。
- Claude Code：先使用随附的 `/stm32-toolkit:setup-stm32-env` 技能，再执行其它工作流。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md) —— runtime、调试器与扩展检查。
- [变更记录](CHANGELOG.md) —— 版本历史与保留限制。
