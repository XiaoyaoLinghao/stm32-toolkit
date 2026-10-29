# STM32 Toolkit 标准测试流程

本文件是离线验证、部署与实机验收的执行入口。规格定义要求，源码定义实际入口合同，本文件规定执行顺序，报告记录事实。冲突须先离线解决，不在硬件操作中猜测。主代理维护本流程、调度和验收；实现和新增测试由本地 Claude Code CLI 按其现有配置负责，作者不能自行接受差异。本文不授予安装、硬件或远端权限。

当前普通烧录频率政策以[100 kHz设计](../superpowers/specs/2026-10-29-flash-default-100khz-design.md)为准：计划v1.3.5源码候选默认100 kHz，显式较高频率只是可选配置，不要求1 MHz实机通过。普通100 kHz不等于under-reset；不得因缺少1 MHz成功证据追加实机或阻塞默认路径验收。下方带日期的旧断点与报告保留原频率事实，不构成现行需求；先核对实际runtime是否包含该改动，旧安装不因源码修改或重启改变。

## 1. 当前断点与证据

2026-10-29 SESSION-TRACE 在等待同一份新硬件授权/就绪答复期间，离线追踪了USB等待分支，并补齐枚举期间Session.get_current可能创建无探针默认选项Session的配置前置；见[源证据及聚焦复核](../codex/returns/SESSION-TRACE/usb-wait-offline-2026-10-29.md)。原project四个默认YAML与两个环境覆盖项当前均不存在，未读取配置内容、导入后端或操作设备。新增前置在b68794a7取得独立NO_BLOCKERS，三条原生命令/三个完整JSON源码包均已核对；原完整入口审查和42+8软件证据仍保留。USB默认10秒与旧服务5秒只构成待实机区分的候选解释，不是根因或延长超时的授权。代码、时限、后端选择、实机次数及20s+2s预算均未改变，仍BLOCKED_NOT_EXECUTED；此前硬件权限/供电独占问题未获新答复，不重复发起或自动执行。以下为此前断点。

2026-10-29 SESSION-TRACE 后续一次构造器/USB诊断的流程、执行卡和实际入口已取得独立 **NO_BLOCKERS**，见[入口审查记录与限制](../codex/returns/SESSION-TRACE/entry-review-2026-10-29.md)。审查源码HEAD `60daa9cc0e38438fa7acf555bdd37f58b644fd08`，CodeHead仍为下方离线通过的e8c43322；16条原生只读命令、25段完整源码（含2225行helper）已核对，未执行helper/后端/枚举/USB或测试，也未编辑产品/测试。新硬件授权、当前供电/原板原探针独占及变化确认仍缺，状态 **BLOCKED_NOT_EXECUTED**，不是READY；已审查执行卡不能自行授权或重用旧实机次数。补充依赖源hash、实际解释器版本及字段只是代码路径声明的限制已留证，原物理原因与完整三项目标仍未解决。以下为软件与历史断点。

2026-10-29 SESSION-TRACE 最终离线诊断已 **SOFTWARE_COMPLETE_HARDWARE_PENDING**，CodeHead `e8c43322efa454ac5ddc782572c073e566b432fd`，见[当前验收记录](../codex/returns/SESSION-TRACE/implementation-report.md)。Claude新执行全部42项、主代理在干净精确提交另独立8项均通过，0失败/跳过/错误，实际退出0且tracked源码hash未变；原生未提供数值退出时仍记null。仅修新增测试的回收等待：在同一固定10秒清理deadline内观察真实既有owner判定，之后只acquire一次；其他41个测试函数AST、诊断脚本和产品lease保持不变。原文件调用一次Grep越过精确只读范围，仍保留dispatcher未接受，实际一个范围内Edit与其后独立审查、另行获准的验证分开记录，未追溯接受或重启编辑调用；一次上下文校正额度未用并到期。旧26/14、41/1与准备错误均保留。该结论仅使后续一次构造器/USB留证可以进入执行卡与独立入口审查准备；尚无新硬件授权/READY，不执行烧录或自动恢复。原物理连接原因、IPSR/reset实效与完整三项目标仍未解决，未安装、打包或推送发布。以下为历史断点。

2026-10-29 SESSION-TRACE 显式直接CPython运行时的新CodeHead `439900a2397a0862d28afecc3012294f6f0100cd` 已全新执行42项，**41通过/1失败/0跳过/0错误**，主代理在干净精确提交另独立8项通过；所有tracked源码hash未变，见[当前执行与审查](../codex/returns/SESSION-TRACE/implementation-report.md)。诊断脚本Git blob保持不变；Claude仅修改测试适配，两个verify调用均实际完成原生PowerShell inventory/smoke和全部9条命令。失败为新增租约释放负例的最后回收步骤PROBE_BUSY；构造、Session关闭、唯一释放错误及整体失败断言已通过，但退出码已终止不保证现有Windows owner identity已不可查询。独立通过不能覆盖原失败，当前仍REVISION_REQUIRED，下一次只准备测试在有限预算内等待真实既有回收条件，不能放宽PID/租约/健康校验或改诊断脚本。原生成功未提供数值退出时仍记null；实际pytest退出按外置证据记录。旧venv失败及主代理换行hash准备错误均留证。尚无新的修正调用或硬件授权，不是软件接受/硬件READY；原物理连接原因与完整三项目标未解决。以下为历史断点。

