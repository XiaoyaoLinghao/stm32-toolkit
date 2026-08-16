# STM32 Toolkit 分层架构与未来开发计划整合修订设计

**日期：** 2026-08-16

**状态：** 待用户审阅的计划修订提案

**性质：** 只调整尚未实施部分的实现来源和开发顺序，不缩减产品范围

**0.6 书面冻结基线：** `a31f997e0be87f6e14ad85b7cd033b4f4073b62f`

**本文档分支基线：** `513af0170df3a32705c59ff80ae7752f8accab33`

**当前活动开发：** STM32TK-0601 Task 7；活动工作树的未提交内容不属于本文档

**远程权限：** 无 push、PR、merge、close 或远程分支操作授权

## 1. 决策摘要

STM32 Toolkit 继续保持一个由 Claude Code 调用、主要工作于 VS Code、可离线运行、按项目隔离的完整产品。产品不改造成要求用户分别理解和操作多个独立平台的工具集合。

未来开发采用以下策略：

1. 已完成的 0.2–0.5 产品行为默认保留，不因发现相似开源项目而重写。
2. 正在实现的 STM32TK-0601 继续完成，因为统一测试、证据和身份合同是后续所有集成的验收基础。
3. 尚未实现的通用执行能力优先直接采用成熟组件，不先开发一套自有实现再替换。
4. STM32 Toolkit 自己掌握产品控制面：身份、授权、隔离、证据、诊断状态和统一 CLI/MCP 合同。
5. 外部组件只作为受约束的执行引擎或可选 provider，不能成为新的产品控制面。
6. 任一候选组件只有通过真实输出、Windows、离线、安全、许可证和回退门禁后才能进入产品。
7. 本文档在被用户审阅并形成新的书面冻结 CodeHead 前，不取代 `a31f997e0be87f6e14ad85b7cd033b4f4073b62f` 的现有冻结要求。

该策略的目标不是追求最多依赖，而是减少尚未发生的重复建设，同时保护已经验证的行为。

以下已确认约束保持不变：

- Linux 支持继续按当前决定冻结延期；
- 0.4 遗留实体机验证和 0.6 实体机验证继续在 0603 后统一执行；
- 每次实体机 reset、flash 或其他 MODIFY 仍需绑定精确 action digest 的单次用户授权；
- 当前不授权 push、PR、merge、close、远程分支删除或其他远程 Git 修改；
- 不使用 OpenClaw 或其他外部 AI 协调产品开发；
- 不以开源整合为理由缩减 0601、0602、0603 或最终 0600 的产品范围。

## 2. 背景与问题

现有路线按版本组织，但版本边界混合了不同性质的工作：

- 0.2 建立插件和项目隔离内核；
- 0.3 同时包含项目/构建基础和 Keil 迁移工作流；
- 0.4 同时包含探针仲裁基础和调试工具；
- 0.5 同时包含 Monitor 数据服务和用户界面；
- 0.6 又同时包含第二代证据基础、AI 诊断、Monitor 分析和发布治理；
- 0.7–1.0 同时包含新工程创建、产品加固和最终验收。

因此，单纯按版本判断“基础”或“上层”容易导致两类错误：

1. 把已有成熟执行引擎的能力当作 Toolkit 核心重新实现；
2. 为了复用开源项目而替换真正属于 Toolkit 的身份、安全和证据能力。

未来计划必须改用分层判断，再决定自研、复用或延期。

## 3. 产品分层

### 3.1 L0：外部执行引擎

L0 不构成 STM32 Toolkit 的产品差异化，原则上不自行重写：

- ARM GNU Toolchain；
- CMake、Ninja、CTest 和 JUnit；
- STM32CubeMX；
- CMSIS、CMSIS-Pack 和设备族包；
- PyOCD；
- pyelftools；
- pyserial；
- VS Code 与 Cortex-Debug；
- SQLite、aiohttp、Preact、ECharts、Vitest 和 Playwright；
- 未来通过验收的 Renode 或 labgrid provider。

