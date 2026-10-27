# STM32 Toolkit 标准测试流程

本文件是离线验证、部署与实机验收的执行入口。规格定义要求，源码定义实际入口合同，本文件规定执行顺序，报告记录事实。冲突须先离线解决，不在硬件操作中猜测。主代理维护本流程、调度和验收；实现和新增测试由本地 Claude Code CLI 按其现有配置负责，作者不能自行接受差异。本文不授予安装、硬件或远端权限。

## 1. 当前断点与证据

2026-10-27 最新本地断点：GCC-DELIVERY-INTEGRATION 在 `2d24028258c310afdfe76823e35ece48937880c8` 已 **ACCEPTED_WITH_FIXES（离线集成范围）**，见[执行与独立复核记录](../codex/returns/GCC-DELIVERY-INTEGRATION/implementation-report.md)。无 Git 的 Keil 独立交付和新建 GCC 工程两条完整流程，Claude 与主代理在最终提交各自14/14通过，包含真实 GCC 构建、输出目录独立搬移、正常受管模拟烧录/读回和清理。集成发现并修复新建工程缓存仍引用暂存路径及首次锁初始化竞态；创建138+1平台跳过、重新生成132+1、创建接口151均复核。受影响矩阵去重2,322通过/3平台跳过，明确包含未变源码证据复用，并非最终提交全仓库重跑或发行覆盖率验收。用户确认无离线厂商包：仅外部 CubeMX 生成采用合成适配器，其余核心流程为实际实现；真实厂商生成、安装/VS Code和硬件不记PASS。M3b2准备副本/引导及跨分支离线集成已关闭；原工程、运行时、全局配置、硬件未改，未改版本、未推送或发布。以下为历史断点。

2026-10-26 最新本地断点：RETEST-GUIDANCE 在 `9d8b06427cd237309c5f3061316b37ebc0a73d06` 已 **ACCEPTED_WITH_FIXES**，见[执行与独立复核记录](../codex/returns/RETEST-GUIDANCE/implementation-report.md)。Claude 完整相关组317/317、主代理独立23/23通过，重叠证据不相加。用户报告已安装v1.3.2并完成复验；本轮仅只读复核其外部测试副本，178文件哈希未变。7项编码依赖及1项缺少汇编返回的阻断仍保留，现提供准确处置指引，不宣称迁移无阻断或语义等价。CLI JSON编码缺陷已修复。此补丁仅本地源码，未安装、构建发布或推送；原工程、硬件和全局设置未改。后续新包的实际安装/VS Code验证仍由用户负责，旧发布例外不转移。以下为历史断点。

2026-10-26 v1.3.2 最新发布断点：[发布与公网核验记录](../codex/returns/STM32TK-132/publication-2026-10-26.md)。Release `423877513` 于 `2026-10-26T05:10:19Z` 公开并设为Latest，`draft=false/prerelease=false`；标签与target绑定冻结源码 `acb71b9f39e8ae4799179b0cab088245c0a5ea5b`。13附件匿名下载全部HTTP200、实际长度与SHA-256匹配双构建冻结包。仅本候选的 USER_APPROVED_EXCEPTION 已获明确批准并在Release公开，覆盖率/跳过/复用限制及永久门槛保持原义。最终实际安装和VS Code仍由用户执行，USER_VALIDATION_PENDING；未改原工程、既有runtime、全局设置或硬件。冻结包文档保留构建时状态，后续master文档和本记录说明实际发布。以下为历史断点。

2026-10-26 v1.3.2 发布授权断点：用户明确批准仅对冻结 `acb71b9f39e8ae4799179b0cab088245c0a5ea5b` 的既有13文件候选接受披露限制并发布Latest，见[授权记录](../codex/returns/STM32TK-132/authorization-2026-10-26.md)。资格处置为 USER_APPROVED_EXCEPTION，永久门槛未改、未达标数值不变为PASS。下一步非强推源码/标签、上传核验13文件、发布并匿名复核；最终实际安装/VS Code仍由用户负责，USER_VALIDATION_PENDING，不改原工程、不操作硬件。以下为历史断点。

2026-10-26 v1.3.2 冻结包断点：[候选核验记录](../codex/returns/STM32TK-132/candidate-build.md)。源码 `acb71b9f39e8ae4799179b0cab088245c0a5ea5b` 已完成两个独立干净树官方构建，13文件逐一同hash，安全解压后官方bundle验证退出0。Windows ZIP为113,770,074字节、SHA-256 `1773a5e6b61a882bbd3d77a2a23902bd24f88ed296fb6e12dfccc03594c77f79`。冻结源码相对测试head仅新增治理文档；覆盖率、平台跳过与明确复用的限制未改变，等待仅对此候选的资格处置，不自动沿用v1.3.1例外。尚未推送或发布v1.3.2；最终实际安装/VS Code由用户负责，原工程和硬件不操作。以下为历史断点。

2026-10-26 v1.3.2 当前断点：诊断与版本对齐软件在 `c1985337bb1b74eab38deb12509ace22f191ab07` 独立审核为 **ACCEPTED_WITH_FIXES**，见[执行与复核记录](../codex/returns/STM32TK-132/version-review.md)。版本相关完整分组746通过/1平台跳过，setup隔离夹具45通过，Monitor受影响完整组288通过；独立76项及前期837项等重叠证据单列，不相加冒充全量。原失败和未完成Monitor运行保留，修正后相关组重跑通过。原生分支数据仅按完全匹配源码复用，变更文件旧弧已移除；Toolkit总体/风险87.3028%/87.5015%、Monitor风险92.2527%，永久门槛未满足，发行仍 **NOT_QUALIFIED**。下一步冻结源码、双构建并核验13文件，再对具体候选处理例外；旧v1.3.1批准不自动沿用。最终安装/VS Code继续由用户负责，USER_VALIDATION_PENDING，不改原工程、既有runtime、全局设置或硬件。GitHub Latest仍为v1.3.1，以下为历史断点。

