# STM32 Toolkit 标准测试流程

本文件是测试执行顺序、前置检查和失败处理的唯一流程入口。适用于离线验证、部署和实机验收；操作前必须阅读本文件及对应已批准规格。规格定义验收要求，源码定义实际入口契约，本文件规定执行流程，实际报告记录发生的事实。三者冲突时先离线解决，不能临场猜测硬件步骤。

维护责任：主对话框代理维护流程、调度、授权账本和验收结论；Luna/max 负责产品实现及实现测试，独立审查者检查变更。文档修正不触发打包、部署或整轮实机测试。本文件不授予硬件或远程操作权限。

## 1. 从真实断点继续

先读第 8 节和最近执行报告，记录实际工作树、分支、完整 HEAD、accepted base、规格/实现/审查所有者、部署 source commit、工程及 data/runtime 路径、有效证据和剩余场景。核对 tracked/untracked、已提交/未提交、已推送/未推送状态；不能从默认 master 推测状态。保留不属于本轮的改动及产物。

本流程覆盖三个场景：软件修改后的相关离线验证与部署；固定身份下的 Target、运行观测及 IDE 交接；共同验收身份下的 P3 失败、Diagnostic、受控 P4 修复与 FixVerification。非目标是重测未改变的已验行为、升级到 50ms、自动恢复坏板或绕过身份契约。

分别记录：`PASS` 有满足条款的证据；`READY` 入口及前置条件成立、尚未执行；`PENDING` 尚缺结果；`BLOCKED` 存在已知前置或契约缺口；`TERMINAL_STOPPED` 该次执行已结束。不能因为本轮没重测就撤销旧 PASS，也不能把部署 READY 写成整个验收 READY。

## 2. 实机前必须填齐的一张执行卡

使用 run 目录里的普通 Markdown/JSON 即可，不新增通用诊断框架或验证器。一次授权可以覆盖明确的连续步骤，无需逐命令重复确认；终态失败后的重试、范围变化或恢复策略必须重新核对并取得相应授权。

| 必填项 | 执行前必须回答 |
| --- | --- |
| 场景与依据 | 对应哪条规格、交付什么新证据、复用哪些有效 PASS？ |
| 版本与路径 | 实际代码/部署身份；工程、data、runtime、ELF 路径已核实？临时输出位于 D 盘？ |
| 身份来源 | workspace/session/build/ELF/input snapshot/Git/probe/target/flash receipt 来自哪里，哪些字段必须相等？ |
| 状态与所有权 | 最后已证实 target 状态及时间；Toolkit/IDE/无人持有哪个 lease/ticket？用户灯态与机器状态分开记录？ |
| 操作契约 | 现有入口、参数、running/halted 前置、连接及执行的状态变化、输出字段，源码依据在哪里？ |
| 授权与预算 | 当前用户授权原文及范围、新 action 来源、固定次数/时长/超时、是否允许 flash/reset/halt/resume？ |
| 判定与收尾 | 成功字段、下一步条件、首错停止条件、既有 cleanup 及其终态证明？ |
| 留证 | stdout/stderr、原始异常 code/details/cause、阶段、身份、TestRun/receipt/lease 保存到哪里？ |

关键字段未知的步骤不是 READY。先用现有源码、日志、CLI help 或既有函数离线补齐。若公共响应吞掉原始异常，必须在首次获准实机前准备好现有异常边界的捕获方式；不能失败后无授权重连补日志。新增脚本前说明现有入口为什么不够，并先离线验证。

provenance 拒绝必须记录检查函数/行号、逐字段预期值/实际值及各自来源、最后已证实阶段，不能只看错误码或 gitDirty。迁移后文件字节相同不保证 device/inode 身份相同；使用既有只读验证入口，不改 pin、不复活已消费记录。按场景创建 session：当前固件观测和 T9 沿用有效 flash receipt 的绑定，T10 按共同身份契约另建，不能每条命令任意换 session。

## 3. 状态契约表