2026-10-29 SESSION-TRACE 两次修正后的CodeHead `1c8d32c3f0a8fe166034ed934bf2d87347502c14` 已完成40项新执行，**26通过/14失败/0跳过**，源码hash未变；见[当前执行与原因](../codex/returns/SESSION-TRACE/implementation-report.md)。第二次文件委派审计通过、无工具错误，一次同文件校正额度未使用；测试未通过。首项失败是Popen测试替身破坏Windows asyncio导入；其余13项在READY PID不匹配前被阻断：venv启动器PID不是实际Python PID，未进入被测构造/超时阶段。Primary已独立用纯软件进程观察复现，并确认现有直接CPython3.12.14＋既有pyocd0.45.1依赖路径的可行性，未调用helper/探针。按两轮限制停止局部helper修补，转入[显式直接运行时与测试适配设计](../superpowers/specs/2026-10-29-session-trace-runtime-design.md)，保持严格PID/租约校验；旧venv入口仍不合格。新方案须明确授权、只改测试适配、在固定真实解释器和同一源码/依赖路径全新完成矩阵及独立验收。当前为执行/验证接口REWRITE_REQUIRED，尚非软件接受或硬件READY；原物理连接原因与完整三项目标未解决。未安装、操作硬件或推送发布。以下为历史断点。

2026-10-29 SESSION-TRACE 首次有界修正已由用户授权并执行，但原生Edit未匹配原文后仍继续编辑，Primary停止了经核实的本次Claude CLI；见[当前修正处置](../codex/returns/SESSION-TRACE/implementation-report.md)。保留的部分CodeHead `d1b975d4d9f044b08fd6e73e1c3bb2b42e884237`，25次成功写入仅改诊断脚本，测试文件未改；无范围外写入、命令或测试，原错误、停止记录与CLI退出4294967295保留，dispatcher未接受。Primary已在干净精确CodeHead审查全部修正差异，仍REVISION_REQUIRED。**旧测试依赖的模拟环境开关已从脚本移除，测试尚未迁移到私有Python注入，不能在只修收集问题后直接运行旧CLI构造用例，以免调用真实后端。** 下一次先完成测试迁移和余下错误合同，再固定源码、审查、分开执行离线验证；没有新的修正调用授权或硬件READY。原c01仍0通过，实际连接超时及完整三项目标未解决。以下为历史断点。

2026-10-29 SESSION-TRACE 初版候选独立完整差异审查为 **REVISION_REQUIRED**，见[当前审查及执行记录](../codex/returns/SESSION-TRACE/implementation-report.md)。Accepted base `bee6118339166e7d57a0e8ed1fc29ddf85242d0c`，诊断/测试CodeHead `e385e5b17b1dfb1835e4a8db3dc67c2a8309f951`。Claude文件调用38次范围内写入，原生两次不存在路径Read及一次畸形Write错误保留，dispatcher未接受；后续独立PowerShell验证实际退出4，动态导入/dataclass收集错误1项、通过0项，tracked源码hash未变。Primary已在干净精确CodeHead审查全部六文件差异，提出七项有界修正，未执行自动重新委派。不是软件接受或硬件READY；实际连接超时、IPSR=3和完整三项目标仍未解决。用户无原ARMCC产物，ABI维持未验证。仅准备原两文件修正，按全局AGENTS明确有界授权后再委派、分开验证；不操作硬件、安装、打包或远端。以下为历史断点。

2026-10-29 剩余三项按[当前顺序计划](../superpowers/plans/2026-10-29-remaining-three-plan.md)继续。初版ATTACH-ISOLATION两轮未收敛，已REWRITE_REQUIRED并保留，见[前序处置与来源](../codex/returns/SESSION-TRACE/predecessor-disposition.md)。当前SESSION-TRACE在accepted base `bee6118339166e7d57a0e8ed1fc29ddf85242d0c`冻结[新执行接口](../superpowers/specs/2026-10-29-session-trace-design.md)，IMPLEMENTATION_PENDING：直接启动独立解释器，匹配READY后才写一次GO，未获GO的子进程不得访问USB，沿用真实子进程OBSERVE租约。它尚未实现或通过软件验收，不能作为实机入口；整个goal仍在第1项，实际连接原因未定，第2、3项未完成。未操作硬件、安装、打包或推送发布。后续仍须完成离线验证、独立入口审查、真实身份执行卡与新明确硬件授权。以下为历史断点。