2026-10-26 最新发布：[v1.3.1 已公开发布为 Latest](../codex/returns/STM32TK-131/publication-2026-10-26.md)。用户明确要求先发布，再自行独立测试。Release 423752112 的版本页和 Latest API 均返回 `draft=false`、`prerelease=false`，标签/target 为冻结源码 `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`。13 个附件匿名下载均为 HTTP200，大小与 SHA-256 全部匹配冻结构建。最终安装/VS Code 验证仍由用户负责并记 USER_VALIDATION_PENDING；保留原批准限制，不转换成 PASS，不操作原工程或硬件。主代理本轮优化、构建和发布交付已完成，以下为历史断点。

2026-10-26 最新远端交付：[GitHub 交付记录](../codex/returns/STM32TK-131/github-delivery-2026-10-26.md)。本机 Git Credential Manager 登录复核通过，按用户明确授权以非强推方式将 `master` 推送至 `a1bb1908fb1fa992cc3e9f6b9bb802b309157d78`；`v1.3.1` 标签指向冻结构建源码 `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`，远端身份已核对。Release 草稿423752112已创建，未公开发布为Latest。最终实际安装与VS Code实测由用户负责，仍为 USER_VALIDATION_PENDING；不重新启动自动IDE验证，不操作原工程或硬件。后续文档提交只记录交付，不改变冻结包。以下为历史断点。

2026-10-26 最新交接：[授权与隔离安装记录](../codex/returns/STM32TK-131/authorization-2026-10-26.md)。用户已批准既有 PowerShell7 和仅针对冻结 `7ff99e50011b6321ae3f0c9bb2edfab91724be3e` 的已披露限制例外。该候选在 `D:/codex-tmp/r131/ide-data` 完成 Check → Bootstrap → Check，均退出0，最终 healthy/matching、1.3.1、generation1。用户随后接手最终实际安装与 VS Code 验证，状态为 USER_VALIDATION_PENDING，不记 PASS；主代理停止 IDE 自动验证，按本次明确授权处理 GitHub 推送。升级/回滚无新通过记录。Git Credential Manager 账户仍为空，等待该客户端登录；未推送、未发布，不触碰原工程或硬件。以下为历史断点。

2026-10-26 最新发行候选：[同源双构建记录](../codex/returns/STM32TK-131/candidate-build.md)。冻结源码 `7ff99e50011b6321ae3f0c9bb2edfab91724be3e` 的13文件逐一同hash，独立官方bundle验证通过，尚未发布。后续获准安装须使用 `D:/codex-tmp/r131/frozen-bundle/stm32-toolkit-1.3.1` 及新的运行日志，不得复用旧候选路径或误选PowerShell5.1的历史setup helper。安装解释器修正、本机Git登录仍待既有问题回复；数值门槛、实际安装/升级/回滚与VS Code资格未完成。当前8,838通过/19跳过是源绑定复用，不是最终单一提交全量重跑。不得因旧例外或时间经过自动发布、切换解释器重试或触碰硬件。以下保留历史断点。

2026-10-26 此前复核：ARMCC-DIRECTIVE-PREFIX 已 **ACCEPTED_WITH_FIXES**，见[报告](../codex/returns/ARMCC-DIRECTIVE-PREFIX/implementation-report.md)。CodeHead `0ddfa8c92d6c0296ff6f34334fb99c7ba10dcb2e`；Claude 新增42/42、主代理203/203、受影响完整文件回归898/898通过。旧源码分支数据已从新聚合副本移除，再采纳当前原生数据；原始数据保留。当前去重复用队列8,838通过/19跳过，数值门槛仍未满足；不是最终单一提交全量重跑。下一步冻结源码并完成候选双构建，安装解释器修正及本机Git登录仍待原问题回复；实际VS Code、安装和发布未完成。以下为历史断点。

2026-10-26 此前补测：RECOVERY-AUTHORITY-REGRESSION 已 **ACCEPTED_WITH_FIXES**，见[报告](../codex/returns/RECOVERY-AUTHORITY-REGRESSION/implementation-report.md)。CodeHead `1b2696ff768c5880cc6bdae232d7093f5f1be0ac`；最终 Claude 新增22/22、主代理140/140；310项未变相关通过结果明确复用。首轮双方各12个JSON比较夹具失败及后台通知后禁用Read拒绝均保留，失败运行覆盖率数据未导入。新增12个Toolkit分支；当前队列8,796通过/19跳过，Toolkit总体/风险87.4814%/87.6166%，Monitor风险92.2527%，永久门槛未满足。ARMCC注释前缀指令问题正独立复现；安装解释器修正、本机Git登录待原问题回复，实际VS Code、最终双构建及发布仍未完成。不是最终单一提交全量重跑，不授予硬件资格。以下为历史断点。

2026-10-26 此前补测：DIAGNOSTIC-INTEGRITY-REGRESSION 已 **ACCEPTED_WITH_FIXES**，见[报告](../codex/returns/DIAGNOSTIC-INTEGRITY-REGRESSION/implementation-report.md)。CodeHead `83365c700baa9fe79ba6784efbac87365c93cfda`；Claude 226 通过/1 个原有 WinError 1314 符号链接能力跳过，主代理独立 25/25，新增 24 项及 7 个 Toolkit 分支。全部新增用例与原生 Windows 锁测试执行通过，既有跳过明确留待主代理负责的具备符号链接能力的最终资格环境。当前去重复用队列 8,774 通过/19 跳过；Toolkit 总体/风险 87.4129%/87.5430%，Monitor 风险 92.2527%，永久门槛仍未满足。继续恢复流程完整性复核；安装解释器修正、本机 Git 登录仍待用户响应，实际 VS Code、最终包及发布未完成。不是最终单一提交全量重跑。以下为历史断点。

2026-10-26 此前补测：MONITOR-INTEGRITY-REGRESSION 已 **ACCEPTED_WITH_FIXES**，见[报告](../codex/returns/MONITOR-INTEGRITY-REGRESSION/implementation-report.md)。CodeHead `0be59bf039747ac6ba9b1effc6fe454261588bbb`；最终 Claude 494/494、主代理独立 109/109，新增 21 项及 24 个 Monitor 风险分支。首轮双方各两项新夹具失败均保留，修正 SourceIndex truncated 参数与真实 SQLite WAL 准备后完整相关组复跑通过。当前去重复用队列 8,750 通过/19 跳过；Toolkit 总体/风险 87.3729%/87.5000%，Monitor 风险 92.2527%，永久门槛仍未满足。继续诊断完整性补测；安装解释器修正、本机 Git 登录待用户响应，实际 VS Code、最终包及发布未完成。不代表最终单一提交全量重跑或硬件资格。以下为历史断点。

