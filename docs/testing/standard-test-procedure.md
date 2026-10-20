# STM32 Toolkit 标准测试流程

本文件是离线验证、部署与实机验收的执行入口。规格定义要求，源码定义实际入口合同，本文件规定执行顺序，报告记录事实。冲突须先离线解决，不在硬件操作中猜测。主代理维护本流程、调度和验收；实现和新增测试由 gpt-6-sol / max 子代理负责，作者不能自行接受差异。本文不授予安装、硬件或远端权限。

## 1. 当前断点与证据

2026-10-20 当前活动切片为 Monitor 变量角色、extern 映射、版本化源码快照与目录层级，依据[规格](../superpowers/specs/2026-10-20-monitor-variable-directory-design.md)及[计划](../superpowers/plans/2026-10-20-monitor-variable-directory-plan.md)。Accepted base `34256353d3b7ab0f8eacaa9b8065759299855933`，分支 `codex/monitor-variable-directory`；主代理负责规格/集成/独立复核/验收/运维，`variable_directory_impl` 是唯一 gpt-6-sol/max 实现者，最终审查者须独立。当前状态 IMPLEMENTING，尚未接受或部署本切片。原服务仍从 `D:\codex-tmp\ma1020\review` 的上述 accepted head 运行，PID20004、exec77714，服务卡 `D:\codex-tmp\ma1020\service.json`；本轮根 `D:\codex-tmp\mv1020`。当前 MR 旧构建/ELF/169路径快照及原收据必须保留，新策略171路径的构建/索引验证在独立项目副本完成，不伪补旧身份或执行硬件。真实浏览器/认证HTTP/新硬件继续暂缓；此前 Edge 新标签短入口可用是用户手工确认，不是自动浏览器或关闭重开证据。下方既有验收作为历史保留。

2026-10-19完整源文件目录树的软件与本机服务更新已ACCEPTED，依据[规格](../superpowers/specs/2026-10-19-monitor-source-file-tree-design.md)、[实施计划](../superpowers/plans/2026-10-19-monitor-source-file-tree-plan.md)及[最终审查与部署](../codex/returns/MONITOR-SOURCE-FILE-TREE/review.md)。Accepted base `3c4e2594bafc8d7ca2f1b00c1efe6683639cf05c`，CodeHead `41b5cc37f60d26da2ed323dd7b934fc980b3df61`，实施报告head `f6ba4cbb21e2b8ceb3577a95a46bbdccaaaaec87`；分支`codex/monitor-source-file-tree`，file_tree_impl唯一实现、file_tree_review_sol（显式gpt-6-sol/max）独立完整差异审查NO BLOCKERS，主代理独立复核、验收并部署。实现者143项Python/474项UI、类型/lint/build/dist通过；主代理精确干净CodeHead的72项UI、119项源码集成、29项静态资产和7文件重建一致性通过。8765已从`D:\codex-tmp\st1019\review`运行该CodeHead，PID22740/exec27630，运维卡`D:\codex-tmp\st1019\service.json`。文件/函数metadata与变量分页分离，空文件/函数保留，变量按scope懒加载；当前工程离线21/21单元、184文件、0 issue。版本保持1.1.2。浏览器、实际认证HTTP和新硬件仍DEFERRED，无远端/安装权限变化。此前源码目录验收记录作为历史保留如下。

已发布 v1.0.0/v1.0.1 的固定身份、一次性覆盖率例外和限制见[发布状态](../release-status.md)。旧例外不自动延续至新版本；2026-10-10 用户为 v1.0.1 批准的“不低于 v1.0.0”条件与已完成测量保留在[发布资格](release-qualification.md)和[执行记录](../codex/returns/STM32TK-101/execution.md)，分母、成员和永久门槛不改。