2026-10-29 FLASH-DEFAULT-100KHZ 已完成离线审查修正与验收，整体 **SOFTWARE_COMPLETE_HARDWARE_PENDING**，见[执行与独立验收记录](../codex/returns/FLASH-DEFAULT-100KHZ/implementation-report.md)。Accepted base `4fe1be23d7b2c8a282757e1b8b45f73ee3484043`，最终产品/测试CodeHead `f55e95486fdec6e5cda8b9f25b70767a1f3ef1a4`；Primary设计/完整差异审查与验收、本地Claude CLI实现。普通生产缺省改为100 kHz，省略仍保留传入worker配置、显式频率及原验证规则保留；普通100 kHz不等于under-reset，不再把1 MHz作为实机门槛。CLI/MCP/Skill/指南、设计与测试已同步，历史实机事实保留。全部受影响矩阵在精确最终CodeHead新执行，893个不同用例通过，主代理干净工作树独立125项（含全部8项新增，重复不相加），0失败/跳过，Skill格式检查通过；不是全仓覆盖率或发行资格。委派read-scope偏差、原调用轮数上限及未执行尾项的独立调度均留证，未将拒绝调用改判通过。旧Session构造超时与IPSR=3原因、复位准备的实机效果仍未证实。源码仍Unreleased/计划v1.3.5，元数据1.3.4；未操作硬件、安装、打包或推送发布。后续另授权的普通100 kHz实机前须填新执行卡、核对实际runtime并取得更新入口合同的独立审查。以下为历史断点。

2026-10-29 ATTACH-PROGRESS 离线续查记录见[Session构造与频率依据](../codex/returns/ATTACH-PROGRESS/attach-frequency-offline-2026-10-29.md)。源码HEAD `75e18b7a1f9a8c04eb07d53a7dc7438d540d0d68`、产品CodeHead仍`e8d7e16436dc7130ec70b6fea0efdc8650ce791a`。静态依赖追踪确认CMSIS-DAP会话构造可临时打开USB并查询协议信息；配置SWD时钟发生在后续Session.open内，因此当前session-create末标记不能证明1MHz导致超时。一次纯导入诊断退出0：默认驱动导入约0.577秒，其后Board模块已加载；新进程使用既有OS缓存，不是实机复现或硬件资格。1MHz来源是早期Toolkit普通默认值、与pyOCD默认一致，不是板卡最低需求；整套设备普通1MHz稳定性尚未验证，既有100kHz+under-reset成功不能分离频率和复位效应。保守100kHz默认可作为产品选择评估，主要代价是SWD传输变慢及预算/性能复核，不能冒充当前USB构造超时的已证实修复。本轮只离线检查源码并记录诊断，无新探针枚举/连接、产品/测试/默认/时限修改、安装或远端操作；原实机一次授权仍已消耗，物理根因未定，整体仍SOFTWARE_COMPLETE_HARDWARE_PENDING。以下为历史断点。

2026-10-29 ATTACH-PROGRESS 更新流程、执行卡及捕获包装已取得独立Claude CLI完整审查NO_BLOCKERS，并执行新授权的原板/原探针唯一一次普通1MHz源码候选烧录，见[实机执行与阶段证据](../codex/returns/ATTACH-PROGRESS/hardware-validation-2026-10-29.md)。执行HEAD `f71efe4b63600c533ddd4263a9905f4816b2c2db`、产品CodeHead `e8d7e16436dc7130ec70b6fea0efdc8650ce791a`；CLI退出2、`PROBE_CLOSE_FAILED`，主诊断仍为service-attach-deadline超时，terminal wait超时；自有worker中止、后续清理及租约释放记录成功，物理状态仍UNKNOWN。新progress最后收到session-create@3688ms，之前driver-acquire@0、probe-enumeration@2983ms；snapshot为5983ms，未收到target-resolve-before-open/session-open。它将离线排查收窄至会话构造边界及可能未收到的后续帧，不证明精确硬件耗时、具体阻塞行或后续目标操作从未发生。未进入烧录前复位/编程/回读，无本次成功收据，六项工程文件hash及源码未变。首错后只检查文件证据，未重试、恢复或追加硬件操作；新一次授权已消耗。原始截断部分审查及主代理准备校验错误保留，完整19段审查和READY后离线检查通过才执行实机。当前实机 **FAILED_AT_ATTACH_HARDWARE_VALIDATION_INCOMPLETE**，既有离线软件接受不变，整体仍 **SOFTWARE_COMPLETE_HARDWARE_PENDING**；IPSR=3根因和复位修复实效未证实。仍为Unreleased/计划1.3.5源码、元数据1.3.4，未安装、打包、推送或发布。下一步先离线定位Session构造路径，进一步实机另需有界执行卡和新授权；以下为历史断点。