2026-10-26 此前补测：FIRMWARE-INTEGRITY-REGRESSION 离线测试切片已 **ACCEPTED**，见[报告](../codex/returns/FIRMWARE-INTEGRITY-REGRESSION/implementation-report.md)。CodeHead `25b29d2e71009c1de7b45cc5fbd00b72a419a98f`；Claude 50/50、主代理独立 24/24，新增 14 项与 23 个 Toolkit 分支。当前去重复用队列 8,729 通过/19 跳过；Toolkit 总体 87.3729%、风险核心 87.5000%，Monitor 风险核心仍 91.5666%，永久门槛未满足。不是最终单一提交全量重跑。继续 Monitor 完整性测试；安装解释器修正与本地 Git 登录仍待用户响应，实际 VS Code、最终包及发布未完成。首次误调禁用 Bash 已停止且无编辑；新文件会话与原生 PowerShell 执行分开留证。以下是历史断点。

2026-10-26 此前补测：MIGRATION-BOUNDARY-REGRESSION 离线测试切片已 **ACCEPTED**，见[报告](../codex/returns/MIGRATION-BOUNDARY-REGRESSION/implementation-report.md)。CodeHead `d30b20ca7592ba433a88f7bfda6fb06ecc98caab`；Claude 相关完整组 264/264、主代理独立 81/81，新增 60 项及 51 个 Toolkit 分支。当前去重复用队列 8,715 通过/19 跳过；Toolkit 总体 87.2415%、风险核心 87.3589%，Monitor 风险核心仍 91.5666%，永久门槛仍未满足。不是最终单一提交全量重跑。继续外部固件完整性测试；安装解释器修正与本地 Git 登录待用户响应，实际 VS Code、最终包及发布未完成。以下集成记录保留补测前状态。

2026-10-26 v1.3.1 集成断点：源码优化与版本对齐已完成，**发行仍为 REVISION_REQUIRED / NOT_QUALIFIED**。见[当前报告](../codex/returns/STM32TK-131/implementation-report.md)、[独立复核](../codex/returns/STM32TK-131/review.md)及[机器可读证据](../codex/returns/STM32TK-131/evidence.json)。Python 完整收集 8,674 项；经过保留原失败的完整组修正与明确复用，当前 8,655 通过、19 平台/外部数据跳过，不宣称最终单一提交全量重跑。Toolkit 总体/风险核心覆盖率 86.9501%/87.0459%，Monitor 风险核心 91.5666%，均未达到各自永久门槛。先复核有意义的离线测试缺口，不自动沿用旧版例外。

UI 526 通过、1 可选外部数据跳过，各文件分支门槛通过；实际 Edge 44/44 与两组原预算性能测试通过。13 文件验证候选通过哈希和官方 bundle 验证，但最终同源可重复构建、实际隔离安装/升级/回滚及 VS Code/MCP 仍待完成。初次误选 Windows PowerShell 5.1 的 Check 被执行策略拒绝，未执行安装；更正为现有 PowerShell 7 的请求与本地 Git 登录仍待用户响应，不能改策略或换工具绕过。原工程、硬件、既有 runtime/全局 Skill 和远端未改。以下各条是保留的历史断点；其中“下一步”只描述当时状态。

2026-10-25 DIAGNOSTIC-TAIL 指引/测试切片已 **ACCEPTED_WITH_FIXES**，见[独立复核](../codex/returns/DIAGNOSTIC-TAIL/review.md)。Accepted base `99c93ccfb63b104aeb58ce23f8a78b9d98ddb932`，CodeHead `712bd1721b10618b174b5ea35aef7c3407f48a4b`。双方各82通过/1真实文件符号链接平台跳过，最终32项通过；四个Skill结构通过。新AI消费复测已纠正构建默认超时的重复授权及preflight/PLAN字段混用，保留既有原始日志；不是实际IDE验收。旧1.3.0可用字段的概括性描述须在紧接的统一1.3.1版本对齐中按冻结源码澄清，不把它当MCP过期证据。下一步为完整回归/覆盖率、实际VS Code、构建与发布；原工程及硬件未操作。

2026-10-25 MEMORY-MARGIN 离线切片已 **ACCEPTED_WITH_FIXES**，见[独立验收](../codex/returns/MEMORY-MARGIN/review.md)。Accepted base `1b16a38181770569cf1d0f533a73e94690231a32`，CodeHead `9a7a8a5f00a9c19333fffc6201ca2515310bb39c`。Claude Code CLI 编码与测试，主代理完整独立审查；双方各562个不同用例有通过证据（按未变产品/测试复用部分首轮通过结果），最终作者232/233后单项LF夹具复核通过、主代理64/64，另主代理169/169相关回归通过。首轮PT_LOAD夹具及作者工作树LF/CRLF差异已修正验证，原失败保留，不宣称最终全量矩阵。每个已声明区域按 free<1024 或 free*20<length 给出非阻断告警，identity可选摘要参与hash并在当前固件准入重算；静态空闲不证明连续可用空间、运行期峰值或外部内存初始化。原工程/硬件/runtime/版本/远端未操作；诊断尾项、整体回归与实际VS Code及v1.3.1构建发行继续由主代理负责。

2026-10-25 FLASH-FREQUENCY 离线切片已 **ACCEPTED_WITH_FIXES**，见[独立验收记录](../codex/returns/FLASH-FREQUENCY/review.md)。Accepted base 449c30e056f614d1ecc9a4340c0ea5feda28f07b，最终 CodeHead 4cd1baf11a028438a69bf1cf74b91833731b13ed，产品/指引测试head a8095f03e9a8a5fa1d9dddf51075a6ac02e932f5。Claude Code CLI 编码与测试，主代理在独立干净树完整审查。双方各424项核心通过；相关386项回归中385项通过、1项旧多RAM夹具缺layout在接受基线同样失败。仅补齐该夹具7行显式布局，双方最终定向1项通过；424+385未变用例复用，共810个不同通过用例（含95项新增），未宣称最终全量矩阵重跑。频率CLI/MCP入口、执行前冲突拒绝、完整结果字段、受管条件恢复建议及单次调用/无自动重试均接受；Skill结构与新AI消费模拟通过。流程新增条目经独立只读复核。13处本轮临时目录清理被自动策略拒绝（blocked by policy），保留且未绕过。原工程、硬件、runtime/全局技能、版本及远端未操作，真实IDE/频率/复位接线资格留待主代理负责的后续授权集成，不授予发行资格。