2026-10-19源码变量目录及已集成探针反馈的软件已ACCEPTED。入口为[规格](../superpowers/specs/2026-10-19-monitor-source-catalog-design.md)、[计划](../superpowers/plans/2026-10-19-monitor-source-catalog-plan.md)和[最终验收与部署](../codex/returns/MONITOR-SOURCE-CATALOG/review.md)。Accepted base `1c320d9dc102ca11a280b97e210517ac5a852b63`，CodeHead `423dc766e60233e4e79bd1ed5306e6631c1d3daa`，报告head `983540580f9e70f04e9e4770b9a16858fc4cd476`。唯一实现者source_catalog_impl、独立审查者source_catalog_review，主代理负责集成验收和部署。实现者266项Python/475项UI及类型/lint/build/dist通过；主代理精确干净Head的72项UI、113项Python集成、29项静态资产和7文件重建一致性通过，独立完整差异审查NO BLOCKERS。

8765已从上述CodeHead干净树`D:\codex-tmp\sc1019\review`通过原project/data/session公开open更新，当前PID10792、exec33017，运维卡`D:\codex-tmp\sc1019\service.json`；旧PID17680已正常停止。版本保持1.1.2，无远端动作。浏览器、实际认证HTTP、关闭重开及新硬件验证仍由用户暂缓；当前21/21编译单元只读AST证据不构成实机采样PASS，历史样本保留原身份。

本轮复用reducer/controller既有合同，数值固定在波形上方；按selectedSeries决定波形是否占位；仅设备抽屉自己的写入ACK成功并经reducer采用才自动返回。共享App/CSS风险由最终UI unit/a11y、两项类型检查、lint、build和dist一致性覆盖；主代理在精确CodeHead干净树进行精选集成和完整差异审查。上一轮CodeHead `8649c494721e8cb631c84855a204dc271e09df00`的438项既有全量及主代理34项UI/29项静态测试证据见[既有验收](../codex/returns/MONITOR-WORKBENCH-REFACTOR/review.md)，不替代本轮受影响验证。服务验收只核对源码、资源和OS进程监听，浏览器及新版硬件仍DEFERRED。

先前数值优先CodeHead `543741b2d42c2e51ddcc8ae41b3b3100ea5eaad3`的证据见[数值优先验收](../codex/returns/MONITOR-VALUES-FIRST/review.md)，探针反馈CodeHead `838b5bcd5dd55d5c87f79478d0a2a1b17b3e5c60`见[探针反馈验收](../codex/returns/MONITOR-PROBE-FEEDBACK/review.md)。它们已在本地集成并由最终回归覆盖，旧部署卡仅为历史记录，不再代表当前监听。

成功反馈只由本次有效且经reducer采用的写入ACK触发；实际用户HTTP响应仍未观察，不能据软件修复声称原现场根因已被证实。部分目录、身份/代次失效、取消及Windows自有编译器子树的回收均已有回归；清理临时目录被自动策略拒绝的精确清单见最终报告，未重试或绕过。

先记录实际工作树、分支、完整 accepted base/CodeHead、设计/实现/审查者、部署 source、project/data/runtime 路径、授权、有效证据和剩余场景。检查 tracked/untracked、已提交/未提交、已推送/未推送状态；保留无关改动。使用精确 CodeHead 的干净隔离工作树审查完整差异。

状态含义：PASS 为证据满足条款；READY 为前置成立但未执行；PENDING 为尚缺结果；BLOCKED 为已知前置缺口；TERMINAL_STOPPED 为本次执行结束。REUSED 必须附原证据及适用性；N/A 不能代替缺失、失败或不可用硬件。文档变化本身不触发重测；相关产品字节、环境、依赖或身份变更只使对应证据需要重新核对。

## 2. 离线环境与执行卡

Windows 使用已核实的 PowerShell、解释器与工作目录。每次运行把 TEMP、TMP、TMPDIR 一起指向本轮短目录，显式指定 pytest basetemp、缓存、构建及日志路径；默认根为 `D:\codex-tmp`。CPython 会优先读 TMPDIR。不同进程/代理不共享可变 basetemp，禁止写回借用的环境或共享缓存。

从被测仓库根运行，PYTHONPATH 显式指向同一工作树源码。Fault 的 DWARF fixture 有仓库根相对路径；先核对入口和 fixtures。预检含 64 字符 plan ID 的 configuration-staging 最终路径长度，长路径错误先分类 ENVIRONMENT，不直接修改生成器。记录完整 argv、退出码和 stdout/stderr。