源码路径相对于 `tools/stm32-toolkit/src/stm32_toolkit/`，核对基线为部署 source `5f036363383e6c85cc87426da1b4a1c20dfe7acc`。行号用于定位，入口改变时按函数重新核对并更新。

| 入口 | 实际状态契约及源码依据 | 执行限制 |
| --- | --- | --- |
| 正常 Target prepare | `testing_workflows.py:502-556` 建 OBSERVE，attach 后才持久化授权；`probe/pyocd_backend.py:978-988` 连接暂时 halt，然后 resume 并验证 running | 需要连接授权及唯一 owner；不烧录；无新 digest 不得 execute |
| 正常 Target execute | `testing_workflows.py:647-654` 使用 MODIFY；`probe/pyocd_backend.py:970-977` 要求 attach halted；`testing/target.py:899-929,1599-1619` flash/readback 后 reset，必要时 resume，再开 transport | 只消费本次匹配的新 digest；flash 成功不等于程序运行成功，须得到真实 TestRun |
| 变量/有限采样 | `debug/read.py:237-253,580-603` 走 memory.read；`probe/pyocd_backend.py:1193-1225` 无 halted 前置 | 允许运行态读取；正常 attach 仍有暂时停核。接口允许不等于已物理证明底层全程无瞬时停核 |
| SVD 外设寄存器 | `debug/read.py:606-637` 解析后仍走 memory.read | 只读已核对安全的路径；不同于 core register；单点 ODR 仅证明当时位值 |
| 完整 Fault | `debug/fault.py:227-245,514-558` 初次/最终 core register 要求 halted 且稳定；`debug/model.py:563-600` 强制 halted 报告 | 必须有保持 halted 的入口和所有权/控制契约；运行正常不等于无活动 Fault |
| 当前公共 Fault wrapper | `hardware_workflows.py:979-1015,1146-1166` 固定 OBSERVE attach 并恢复 running，CLI/MCP 没有保持停核参数 | **BLOCKED：入口状态与 Fault 前置冲突。** 不能先 halt 再调用会 resume 的 wrapper，也不能放宽检查或把所有 OBSERVE 改为 halt |
| IDE handoff | `probe/handoff.py` 的 begin/end 和 `CortexDebugAttachContract` 管理 ticket 与身份 | begin 成功后由 IDE 独占；正常 detach 后原 ticket end，回收成功才可 Toolkit read |

连接时暂时停核是用户已接受的边界；连续采样阶段不得 halt/reset/resume，二者分别留证。完整 Fault 停核场景不能混入不停核采样，也不能在 IDE 持有探针时用 Toolkit 抢读。

## 4. 固定顺序与出口

1. **离线准备**：执行卡、入口、原始错误保留齐备；仅跑受影响的既有验证。报告/命名修正不触发产品测试。候选改变且获准时才部署一次，核对最终固定 runtime 路径下的版本/manifest/安装字节；有效部署结果继续复用。
2. **正常 Target（确有需要时）**：一次 prepare → 核对身份/digest → 一次 execute → 公共 test show。核对 physical 来源、断言/mailbox、flash/run 身份及 cleanup。已经接受的 P2 不因进入下一轮而重烧。
3. **运行中观测**：绑定当前固件，固定有限 testtime/GPIO 预算。计数增长证明活性；不同时刻的 PE4 变化才证明位翻转；ODR 单点、用户 D4 观察、Target heartbeat 分别留证，不能互相冒充。预算内没观测到则记未证实，不追加读取直到通过。完整 Fault 独立列为阻塞项。
4. **T9**：先离线核对 IDE/GDB/PyOCD 服务入口、target/pack 支持、实际 ELF/外置 workspace、真实 UI 操作者和 detach 方法。一次 begin → 本次返回配置 → IDE attach/只读观察/正常 detach → 原 ticket end → Toolkit typed read → 同绑定 MCP 只读。异常停止，不 steal、不杀无关 owner、不重复 begin。
5. **T10**：P3 修改/烧录前，必须明确两侧 Target、物理 Monitor history 采集入口/预算、LED selector、Analysis/Diagnostic 和恢复意图的数据流。只有 publish 命令不算采集入口 READY。按批准计划完成 T9 后，执行第 5 节 T10 顺序。
6. **收尾**：记录每项状态、证据/hash、身份及阶段；保留租约释放与所属 worker 退出的正面证据。板态仅由既有获准测量或用户观察记录，不为收尾额外隐式访问硬件。Task11 lineage、Task12 全量 diff 未完成不得宣布 VS10-A 完成。