Toolkit 对 L0 的责任是发现、固定版本、限制输入、验证输出、绑定身份并转换成统一证据，而不是复制其内部功能。

### 3.2 L1：Toolkit 产品内核

L1 是必须由本项目掌握的真正代码基础：

- Claude Code plugin、CLI、MCP 和薄 Skills 的统一入口；
- `OperationResult`、关闭的 JSON Schema、协议和版本协商；
- canonical project root、logical project、workspace、session 和 firmware identity；
- 项目数据隔离、路径约束和确定性进程执行；
- 只读、诊断、修改操作分级及精确授权；
- 探针租约、所有权、交接和冲突证据；
- Evidence identity、envelope、artifact、manifest、catalog、GC 和审计；
- Test run identity、统一结果模型和 Host/Target 共同协议；
- 外部执行引擎的关闭适配接口。

版本来源主要是 0.2、0.3/0.4 的基础部分和 STM32TK-0601。

### 3.3 L2：STM32 领域平台

L2 将 L0 能力转换为可被上层稳定消费的 STM32 服务：

- Keil、CubeMX、CMake 工程适配；
- build、MAP、ELF、DWARF、SVD 和 firmware identity；
- flash、read、sample、register、Fault 和 debug control；
- Host/Target test executor；
- mailbox、RTT、UART 和 semihosting transport；
- Monitor sampling、history、storage 和 loopback protocol。

L2 采用“Toolkit 定义接口和安全语义，成熟组件完成执行”的方式。

### 3.4 L3：用户产品与智能层

L3 是建立在 L1/L2 上的上层产品价值：

- Keil 一次性迁移工作流；
- Monitor UI；
- AI hypotheses、observation plan、evidence assessment 和 fix verification；
- 跨 run 对齐、差异、质量、halt impact、annotation 和 diagnostic marker；
- AI analysis bundle；
- CubeMX 驱动的新工程创建；
- 面向用户的完整编码、构建、测试、烧录、监控和诊断闭环。

STM32TK-0602、STM32TK-0603 和 0.7 新工程创建主要属于 L3。

### 3.5 L4：交付与质量保障

L4 证明产品可以发布，但不是新的运行时功能：

- managed runtime、离线包、安装和升级；
- performance calibration；
- Windows、Linux、浏览器和硬件矩阵；
- dependency/security audit；
- candidate、resume、reconcile、final 和 release report；
- 真实板卡纵向验收。

STM32TK-0600 和 0.7–1.0 计划中的验收、打包、安全与最终 gate 属于 L4。

## 4. 版本重新定性

| 版本或模块 | 分层性质 | 后续处理 |
|---|---|---|
| 0.1 | 概念原型 | 保留历史，不作为兼容基础 |
| 0.2 | L1 第一代产品内核 | 保留公共行为 |
| 0.3 | L1/L2 项目与构建基础；L3 Keil 迁移 | 已完成路径保持兼容 |
| 0.4 | L1/L2 探针与调试基础；部分 L3 调试工具 | 已完成路径保持兼容 |
| 0.5 | L2 Monitor 平台；L3 Monitor UI | 不替换，只增量扩展 |
| 0601 | L1/L2 证据与测试基础 | 按冻结合同完成 |
| 0602 | L3 诊断闭环 | 只自研诊断语义，复用 Probe v2 |
| 0603 | L3 Monitor 分析与 UI | 只新增分析能力，复用现有服务和 UI 栈 |
| 0600 | L4 发布治理 | 复用统一 gate，不继续扩张控制器范围 |
| 0.7 | L3 新工程创建 | 直接采用 CubeMX 原生 CMake 和设备事实 |
| 0.8–0.9 | L4 兼容、打包和纵向验收准备 | 不增加新的平行平台 |
| 1.0 | L4 真实纵向接受状态 | 证明闭环，不再扩产品范围 |