任何 Python 进程包装的 CLI/进程创建须放在 `if __name__ == "__main__":` 中；实机前用真实 Windows spawn 入口和纯软件 child 验证导入不会重入。优先用既有入口；新增捕获包装须说明证据缺口并先离线审查。若按命令行片段检查进程，避免把父 PowerShell 自身误判为 backend；只读核对 PID、可执行路径、父子关系与阶段，不杀无关进程。

实机前在 run 目录保存一张普通 Markdown/JSON 执行卡，无需新框架：

| 项目 | 执行前必须确定 |
| --- | --- |
| 场景 | 规格条款、所需新证据、可复用 PASS |
| 版本与路径 | source/runtime/build/ELF 身份，project/data/output 绝对路径 |
| 身份 | workspace/session/input snapshot/Git/probe/target/receipt 来源及相等条件 |
| 状态与所有权 | 最近证实的 target 状态和时间，Toolkit/IDE lease/ticket owner |
| 入口 | 实际 argv、状态前置、连接/执行副作用、返回字段、源码函数依据 |
| 授权与预算 | 当前授权范围，新 action 来源，固定次数/时长/超时，允许的控制操作 |
| 成功与停止 | 成功证据、下一步条件、首错停止、既有 cleanup 终态证明 |
| 留证 | 原 code/details/cause、最后阶段、动作消费、TestRun/receipt/lease 保存位置 |

缺关键项不标 READY。先用源码、既有纯校验或 CLI parser 离线核对，不调用 backend。一次授权可覆盖明确连续步骤；终态失败后的重试、恢复或扩展范围另核对授权。Target execute 自身要求 probe-id，不能因 prepare 已指定而省略；动态 digest 只来自本次真实返回。

SVD 场景在首次硬件操作前以实际 project/target/device、完整 SVD 和 readableRegions 复用 select_svd 做语义预检。整个选定文件的每个寄存器都必须在可信区域内，单点 Watch 合法或文件 hash 相等不代表整个选择合法。配置变化后重做相关检查。

迁移工程重新构建前核对 CMakeCache 的 CMAKE_HOME_DIRECTORY/CMAKE_CACHEFILE_DIR。旧路径缓存须先留证、核实生成物归属与 reparse 边界，再移入本轮证据目录并使用当前构建入口；不复活退役工程，不因此重烧已有有效固件。

原始异常必须在首次获准执行前具备留证路径。details.programDiagnostic 仅说明对应编程阶段，program-call 不证明已经擦除/写入。按当前源码检查 backend、IPC、外层映射是否保留所需字段；若 prepare/attach 信息会丢失，先离线验证最小捕获边界，不能失败后自动重连补日志。

## 3. 状态和所有权

按被测版本的函数重新核对，不复用旧部署的行号或机器路径。

| 入口 | 前置和结果边界 |
| --- | --- |
| 正常 Target prepare | OBSERVE 连接，可能短暂停核，再恢复并验证 running；授权持久化前的失败不能视作可 execute |
| 正常 Target execute | 使用匹配的新 MODIFY action；flash/readback 后按既有流程 reset、必要 resume、启动 transport；须有真实 TestRun |
| Target recovery-under-reset | prepare 只做静态检查；execute 从该新 action 派生 100kHz SWD/under-reset MODIFY，先核对真实身份；sector erase、keepUnwritten=true、auto_unlock=false，保留既有 readback/reset/条件 resume/transport/cleanup |
| 普通 flash / recovery flash | 与 Target 测试流程不同；成功编程或 receipt 不证明运行态。恢复烧录保持既有 halted 后置，不擅自 reset/run |
| 变量/SVD/有限采样 | memory.read 不要求 halted；OBSERVE attach 的瞬时停核与后续持续采样分别留证，采样不得隐式 halt/reset/resume |
| 完整 Fault | 核心寄存器必须 halted 且稳定；默认 running OBSERVE 不能满足该前置。显式 halt-for-analysis 使用受控 CONTROL、独立授权、身份校验及 bounded resume/cleanup |
| IDE handoff | begin 后 IDE 独占；正常 detach、原 ticket end 和成功回收后 Toolkit 才能访问 |