## 5. 公共模板及 T10 数据流

模板不能连续粘贴执行，也不构成授权。`TK` 为已核实 D runtime 的 `Scripts/python.exe -I -m stm32_toolkit.cli`；Target/read/debug/diagnose/scenario 命令附 `--project-root <P> --data-root <D> --session-id <S> --json`。build 例外，不附 data/session。

```text
TK build --project-root <P> --preset arm-debug --json
TK test target prepare --probe-id <selector> --case-id d4-heartbeat
TK test target execute --probe-id <selector> --authorized-action-digest <本次新digest>
TK test show <实际nativeRunID>
TK read sample --probe <selector> --expected-build-id <build> --expected-elf-sha256 <elf> --expression testtime --interval-ms 250 --count 3
TK read register --probe <selector> --expected-build-id <build> --expected-elf-sha256 <elf> --path GPIOE.ODR
TK debug handoff begin --probe <selector> --expected-build-id <build> --expected-elf-sha256 <elf> --authorized --watch testtime
TK debug handoff end --probe <selector> --ticket <本次原ticket>
TK read variable --probe <selector> --expected-build-id <build> --expected-elf-sha256 <elf> --expression testtime
```

保存完整响应，再提取标量。Target run ID 取 `data.run.run_id`，evidence 取 `data.evidence_id`；`data.test_manifest` 是 artifact 引用，不能当 run ID。MCP `stm32_variable_read` 使用 `probeId/expectedBuildId/expectedElfSha256/expressions`，project/data/session 由服务端绑定并核对等价身份。

T9 外置 run-owned `.code-workspace` 的 folders 指向实际 P2；launch/configurations 包装本次 begin 返回的 Cortex-Debug 片段并加 name/type。保留 `servertype=pyocd`、`request=attach`、`targetId=target` 及返回的 serialNumber/boardId/executable。boardId 不可用 selector/fingerprint 或旧 raw ID 替代；executable 保留返回的 `${workspaceFolder}/...` 展开形式，确认解析后 ELF 存在且身份匹配。不写 P2 `.vscode` 改变输入身份。原生 UI 不可自动控制时由用户操作，headless DAP/fixture 不等价。

workspace 级 launch 必须显式设置 `cwd` 为实际工程的**绝对路径**。Cortex-Debug 1.12.1 的 `resolveDebugConfigurationWithSubstitutedVariables(folder,config,...)` 在 cwd 缺失时执行 `config.cwd || folder.uri.fsPath`，相对 cwd 也会访问 folder.uri；workspace 级回调的 folder 可为 undefined。不得假设顶层 folders 会自动给该回调补齐上下文。配置核对须覆盖此分支，不能只检查命令参数。

handoff begin 前，还必须在**不启动调试**的情况下确认实际 IDE 已成功打开目标 workspace，核对真实 executable/version/profile 与扩展激活状态；可使用当前窗口确认或该实例的启动/renderer/extension 日志。exe 存在或 Start-Process 返回不算成功。更新锁、启动退出或实际窗口属于另一安装时先记录并解决该环境前置，不终止无关更新程序，也不先交出探针再排查界面启动。

在同一离线阶段，用配置实际选中的最终 runtime `pyocd.exe --version` 验证真实入口，并核对最终 Python 绑定及无 staging 残留；模块 parser/import 成功不能替代此项。缺失、退出非零或版本不符先修复，禁止进入 handoff。部署说明及这次 IDE 故障的复用核对项统一见 [Windows 部署与 IDE 前置核对](windows-deployment-and-ide-preflight.md)。