2026-10-29 ATTACH-PROGRESS 已完成离线审查修正与验收，整体 **SOFTWARE_COMPLETE_HARDWARE_PENDING**，最终产品/测试CodeHead `e8d7e16436dc7130ec70b6fea0efdc8650ce791a`，见[当前执行与独立验收记录](../codex/returns/ATTACH-PROGRESS/implementation-report.md)。attach超时/取消的既有诊断可带闭合`progress`：父进程收到的阶段标记与近似耗时，按当前私有请求token隔离，保留至自有worker中止后；成功响应、原时限、频率、授权、控制及清理合同不变。修正了驱动/枚举标记位置、冻结后帧校验及测试断言/收帧等待；另通过accepted-base同错对照确认并修正一个既有Monitor测试的旧Git次数预期，未改Monitor运行逻辑。受影响矩阵去重1,063通过，Claude1,063、主代理独立67（不相加）；主代理在精确最终CodeHead全新执行全部66项新增用例及修正的Monitor断言。仅1项既有Windows目录句柄阻止rename的用例跳过，明确由主代理在可rename的Linux宿主发行资格阶段补验。复用范围、实际失败、scope审计偏差及调度修正均保留，不是最终提交全仓重跑或发行资格。源码仍为Unreleased/计划1.3.5，版本元数据1.3.4；未操作硬件、安装、打包、推送或发布，旧物理attach超时与IPSR=3根因仍未证实。后续实机须另授权、填新执行卡并先独立审查更新入口合同；旧一次授权已消耗。以下为历史断点。

2026-10-29 ATTACH-PROGRESS 阶段留证切片已冻结规格/计划，但实现委派在只读搜索路径拼写错误及未授权自行更正后由主代理停止，见[保留记录](../codex/returns/ATTACH-PROGRESS/delegation-history.md)。Accepted base `e4d9118e1c83f139db2959acbd4076a357c37992`，委派source freeze `a5d7308e421c7d2724e916d038d8a257dc115eed`；状态 **NOT_IMPLEMENTED_DELEGATION_STOPPED**，无新产品CodeHead、无编辑/测试执行。原生工具清单匹配；一次范围外不存在路径的Grep失败，后续正确路径Grep属于未授权更正；失败日志及实际强制停止证据保留，未重试该调用。已有产品与16项离线续查结论不变；新阶段日志、离线验证与独立验收尚未完成，未接触硬件、安装或推送发布。后续仅在明确有界重新委派授权后恢复，沿用既定文件/工具/模型/执行边界。以下为历史断点。

2026-10-29 FLASH-PREPARATION 继续完成attach离线续查，见[执行与证据审查](../codex/returns/FLASH-PREPARATION/attach-offline-2026-10-29.md)。干净执行HEAD `fa7b2547f657ffd3faa74f9af34d30e0925ecf5b`，产品CodeHead未变；Claude原生PowerShell执行16项既有定向测试全部通过，主代理核对真实工具/命令、外置JUnit新鲜度/身份/hash及全部记录的tracked源码hash。另一次普通诊断测得冷进程驱动依赖加载约0.964秒（模块导入约0.683秒），未枚举或连接硬件；单样本不能解释或排除此前现场延迟。源码确认初始worker握手在服务attach之前已完成，故旧超时范围缩小至后续attach内部/IPC；旧响应无内部阶段进度，物理根因仍未确定。本轮 **OFFLINE_CHECKS_PASS_PHYSICAL_CAUSE_UNRESOLVED**，整体仍 **SOFTWARE_COMPLETE_HARDWARE_PENDING**；未重试实机、改产品/测试/时限、安装或推送发布。后续须先准备并离线审查分阶段连接留证入口；此前一次授权已消耗，不授予新连接或烧录。以下为历史断点。

2026-10-28 FLASH-PREPARATION 一次受明确授权的源码候选普通1MHz烧录在连接阶段失败，见[实机执行记录](../codex/returns/FLASH-PREPARATION/hardware-validation-2026-10-28.md)。执行源码HEAD `7193fcd933020a7084aab9472fc6716d5ca28e82`、产品CodeHead `1bb95790dbe1552b700f588d56e5ef9301b839a2`；入口合同、执行卡和捕获包装已由独立Claude CLI审查为NO_BLOCKERS，离线准入及Windows纯软件spawn检查通过。唯一一次调用退出2，`PROBE_CLOSE_FAILED`，主诊断`service-attach-deadline`超时、terminal wait超时，随后自有worker中止及租约释放等记录成功；目标状态仍未知。未进入新烧录前复位、编程或回读，未生成本次成功收据，旧recovery收据和工程输入hash未变。首错后未重试、恢复或追加硬件读取/控制；一次授权已用完。当前实机结论 **FAILED_AT_ATTACH_HARDWARE_VALIDATION_INCOMPLETE**，既有离线软件接受不变、整体仍 **SOFTWARE_COMPLETE_HARDWARE_PENDING**；原IPSR=3与修复实效未证实。下一步先离线定位attach超时，任何补硬件另填卡并核对新授权。此为源码实验，未修改已安装runtime、打包、推送或发布。以下为历史断点。

