# STM32 Toolkit AI 开发闭环设计

- 状态：已完成设计讨论，等待书面审阅
- 日期：2026-07-29
- 目标产品：在 VS Code 工作区中使用的 Claude Code STM32 Toolkit 插件
- 当前仓库版本：初始原型 `stm32-toolkit v0.1.0`

## 1. 背景

团队拥有既有 Keil STM32 工程，需要将其一次性转换为基于 ARM GCC、CMake 和 VS Code 的工程。转换完成后只维护 GCC 版本，不要求继续双轨维护 Keil 工程。

迁移本身不是产品的最终价值。产品的核心价值是让 Claude Code 能在 STM32 工程中形成完整、可观察、可验证的开发闭环：

1. 理解工程和用户需求；
2. 编写或修改代码；
3. 构建并解释编译、链接结果；
4. 执行主机测试和板端测试；
5. 烧录真实目标板；
6. 监控运行时变量和外设寄存器；
7. 根据用户反馈自主建立假设、采集证据并诊断问题；
8. 修改、重新构建、烧录和复测。

该产品必须始终保持 Toolkit 形态：通过 Claude Code 插件安装和调用，主要工作环境是 VS Code，不发展成需要用户单独部署和维护的独立平台。

## 2. 目标

### 2.1 近期目标

- 对当前真实 Keil 工程完成一次可审计、可验证的 GCC 迁移。
- 建立统一项目模型，使旧工程迁移和未来新工程创建共用一套配置生成与工具链。
- 让 AI 能可靠执行编码、构建、测试、烧录、监控和有证据链的自主调试。
- 重构 `stm32-monitor`，修复当前缺陷，同时保留已经确认的产品需求。
- 让 Toolkit 以 user scope 安装一次后，在不同项目中自动可用并严格隔离数据。

### 2.2 后续目标

- 从零创建 CubeMX + CMSIS + HAL 工程，并允许性能敏感模块使用 LL。
- 遇到真实的新芯片、新工程结构或特殊编译器语法时，按需扩展兼容能力。

## 3. 非目标

- 当前不建设批量迁移平台。
- 当前不预先覆盖所有 STM32 系列、TrustZone、双核或外部存储场景。
- 不在 ARMCC 到 GCC 迁移期间同时执行 SPL 到 HAL 的驱动框架重写。
- 不维护 Keil 与 GCC 两套长期构建系统。
- 不提供项目内置或业务预置的 Monitor 监控组。
- 不依赖 Codex 专有能力、云端常驻服务、外部数据库或其他 IDE。
- 不允许 AI 无授权修改 Option Bytes、任意写内存或执行全片擦除。

## 4. 设计原则

### 4.1 薄 Skill，确定性工具核心

Skill 负责：

- 理解用户意图；
- 选择工作流；
- 形成和验证诊断假设；
- 解释结构化结果；
- 决定是否继续修改和验证。

CLI、MCP 和 Probe Service 负责：

- 解析工程；
- 转换源码；
- 生成配置；
- 构建、烧录和测试；
- 访问探针；
- 采样和解码数据；
- 执行确定性校验；
- 返回版本化的结构化结果。

核心操作不得只依赖 Markdown 指令临时生成。相同输入应产生可重复结果。

### 4.2 真实需求驱动泛化

当前只实现真实工程需要的目标芯片、ARMCC 差异、内存配置和驱动框架。统一接口保留扩展能力，但不提前维护虚构的芯片或工程规则库。

### 4.3 迁移风险与驱动重构风险分离

旧工程迁移时保留原框架：

- SPL 工程继续使用 SPL；
- HAL 工程继续使用 HAL；
- LL 工程继续使用 LL；
- 裸寄存器工程保持裸寄存器实现。

迁移只处理编译器、汇编、启动、链接、构建和调试差异。驱动框架升级是迁移完成后的独立任务。

### 4.4 AI 结论必须有证据链

AI 调试结论必须关联：

- 对应源码与构建版本；
- 使用的 ELF、DWARF 和 SVD；
- 读取的变量、寄存器和日志；
- 执行的断点、暂停或测试；
- 支持和反驳各假设的证据；
- 修复后的复测结果。

### 4.5 默认非侵入式，操作逐级授权

观察操作默认不暂停 CPU。断点、单步和暂停属于诊断模式；修改、烧录和复位属于修改模式。每次高影响操作都必须来自用户当前任务的明确授权。

## 5. 总体架构