本机环境适配（仅 Cortex-Debug 1.12.1 + PyOCD 0.45.1）：原始 handoff 返回值及 boardId 完整保存。该扩展的 PyOCD 控制器把 launch.boardId 转为旧 `--board`，而当前 pyocd.exe 不接受此参数；pyocd-gdbserver.exe 又不接受扩展附加的 `gdbserver` 子命令。故仅在本次外置 launch 中省略 boardId，并设 `serverArgs=["--uid", <本次返回的原始boardId>, "--connect", "attach"]`；其他返回字段不变，serverpath 指向已核实的 D runtime pyocd.exe，cmsisPack 指向已验证包含该 target 的实际 pack。禁止丢失原始身份或让 PyOCD 自动挑探针。

离线依据：扩展 `dist/debugadapter.js` 的 PyOCDServerController.serverArguments() 仅在 boardId 存在时追加 --board，最后追加 serverArgs，不读取 serialNumber；当前 PyOCD parser 接受上述完整参数。`pyocd/subcommands/base.py:95-96` 定义 --connect，`gdbserver_cmd.py:184-197` 传入 Session；未设 --reset-run 时 `234-236` 不执行 reset，Cortex-Debug attach 仍会 monitor halt。此适配不修改插件/安装/固件、不新增启动脚本，连接时停核在当前授权内。实际结果必须标明“适配后的 IDE 路径”；不能把它宣称为原始生成配置直接可用或原始兼容缺口已修复，完整 T9 是否满足原规格须单独判定。

该版本对还须核对服务 ready 信号：Cortex-Debug 默认 `GDB server started (at|on) port` 不匹配 PyOCD 0.45.1 的 `GDB server listening on port`。仅外置 launch 增加现有字段 `overrideGDBServerStartedRegex="GDB server (?:started (?:at|on)|listening on) port [0-9]+"`，用已取得日志离线验证匹配及 STDIO 反例，独立审查后才进入下一次获准 IDE 步骤；不延长超时或重连补同一证据。

T10 顺序如下；动态值只能来自真实返回，缺少的输入结构必须在开始前明确：

| 步骤 | 操作与必要引用 |
| --- | --- |
| A | 新 UUID attempt，scenario=`legacy-keil-physical-repair`、version=1；scenario attempt begin → checkpoint project-materialized。P3/P4/Diagnostic 共用 EvidenceIdentity.session_id，各 flash/action/lease 独立且新鲜 |
| B | 获准后只将 Main/Main.c 的 `LED1=!LED1;` 改为 `LED1=1;`；真实 build → checkpoint firmware-built-before → 新 prepare/execute → P3 physical failed。仅预期 heartbeat 断言失败可继续，基础设施/身份/超时错误不能算预期 P3 |
| C | checkpoint target-failure-observed 绑定 P3 run；`diagnose start <P3> --failed-run-mode target --operation-id <新ID>` → begin/hypothesis add/plan add、run/hypothesis assess，形成实际诊断。failed-run-mode 默认 host，不可省略 |
| D | P3 固件仍运行时，使用已准备入口采集有限 Monitor window 并 publish failed-before；不能切换 P4 后补采 P3 |
| E | 核对实际 before 文件 SHA、完整 InputSnapshot、Diagnostic 对应的 source-change intent → checkpoint diagnosis-completed → scenario attempt resume → 核对返回 revision/actionDigest → authorize-source-change --authorized。旧 planned intent 只是候选，不是授权 |
| F | 只恢复获准那一行 → 真实 build，完整 after InputSnapshot 等于 intent 派生值 → diagnose source-change declare → checkpoint firmware-built-after → 新 prepare/execute → 同 T10 身份 P4 physical passed |
| G | P4 运行时采集真实 window → publish fixed-after → compare/bundle 绑定两侧 monitor refs、TestRun、declaration、Diagnostic。selector 必须证明 LED 修复，只有 testtime 增长不够 |
| H | VerificationPlan → verification start → marker attach → verification complete；Diagnostic=RESOLVED 且 FixVerification=PASSED 后，checkpoint target-fix-verified 绑定 P4 native ID 和实际 fix-verification-id |