2026-10-28 FLASH-PREPARATION 的离线软件范围已通过审查修正与验收，整体状态 **SOFTWARE_COMPLETE_HARDWARE_PENDING**，最终CodeHead `1bb95790dbe1552b700f588d56e5ef9301b839a2`，见[执行与独立验收记录](../codex/returns/FLASH-PREPARATION/implementation-report.md)。普通受管/导入烧录新增一次明确SYSRESETREQ reset-and-halt和HALTED确认；under-reset复用连接复位，只检查暂停；准备失败即停止编程/回读/成功收据，保留清理。新增两个诊断阶段与选定策略字段，正常频率及只读路径不变。受影响矩阵988个不同用例取得通过证据，Claude627、主代理761（重复不相加），最终精确CodeHead新增33项和文档54项均独立通过；复用范围、原调用异常、两项已修正断言失败和一项既有30ms时序失败的串行对照均保留在报告中，不是最终提交全仓重跑或发行资格。改动为Unreleased、计划v1.3.5，源码版本元数据仍1.3.4；未打包、安装、操作硬件、合并或推送发布。实机故障是否消除仍未证实；后续硬件由主代理在独立授权阶段填卡，先取得更新入口合同的独立审查。以下为历史断点。

2026-10-28 问题2由用户明确交主代理继续调查，见[离线续查报告](../codex/returns/POST134-USABILITY/flash-offline-followup.md)。已找到under-reset/100 kHz的61,516字节校验成功收据；已通过源码和无硬件替身调用检查确认标准API路径缺少pyOCD CLI的烧录前reset-and-halt。该差异是优先修复候选，尚未证明现场HardFault根因或修复有效性；未改产品代码、未操作硬件、未安装或推送发布。后续须先定义烧录前状态准备合同；本记录不授予复位/重试权限，也不改变下述1/3/4/5/8的软件验收。

2026-10-28 POST134-USABILITY 本地软件已 **ACCEPTED_WITH_FIXES**，CodeHead `29d13fc75881bfc771d81aa1c54f45948a6fa0f0`，见[执行与独立验收记录](../codex/returns/POST134-USABILITY/implementation-report.md)。已完成1（preset证据隔离）、3（CLI字段诊断）、4/5（共享迁移调试引导和空launch说明）、8（发布文档）；2仅完成离线调查，实机失败根因未证实。Claude构建相关319通过、迁移相关229通过/1平台跳过；另明确复用未变CLI的90项证据，受影响矩阵去重638通过/1跳过，并非最终提交全仓重跑。主代理在干净精确CodeHead独立183/183通过；一个原生pending命令按既有绑定证据核对完成，未重跑。旧失败、超轮数及scope审计拒绝保留，不追溯接受；见[此前部分处置](../codex/returns/POST134-USABILITY/partial-review-2026-10-28.md)。真实文件symlink检查因宿主能力跳过，留待后续发行资格阶段的具备能力宿主；新reparse注入用例已通过。新改动列为Unreleased、计划v1.3.5，源码版本仍1.3.4；本轮未打包、安装、推送发布、修改原工程或操作硬件，既有v1.3.4发布限制和例外不转移。以下为历史断点。

2026-10-28 v1.3.4 已公开为Latest：Release426198381于2026-10-28T02:39:44Z发布，target/标签绑定冻结 `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead`。13附件均匿名下载HTTP200且大小/SHA-256匹配双构建候选，见[发布记录](../codex/returns/STM32TK-134/publication-2026-10-28.md)。Windows ZIP首次网络失败保留，经用户明确批准的一次有界续传成功，只清理该失败starter，8成功附件保留。候选专属例外不改变永久门槛/失败/跳过事实。中英文README、changelog及现行指引已同步并独立审查；最终文档合同172通过/1平台跳过，见[审查记录](../codex/returns/STM32TK-134/publication-guidance-review.md)，冻结包保留构建时状态、master文档说明实际发布。最终安装/VS Code仍USER_VALIDATION_PENDING、由用户负责，原工程/既有runtime/硬件未操作。以下为历史断点。

2026-10-28 v1.3.4 资格处置：用户明确批准只对冻结 `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead` 的13文件候选接受已披露覆盖/复用/失败保留/跳过/平台限制并发布Latest，见[授权记录](../codex/returns/STM32TK-134/authorization-2026-10-28.md)。处置为 USER_APPROVED_EXCEPTION，永久门槛未变、未达标不变PASS；另明确批准仅发布脚本进程内复用既有GCM凭据，不显示/保存/更改认证。下一步非强推源码/标签、上传核验、公开发布与匿名下载复核。最终安装/VS Code由用户负责，原工程和硬件不操作；远端发布尚未发生。以下为历史断点。