2026-10-25 DOCTOR-READINESS 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/DOCTOR-READINESS/review.md)。Accepted base `8737aaea950d2eec7f79c44b7b95bf07ca0ab471`，最终 CodeHead `353ab42f60324a1fb94ff8daf8875f80d138ce48`。Claude Code CLI 编码/测试，主代理在独立干净工作树完整审查；最终双方各304项核心通过、1项真实目录符号链接因主机能力延至主代理负责的集成/发行环境，另97项创建回归按未变共享代码/测试复用，共401个不同通过用例。实际只读观察本机默认profile得到cpptools 1.34.4、cmake-tools 1.24.42、cortex-debug 1.12.1；PATH/限定默认目录未找到UV4/ARMCC，不证明任意位置未安装或原生构建可用。完整/未知/缺失诊断、声明来源、严格CLI/MCP参数及根先验已验证；真实IDE/调试仍待验收。官方语言包长版本格式的实测问题已修正并回归。10处临时目录清理被自动策略拒绝（blocked by policy），已保留且未绕过。原工程、硬件、runtime、全局技能、版本与远端未改，不授予发行资格。

2026-10-25 VSCODE-TASKS 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/VSCODE-TASKS/review.md)。Accepted base `e7614e49ba384117770ff8b01f57489da8676223`，最终测试 CodeHead `4c79ef53111408ae2f5071f6edb52cbadb8363fb`。Claude Code CLI 编码/测试，主代理在独立干净工作树完整审查。双方首轮各469项（461通过/7失败/1平台跳过）；修正后各483项（482通过/0失败/1跳过）与539项相关回归通过，随后各51项任务/指引及最终13项绑定/指引复核通过。合并未变执行代码的复用证据，1022个不同用例通过、1个真实文件符号链接用例延至主代理负责的具备能力的Windows/Linux集成/发行环境，不宣称最终全量矩阵重跑。新增显式可执行路径绑定、五个独立process任务和窄CLI适配器；完整当前固件准入、默认deny、原ticket/会话/探针绑定、既有end失效拒绝及managed/imported分流不放宽。真实VS Code/扩展/IntelliSense/handoff UI仍待集成验收。14处已核对临时目录清理被自动策略拒绝（blocked by policy），未删除或绕过，含reparse的4处夹具及失败材料另保留。产品仍1.3.0；原工程、硬件、runtime/全局技能、冻结包和远端未操作，不授予发行资格。后续IDE/硬件仍按下方既有流程与实际授权执行。

2026-10-25 BUILD-STALE-GUIDANCE 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/BUILD-STALE-GUIDANCE/review.md)。Accepted base `fefa21fe14de1a3710799e9cf39f33f3a41815d0`，最终测试 CodeHead `eb7bacb705b812e217998e063f8db5fb88725feb`。Claude Code CLI 编码/测试，主代理在独立干净工作树完整审查。双方首轮各242项（230通过/12测试缺陷失败），修正后各51项（50通过/1过时文字断言失败），最终各13项通过、0失败/跳过；243个不同用例有通过证据，最终230项按未变产品字节和未受影响用例复用，不宣称全量最终矩阵。BUILD_OUTPUT_STALE 增加首个失配原因、固定字段及按实际 preset/clean/timeout 的条件重建建议；CLI 明确绝对 project-root 绑定，缺绑定拒绝和参数回放通过；既有准入、不可变响应、收据及受管漂移保护不变。Skill/VS Code 指引与清理范围、失败路径字段模拟复核通过。初次文件任务误调禁用 Bash echo no，未执行但未按要求立即停止，主代理在完整日志核对发现后保留并使用新纯文件会话修正；实际测试单独使用原生 PowerShell，未扩大权限。本轮8处临时目录清理被自动策略拒绝（blocked by policy），未删除或绕过。产品仍1.3.0；原工程、硬件、runtime/全局技能、冻结包和远端未操作，不授予发行资格。

2026-10-25 ARMCC-FLOAT-ABI 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/ARMCC-FLOAT-ABI/review.md)。Accepted base `386d63bc2fc5c633c1296c87601ae188cf09ebfd`，测试 CodeHead `1bf7a7a3b44538a13d826e1790d15bde2bf15532`。Claude Code CLI 编码/编写测试，主代理在独立干净工作树完整审查；最终双方各672项通过、0失败/跳过，其中32项新增ABI用例。另311项共享夹具调用方回归通过，按产品与相关测试字节不变复用，共983个不同通过用例；不宣称最终全仓库/发行矩阵重跑。首轮双方各671通过/1失败，原因是新测试把uvprojx文件当成目录传入，修正两处`.parent`后复核；不是环境缺失，不放宽产品校验。删除无依据的数字uFloatingPoint→ABI映射，保留有条件、明确未验证的ARMCC/M4/FPU2 hard推断；捕获RvdsVP并阻断不支持的选择器，preflight/PLAN/report共享且绑定ABI证据，baselineVerified恒false。原工程仅只读核对配置，SHA前后相同，无AXF/MAP基线证明；未构建原工程或操作硬件。指引模拟发现并修正“有blocker不能生成任何PLAN”的误读，明确可返回带blocker的诊断PLAN但不可APPLY，复测和Skill结构校验通过。报告阶段仅指引澄清，无代码/测试变化。初次文件任务误用未开放Bash已停止、未执行shell；日志与两次65-turn续作留证。清理本轮测试临时目录被自动审批策略拒绝，仅返回blocked by policy，保留且未绕过。产品仍1.3.0；runtime/全局技能/冻结包/远端未改，不授予发行或硬件资格。