attempt 写操作使用当前 attempt revision；Diagnostic 写操作分别使用新 operation-id 和当前 Diagnostic revision，不能混用。hypothesis add 带 statement；plan add 带 steps-file、run 带 plan-id；assess 带 hypothesis-id/plan-id/step-id/polarity/rationale。Diagnostic ID 是实际 32hex，FixVerification ID 是实际 64hex。P3/P4 分别核对 execution_source=physical、physical_transport_evidence=true、build/ELF/input/session/probe/target，以及相同 mailbox transport_config_digest，不能只看 passed 字样。

`MON` 是安装的 `Scripts/stm32-monitor.exe`，不能用无 main 调用入口的 `python -m stm32_monitor.cli`。以下附 `--project <P> --data-root <D> --session-id <T10共同S> --json`；只发布/分析已有 history，**不生成物理采样窗口**。

```text
MON physical publish --scenario-role <failed-before或fixed-after> --test-run-id <P3或P4> --run-id <实际historyRun> --group-id <实际group> --start-sequence <起点> --end-sequence-exclusive <终点不含> --start-captured-unix-ns <起点> --end-captured-unix-ns-exclusive <终点不含> --probe-id <history.binding.probeId原始selector>
MON analysis compare --request-file <request.json> --diagnostic-session-id <diagnostic> --hypothesis-id <hypothesis> --polarity supports --rationale <实际理由> --source-change-file <declaration.json>
MON analysis bundle --request-file <同一request.json> --publication-file <publication.json> --failed-before-test-run-id <P3> --fixed-after-test-run-id <P4> --source-change-file <同一declaration.json>
```

physical publish 的 --probe-id 必须取 `history.binding.probeId` 原始 selector，离线验证 `sha256(selector)==TestRun metadata.probe_id`；不得传已发布 `MonitorRunRef.probe_id` 的 SHA-256 值，否则会重复哈希并导致身份比较失败。字段来源见 Monitor `replay.py:1441-1450,1893-1899,1931-1965`。

publish 的 data.monitor_run_ref 填 request before/after；compare 的 data.analysis_publication 单独保存为 publication.json，不能传完整响应；其中 diagnostic_marker_ref 用于 marker。要求 quality=VALID、conclusion=COMPLETED、changed=true。VerificationPlan ID 必须等于 declaration.validation_plan_id，绑定两侧 run/evidence、declaration、analysis ID/evidence，required_monitor_quality=VALID、expected_changed=true。verification complete 引用实际 P3/P4 operation IDs 和 monitor.analysis.compare、monitor.analysis.bundle。不生成 VS08 AcceptanceRecord 冒充物理验收。

## 6. 首错即停，先分类再改动

非预期枚举/attach/状态/身份/烧录/读取/发布/清理错误发生后，停止后续硬件及动作消费。保存原响应/异常链、最后成功阶段、授权消费状态、flash/TestRun 是否产生、当前 lease/ticket。执行原入口约定 cleanup；同次调用内部清理与外部重新调用硬件必须分开报告。cleanup 未证实成功则状态未知/阻塞，不能把超时或发送进程终止信号写成释放成功。

分类 PRODUCT、INFRASTRUCTURE、ENVIRONMENT、PLATFORM、HARDWARE、REPORT；未确证则列明唯一证据缺口。不能凭错误码、gitDirty、D4 常亮猜根因。优先调用现有函数或复用测试离线定位。产品修复按规格、Luna/max 实现和独立审查；流程修正由主代理维护，不能放宽身份/状态契约让测试变绿。

确需硬件补证时，先说明唯一假设、一次操作边界、成功标准和失败停止条件，再申请新授权。不自动重试、不切 under-reset、不擅自 reset/halt/resume、解锁、断电或换板。用户重连/换板后重新记录现场与证据适用范围，不继承旧 action。

## 7. 保留成果和维护规则