2026-10-28 v1.3.4 冻结包：`a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead` 的两次官方离线构建13文件逐项同hash，安全解压后官方bundle验证退出0，见[候选记录](../codex/returns/STM32TK-134/candidate-build.md)。软件已独立审查ACCEPTED_WITH_FIXES；永久覆盖门槛仍未满足，当前 **LOCAL_CANDIDATE_NOT_QUALIFIED**，等待只对具体候选的资格处置，旧例外不转移。现有Git推送dry-run已验证但未实际推送；API发布脚本的进程内现有凭据复用需本次never-read规则的有限例外，准备脚本尚未执行。最终安装/VS Code仍由用户负责，原工程、既有runtime与硬件未操作。以下为历史断点。

2026-10-28 v1.3.4 软件复核：include guard 判定与引号头文件编码发现已在 CodeHead `08ff6e82931a0a4ac35cd6f020a2f9eaee67aea5` 独立审查为 **ACCEPTED_WITH_FIXES**，见[执行与独立审查](../codex/returns/STM32TK-134/implementation-report.md)。受影响矩阵为1,263通过/1平台跳过，明确复用未变源码证据并保留原失败和定点修正结果，非最终提交全仓重跑。原工程preflight提前列36个C与24个可达头文件编码阻断；保留guard的既有UTF-8副本已0 blocker、planReady=true，destination dry-run为191输出，工程字节未变、目标目录未创建。永久覆盖门槛未满足，发行仍 **NOT_QUALIFIED**；下一步冻结双构建13文件，再对具体候选单独处置，v1.3.3例外不转移。未推送/发布v1.3.4、未安装或操作硬件；最终安装/VS Code仍由用户负责。以下为历史断点。

2026-10-27 v1.3.3 已完成发布和公网校验：[发布记录](../codex/returns/STM32TK-133/publication-2026-10-27.md)。Release `425062317` 于 `2026-10-27T05:22:56Z` 设为Latest，标签绑定冻结 `46ca09084bbe39f670714d19d7d55f9365ef06be`。13附件匿名下载均HTTP200、大小及SHA-256匹配双构建候选；中英文README和现行调用指引已同步，文档合同检查通过。仅本候选的已披露例外保持原义，永久门槛未变。最终安装/VS Code仍USER_VALIDATION_PENDING、由用户负责；未改原工程/硬件。冻结包保留构建时文档状态，master文档说明实际发布。以下为历史断点。

2026-10-27 v1.3.3 资格处置：用户明确批准仅对冻结 `46ca09084bbe39f670714d19d7d55f9365ef06be` 的13文件候选接受已披露限制并发布Latest，见[授权记录](../codex/returns/STM32TK-133/authorization-2026-10-27.md)。处置为 USER_APPROVED_EXCEPTION，永久门槛未改，未达标及跳过不变为PASS。下一步非强推源码/标签、上传校验及公网核验；最终安装/VS Code由用户负责，原工程/硬件不操作。以下为历史断点。

2026-10-27 v1.3.3 冻结包：`46ca09084bbe39f670714d19d7d55f9365ef06be` 两次官方离线构建的13文件大小/hash完全一致，官方 bundle 验证退出0，见[候选记录](../codex/returns/STM32TK-133/candidate-build.md)。Toolkit总体/风险82.5877%/82.4231%、Monitor风险92.3681%仍未达门槛；首次性能失败和随后定点对照通过分别保留。当前 LOCAL_CANDIDATE_NOT_QUALIFIED，需仅对具体候选处置限制；还未推送/发布。最终安装和 VS Code 由用户负责，原工程/硬件不操作。以下为历史断点。

2026-10-27 v1.3.3 版本与发布复核：CodeHead `d281addbbdb70e36c270e24828868d7e936dc6e1` 的版本/文档修改已 **ACCEPTED_WITH_FIXES**；发行资格仍 **NOT_QUALIFIED**，见[复核记录](../codex/returns/STM32TK-133/version-review.md)。真实 GCC 两条流程14/14通过，正常受管模拟烧录已验证；功能/UI/安装夹具及性能定点对照证据均保留，原始性能失败未抹去。当前 Python 覆盖率未达永久门槛，明确使用完全匹配源码的既有证据，非最终提交全量重跑。下一步冻结双构建及具体候选处置；最终安装/VS Code 由用户负责，原工程/硬件不操作。尚未推送或发布 v1.3.3。以下为历史断点。

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
| 烧录前准备（计划v1.3.5源码候选） | 先确认实际部署源码/运行时包含FLASH-PREPARATION，不能仅凭版本号推断。普通受管/导入烧录在既有授权、身份与镜像准入后请求一次SYSRESETREQ reset-and-halt，再确认HALTED；受管under-reset复用连接时复位，只重新确认HALTED。记录details.flashOptions.preProgramReset/preProgramHaltRequired，作为选定策略而非已执行证据。准备失败即停，不进入编程、回读或成功收据，不补偿halt/reset/resume或重试。未发布/未安装的源码候选不会改变现有runtime |
| 连接阶段留证（计划v1.3.5源码候选） | 先核对实际源码/runtime包含ATTACH-PROGRESS，不能凭仍为1.3.4的元数据推断已安装。原attach超时/取消诊断可附加attachDiagnostic.progress，记录version/clock/elapsedMs/events；它是当前请求的父进程收帧近似时间与最后收到的阶段入口，可能仅有worker-dispatch，不是精确硬件耗时、完成证明或目标状态。按原样保存code/details及cleanup，缺字段或缺后续帧不补读目标、不重连补日志；旧请求trace不得迁移，队列未派发不得冒用旧trace。所有原授权/时限/频率/首错停止规则仍有效 |
| 授权与预算 | 当前授权范围，新 action 来源，固定次数/时长/超时，允许的控制操作 |
| 成功与停止 | 成功证据、下一步条件、首错停止、既有 cleanup 终态证明 |
| 留证 | 原 code/details/cause、最后阶段、动作消费、TestRun/receipt/lease 保存位置 |