2026-10-25 COMMENT-REVIEWED-REPLACEMENT 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/COMMENT-REVIEWED-REPLACEMENT/review.md)。Accepted base `3cd5eea7ccfa6599782400b8009496424ec99802`，CodeHead `045bea3574dece7ea5740d6eaa76a3a731150cc0`。Claude Code CLI 编码/测试，主代理在精确干净工作树完整审查；最终双方各82项通过、0失败、0跳过（39项既有助手、31项新增替换、12项AI调用指引），两个受影响Skill结构校验通过。初轮双方各78通过/1失败/1跳过留证；修正测试预期中遗漏的空格，以真实GB18030截断序列替代可跳过用例，并补充分块边界测试。审核要求保留解码映射前字符上限及私用区DBCS行末歧义检查，最终均已验证。新增显式 `--replace-invalid-with '?'`、只读预览损失记录、绑定精确planId的逐文件 `--confirm-file` 与外部副本；默认严格模式、原文件保护、非注释/歧义阻断不变。助手1.1.0、plan/manifest schema2需要旧计划重新预览；产品版本仍1.3.0。原工程、硬件、runtime、全局技能及冻结资产未操作，已安装/冻结1.3.0不含本补丁；不是全量发行资格。报告阶段仅澄清指引中两种危险trigraph措辞，helper/tests与测试CodeHead一致。

用户已指定：剩余约定优化全部完成后，统一更新产品与发行版本至 **v1.3.1**。失效构建诊断/clean指引、VS Code生成配置/任务、doctor就绪检查与烧录频率/失败提示的离线源码切片已完成；仍待内存余量告警及后续集成/发行验证，真实IDE行为未验收。本次未提前改版本号、重建发行包或发布；既有硬件入口和授权边界继续适用。

2026-10-25 PY-OCD-DEBUG-CONFIG 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/PY-OCD-DEBUG-CONFIG/review.md)。Accepted base `7b25b890f02892626c5ba6201bd3dec2712a95e4`，CodeHead `313743acfa609d6c29ca8bb9cbec3800f3577418`。Claude Code CLI 编码/测试，主代理在精确干净工作树完整审查；最终作者与主代理各344项通过，包含82项新增。1164项历史回归有通过证据，其中902项按记录复用；共1246个不同用例通过，不宣称最终全量矩阵重跑。初轮7项新测试失败、6项回归失败及接受基线中的旧转换夹具失败均已留证并修正。4项真实符号链接检查延至主代理负责的具备能力的Windows/Linux发行验证，模拟reparse检查通过。配对debug.backend/debug.target配置、只读PLAN、manifest与受管文件同事务APPLY/回滚、完整缺失诊断、非阻断迁移后提示及VS Code/Skill指引已接受；配置不证明target支持或实机状态，原有Git/固件身份/SVD/授权与独立探针发现边界保留。原工程、硬件、已安装runtime、全局技能、冻结发行资产未操作；已安装/冻结1.3.0不含本源码补丁。本断点不授予安装、硬件或发行权限，既有执行流程继续适用。

2026-10-24 LINKER-FRAGMENT 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/LINKER-FRAGMENT/review.md)。Accepted base `b7ef2ebf2da37e127bf600d58878789cfbb23eb6`，CodeHead `114b1f2074a9ff39f9dd399fc8b4e51584fa2a3c`。Claude Code CLI 编码/测试，主代理在精确干净工作树完整审查。最终作者及主代理各108项新增通过、1项符号链接跳过；作者另574项模型/生成/构建回归通过、2项符号链接跳过。951项相关回归按未变产品与测试字节复用，另3项符号链接跳过；共1059个不同用例有通过证据，未宣称最终全量矩阵重跑。初轮7项失败（3项诊断期望、4项未进入编译的夹具路径）及修正、CLI未执行调用异常均留证；4项真实符号链接验证延至主代理负责的具备能力的Windows/Linux发行验证。generation.linkerFragment、受限RAM NOLOAD节、共享区域图、ELF非重叠/区域/属性验证、精确片段摘要与删除/移除选项的构建拒绝已接受；实际GNU编译链接、CMake/Ninja重链接及clean build通过，VS Code/Skill调用指引已同步。片段不负责初始化内存；原工程、已安装runtime、全局技能、冻结资产及硬件未操作。已安装/冻结1.3.0不含本源码补丁，重启VS Code不会安装它。本记录仅更新离线验收断点，既有硬件入口合同、安装与发行权限保持不变。

2026-10-24 EXTRA-MEMORY-REGIONS 离线切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/EXTRA-MEMORY-REGIONS/review.md)。Accepted base `e4c7314af220295037ed6d273127d9873ba3eedc`，CodeHead `540a62cbdf6d92de69b078736f8ffa5a9ec77477`。Claude Code CLI 编码/测试，主代理在精确干净工作树完整审查。56项新增通过；最终296项迁移回归及141项构建回归通过，另1项符号链接跳过；独立最终71项通过，先前566项模型/生成和158项产物检查按未变路径复用（另2项符号链接跳过）。共1217个不同用例有通过证据，未宣称最终全量矩阵重跑。初轮3项失败及修正留证；3项真实符号链接验证延至主代理负责的具备能力的Windows/Linux发行验证。显式 memory.extraRegions、完整共享区域图、fixedSections/linker/ELF/MAP/identity、CLI/MCP与VS Code指引已接受；实际GNU编译链接和纯软件SRAM烧录拒绝已验证，不证明外部内存初始化或实机行为。原工程、已安装runtime、全局技能、冻结资产及硬件未操作；已安装/冻结1.3.0不含本源码补丁。无新增硬件或发行授权，后续仍按下方既有入口合同执行。