### 何时修改，何时可以跳过

| 情况 | 处理方式 |
| --- | --- |
| 入口参数/返回字段、状态迁移、所有权、身份契约、错误或 cleanup 行为改变；发现遗漏/冲突；正式验收要求改变 | **必须修改**相应流程条目，标明依据及受影响步骤；独立审查新增/改变的内容后才执行依赖步骤。未受影响且已审查的内容不重审 |
| 只变化当前 HEAD、session、路径、授权或本轮结果，操作契约不变 | 更新当前断点和本轮执行卡，不重写通用流程，不触发产品回归或整轮流程审查；路径迁移若改变身份/入口契约则按上一行处理 |
| 仅排版、错别字、链接或报告命名修正，语义不变 | 可直接修正并检查差异/引用，不重跑测试；一旦改变参数或判定含义就不是纯排版 |
| 某项已有 PASS，且该验收条款要求的版本/固件/身份/环境/契约仍适用 | 可跳过**重复执行**，在卡中记 REUSED、原证据和适用依据，验收条款仍由该证据覆盖 |
| 某步骤对本次场景不适用，或有相同覆盖能力的已批准入口 | 可记 N/A 或使用等价入口，说明不适用理由/等价契约及证据；不能把缺失证据、缺硬件、失败或入口阻塞写成 N/A |
| 临时改变预算、命令、顺序或连接策略 | 若仍在已批准契约与当前授权内，由主代理在执行前记录限定范围/理由/等价性；涉及契约变化先改流程并审查，涉及新控制或失败重试另取授权。例外本轮结束失效 |

不能忽略授权、身份匹配、状态前置、唯一 owner、有限预算、首错停止和证据真实性。显式用户新要求优先于旧流程，但只覆盖其明确改变的范围；不得将“开始测试”解释成放弃这些边界或取消必验条款。一个场景 BLOCKED 时，可继续前置独立且已授权的场景，在报告中保留未闭合项；不能借此宣称整体验收完成。

每轮实际结果进入执行报告；第 8 节只更新当前状态及指针。旧 run-local 卡片是历史快照，不是下一轮入口。操作、状态前置、参数/输出或流程遗漏有变化时，先更新本文件相关条目并独立审查，再执行依赖步骤；不能只在聊天中修正。

复用证据逐条核对规格要求的身份/版本/环境/契约未变，写明来源和范围。文档改变不使产品证据失效；相关固件/产品字节/绑定改变只补受影响结论。attempt 7、-12 不改标为当前 T10 lineage，也不因新失败删除。文档、等待、测试数量不计作产品进度。

按已核实绝对路径清理本轮不再需要的临时输出；保留源码测试、可复用基线、用户数据、共享缓存、rollback、授权账本、有效 PASS 和最小失败证据。Windows 使用同一 PowerShell 原生命令，删除前确认在本轮目录内。自动策略拒绝 cleanup 时记录保留，不换工具/路径绕过。没有新测试不制造清理工作。

## 8. 当前验收断点（2026-09-11）

09 超时的后续离线定位：真实 stdio 中仅构造/关闭 worker 即复现 10 秒超时；仅对 Windows spawn worker 显式设 child stdin=NUL 后 1.469 秒 ready、关闭后无残留、协议正常。独立审查确认 stdin 继承触发的进程环境兼容问题，发生在服务/探针访问前；更底层阻塞栈未取得。诊断及最小修正边界见 [MCP worker stdin 修正计划](../superpowers/plans/2026-09-11-stm32tk-mcp-worker-stdin-repair.md)。产品修复尚未实现/部署，无硬件重试；下段“根因不足”为当时断点，已由此处取代。