缺关键项不标 READY。先用源码、既有纯校验或 CLI parser 离线核对，不调用 backend。一次授权可覆盖明确连续步骤；终态失败后的重试、恢复或扩展范围另核对授权。Target execute 自身要求 probe-id，不能因 prepare 已指定而省略；动态 digest 只来自本次真实返回。

SVD 场景在首次硬件操作前以实际 project/target/device、完整 SVD 和 readableRegions 复用 select_svd 做语义预检。整个选定文件的每个寄存器都必须在可信区域内，单点 Watch 合法或文件 hash 相等不代表整个选择合法。配置变化后重做相关检查。

迁移工程重新构建前核对 CMakeCache 的 CMAKE_HOME_DIRECTORY/CMAKE_CACHEFILE_DIR。旧路径缓存须先留证、核实生成物归属与 reparse 边界，再移入本轮证据目录并使用当前构建入口；不复活退役工程，不因此重烧已有有效固件。

原始异常必须在首次获准执行前具备留证路径。details.programDiagnostic 仅说明对应编程阶段，program-call 不证明已经擦除/写入。按当前源码检查 backend、IPC、外层映射是否保留所需字段；若 prepare/attach 信息会丢失，先离线验证最小捕获边界，不能失败后自动重连补日志。

### SESSION-TRACE 一次构造器诊断的后续实机入口

该入口只用于当前Session构造超时调查，须先满足[离线诊断门槛](../codex/returns/SESSION-TRACE/implementation-report.md)和[显式直接运行时设计](../superpowers/specs/2026-10-29-session-trace-runtime-design.md)，再由独立审查者复核本节、真实源码入口与run目录执行卡。它不是已安装Toolkit CLI或普通烧录，不继承过去一次烧录授权；未获本次明确硬件授权及新供电/独占确认，不标READY、不运行`run`或`child`。

执行卡必须绑定干净source HEAD与已验收CodeHead、实际helper字节hash、固定真实CPython可执行文件/hash、同树Toolkit源码和既有只读pyOCD依赖。Windows venv启动器不是本诊断支持的执行镜像；不在失败后换解释器、不接管子孙PID或放宽READY的PID/source/request/lease相等检查。临时目录与一次输出目录单独绑定；后者执行前必须不存在，已有证据不覆盖。记录真实project/target/public probe selector和原共享data root，不创建替代注册表或移除旧lease。只读文件快照中的released不证明当前独占，执行时仍由真实guard/owner/loopback health合同拒绝占用或handoff。

固定一次父调用、一个直接child、一个原始20秒总deadline和至多2秒自有协作终止等待；父进程持有明确句柄、claim/READY与期限均匹配后才写一次GO。GO前的真实租约和回环health不枚举设备；GO后只允许一次默认驱动获取、一次现有精确selector枚举/选择、一次选中探针的`Session(auto_open=False)`构造和成功返回后的既有Session.close。该构造可临时打开USB并查询元数据，需要实机授权。选项与正常100kHz路径一致，不调用Session.open、目标reset/halt/resume、编程、读回或恢复；100kHz仅是传入选项，在Session.open之前不能证明已配置实际SWD时钟。固件不是此诊断输入，板上固件身份/CPU状态均UNKNOWN，不能把现存ELF/hash当作运行证明。

枚举内部可能先由Session.get_current创建probe=None的默认选项Session，并按PYOCD_PROJECT_DIR或child cwd读取默认配置；之后选中探针Session的no_config=true不能覆盖此前行为。见[离线等待路径及配置边界](../codex/returns/SESSION-TRACE/usb-wait-offline-2026-10-29.md)。本执行卡还须在实际启动进程复核PYOCD_PROJECT_DIR、PYOCD_USB_BACKEND均未设置，且原project目录中pyocd.yaml、pyocd.yml、.pyocd.yaml、.pyocd.yml四项均不存在（包括重定向/悬空链接）。若出现任何一项，离线停止并核对，不读取/删除配置或清空覆盖项来制造旧前置。记录可能存在的无探针选项对象，不能把“一次选中探针会话构造”误写成库内只实例化一个Session。此补充前置须取得聚焦的独立复核后，才可进行依赖它的硬件步骤；不增加操作次数、权限或预算。