受控 Fault 最多执行既有一个 halt 和一次恢复 resume，不 reset/flash/reattach/retry，未知身份不猜测恢复。核对当前 controlledSnapshot 字段及原45秒恢复总预算和 RPC/cleanup 预算，不能套用无关外层超时。完整 Fault 与不停核采样是不同证据。

provenance 拒绝须逐字段记录预期/实际及来源。相同 ELF 不等于相同 build/input/session/probe；相同文件字节不保证相同文件身份。不得改 pin、hash 或复活已消费记录。灯态、单点寄存器值和 CPU 活性分别记录，不相互替代。

## 4. 执行顺序与接口核对

1. 完成离线执行卡、相关软件检查和原始异常留证准备。只有实际需要且获准才部署候选；在最终 runtime 路径验证版本、manifest 和入口字节。
2. 如需正常 Target，执行一次 prepare → 身份/digest 校验 → execute → public show。核对 physical 来源、断言/mailbox、flash/build/run 绑定和 cleanup；不因下一场景重烧已接受固件。
3. 运行观测绑定当前 receipt，固定时间/样本预算。count 是 scheduled slots，不保证 delivered values；首读可耗秒级。按有效值、身份、丢失和窗口判定，未观测到就记录未证实，不循环补采至通过。
4. IDE 场景先完成[部署与 IDE 前置核对](windows-deployment-and-ide-preflight.md)：真实 UI、扩展版本/profile、最终 pyocd.exe、target/pack、实际 ELF 与外置 workspace 均可用，再 begin → 原样使用本次配置 → attach/观察/正常 detach → 原 ticket end → 同绑定 Toolkit/MCP read。
5. 物理失败—修复场景须先具备 Target、两侧 Monitor 采集、发布、Analysis/Diagnostic 与恢复授权的完整数据流，再执行下一节。只存在 publish 命令不等于具备采集入口。
6. 记录各结论、身份及证据、lease 释放和 worker 退出。收尾不隐式访问板卡；缺失的合同或 lineage 仍保留为阻塞。

命令按安装版本的子命令 help 和 parser 核对，不从邻近命令猜参数。Target/read/debug/diagnose/scenario 显式绑定 project/data/session；build 按自身入口。保存完整响应后提取标量，Target nativeRunID、evidence ID、artifact 引用不能混用。MCP 也必须绑定同一身份。

IDE 使用 run-owned 外置 workspace，不为验收修改工程的 .vscode 而改变构建身份。核对 CortexDebugLaunch schema/profile 与真实扩展/PyOCD 版本，再原样包装 configuration；保持绝对 cwd、真实 target、UID、ELF、就绪正则与 attach 语义。canonical cortexDebug 身份信息及内部 companion 仍保存并校验 boardId。未知版本不得猜兼容参数或让 PyOCD 自动选 probe。最终 runtime 的 pyocd.exe --version 必须通过，模块 import 不替代 console entry 检查。

## 5. 物理失败、诊断、修复和续验

正常路径在共同 EvidenceIdentity.session 下完成 failed-before TestRun、Diagnostic、受授权源码变更、fixed-after TestRun 和两侧物理 Monitor window；action、lease 和操作 ID 各自新鲜。两侧 window 均须 publish 并重新读取后才能成为后续引用。不同操作的 lease 不可复制来消除不匹配。

| 顺序 | 必要合同 |
| --- | --- |
| 建立场景 | 新 attempt ID 和对应 scenario/version；project-materialized、firmware-built-before 使用真实身份 |
| 失败前 | 仅预期行为断言失败可作为 failed-before；基础设施/身份/超时错误不能冒充预期失败 |
| 诊断与采集 | Diagnostic 明确 failed-run-mode=target；P3 仍运行时采集、发布 failed-before，切换 P4 后不能补采 P3 |
| 变更授权 | diagnosis-completed → resume → 当前 revision/actionDigest → authorize-source-change；planned intent 本身不是授权 |
| 修复后 | 仅修改获准范围；完整 after InputSnapshot 等于 intent 派生值；声明变更、构建、新 Target action、同身份成功 TestRun |
| 比较与完成 | 发布 fixed-after；compare/bundle 绑定两侧引用、TestRun、declaration、Diagnostic；真实 marker、VerificationPlan、FixVerification 和最后 checkpoint 完成链路 |