最新 continuation 09：适配后的 IDE 路径 PASS（用户 testtime=10、GDB exit 0、D4 闪烁；本地 session events 佐证 attach/terminated），原 ticket end/reacquire OK，一次 CLI 读取 testtime=10。随后一次 MCP 读取返回 PROBE_TIMEOUT，本轮 **TERMINAL_STOPPED_MCP_PROBE_TIMEOUT**，没有重试。最终 registry=released、handoff=observing/ticket=null，无 Python/PyOCD/GDB 残留；MCP 后 D4 未再次目视确认。根因/具体超时阶段证据不足，下一步仅离线定位。原始生成配置兼容缺口及 T9 MCP 等价仍未闭合，T10/VS10-A 未完成。证据 `D:\codex-tmp\t9t10-t9-20260911-09` 及下方 T9 执行记录。以下 07/08 为历史断点，原外部预约现已消费释放。

最近 IDE 尝试：continuation 07 已因用户报告 `PyOCD: GDB Server Quit` **TERMINAL_STOPPED**。实际扩展日志确认正确 T9 attach 配置进入 initializing/capabilities 后 terminated；没有成功 attach/detach 证据。当时离线确认所配置的 pyocd.exe 内嵌已不存在的 D runtime staging Python，`--version` 退出 1，而最终 runtime Python 的 `-I -m pyocd --version` 返回 0 / 0.45.1。原 IDE server stderr 尚未取到，不能宣称已还原全部现场错误。当时的启动入口阻塞已按下段修正，后续硬件仍停止；未重复 begin、未执行 end/reacquire，最后已核实的 externally-owned 预约保留。证据目录 `D:\codex-tmp\t9t10-t9-20260911-07\gdb-server-failure`。参见 [T9 执行记录](../codex/returns/2026-09-11-stm32tk-1001-t9-ide-attempt-06.md)。

后续离线修正已完成：部署脚本增加 PyOCD 最终化/绑定/版本检查并独立接受，本机从原 manifest 验证的同版本 wheel 限定修复后，真实 pyocd.exe 与模块版本均为 0 / 0.45.1。运行时产品 source、固件、receipt、runtime-state 及外部预约哈希未变；没有重新打包、全量部署或访问硬件。启动器阻塞已解除，07 仍为历史终态失败，下一步 IDE 重试及原 ticket 回收仍需新授权。参见 [修复及验证记录](../codex/returns/2026-09-11-stm32tk-runtime-pyocd-launcher-repair.md)。

当前 continuation 08 已因用户报告“testtime=不可用，PyOCD报错” **TERMINAL_STOPPED_IDE_PYOCD_ERROR**。修复后的 EXE 哈希未变；当前没有 PyOCD/GDB/Python 进程，handoff/registry 仍为 externally-owned。扩展日志记录 T9 初始化、capabilities 后 terminated，未证明 server ready、attach 或成功 Watch 读取；已有多个会话记录，不能无时间链把它们都算作本轮操作。原始 gdb-server 错误尚缺，已请求用户复制现有输出，不重新连接补日志。暂停 end/reacquire、CLI/MCP 读取及重试。证据及执行卡：`D:\codex-tmp\t9t10-t9-20260911-08`。原生窗口工具身份校验失败仍限制直接读取 UI；不据错误码或变量不可用猜测硬件原因。

用户随后提供的终端原文补齐阶段：DP/AP/ROM/CPU 发现完成，GDB 已监听 50000；因此早先的“server ready 未证明”已被这份新证据替代。离线实际扩展函数复现就绪正则不匹配，10 秒超时关闭路径与现有约 10.4 秒时间记录一致，分类为 IDE 版本兼容；完整现场 timeout/kill DAP 记录仍缺。外置配置已仅添加上述 ready override，已通过独立审查，未启动服务或重试硬件，08 仍终态停止。