## 5. 已完成行为的保护边界

### 5.1 外部合同保持兼容

下列合同不得因引入 provider 而发生无意变化：

- 已发布 CLI 命令、MCP tools 和 Skill 语义；
- `OperationResult` 及错误代码的关闭性；
- 当前和前一 Project Schema 的读取与显式升级规则；
- workspace/session/firmware identity 计算及绑定；
- Keil→GCC 单向迁移和既有受管文件规则；
- build、flash、handoff、typed read、sampling、Fault 和 Monitor 行为；
- 探针只允许一个所有者，不抢占、不杀死无关进程；
- 修改、复位、烧录和其他高影响操作的精确授权；
- 已经持久化的 Monitor 和 Evidence 数据。

### 5.2 允许的最小变化

为了接入尚未实现的 provider，可以进行以下变化：

- 在既有公共函数内部增加一个窄适配器调用；
- 为新工程或新能力增加关闭枚举值；
- 增加 provider-specific evidence 字段，但不能改变既有字段含义；
- 把重复的底层执行移到 adapter 中；
- 增加真实工具输出 fixture 和合同测试。

任何修改既有文件的工作都必须证明旧项目默认仍走原路径，并运行完整旧回归。

### 5.3 明确禁止

- 不用新 provider 静默重新生成已迁移工程；
- 不把既有 `.stm32-project.json` 自动转换为另一项目系统；
- 不删除 0.3–0.5 实现来强迫所有项目使用新组件；
- 不让外部组件直接写 Toolkit Evidence 或本机状态；
- 不把外部组件的路径、日志或退出码直接当作可信结论；
- 不在失败时静默切换到另一执行引擎并声称同一次操作成功；
- 不增加通用 provider 市场、动态插件加载或远程服务发现机制。

## 6. 开源组件决策矩阵