构造前一次真实faulthandler延迟1秒，repeat=false/exit=false，返回后取消；按固定文件留证attempt/request/claim/READY/GO/result/events、child stderr和私有栈。总体成功要求匹配记录、确认child退出0、一次构造/关闭、无禁止动作、trace/lease/handle清理成功；不要求快于1秒时也产生非空栈。超时、取消、拒绝、身份、持久化或清理任一失败，保留 initiating 与 cleanup 后立即停止，不补枚举/连接/烧录/复位或恢复，也不延长原deadline。自有child仍活着或启动未知时保留UNKNOWN与其自有lease，不强杀、不删除注册表、不关闭活/未知句柄或声称已回收；后续处置另核对真实所有权与授权。一次诊断返回只证明该次自有操作，不能单独完成原超时根因、IPSR=3或烧录验收。

## 3. 状态和所有权

按被测版本的函数重新核对，不复用旧部署的行号或机器路径。

| 入口 | 前置和结果边界 |
| --- | --- |
| 正常 Target prepare | OBSERVE 连接，可能短暂停核，再恢复并验证 running；授权持久化前的失败不能视作可 execute |
| Monitor 普通连接/释放 | 专用 observe-preserve、100kHz attach；不主动 halt/resume/reset，失败清理同样不补偿恢复。原来 running 或 halted 均保持其状态；禁用 pack/config/user 调试序列，使用已验证的 pyOCD 通用初始化路径。软件路径通过不等于板上无瞬时影响已实测 |
| 正常 Target execute | 使用匹配的新 MODIFY action；flash/readback 后按既有流程 reset、必要 resume、启动 transport；须有真实 TestRun |
| Target recovery-under-reset | prepare 只做静态检查；execute 从该新 action 派生 100kHz SWD/under-reset MODIFY，先核对真实身份；sector erase、keepUnwritten=true、auto_unlock=false，保留既有 readback/reset/条件 resume/transport/cleanup |
| 普通 flash / recovery flash | 与 Target 测试流程不同；普通烧录可显式选择频率，省略保留既有配置（当前生产normal默认100kHz；1MHz仅显式可选，不是验收门槛）。显式频率若与选定策略冲突，在副作用前拒绝；受管recovery保持100kHz，显式其它频率拒绝；导入flash仅支持normal频率。成功编程或receipt不证明运行态；恢复烧录保持既有halted后置，不擅自reset/run。details.flashOptions仅记录选定配置，不证明实测频率或attach发生 |
| 变量/SVD/有限采样 | memory.read 不要求 halted；按实际入口区分 Monitor 的 observe-preserve 与其他保留原合同的普通 OBSERVE。连接阶段和后续持续采样分别留证，采样不得隐式 halt/reset/resume |
| 完整 Fault | 核心寄存器必须 halted 且稳定；默认 running OBSERVE 不能满足该前置。显式 halt-for-analysis 使用受控 CONTROL、独立授权、身份校验及 bounded resume/cleanup |
| IDE handoff | begin 后 IDE 独占；正常 detach、原 ticket end 和成功回收后 Toolkit 才能访问 |

若实际版本支持details.recoverySuggestion，只将其视为受管normal失败且自有清理完成后的条件建议；检查原code/details/attachDiagnostic/programDiagnostic及清理终态。它不授权或触发第二次调用，不能用于导入路线，也不绕过身份、授权或清理失败。终态失败立即停止；是否执行一次新的under-reset须先复核原身份/目标供电/复位接线/所有权与新授权，在新执行卡记录固定100kHz及有限次数。不得自动降频、重连、重烧、reset/resume或切换路线。冻结/已安装1.3.0没有本源码选项；重启不会安装补丁。

FLASH-PREPARATION候选的正常烧录授权明确包含烧录前SYSRESETREQ reset-and-halt与暂停确认；只读Monitor、发现和handoff不获得该动作。`programDiagnostic.stage=pre-program-reset`或`pre-program-halt`分别定位复位调用或暂停确认失败，保留原始闭合诊断及既有cleanup结果，不能继续编程/回读/生成成功收据。under-reset连接复位不再叠加此SYSRESETREQ；普通/导入flash均不因此增加烧录后reset/run，Target原有烧录后独立控制流程仍按原合同授权。`preProgramReset=sysresetreq`或`under-reset-connect`及`preProgramHaltRequired=true`可以出现在未到达准备阶段的失败响应中，不证明动作或硬件状态。此入口合同须在后续硬件执行前由独立审查者复核并填卡；本轮离线实现与文档不授予硬件、安装或重试权限。

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