```text
Claude Code Plugin
├── Skills：意图理解、策略、诊断和工作流编排
├── stm32-toolkit CLI：工程、构建、测试、烧录
├── STM32 Toolkit MCP：Claude 可调用的结构化工具
├── Probe Service：唯一硬件访问和会话仲裁层
├── stm32-monitor：人和 AI 共用的实时观察界面
├── Schemas：项目、结果、协议和诊断会话模型
└── Templates：CMake、VS Code、测试和新工程模板
```

数据流：

```text
Keil .uvprojx ── migrate ──┐
                           ├── .stm32-project.json
CubeMX/new project ─ create┘             │
                                         ▼
                             configure/build/test/flash
                                         │
                                         ▼
                          Probe Service ── STM32 Target
                          │       │
                          │       ├── AI Debug MCP
                          │       ├── stm32-monitor
                          │       ├── target tests
                          │       └── Cortex-Debug handoff
                          ▼
                    structured evidence
```

## 6. Claude Code 插件边界

### 6.1 插件结构

```text
stm32-toolkit/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── setup-stm32-env/
│   ├── migrate-keil/
│   ├── create-stm32-project/
│   ├── configure-stm32-project/
│   ├── build-firmware/
│   ├── test-firmware/
│   ├── debug-firmware/
│   └── stm32-monitor/
├── .mcp.json
├── bin/
├── tools/
├── schemas/
├── templates/
├── tests/
├── LICENSE
└── CHANGELOG.md
```

### 6.2 安装方式

插件默认安装在 Claude Code user scope，使同一用户在所有项目中都能访问 Toolkit。项目不复制 Skills，也不逐项目手工注册 MCP。

团队项目可以记录 Toolkit 版本要求，但不把用户状态写入仓库。

### 6.3 插件路径变量

- `${CLAUDE_PLUGIN_ROOT}`：当前插件版本的只读程序、Schema 和模板。
- `${CLAUDE_PLUGIN_DATA}`：跨插件升级保留的运行时、依赖、缓存和用户数据。
- `${CLAUDE_PROJECT_DIR}`：当前 Claude Code 会话的项目根目录。

不得在 `${CLAUDE_PLUGIN_ROOT}` 中写持久数据，因为插件升级会改变安装路径。

### 6.4 MCP 自动启动

插件内置 `.mcp.json`，将 MCP 绑定到当前项目：

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "${CLAUDE_PLUGIN_ROOT}/bin/stm32-toolkit-mcp",
      "args": [
        "--project-root",
        "${CLAUDE_PROJECT_DIR}",
        "--data-root",
        "${CLAUDE_PLUGIN_DATA}"
      ]
    }
  }
}
```

每个会话的 MCP 从启动时绑定一个项目根目录，不能在运行中切换项目。所有文件路径必须经过规范化并验证位于项目根目录或该项目专属数据目录中。

### 6.5 环境未完成时的 Skill-only 引导

版本化 MCP runtime 未安装或损坏时，MCP launcher 必须失败关闭，不使用系统 Python 回退。此时 Claude Code 仍可发现插件 Skill `/stm32-toolkit:setup-stm32-env`；该 Skill 通过显式内联插件路径执行只读 CHECK，并返回 runtime 的 `missing`、`healthy` 或 `broken` 结构化证据。

用户明确授权后，Bootstrap 或 Repair 在 `${CLAUDE_PLUGIN_DATA}/runtime/.staging/` 的唯一目录中构建，验证 Toolkit 精确版本和 doctor 后才提升到 `runtime/0.2.0`。Repair 先隔离损坏 runtime，并在提升失败时回滚。环境完成后，插件 `.mcp.json` 才启动 MCP 并提供 `stm32_doctor`、`stm32_project_detect` 和 `stm32_project_context`。Skill 检查不访问硬件、不安装外部工具，也不写项目目录。

## 7. 项目上下文和数据隔离

### 7.1 标识

每个项目包含：

- `logicalProjectId`：存储在 `.stm32-project.json` 中的稳定 UUID；
- `workspaceId`：由 `logicalProjectId` 和规范化绝对路径计算的哈希；
- `sessionId`：每个 Claude Code/MCP 会话的随机唯一标识。

同一仓库的两个本地克隆具有不同 `workspaceId`，避免共享运行状态。

### 7.2 数据分层

```text
${CLAUDE_PLUGIN_DATA}/
├── runtime/<toolkit-version>/
├── config/user.json
├── packs/
├── probe-registry/
└── projects/<workspaceId>/
    ├── metadata.json
    ├── monitor/
    │   ├── watch-groups.json
    │   ├── last-session.json
    │   └── exports/
    ├── diagnostics/
    ├── logs/
    ├── cache/
    └── sessions/<sessionId>/
        ├── context.json
        ├── diagnostic-state.json
        ├── monitor-runtime.json
        ├── artifacts/
        └── session.log