2026-10-24 ARMCC-COMMON-SYNTAX 离线迁移切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/ARMCC-COMMON-SYNTAX/review.md)。Accepted base `07f5e1b7720f885f0e005935256ec9466e0af261`，CodeHead `d298757a36a8b106d02a5f133bdab51e87db1373`。Claude Code CLI 编码与测试，主代理独立完整差异审核。47项新功能通过；1198项相关回归为1194通过/1历史夹具失败/3符号链接条件跳过，该失败在accepted base同样复现；固定历史producer版本后，作者与主代理各22项受影响检查通过，保持原哈希断言。主代理另88项聚焦、47项新功能通过；作者Skill校验通过。1195项回归有通过证据，未宣称最终全量重跑；仅文档及单个测试夹具改变，其余按精确字节复用。3项真实符号链接检查延至主代理负责的具备能力的Windows/Linux发行验证环境。早期失败与一次未执行的Bash调用异常留证。常见naked asm、对齐/有界宏固定地址、精确no-semihosting pragma、newlib身份与AI指引已接受；真实GNU编译/链接/反汇编仅为离线证据，不是完整CMake、Keil等价或实机资格。前一include-only切片在本次回归中复核。原工程、已安装runtime、全局技能、冻结发行资产及硬件未操作；本地源码尚未打包安装，重启VS Code不会安装补丁。硬件/发行入口与授权仍按下方既有合同执行。

2026-10-24 KEIL-SCOPED-INCLUDES 离线迁移切片已 `ACCEPTED_WITH_FIXES`，见[独立验收记录](../codex/returns/KEIL-SCOPED-INCLUDES/review.md)。Accepted base `e9b242ec8f97f30135693ca5b0f3f9d8465a7615`，CodeHead `22bbc94b2343327e6d4ca71764b495806d1d8f0a`。Claude Code CLI 编码及测试，主代理在精确干净工作树完整审核并复核。最终作者与独立各30项新功能通过；320项相关回归和51项独立集成/布局检查按未变字节复用，保留两轮测试代码失败记录，不声称最终全量重跑。安全 group/file include-only 合并、相对路径/冲突/有界清单、PLAN 身份与 APPLY 重检、报告及 VS Code/Skill 指引已接受；defines/misc/汇编等未知编译语义继续阻断。原工程、已安装runtime、全局技能、冻结发行资产及硬件未操作。此补丁仍仅源码，不授予安装、发行或硬件资格；硬件入口合同仍以下方 EXTERNAL-FIRMWARE 等记录为准。

2026-10-24 AI-CALL-GUIDANCE 离线调用引导切片已 `ACCEPTED_WITH_FIXES`，依据[独立验收记录](../codex/returns/AI-CALL-GUIDANCE/review.md)。Accepted base `c6cf5cda7a25e4aa0b1335558ab0ffe16fbb32be`，CodeHead `e02365f4ba7ec3c3bcaef3efae6d473215d6f7e6`。Claude Code CLI 编码与测试，主代理独立完整差异审核；最终80项定向通过，189项未变相关回归按记录复用，独立103项及最终33项通过，五个受影响 Skill 格式校验通过。仅完善实际 MCP 版本/绑定证据、完整诊断、managed/imported 分流及 Skill/VS Code 指引，保留原有准入和硬件合同。本补丁尚未进入冻结的1.3.0发行文件或已安装runtime，重启VS Code不等于安装补丁；原工程与硬件未操作。下一次硬件验收仍须按下方执行卡和既有EXTERNAL-FIRMWARE合同核对，不因本次离线接受获得授权。

2026-10-24 EXTERNAL-FIRMWARE 离线软件切片已 `ACCEPTED_WITH_FIXES`，依据[规格](../superpowers/specs/2026-10-23-external-firmware-design.md)、[计划](../superpowers/plans/2026-10-23-external-firmware-plan.md)和[独立验收记录](../codex/returns/EXTERNAL-FIRMWARE/review.md)。Accepted base `6b4c13b6fa76f320503b14679c8eb7bfc712c9af`，CodeHead `4f002cd1479dc98c2dc9c48d7e75dddf896de2f2`。本地 Claude Code CLI 负责实现与测试，主代理独立审查；52项新功能独立通过，最终191项相关回归通过，另924项未变回归按验收记录复用。此断点仅接受离线软件；v1.3.0 本地构建按[交付计划](../superpowers/plans/2026-10-24-v130-local-release-plan.md)留证，不代表全量发行资格。原工程、已安装 runtime 和硬件均未操作；v1.2.0 例外不沿用。后续实机前仍须填写下节执行卡并获得对应授权。

外部固件入口须先 readonly import PLAN → 原参数与 planId 的授权副本 APPLY → readonly ADMIT。导入副本的授权不授予硬件操作；ADMIT 的 offlineReady 不等于目标已验证。后续另获授权的 flash-imported 绑定 importId、原始 source SHA256、target、声明范围及 probe，使用独立 MODIFY 工作流、芯片 Flash map 校验与完整 readback。成功响应 details.postFlash.targetState=unknown、details.postFlash.runVerified=false（收据同样记录 runVerified=false），不证明固件运行；不能作为受管 debug、Monitor 或 Target 的构建身份。硬件失败后仍遵守首错停止，不因导入成功自动重试或 reset/resume。若开始新的发行覆盖率度量，先将 external_firmware.py 纳入 Toolkit 风险核心范围，保留永久门槛。

2026-10-21 v1.2.0 版本统一与源码交付已ACCEPTED，依据[规格](../superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)、[计划](../superpowers/plans/2026-10-21-monitor-v120-delivery-plan.md)和[验收记录](../codex/returns/MONITOR-V120/review.md)。Accepted base `45e1acde2e89a4d14570efe9c0f4d9b4e5e2f907`，CodeHead `e6cdf2c7625f6e68aecfcafbfd4a0d26ca2c5eec`，报告head `e1fd32fe0a43ec0e014dce29a8a901f2e0b4ec41`，分支 `codex/v1.2.0`。v120_impl唯一实现、v120_review独立完整差异审查，均为gpt-6-sol/max；主代理负责规格、集成、完整复核、验收及获授权远端操作。版本、旧runtime/producer兼容、发行锚点、导出精确版本、UI检查与本地wheel元数据通过，独立52项聚焦和最终5项通过；未发布历史中的三段审查缺口已独立补审，189+2+76项Python及40项UI通过。Monitor功能源码和7个UI资产与accepted base一致。用户授权push、合入master及清理已合并历史分支；实际远端head及删除结果以 `D:\codex-tmp\v12021\delivery.json` 为准，不创建tag/Release。现有1.1.2固件不能满足1.2.0原有精确身份合同，local promotion DEFERRED，8765保留ur1021的1.1.2服务（PID30040），未重启、改库、重建或烧录。浏览器、物理及完整发行资格继续DEFERRED。29处临时目录已清理；1处reparse和3处自动策略拒绝清理hold见验收记录。下方保留历史断点，不代表新的部署状态。