| 项目 | 状态及下一步 |
| --- | --- |
| 工作树 | `D:\workspace\stm32tk-1001-legacy-hardware-impl`，分支 `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`；本次文档 accepted base `35e08b72179dfa1784d447f09d2b2c33b39f0064` |
| 部署 | source `5f036363383e6c85cc87426da1b4a1c20dfe7acc` / 0.9.0，Check healthy/matching、安装字节检查有效；不重新部署 |
| runtime / data | `D:\codex-tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0` / `D:\codex-tmp\stm32tk-vs10a-legacy-campaign\data` |
| P2 | `D:\codex-tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`，HEAD `4bfcf9f95b1d761c9a82042d6ded751d068c1e06`；保留现有 untracked 产物，不声称目录全净 |
| P2 build / ELF | build `77d787ee83f744831316f9531b825935ef276520472221a8174f7a7d4cfe57f9`；`build/arm-debug/LWIP.elf` SHA256 `10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead` |
| 正常 Target | **PASS**：session `vs10a-t9t10-p2-20260911-04`，run `target-v2-c3ff80b549561c68d3a5961072d728ba`，heartbeat 1/1、54896 字节 readback；用户确认结束后 D4 仍闪烁。当前 flash receipt 属于 04；不重烧，digest 已消费 |
| observation 05 | **TERMINAL_STOPPED**：Fault 返回 FAULT_TARGET_NOT_HALTED / state=running；无 Fault report、无“无活动 Fault”结论；此后无采样/GPIO/handoff。lease released、runtime 进程 0、P2 receipt 未变 |
| 必要观测 | **PENDING**：按原 Task7 逐项核对 -12 能覆盖的相同固件/probe/workspace 条款，仅补缺口；完整 Fault 公共入口 **BLOCKED**，见第 3 节 |
| 100ms / 历史 | -12 的 30 秒 299 批、P95 102.8332ms 连续不停核 PASS 和 attempt 7 历史实机 PASS 保留，不冒充当前 T10 run |
| T9 | 09 适配后 IDE attach/Watch/detach PASS；end/reacquire OK，CLI typed read PASS；MCP PROBE_TIMEOUT 后终态停止，预约已释放。保留原始生成配置兼容缺口，完整 T9 未通过 |
| T10 | 软件独立接受；P3/P4/Diagnostic/FixVerification **PENDING**；当前候选物理窗口采集入口/预算/LED selector 尚待完整冻结，完成前不得开始 P3 |
| VS10-A | **未完成**：剩余观测、T9、T10、Task11 lineage 和 Task12 全量 diff |

T9 本次实际运行的 IDE 为 `D:\Program Files\Microsoft VS Code\Code.exe` 1.129.1；此前 C 盘 `C:\Users\ZhangYang\AppData\Local\Programs\Microsoft VS Code\new_Code.exe` 因更新锁退出，不能继续列作已就绪入口。后续以实际进程及加载上下文重新核对。GDB 为 `C:\ST\STM32CubeCLT_1.22.0\GNU-tools-for-STM32\bin\arm-none-eabi-gdb.EXE`，Cortex-Debug 1.12.1。外置 workspace 必须指向上表 project-standard-math，不能误用 sibling project。本地 pack 3.1.1 与 manifest 声明 2.17.1 不同，应核对实际 PyOCD target 支持/来源，不能静默等同。C 盘安装程序允许使用，旧 C temp/tmp 工作产物不可用。

可核验依据：

- [P2 各次执行及最新断点](../codex/returns/2026-09-11-stm32tk-1001-p2-serial-attempt-01.md)；04 原证据 `D:\codex-tmp\t9t10-p2-20260911-04`，05 原证据 `D:\codex-tmp\t9t10-p2-observe-20260911-05`。
- [软件集成与部署](../codex/returns/2026-09-11-stm32tk-1001-t9-t10-local-delivery.md)。
- [VS10-A 规格](../superpowers/specs/2026-08-25-stm32-toolkit-1001-legacy-keil-real-board-closed-loop-design.md)、[原计划 Task7–12](../superpowers/plans/2026-08-25-stm32-toolkit-1001-legacy-keil-real-board-closed-loop.md)、[运行/停核状态契约](../superpowers/plans/2026-09-10-stm32tk-1001-protocol-test-state-alignment.md)。
- Task12 Toolkit 全量 diff 基线 `9b7839bb01f88a9e3d2c13203f38aa0d11647232`，工程 P0–P4 全量 diff；软件切片 base `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1` 不替代最终历史基线。