```

用户监控组属于用户数据，并按 `workspaceId` 隔离；它们不进入源码仓库。

### 7.3 项目内数据

项目仓库只保存可共享、可重复构建的事实：

```text
Project/
├── .stm32-project.json
├── .stm32-toolkit/
│   ├── generated-files.json
│   └── toolchain-requirements.json
├── CMakeLists.txt
├── CMakePresets.json
├── .vscode/
├── App/
├── Core/
├── Drivers/
└── Tests/
```

本机特有覆盖保存在 `.stm32-toolkit/local.json`，并加入 `.gitignore`。

### 7.4 多会话和多项目

- 不同项目使用不同 MCP 进程、`workspaceId`、数据目录和 Monitor 端口。
- 同一项目的不同会话使用不同 `sessionId`，但可以共享用户监控组。
- 第一版只支持一个活动 STM32 项目根目录。
- 检测到多个 Claude MCP roots 时要求用户选择，不自动猜测。

## 8. 统一项目模型

`.stm32-project.json` 是迁移和新工程创建的共同输入：

```json
{
  "schemaVersion": 1,
  "logicalProjectId": "uuid",
  "generatedBy": {
    "tool": "stm32-toolkit",
    "version": "1.0.0"
  },
  "project": {
    "name": "motor-controller",
    "origin": "keil-migration"
  },
  "target": {
    "device": "STM32F429ZGTx",
    "core": "cortex-m4",
    "fpu": "fpv4-sp-d16",
    "floatAbi": "hard",
    "devicePack": "STM32F4xx_DFP"
  },
  "framework": {
    "type": "spl",
    "version": null
  },
  "build": {
    "sources": [],
    "includePaths": [],
    "defines": [],
    "compileOptions": [],
    "assemblySources": []
  },
  "memory": {
    "source": "keil",
    "regions": []
  },
  "debug": {
    "backend": "pyocd",
    "target": "stm32f429zgtx",
    "svd": null
  },
  "generation": {
    "cubeMxIoc": null,
    "generatedDirectories": [],
    "userDirectories": []
  }
}
```

配置生成器只消费该模型，不自行猜测工程事实。

## 9. 工具选择和能力发现

所有 STM32 Skills 的第一步是调用 `stm32_project_context`。返回内容包括：

- 项目 ID、根目录、来源和驱动框架；
- 芯片、内核、FPU 和调试目标；
- 构建系统、ELF 路径和 ELF 是否新鲜；
- 探针 ID、所有者和固件匹配状态；
- 当前可用的构建、测试、监控和调试能力；
- 缺失配置和推荐动作。

AI 优先使用高层工具：

| 任务 | MCP/CLI 工具 |
|---|---|
| 获取工程上下文 | `stm32_project_context` |
| 检查环境 | `stm32_doctor` |
| 解析 Keil | `stm32_keil_inspect` |
| 转换工程 | `stm32_keil_convert` |
| 生成配置 | `stm32_project_configure` |
| 构建 | `stm32_build` |
| 烧录 | `stm32_flash` |
| 主机测试 | `stm32_test_host` |
| 板端测试 | `stm32_test_target` |
| 启动监控 | `stm32_monitor_start` |
| 读取变量 | `stm32_variable_read` |
| 连续采样 | `stm32_variable_sample` |
| 读取外设 | `stm32_register_read` |
| Fault 分析 | `stm32_fault_analyze` |
| 自主诊断 | `stm32_diagnostic_session` |

工具必须自行验证前置条件：

- ELF 过期时拒绝基于该 ELF 调试；
- 目标不匹配时拒绝烧录；
- SVD 不匹配时拒绝外设读取；
- 构建失败时拒绝烧录旧产物；
- 探针被其他会话占用时返回所有者；
- 文件路径越过工作区时拒绝访问。

## 10. Keil 一次性迁移

### 10.1 阶段

1. `inspect`：只读解析 `.uvprojx`，列出 Target、芯片、宏、Include、源码、汇编、链接配置和 ARMCC 专有语法。
2. `baseline`：记录已有 AXF/MAP、Flash/RAM、入口点和关键符号。
3. `convert`：在 Git 迁移分支中应用 GCC 兼容补丁，生成变更报告。
4. `configure`：生成 CMake、GNU linker、GCC startup、VS Code 和 PyOCD 配置。
5. `verify`：完成编译、链接段、资源、关键符号和硬件冒烟测试。
6. `accept`：确认 GCC 工程成为唯一维护版本，Keil 文件归档。

### 10.2 安全规则

- `inspect` 和 `--dry-run` 永远只读。
- 迁移前要求 Git 基线或等价可恢复快照。
- 每个源码转换记录文件、位置、原语法、目标语法和原因。
- 不在唯一未受版本控制的副本上原地修改。
- 不同时执行 SPL 到 HAL 等业务性重构。

### 10.3 验收门禁

- 工程结构：源文件、Include、宏、汇编和条件编译完整。
- 编译：错误为零，新增警告已解决或有明确豁免。
- 二进制：入口点、向量表、内存区域、关键符号和特殊 section 正确。
- 资源：Keil 与 GCC Flash/RAM 差异在批准范围内。
- 硬件：可烧录、复位、进入 `main()` 并完成冒烟测试。
- 业务：通过当前工程定义的关键变量、外设状态或通信响应。

迁移产物：

```text
artifacts/migration/
├── inspection.json
├── conversion-report.json
├── build-result.json
├── memory-comparison.json
├── smoke-test.json
└── migration-summary.md
```

## 11. 新工程创建

新工程默认技术路线：

- CMSIS Core 和 CMSIS Device 为基础；
- STM32Cube HAL 为默认驱动框架；
- 性能敏感模块允许 LL；
- CubeMX 负责芯片、封装、引脚、时钟和外设初始化；
- CMake 是唯一构建系统。

支持两种入口：

- 最小自动模式：生成可进入 `main()`、可构建、烧录和调试的最小工程。
- CubeMX 模式：创建或导入 `.ioc`，由 Toolkit 补齐统一构建、调试、测试和 AI 配置。

推荐目录：

```text
Project/
├── App/
├── Core/
├── Drivers/
├── Tests/
│   ├── host/
│   └── target/
├── cmake/
├── linker/
├── .vscode/
├── project.ioc
├── .stm32-project.json
├── CMakeLists.txt
└── CMakePresets.json
```

AI 默认修改 `App/` 和 `Tests/`。修改 CubeMX 管理区域前必须明确说明重新生成风险。

## 12. AI 自主调试

### 12.1 诊断会话

用户反馈问题后，AI 执行：

1. 验证源码、Git 状态、ELF、固件和目标板身份一致；
2. 阅读相关代码并梳理数据流、控制流和候选变量；
3. 创建有排序的候选假设；
4. 优先执行非侵入式观察；
5. 根据证据设计下一轮实验；
6. 必要时使用断点、暂停、单步或板端测试；
7. 形成根因、证据链和修复建议；
8. 在任务包含修复时修改、构建、烧录并复测。

诊断状态至少包含：

```json
{
  "symptom": "motor does not rotate",
  "hypotheses": [],
  "observations": [],
  "actions": [],
  "conclusion": null,
  "firmwareIdentity": {},
  "startedAt": "timestamp"
}
```

### 12.2 操作分级

观察模式允许：

- 阅读源码和产物；
- 读取变量和寄存器；
- 连续采样；
- 读取 RTT/UART；
- 获取 Fault、调用栈和 CPU 寄存器。

诊断模式允许：

- 临时断点；
- 暂停和恢复；
- 单步；
- 捕获函数入口；
- 有限诊断测试。

修改模式允许：

- 修改代码；
- 构建；
- 烧录；
- 复位；
- 执行板端测试。

诊断模式在用户要求调试或排查时生效；修改模式要求当前任务明确包含修改、修复或验证新固件。

## 13. Probe Service

Probe Service 是唯一持有 PyOCD Session 的组件。Monitor、AI MCP、板端测试和 CLI 共享它；Cortex-Debug 通过显式交接获得独占控制。

职责：

- 按探针唯一 ID 获取租约；
- 记录 `workspaceId`、`sessionId`、操作和 PID；
- 在 Monitor、AI、测试和 GDB 之间仲裁；
- 独占调试时暂停 Monitor，结束后恢复监控选择；
- 烧录前释放读会话；
- 清理仅属于自身的过期资源；
- 禁止无差别终止 PyOCD 进程；
- 记录目标板和固件版本。

全局探针锁：

```text
${CLAUDE_PLUGIN_DATA}/probe-registry/<probeUniqueId>.lock
```

一个物理探针同时只能属于一个工作区会话。发生冲突时显示当前所有者，不自动抢占。存在多个探针且项目未绑定时要求用户选择。

## 14. stm32-monitor 需求基线

允许完全重构实现，但以下需求不可回退。

### 14.1 变量和寄存器

- 自动发现项目配置、ELF 和精确匹配的 SVD；
- 通过 DWARF 正确支持有符号数、浮点数、枚举、数组和结构体；
- 变量搜索和模块分组；
- 数组元素展开和选择；
- SVD 外设和寄存器浏览、选择与实时监控；
- 显示数值、Hex 和趋势方向；
- 单个读取失败不影响整体监控。

### 14.2 实时监控

- 保留 100ms 到 5s 可调采样范围；
- 连续后台采样；
- 暂停和恢复；
- 多变量趋势图；
- 缩放和历史浏览；
- 尽量不暂停 CPU；
- 地址合并和带宽控制；
- 显示实际采样率、延迟和丢失点。

### 14.3 用户监控组

- 所有命名监控组都由用户在界面创建；
- 不提供项目预置、业务预置或固定 preset；
- 支持保存、加载、重命名、删除、导入和导出；
- 自动恢复上次监控状态；
- 按 `workspaceId` 存储在用户数据目录；
- AI 可以建议监控项，但不能静默创建或覆盖监控组。

### 14.4 导出和 AI

- CSV 历史导出；
- JSON 快照导出；
- AI 分析入口；
- 快照包含变量定义、类型、采样时间和固件身份；
- AI 可访问异常前后的历史，不只读取最后一个值；
- AI 诊断结果可关联趋势图时间点。

### 14.5 探针生命周期

- 显示连接状态；
- 显式连接、释放和重连；
- 无客户端时可自动释放；
- 烧录、GDB 和 Monitor 安全切换；
- 切换后恢复监控组；
- 不终止其他 PyOCD 进程。

### 14.6 多项目 Monitor

- 使用动态本地端口，不固定占用 8888；
- 只绑定 `127.0.0.1`；
- 每个实例使用随机访问令牌；
- 页面显示项目名、芯片和固件版本；
- 导出进入对应 `workspaceId/sessionId`；
- 不同项目不共享历史、端口或运行状态。

## 15. 测试体系

### 15.1 主机单元测试

使用 CMake、CTest 和 Unity/CMock 测试：

- 协议解析；
- 状态机；
- 控制算法；
- 数据转换；
- 校验和错误处理。

### 15.2 ARM 构建验证

- 全部配置成功编译链接；
- Flash/RAM 不超限；
- 关键段地址正确；
- 中断处理函数存在；
- 不存在未解析符号；
- 警告预算没有恶化。

### 15.3 板端测试

通过 RTT、UART、Semihosting 或约定的内存结果区返回结构化结果。AI 能读取失败用例、采集相关运行时证据并进入诊断循环。

### 15.4 Toolkit 自身测试

- `.uvprojx` 解析夹具；
- ARMCC 转换黄金文件；
- Project Schema 校验；
- 配置生成快照测试；
- Fake/Mock Probe；
- 录制监控数据回放；
- DWARF 类型解码测试；
- MCP 契约测试；
- Monitor UI 行为测试；
- 至少一块真实目标板的端到端硬件测试。

## 16. 版本机制

### 16.1 Toolkit 版本

插件、CLI、Probe Service、Monitor 和内置 Skills 采用统一 SemVer 发布版本。

- Major：不兼容接口或工作流变化；
- Minor：向后兼容的新能力；
- Patch：缺陷修复。

### 16.2 Project Schema

`.stm32-project.json` 包含 `schemaVersion` 和生成工具版本。CLI 至少支持当前 Schema 和前一个 Schema。升级必须显式执行 `project upgrade --dry-run` 和 `project upgrade`，禁止静默改写。

### 16.3 生成文件

Toolkit 管理文件记录生成器和模板版本。重新生成时区分：

- 完全管理文件；
- 用户可编辑文件；
- 已偏离模板的文件。

用户文件不得直接覆盖，偏离模板时先生成差异。

### 16.4 MCP/Probe/Monitor 协议

通信携带协议名、协议版本和 Toolkit 版本。不兼容时明确报错。

### 16.5 固件身份

构建产生：

- Git commit；
- ELF SHA-256；
- 构建 preset；
- 构建时间；
- 目标芯片。

Monitor 和调试报告显示固件身份，避免用旧 ELF 分析新固件。

### 16.6 Doctor

`/stm32-toolkit:setup-stm32-env` 和 `stm32-toolkit doctor` 检查：

- 插件、CLI、Probe Service 和 MCP 版本；
- Python 运行时；
- ARM GCC、CMake、Ninja；
- PyOCD 和 CMSIS-Pack；
- CubeMX/CubeCLT；
- VS Code 扩展；
- Project Schema；
- Monitor 协议。

## 17. 错误模型和审计

所有核心命令返回版本化结构化结果：

```json
{
  "ok": false,
  "operation": "build",
  "stage": "link",
  "code": "FLASH_OVERFLOW",
  "message": "FLASH overflowed by 8192 bytes",
  "artifacts": {
    "buildLog": "artifacts/build.log",
    "map": "build/firmware.map"
  },
  "suggestions": []
}
```

规则：

- 构建失败后不继续烧录；
- 板端测试失败时保留 ELF、MAP、日志、测试结果和 Fault 快照；
- AI 的工具调用、断点、暂停、复位和烧录进入会话审计日志；
- `suggestions` 提供事实线索，诊断策略由 Skill 决定。

## 18. 分阶段交付

### 18.1 第一阶段：真实工程纵向闭环

围绕一个当前 Keil 工程完成：

```text
Keil 解析
→ GCC 转换
→ CMake/VS Code 配置
→ 构建
→ 烧录
→ stm32-monitor 实时观察
→ 用户反馈问题
→ AI 建立假设并自主采集证据
→ 定位和修复
→ 重新构建烧录
→ Monitor 和板端测试确认
```

第一阶段同时建立：

- Project Schema；
- CLI/MCP 骨架；
- 项目隔离；
- Probe Service；
- Monitor 需求兼容；
- 诊断会话；
- 结构化结果和基础测试。

验收条件是 AI 完成一次有证据链的自主诊断闭环，而不仅是成功生成配置文件。

### 18.2 第二阶段：完善 AI 编码、调试和测试

- 扩充主机与板端测试；
- 完善 Fault、RTT/UART 和断点诊断；
- 强化固件身份和诊断审计；
- 提高 Monitor 性能和类型支持。

### 18.3 第三阶段：从零创建工程

- `/create-stm32-project`；
- CubeMX `.ioc` 工作流；
- CMSIS + HAL/LL；
- 标准 App/Tests 目录；
- 复用同一构建、监控、测试和调试闭环。

### 18.4 按需扩展

只有出现真实需求时才增加新 STM32 系列、新 Keil 结构、特殊汇编、TrustZone、双核、外部存储或新探针后端。

## 19. 当前原型的重构要求

现有原型中的以下问题属于第一阶段范围：

- 变量类型只按字节数猜测；
- 外设寄存器选择尚未实现；
- 前端覆盖浏览器原生 `setInterval`；
- Monitor 与 MCP 争用探针；
- Session 重连重复打开；
- 启动时终止所有 PyOCD 进程；
- SVD 可能匹配到错误芯片；
- CLI 参数与项目配置优先级错误；
- Web 静态资源打包不完整；
- AI 快照缺少源码、ELF 和固件身份；
- `read-var` 没有持久诊断状态和证据模型；
- 缺少自动化和硬件回归测试。

重构不得删除本设计第 14 节确认的 Monitor 产品需求。

## 20. 最终成功标准

给定当前旧 Keil 工程，Claude Code 能通过 STM32 Toolkit：

1. 生成迁移风险报告；
2. 在可审计变更中完成 GCC 转换；
3. 成功构建、烧录并通过硬件冒烟测试；
4. 根据新需求修改代码并生成测试；
5. 在 Monitor 中持续观察真实运行状态；
6. 根据用户反馈建立诊断假设；
7. 自主选择安全工具采集变量、寄存器、日志和 Fault 证据；
8. 定位根因并在授权范围内修复；
9. 重新构建、烧录和测试，证明问题已解决；
10. 全过程不混合其他项目的数据、监控组、会话或探针状态。

未来新工程通过 CubeMX/CMSIS/HAL/LL 入口复用相同闭环。