2026-10-21 Monitor 合并变量一致读取软件切片已ACCEPTED，依据[规格](../superpowers/specs/2026-10-21-monitor-u16-consistent-read-design.md)、[计划](../superpowers/plans/2026-10-21-monitor-u16-consistent-read-plan.md)及[验收记录](../codex/returns/MONITOR-U16-CONSISTENT/review.md)。Accepted base `ba390750127d9f89efd521a503f5338976640203`，最终CodeHead `d6e3749b65bf2266298a8002971f738d2aee85ea`，分支 `codex/monitor-u16-consistent`。主代理负责规格／集成／完整差异审查／验收／运维，u16_compact_impl唯一实现、u16_compact_review独立审查，均为gpt-6-sol/max。当前PC_send2[53]/[54]使用同一对齐SRAM字的连续匹配快照，最多三读；不稳定则输出缺口，不回退分字节或沿用旧值。实现者精确代码头302项Monitor、431项Toolkit及跨包回归通过，另1项既有Windows目录rename条件跳过；独立27项聚焦及最终3项隔离测试通过，完整差异无阻断；主代理3项真实软件调用链集成按未变产品字节复用，7项打包UI资产保持一致。8765实际切换与默认浏览器授权交付以 `D:\codex-tmp\ur1021\service.json` 为准；成功卡生成前uw1021仍是旧服务。数据库schema3不迁移，停服备份与保留证明在同一运行根。版本1.1.2和固件逻辑不变，分组／波形／CSV兼容；不能将固件的两次字节写入视为原子发布。浏览器／认证HTTP／新物理验证继续DEFERRED，无远端动作。测试临时目录清理被自动审批策略拒绝，已记录hold且未绕过。

2026-10-21 Monitor 低／高字节16位组合与源码目录精简软件切片已ACCEPTED，依据[规格](../superpowers/specs/2026-10-21-monitor-u16-compact-design.md)、[计划](../superpowers/plans/2026-10-21-monitor-u16-compact-plan.md)及[验收记录](../codex/returns/MONITOR-U16-COMPACT/review.md)。Accepted base `b7d5f43cec3efcfa18ecc1dc7c1e62a839434be7`，CodeHead `3d11c00c5068d988bd8943923f5fe0d2cb67886c`，报告head `2a6ffda67109f8271a04c0df1680e6c22dc1cd2f`，分支 `codex/monitor-u16-compact`。主代理负责规格／集成／完整差异审查／验收／运维，u16_compact_impl唯一实现，u16_compact_review独立审查，均为gpt-6-sol/max。固定u16le观测项可保存、同批计算、画图及导出CSV；目录仅保留文件、变量和成员层级，诊断移入全局抽屉。schema3启动前迁移已验证旧组／历史首次读取与失败取消清理。实现者658项Python、506项UI通过（另1项既有可选跳过）及类型/lint/build/dist通过；独立12项Python、25项UI及真实数据库副本字节保留通过；主代理精确CodeHead的102项Python、51项UI及7文件重建一致性通过。8765成功切换与默认浏览器交付以 `D:\codex-tmp\uw1021\service.json` 为准，成功卡生成前uc1021仍为旧服务；停服后数据库回滚备份与迁移保留证明在同一运行根。版本1.1.2和固件不变；浏览器／认证HTTP／物理继续DEFERRED，无远端动作。清理完成项与4处测试reparse hold见验收记录。

2026-10-21 Monitor 信息与操作简化软件切片已ACCEPTED，依据[规格](../superpowers/specs/2026-10-21-monitor-ui-clarity-design.md)、[计划](../superpowers/plans/2026-10-21-monitor-ui-clarity-plan.md)及[验收记录](../codex/returns/MONITOR-UI-CLARITY/review.md)。Accepted base `c9651203b6bab44feca192868846c67b8f7581b3`，CodeHead `ec3b6fa64b9eef0ce0c987890ad958b7cc9ef620`，报告head `c2e9a381c75c883c110bef07b967a0214705d75b`，分支 `codex/monitor-ui-clarity`。主代理负责规格/集成/完整差异复核/验收/运维，ui_clarity_impl唯一实现、ui_clarity_review独立审查，均为gpt-6-sol/max。诊断默认收起，目录默认折叠并保留搜索/懒加载/局部重试；采样动作按六状态展示，所有非IDLE保留停止，空预览与保留样本区分。分组、波形和CSV实现不变。独立审查两项发现均修复，最终29项UI通过、1项既有条件跳过；主代理最终29项资产测试和7文件重建一致性通过，先前61项UI集成按未变运行逻辑复用。实现者最终24项受影响UI和静态/build/dist通过，早期498项全量UI按明确边界复用。8765切换后的source/PID/exec/默认浏览器交付以 `D:\codex-tmp\uc1021\service.json` 为准；成功卡前mo1021仍为旧服务。版本1.1.2、固件与数据不变，浏览器/认证HTTP/物理继续DEFERRED，无远端动作。

2026-10-21 Monitor 默认可观测目录与保留目标状态的连接软件切片已ACCEPTED，依据[规格](../superpowers/specs/2026-10-21-monitor-observable-running-design.md)、[计划](../superpowers/plans/2026-10-21-monitor-observable-running-plan.md)及[验收记录](../codex/returns/MONITOR-OBSERVABLE-RUNNING/review.md)。Accepted base `e125bc5ae362abb84ffa3d71b251681aeb7e0d48`，CodeHead `4e1e0bd4864ae337ff95fe06e39c9cbdc32ff0a9`，实施报告head `fef2f22355372296efee7013db7cc8c28b924f84`，分支 `codex/monitor-observable-running`。主代理负责规格/集成/完整差异复核/验收/运维，`observable_running_impl`唯一实现、`variable_directory_review`独立审查，均为gpt-6-sol/max。最终主代理70项Python、23项UI、7文件重建一致性与真实MR离线tree/page/select通过；独立审查9项定向检查通过，完整差异无剩余阻断。实现者最终41项源码、10项UI及类型/lint/build/dist通过；早期494项完整UI及未变连接/分组/导出回归按字节复用，详见验收记录。当前MR53/53单元、43可见文件、808根条目；无探针时为“待连接”，普通局部/参数不显示，保留timer.h的testtime映射及旧快照一处头文件遗漏。默认空文件/作用域裁剪取代先前全文件展示要求。8765切换后的最终干净source/PID/exec/默认浏览器交付结果以 `D:\codex-tmp\mo1021\service.json` 为准；成功卡生成前mv1020仍为旧服务。版本1.1.2、原固件/数据不变，浏览器/认证HTTP/物理状态仍DEFERRED，无远端动作。