| 组件 | 决策 | 使用边界 | 不采用的部分 |
|---|---|---|---|
| [pyOCD](https://github.com/pyocd/pyOCD) | 继续作为主要探针引擎 | flash、halt/resume/step、memory/register、breakpoint、RTT/SWO | 身份、租约、授权、Evidence 仍由 Toolkit 管理 |
| CMake/CTest/JUnit | 继续作为 Host 构建与测试事实源 | discovery、build、test、native report | 不把原始输出直接作为最终 Evidence |
| [STM32CubeMX CLI](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html) | 0.7 新工程的首选生成引擎 | MCU、pin、clock、peripheral、startup/HAL 和原生 CMake | 不接管已完成 Keil 迁移路径 |
| [CMSIS-Toolbox](https://github.com/Open-CMSIS-Pack/cmsis-toolbox) | 有界评估，优先用于 Pack/设备元数据 | cpackget、pack identity、SVD/device facts；必要时验证 cbridge | 不强制所有项目采用 csolution/cbuild 第二项目模型 |
| pyelftools | 继续使用 | ELF、DWARF 和结构验证 | 不由 Toolkit 重写 ELF/DWARF parser |
| pyserial | Target UART 首选执行库 | 关闭端口配置、bounded I/O | 不让自动端口选择绕过项目配置 |
| [Ceedling](https://github.com/ThrowTheSwitch/Ceedling) | 非默认、按真实 CMock 需求启用 | 特定工程的 Unity/CMock host test adapter | 不引入为所有用户必需的 Ruby/第二构建系统 |
| [pytest-embedded](https://github.com/espressif/pytest-embedded) | 借鉴并做 proof-of-fit，不直接接管核心 | DUT/serial fixture 和进程生命周期可作为参考或窄 adapter | 不接受 ESP-IDF 假设，不替代统一 Test/Evidence 模型 |
| [labgrid](https://github.com/labgrid-project/labgrid) | 未来可选 remote-lab provider | 多板资源、远程 exporter、power/reset/serial | 不成为 Windows 本地 1.0 的必需服务 |
| [Renode](https://github.com/renode/renode) | 未来可选 simulation provider | 受支持芯片的虚拟回归和 Robot test | 不把仿真标记为真实硬件 PASS |
| [OpenHTF](https://github.com/google/openhtf) | 不进入核心；未来只评估导出互操作 | 产线或试验站对接 | 不引入第二套 Test/Evidence 生命周期 |
| [Serial Studio](https://github.com/Serial-Studio/Serial-Studio) | 不替换 Monitor | 可作为人工参考 | 双许可证、独立产品边界和重复 UI 不适合作为核心依赖 |
| Zephyr Twister | 当前产品不采用 | 未来只有真实 Zephyr provider 需求时再评估 | 不把 CubeMX/CMake 项目迁移到 Zephyr 生态 |

以上许可证结论仅用于工程筛选；正式纳入依赖时必须保存精确版本的 LICENSE、NOTICE、SBOM 和离线来源证据。

## 7. Provider 与接口策略

### 7.1 只为真实需求建立接口

不建设通用插件平台。只保留或新增以下有限边界：

1. 既有 `ProbeBackend`：PyOCD 继续作为当前实现。
2. STM32TK-0601 `HostTestAdapter`：只负责 CTest discovery/build/run/native result 转换。
3. STM32TK-0601 `TargetTransport`：关闭枚举 mailbox、RTT、UART、semihosting。
4. 0.7 `ProjectCreationBackend`：首个实现是 CubeMX 原生 CMake；只服务新工程创建。
5. 未来 `HardwareLabProvider`：只有出现远程多板需求并通过 labgrid proof-of-fit 后才建立。
6. 未来 `SimulationProvider`：只有选定真实 MCU/board 且 Renode 模型通过验收后才建立。

### 7.2 Provider 输出不是产品真相

所有 provider 输出必须经过以下转换：

```text
untrusted native output
→ bounded parser
→ closed internal result
→ project/firmware/run identity binding
→ Evidence artifact and manifest
→ verifier
→ public OperationResult
```

provider 不能直接产生最终 PASS，也不能直接修改 catalog、diagnostic session 或 Monitor annotation。

### 7.3 旧路径和新路径

- 已迁移 Keil/GCC 工程继续使用现有配置与构建路径。
- 新 CubeMX 工程使用新的 creation backend。
- 两者在生成或读取统一 Project Model 后复用相同 build/test/probe/monitor/diagnostic 流程。
- provider 选择必须来自已验证项目事实或关闭配置，不能由环境猜测。
- 旧路径至少保留到 1.0 真实纵向验收完成；1.0 后的删除需要单独设计和用户决定。

## 8. 对冻结计划的具体修订方向

### 8.1 STM32TK-0601：保持范围和顺序

当前 Task 7 继续按冻结设计完成、提交和独立审查。本文档不得让正在运行的任务重启或丢弃未提交工作。

Task 8–9 的实现来源明确为：

- mailbox：通过 Probe v2 的 bounded memory 访问；
- RTT：通过 PyOCD RTT 能力；
- UART：通过固定版本 pyserial；
- semihosting：通过冻结的调试后端和 host-file deny policy；
- framing、state machine、identity、authorization 和 Evidence：由 Toolkit 实现。

Task 10–13 继续完成 CLI/MCP/Skill、performance、packaging 和候选接受。不得为了采用开源组件降低四种传输或证据范围。

### 8.2 STM32TK-0602：保留诊断，禁止重写调试器

保留全部产品目标：

- append-only diagnostic event chain；
- hypotheses 和 evidence assessment；
- closed observation plan；
- exact authorized debug control；
- source-change binding；
- fix verification；
- portable diagnostic bundle；
- CLI/MCP/Skill。

实施约束调整为：

- 所有 target read/control 必须调用 STM32TK-0601 冻结的 Probe v2；
- 不增加第二探针服务、第二 GDB server 管理器或自定义调试内核；
- 不复制 pyOCD 的 breakpoints、registers、memory 和 run-control 实现；
- 0602 自研代码集中于诊断状态、决策证据、授权边界和验证。

### 8.3 STM32TK-0603：保留 Monitor，只增加分析

保留全部 cross-run analytics、quality、annotation、bundle 和 UI 目标。

实施约束调整为：

- 复用既有 SQLite/history/service/WebSocket/Preact/ECharts；
- 不迁移到 Serial Studio 或第二 Monitor 服务；
- 不重写图表渲染、WebSocket 或浏览器测试框架；
- 新代码集中于数据兼容、alignment、statistics、decimation、quality、markers 和明确 AI bundle；
- 若引入数值算法库，必须先证明确定性、精确舍入、离线包和许可证；否则保持有界自研算法。

### 8.4 STM32TK-0600：收敛为共享接受层

- 0601、0602、0603 复用同一 gate controller、verifier、catalog 和 native-output adapters；
- 不为每个模块建立新 controller；
- 优先消费 pytest、CTest、Vitest、Playwright、npm 等工具的真实原生格式；
- 自定义格式只用于 Toolkit 自身关闭协议，不能伪造外部工具输出；
- 0600 只做最终矩阵、对账、报告和远程动作准备，不增加产品功能。

### 8.5 0.7：新工程创建改为 CubeMX-first

产品目标不变：从零创建 CMSIS + HAL/LL、可构建、可调试、可测试的 STM32 工程。

实现来源调整为：

1. Toolkit 收集和验证 creation request；
2. 生成只读 plan、输入摘要、预期输出边界和 action digest；
3. 授权后调用固定版本 STM32CubeMX CLI；
4. 要求 CubeMX 输出原生 CMake 工程；
5. 验证生成文件、MCU、linker、startup、HAL/LL、Pack 和 toolchain facts；
6. 只在 Toolkit-owned 文件中增加 Project Model、CMake presets 衔接、VS Code、Tests 和 AI 配置；
7. 生成后立即运行 configure/build/firmware identity gate；
8. 不维护手写的全系列 MCU、pin、clock、startup 或 linker 数据库。

CMSIS-Toolbox 的纳入分两步：

- 首先只验证 Pack 安装、设备 identity、SVD 和版本固定；
- 只有 `csolution/cbuild/cbridge` 能在不引入第二用户项目模型的前提下减少代码时，才扩大使用。

### 8.6 0.8–1.0：不再新增平行平台

- acceptance harness 复用 0600 公共 gate；
- packaging 继续采用一个 managed runtime；
- remote lab 是可选 provider，不是本地验收前置；
- simulation evidence 与 physical evidence 严格区分；
- 1.0 gate 只证明既定纵向闭环，不在 gate 阶段增加功能。

## 9. 候选组件准入门禁

每个候选组件必须有一份有界 proof-of-fit，至少覆盖：

### 9.1 功能与合同

- 精确满足所需操作，不用未声明的隐式默认；
- 真实 argv 被固定环境接受；
- native output 使用实际版本生成并脱敏保存；
- parser 关闭验证所依赖字段并与 exit code 交叉一致；
- Toolkit 对外 schema、error 和 identity 不降低。

### 9.2 安全与隔离

- 不越过 canonical project/workspace/evidence root；
- 不访问网络，除非当前操作明确允许且规格记录；
- 不接收任意命令、环境、路径或 credential；
- 不绕过 probe lease 和 MODIFY authorization；
- 超时、崩溃、部分输出和并发时 fail closed；
- 失败 evidence 保留且 create-new retry 规则一致。

### 9.3 平台与交付

- Windows 参考环境真实运行；
- CPython、PowerShell、Node、CMake 等版本被固定；
- 离线 wheelhouse/cache/package 可重复安装；
- 第三方 LICENSE、NOTICE、SBOM 和 advisory snapshot 完整；
- 外部更新不会静默改变结果格式。

### 9.4 性能与维护

- 达到冻结 workload 的时间、内存和大小限制；
- 没有引入需要用户维护的常驻服务；
- 适配层显著小于被替代的未实现代码；
- 上游失效时可以固定版本或以新 provider 替换；
- 不为了一个组件建立宽泛抽象。

未通过任一门禁时的默认决策是“不纳入”，而不是降低合同。

## 10. 开发任务级复用判定

从 STM32TK-0601 Task 8 开始，每个尚未实施任务在编码前回答以下问题并记录在任务报告中：

1. 本任务属于 L1、L2、L3 还是 L4？
2. 哪些行为是 Toolkit 独有的身份、安全或证据语义？
3. 哪些行为已有成熟执行引擎？
4. 当前计划是否要求重写该引擎已有能力？
5. 候选组件是否兼容 Windows、离线和单插件形态？
6. 候选许可证是否允许预期分发和使用方式？
7. 是否能以窄 adapter 接入而不改变公共合同？
8. proof-of-fit 的真实命令、fixture 和失败边界是什么？
9. 接入后减少了哪些尚未实现代码和长期维护责任？
10. 若不接入，具体技术原因是什么？

该判定只允许改变实现来源，不能自行缩减产品需求。

## 11. 执行顺序

### 阶段 A：不打断当前 Task 7

1. 保留活动工作树全部 tracked/untracked 状态；
2. 按现有冻结 brief 完成 Task 7；
3. 运行聚焦测试、changed-file coverage、双 Python 和独立审查；
4. 形成独立本地提交；
5. 不因本文档重新实现已经完成的 Host runner。

### 阶段 B：在 Task 8 前做一次限界计划对账

1. 从实际 Git HEAD 重新读取 0601/0602/0603/0600 规格和计划；
2. 将剩余任务映射到 L1–L4；
3. 确认 0601 Task 8–13 的现有设计已经把 PyOCD/pyserial/CTest 当作执行引擎；
4. 只修正文档中仍要求重复实现底层引擎的段落；
5. 不改变 0601 的 Evidence/Test/Transport/Probe v2 公共合同；
6. 形成 plan delta、依赖清单和真实 proof-of-fit 命令。

计划对账应逐一处理以下权威文档：

| 文档 | 修订方式 |
|---|---|
| `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md` | 增加 L0–L4 分层和未完成任务的复用判定规则 |
| `docs/superpowers/specs/2026-08-14-stm32tk-0600-evidence-diagnostics-program-design.md` | 仅增加跨模块实现来源原则；公共协议不变 |
| `docs/superpowers/plans/2026-08-14-stm32tk-0601-test-evidence.md` | 为 Task 8–9 明确 PyOCD、pyserial、CTest 等执行来源，不改验收范围 |
| `docs/superpowers/plans/2026-08-14-stm32tk-0602-diagnostic-loop.md` | 删除任何可能重复实现 Probe/debug engine 的解释，所有控制复用 Probe v2 |
| `docs/superpowers/plans/2026-08-14-stm32tk-0603-monitor-analytics.md` | 明确复用现有 Monitor/Preact/ECharts 栈，不引入第二 Monitor |
| `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.7-1.0-creation-acceptance.md` | 将 Task 1 改为 CubeMX 原生 CMake first，并增加 CMSIS proof-of-fit 和旧路径保护 |

如果计划修订不改变外部行为，就不重写相应冻结产品 spec；若 proof-of-fit 迫使公共 schema、命令或支持范围变化，必须先形成显式 spec delta 并由用户重新确认，不能藏在实现计划中。

### 阶段 C：完成 0601

按修订后的实现来源完成 Task 8–13。0601 接受后冻结兼容基线，作为 0602/0603 的输入。

### 阶段 D：重排 0602/0603 的实现责任

1. 0602 仅实现诊断领域逻辑；
2. 0603 仅实现 Monitor 分析领域逻辑；
3. 两者复用 0601 gate/evidence/probe/test；
4. 公共基础若再次不匹配，先扫描同类命令并一次修复；
5. 不引入新的协作平台、CI 或远程自动化。

### 阶段 E：在 0.7 编码前完成 CubeMX/CMSIS proof-of-fit

1. 选择一个已具名且受支持的 STM32 目标；
2. 离线调用固定 CubeMX CLI 生成 CMake；
3. 验证 configure/build/ELF/firmware identity；
4. 验证重新生成对用户区域和 Toolkit-owned 文件的影响；
5. 验证 Pack/SVD identity 和版本锁；
6. 根据结果冻结 `ProjectCreationBackend`，再写 0.7 实现计划。

### 阶段 F：1.0 纵向接受

1. 旧 Keil 迁移路径运行一次完整闭环；
2. 新 CubeMX 创建路径运行一次完整闭环；
3. 仿真、replay 和 fake 只作为软件证据；
4. 实体机 MODIFY 每次仍需精确单次用户授权；
5. 最终报告明确外部组件版本、许可证、输出和 Toolkit 验证边界。

## 12. 预计收益与限制

该策略不会显著减少已经完成或正在收尾的 0601 工作，也不会消除 0602/0603 的独特产品逻辑。

主要收益来自：

- 避免 0.7 自建全系列 MCU、startup、linker、pin、clock 和 CMake 生成知识；
- 避免将来重新开发 remote lab 和 simulation infrastructure；
- 限制 Probe/Test/Monitor 对底层库的重复封装；
- 减少长期跟踪芯片、工具格式和调试协议变化的责任。

以当前信息估算，全部剩余工作的直接开发量可能降低约 15%–30%，最大不确定性来自 CubeMX/CMSIS proof-of-fit 和实体机兼容性。这是规划估算，不是交付承诺。长期维护成本的下降预计高于首次开发量下降。

## 13. 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| 外部工具输出版本漂移 | 固定版本、保存真实 fixture、closed parser、双绑定 digest |
| 新 provider 改变旧项目 | 旧路径默认保持；新工程显式进入新 backend |
| 依赖增加导致离线包膨胀 | 只有减少明确代码量的依赖才纳入；记录 wheel/package budget |
| 许可证不适合分发 | 准入前 LICENSE/NOTICE/SBOM 审查；Serial Studio 不进入核心 |
| provider 失败时结果不确定 | 不静默 fallback；保留失败 evidence；返回明确错误 |
| 为未来 provider 过度抽象 | 只为已批准、已验证的第二实现建立接口 |
| 计划修订干扰 0601 | Task 7 先完成；0601 公共合同不变；修订只调整未实现任务来源 |
| 发布基础设施继续膨胀 | 0600 单一 controller/verifier；复用原生格式；禁止模块复制 |

## 14. 修订完成条件

在把本设计提升为新的权威开发基线前，必须满足：

1. 用户审阅并确认本文档；
2. 当前 Task 7 已独立提交和复审；
3. 0601/0602/0603/0600 的 plan delta 明确且无产品范围缩减；
4. 0.7–1.0 计划明确 CubeMX-first、CMSIS 有界使用和旧路径兼容；
5. 每个新增依赖有精确版本、许可证、离线来源和验证命令；
6. 冻结一个新的书面 CodeHead；
7. 实现继续保持本地，不执行未经授权的 push、PR、merge 或其他远程动作。

## 15. 主进程引导原则

主进程收到本设计后应：

- 先完成并保护当前 Task 7；
- 从实际 Git 和进程状态重新核实，不依赖聊天摘要；
- 把本文档作为计划修订输入，而不是已经生效的产品规格；
- 在 Task 8 前完成限界 plan delta；
- 继续 0601，不等待重复技术确认；
- 在 0602/0603/0.7 开发前冻结修订后的权威文档；
- 只在产品范围、硬件 MODIFY 或不可逆决定上请求用户确认；
- 不使用 OpenClaw 或其他外部 AI 协作；
- 不执行任何远程 Git 操作。