原始 session 不同只能用已实现的显式 physical continuation proof 关联，不能重命名记录。bind 验证 predecessor attempt/checkpoint/evidence、真实 fixed-after TestRun/evidence、Diagnostic revision/event head 和源变更祖先链，产生不可变证明和 v3 attempt；新进程 show 复核。证明授予零源码/硬件权限。compare/bundle 与 VerificationPlan/2 显式携带同一 continuation evidence；缺证明时原同 session 规则仍有效。900秒 continuation attempt 过期可按公共 reuse 入口创建新 attempt，不续期旧对象、不重复消费 action、不重烧补账本。

Attempt revision 与 Diagnostic revision 分属不同对象。Physical TestRun 必须核对 execution_source=physical、physical_transport_evidence、完整 build/ELF/input/session/probe/target 和 transport_config_digest。source-change declare 消费已有完整 declaration，不生成 diff evidence；diff artifact 来自两次真实源码间获准范围，before identity 来自真实 TestRun envelope，source SHA 是完整 InputSnapshot，不是单文件 hash。最小 run-local 包装须先审查，不借用测试合成 identity。

Monitor physical publish 的 probe-id 取 history.binding.probeId 原始 selector，离线核对其 hash 与 TestRun 绑定，不能把已哈希的公开引用再传入。两侧窗口必须保留原始时间/sequence边界，不伪造对齐。发布不产生采样。request、source-change 和 publication 使用既有 canonical_replay_json_bytes；完整响应另存，publication 从文件重新解析。compare OK 之后仍要检查 quality=VALID、conclusion=COMPLETED 和所需 changed。

寄存器分析使用显式 request/2 的 selector_kind=register、alignment=bounded-run-relative、scalar_policy=native-uint-register/1 和已批准 max_pairing_skew_ns；不得为通过降低有效配对数、改时间或重采同一充分窗口。result/3 内嵌完整 request，持久化后重新读取计算验证。VerificationPlan ID 等于 declaration.validation_plan_id，绑定真实两侧 run/evidence、analysis、declaration；Target native ID 与 Monitor operation ID 不混用。软件副本验证不能自动完成原业务账本。

板卡引脚、电平、采样频率和批次数只来自对应具体 fixture 规格与现场卡；旧 D3/D4 场景不是所有 STM32 的默认定义。需要重现旧资格场景时从 Git 历史取其原始规格和报告，保留其原身份、阈值与限制，不把历史授权带入本轮。

## 6. 首错停止与清理

任何非预期枚举/attach/状态/身份/烧录/读取/发布/清理错误都停止后续硬件和 action 消费。保存原异常链、最后成功阶段、动作消费和实际产物，执行原入口已有 cleanup。内部 cleanup 与外部重新调用硬件分开；未证实释放即未知/阻塞，发送 terminate 不算 worker 已退出。

先分类 PRODUCT、INFRASTRUCTURE、ENVIRONMENT、PLATFORM、HARDWARE、REPORT；不凭错误码或灯态猜原因。先离线定位，再由实现者修复并独立审查。补硬件证据须具名假设、一次操作边界、成功标准、失败停止及新授权；不自动重试、切 under-reset、reset/halt/resume、解锁、断电或换板。

只有参数/状态/所有权/身份/错误/cleanup合同或验收要求改变才修改本流程并先独立审查受影响条目。只改路径、HEAD、session 或结果则更新执行卡；排版和链接修正不触发测试。一个场景 BLOCKED 时继续独立且已授权的工作，不能因此宣称全体验收。

每次运行后清理归属明确且不再需要的一次性输出。解析绝对路径并确认位于本轮根内，使用同一 PowerShell 的原生文件操作；保留源测试、可复用 fixture、用户数据、共享缓存、rollback、有效证据及最小失败材料。被自动策略拒绝时记录路径及原因，不换工具绕过。当前代码接受与目录清理由执行账本记录。