2026-10-20 Monitor 变量角色、extern 映射、版本化源码快照与目录层级的软件切片已ACCEPTED，依据[规格](../superpowers/specs/2026-10-20-monitor-variable-directory-design.md)、[计划](../superpowers/plans/2026-10-20-monitor-variable-directory-plan.md)及[验收记录](../codex/returns/MONITOR-VARIABLE-DIRECTORY/review.md)。Accepted base `34256353d3b7ab0f8eacaa9b8065759299855933`，CodeHead `c355d030cf2bd711410a846041dc0c4a3f0cfdc4`，实施报告head `ba8552fbdffbbd0d5bf2e83a2eb94cfd92112743`，分支 `codex/monitor-variable-directory`。主代理负责规格/集成/完整差异复核/验收/运维，`variable_directory_impl` 唯一实现、`variable_directory_review` 独立审查，均为gpt-6-sol/max。实现者59项源码、49项恢复流程、493项UI（另1项既有跳过）及类型/lint/build/dist通过；主代理最终CodeHead的32项源码目录、独立真实工程新旧两条53/53-unit tree/page/select路径通过，另252项Python、22项UI及资源重建一致性证据按未变字节复用。独立审查定位并验证三项修复，最终10项定向检查通过，无剩余产品问题。8765授权更新的实际PID/exec/最终干净source head和默认浏览器交付结果以 `D:\codex-tmp\mv1020\service.json` 为准；卡记录成功切换前，ma1020的PID20004/exec77714仍是旧服务。当前MR旧构建/ELF/169路径快照及收据不变，保留一处具名旧快照遗漏；独立新构建171路径、53/53解析、0 issue，未烧录。浏览器/认证HTTP/新硬件继续暂缓，无远端权限变化。清理hold与本轮根见验收记录；下方既有验收作为历史保留。

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

v1.3.1 回归补充：短临时根之外，还要核对嵌套子用例的最终路径；本轮 254/260 字符 hardlink 原生诊断支持路径长度归因，但原始失败未暴露 errno，报告须保留这一限制。Windows 本地化命令如 tasklist/mklink 应保留原始 bytes 和退出码，不把解码线程失败当成空输出成功。真实时限夹具须证明进入了被测操作，再验证跨越其实际 deadline；不得放宽产品时限或性能门槛。

发行打包前除核对精确提交和 tracked/untracked 状态，还须检查被忽略的 package build/lib 与 egg-info 是否遗留退役文件。官方 source/wheel 绑定拒绝不能靠放松校验解决；保留失败材料，使用同一冻结源码且无旧打包残留的独立工作树。文档 checkpoint 不触发全量重测；最终交付的源归档与 manifest 必须绑定最终冻结提交。

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
| 烧录频率与策略 | 对实际支持本切片的CLI/MCP记录显式Hz或省略、选定connectionPolicy；核对frequencyHz/--frequency是否在实际绑定schema/入口中。100000..50000000为配置范围，不是实测时钟或成功证明。普通默认配置不变；受管under-reset固定100000Hz，显式冲突先离线解决；导入路线不支持under-reset |
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
| Monitor 普通连接/释放 | 专用 observe-preserve、100kHz attach；不主动 halt/resume/reset，失败清理同样不补偿恢复。原来 running 或 halted 均保持其状态；禁用 pack/config/user 调试序列，使用已验证的 pyOCD 通用初始化路径。软件路径通过不等于板上无瞬时影响已实测 |
| 正常 Target execute | 使用匹配的新 MODIFY action；flash/readback 后按既有流程 reset、必要 resume、启动 transport；须有真实 TestRun |
| Target recovery-under-reset | prepare 只做静态检查；execute 从该新 action 派生 100kHz SWD/under-reset MODIFY，先核对真实身份；sector erase、keepUnwritten=true、auto_unlock=false，保留既有 readback/reset/条件 resume/transport/cleanup |
| 普通 flash / recovery flash | 与 Target 测试流程不同；普通烧录可显式选择频率，省略保留既有配置（生产normal默认1MHz）。显式频率若与选定策略冲突，在副作用前拒绝；受管recovery保持100kHz，显式其它频率拒绝；导入flash仅支持normal频率。成功编程或receipt不证明运行态；恢复烧录保持既有halted后置，不擅自reset/run。details.flashOptions仅记录选定配置，不证明实测频率或attach发生 |
| 变量/SVD/有限采样 | memory.read 不要求 halted；按实际入口区分 Monitor 的 observe-preserve 与其他保留原合同的普通 OBSERVE。连接阶段和后续持续采样分别留证，采样不得隐式 halt/reset/resume |
| 完整 Fault | 核心寄存器必须 halted 且稳定；默认 running OBSERVE 不能满足该前置。显式 halt-for-analysis 使用受控 CONTROL、独立授权、身份校验及 bounded resume/cleanup |
| IDE handoff | begin 后 IDE 独占；正常 detach、原 ticket end 和成功回收后 Toolkit 才能访问 |

若实际版本支持details.recoverySuggestion，只将其视为受管normal失败且自有清理完成后的条件建议；检查原code/details/attachDiagnostic/programDiagnostic及清理终态。它不授权或触发第二次调用，不能用于导入路线，也不绕过身份、授权或清理失败。终态失败立即停止；是否执行一次新的under-reset须先复核原身份/目标供电/复位接线/所有权与新授权，在新执行卡记录固定100kHz及有限次数。不得自动降频、重连、重烧、reset/resume或切换路线。冻结/已安装1.3.0没有本源码选项；重启不会安装补丁。

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
