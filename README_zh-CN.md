# STM32 Toolkit

[English](README.md) | 简体中文

STM32 Toolkit 是面向 STM32 开发的本地工具。CLI 与 MCP 服务器共用同一后端和同一工程模型，因此终端、支持 MCP 的 AI 宿主和 VS Code 都能执行相同操作。

## 两条核心产品路线

1. **新建 STM32 工程** —— 创建工程、配置受管 ARM GCC/CMake 构建，再通过正常的授权路线编译和烧录。
2. **现有 Keil 工程** —— 先只读 inspect 与 preflight，审阅确定性交付计划，再用 `keil convert --destination <绝对新输出目录>` **应用到一个新的独立输出目录**。Keil 源工程绝不被改写，交付出的工程可独立构建；随后绑定其 `outputRoot`，走同一套 configure、build、flash 路线。

两条路线都不以 Git 为使用条件，Git 只是可选追溯信息。硬件操作需要明确选择设备并授权；本源码树不声称已完成硬件验收。

## 发布状态

当前源码版本：**v1.3.6**。[v1.3.6 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.6) 已于 2026-10-31 发布。当前下载请访问 [Latest 发布页](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/latest)。[v1.3.5](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5) 及更早版本作为历史版本保留。

**文档修订 — 2026-10-31：** 本中英文 README 修正 v1.3.6 原始压缩包中“v1.3.6 尚未发布”的过时说明。v1.3.6 标签仍指向 `b00cbc4edee191712dd6da7e1beb073ff4a74f28`；修订包使用独立的文档源码提交，由 `release-manifest.json` 记录，并配套更新 `CHECKSUMS.sha256`。运行源码、产品与依赖 wheel、固件行为及身份检查均未改变。其它随包文档仍是构建时快照；当前接收步骤与发布事实以 [v1.3.6 接收和安装指南](https://github.com/XiaoyaoLinghao/stm32-toolkit/blob/2606eb7b1fd3f105c3d5442f417d47fdb06acb8f/docs/user-guide.md) 及 Release 页面为准。随包的 [v1.3.5 接收指南](docs/v135-local-candidate.md) 是历史记录。

已安装 v1.3.6 的用户无需为这次文档修订重装或修复 runtime。用修订包修复原始 v1.3.6 安装，会由既有同版本身份检查按设计返回 `source-conflict`；请勿修改 runtime 状态或绕过检查。已有安装可直接在线阅读修正后的 README。

v1.3.6 保持 52 个 MCP 工具、9 个随附 Skill、`pyocd==0.46.0`、普通烧录默认 100 kHz，以及获授权的编程前 `SYSRESETREQ` 复位并停机。它未增加 v1.3.5 的 runtime、project/`generatedBy` 或构建身份兼容性。永久 Toolkit overall/risk 与 Monitor risk 覆盖率门槛仍未满足，原候选的独立授权例外保留。文档修订不声称新的硬件或接收者安装/IDE/MCP 验收。

## 环境要求

Windows x86_64、受管 runtime 所需的 CPython 3.12（`>=3.12,<3.13`），以及原生 PowerShell 7（`pwsh`）。runtime 不会回退到系统 Python。构建固件还需要 ARM GNU 工具链、CMake 与 Ninja；`doctor` 会报告它们的可用性，只读 Keil 检查不需要这些工具。

## 文档

- [用户指南](https://github.com/XiaoyaoLinghao/stm32-toolkit/blob/2606eb7b1fd3f105c3d5442f417d47fdb06acb8f/docs/user-guide.md) —— 安装与升级、Keil 迁移、工程配置、构建、探针、Monitor、MCP 服务器、VS Code 与排障。
- [v1.3.5 接收指南](docs/v135-local-candidate.md) —— 历史 v1.3.5 发布身份核对、先 Check 的接收与升级步骤，以及保留限制。
- Claude Code：先使用随附的 `/stm32-toolkit:setup-stm32-env` 技能，再执行其它工作流。
- [Windows 部署与 IDE 前置核对](docs/testing/windows-deployment-and-ide-preflight.md) —— runtime、调试器与扩展检查。
- [变更记录](CHANGELOG.md) —— 版本历史与保留限制。
