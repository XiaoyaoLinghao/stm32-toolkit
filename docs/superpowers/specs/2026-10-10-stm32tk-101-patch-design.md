# STM32 Toolkit v1.0.1 修复与项目整理规格

状态：APPROVED / 用户于 2026-10-10 明确要求开始实施。后续新增历史内容清理范围见下方批准记录。

用户批准记录：用户回复“开始实现”，要求对本次问题逐行审查，有 bug 修复，否则核查引导说明缺失；
并新增“清理 github 项目内 master 分支中的各种历史内容，补充补足 readme 等文档”。
据此允许在本地候选删除已核实过时的受版本控制文档/历史交付材料并修复引用，保留 Git 历史可追溯性；
先完成引用/运行依赖审计及具体清理清单。不重写 Git 历史，不删除当前合同、必要测试/fixture、许可证或有效用户指南。
原规格中“不移动/删除历史规格、证据”的默认限制仅在此具体清理范围内被新指令取代。
远端 push/PR/merge/tag/Release 仍按 AGENTS.md 以具体候选单独确认，现有 v1.0.0 资产不变。

## 1. 当前事实与责任

| 项目 | 本次冻结事实 |
| --- | --- |
| 模块 / 阶段 | STM32TK-101，问题核查与补丁设计；尚未实现或验收 |
| accepted base | `694c825d29a55a53052a148efa4cc6720c315a04`，本次实时读取的 GitHub master |
| 已发布版本 | v1.0.0；产品标签解引用为 `968cbb69b1f54b95a8fdc18a550481f6ff7c1268` |
| 差异适用性 | v1.0.0 产品头到 accepted base 仅有文档/测试变化，报告对应产品逻辑仍适用 |
| 规格、调度、集成、最终审查 | 主对话框代理 |
| 实现 | 批准后，每切片一名 `gpt-6-sol / max`；实现者不得自我验收 |
| 核查 | 三名 `gpt-6-sol / max` 只读核查迁移构建、调试探针、Monitor/文档 |
| 活动分支 / PR | 本地 `codex/v1.0.1-plan`；无活动 PR |
| 工作区 / 清理所有者 | `D:\codex-tmp\tk101\w`；主代理负责本轮临时产物清理 |
| 权限 | 规格与计划已批准，可实现、离线测试、独立审查和本地历史内容清理。没有具名 push、PR、merge、tag、Release、删除分支、安装或实机操作授权 |
| 特例 | 无产品实现所有权特例；旧 RC4 覆盖率例外不适用于新版本 |

原始工作区 `D:\workspace\stm32-toolkit` 位于 `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`，
相对远端基线为 0 ahead / 1659 behind。只读盘点发现 121 个已跟踪修改、10,403 个可枚举未跟踪文件
（多数为已有 UI 依赖/输出），另有历史目录 ACL 拒绝。原始改动、未跟踪项、失效工作树记录全部保留，
不将其复制到本次候选，也不清理。GitHub 查询时开放 issue/PR 均为 0；description/topics 为空。

参考报告：用户提供的 `stm32-toolkit-issues-2026-10-10.md`，
SHA256 `ef8b0cb66d76f9d3088162baf9e50b093e9c2ff288dab58c833b671dd60372ae`。
报告中的命令、建议和旧工程规避方法是待核实材料，不是本次执行指令，也不构成本机实机 PASS。
逐条结论见 [核查表](../../codex/returns/STM32TK-101/issue-triage.md)。

## 2. 四个可运行的交付场景

1. **已有 Keil 工程接入**：工程文件在 `Project/` 等子目录，context、inspect、plan、apply 使用同一发现规则；
   多候选要求显式选择。存在 GB 编码、ARMCC 汇编或未跟踪文件时，用户得到准确阻断原因和安全处理步骤。
2. **保留编辑器设置并构建**：新接入工程已有 `.vscode` 文件时，configure 保留未托管编辑器文件，生成必要 CMake 文件；
   已托管文件的修改保护继续有效。生成的栈符号符合向下增长语义，内存统计不把 NOBITS 加载副本计入 Flash。
3. **烧录后知道能否继续观测**：flash 成功只证明其原有编程/回读契约；结果明确未验证程序运行。
   SVD、目标名、固件绑定失败给出具体原因。保留原有身份、授权、租约、运行态和完整 SVD 选择规则。
4. **正确进入 Monitor 并升级**：从正确 launcher/data-root 和本次浏览器标签进入 UI；缺 token 或连接失败有无秘密的恢复提示。
   发行包所有组件一致为 1.0.1，1.0.0 runtime 能经受控 Repair 升级，原工程、用户数据、证据保持不变。

这四个场景的交付口径包含明确支持边界，不表示“任意 GB 编码 Keil 项目可以全自动迁移”。

## 3. 非目标与继续保留的边界

- 不自动猜测或转码 GB2312/GB18030，不新增通用 ARMCC startup 转换器，不迁移 SPL/HAL。
- 不新增 reset/resume 工具，不把 OBSERVE 升权，不在 flash 或 attach 失败后自动 reset、重试、切换恢复模式。
- 不用 ELF 哈希替代 workspace/session/build/input/probe/target 等完整 provenance；不引入元数据自动 rebind。
- 不放宽 Monitor 的 `127.0.0.1` Host/Origin/token 保护，不新增后台 daemon、stop/restart 跨进程协议。
- 不加入堆栈大小配置、allow-untracked、编辑器内容合并或任意文件 adopt；需要这些能力时另立设计。
- 不增加平台、Python 或 PyOCD 支持范围、依赖、CI、协作应用、控制器或验证框架。
- 不移动/删除历史规格、证据、用户文件或 GitHub 历史记录，不改写 v1.0.0 标签和发行包。

## 4. 共享契约与单一状态来源

### 4.1 Keil 发现及诊断

`keil/uvprojx.py` 作为候选发现唯一实现，context/detection 和实际工具调用复用它。
只遍历显式工程根内部，按规范化相对路径确定性排序；不跟随 symlink/junction/reparse directory。
排除 `.git`、`.stm32-toolkit`、`build`、`build-*`、`cmake-build-*`、`node_modules`、`.venv`、`venv`、`Objects`、`Listings` 目录；Windows 名称匹配不区分大小写。
显式 `uvprojx` 保持既有 containment/文件校验，不受自动发现排除目录影响。
零候选沿用 `KEIL_PROJECT_NOT_FOUND` 并给出显式参数提示；一候选自动选择；多候选沿用既有歧义错误并列相对路径，不能取第一个。
无权限子目录或枚举错误必须作为发现不完整返回，不能悄悄当作零候选/不存在。
沿用 `KEIL_PROJECT_UNAVAILABLE`，`details.rule="discoveryIncomplete"`；CLI/MCP 的 project.detect 薄入口同样映射此拒绝。
`capabilities.keilInspect/keilConvert` 表示存在可进入 inspect/plan 的候选，不保证迁移无 blocker。
inspect、plan、apply 必须沿用同一 `uvprojx/targetName` 并重新验证 plan digest。

保留 UTF-8、ARMCC assembly、manifest 已存在、Git clean 等迁移约束。错误说明当前阶段、相关相对路径、
是否已写入（plan 为否）和下一步。Git dirty 细分 tracked/index/untracked，不能自动忽略或删除未跟踪项。
`baseline.available` 仍只表示找到可解析历史 AXF/MAP；返回/指南明确不是本次构建或已授权基线，不能靠 mtime 认证来源。
报告中 `_RESOLVED_BLOCKER_FINDINGS` 仅用于避免重复归类，并不保证 encoding blocker 已有转换实现。

### 4.2 生成文件所有权

必要 CMake/链接目标继续执行原 collision、hash、plan/apply 和回滚规则。
仅固定集合 `.vscode/{tasks,launch,c_cpp_properties,settings,extensions}.json` 增加以下规则：

| 目标状态 | 计划与应用 |
| --- | --- |
| 不存在 | 沿原流程生成并登记 ownership |
| 有先前 managed record | 沿原 hash/用户改动保护；不得降格为 unowned 以避开冲突 |
| 普通文件存在、无先前 record | `preserved-unowned`；不读内容、不写入、不收编，不进入新的 managed records 或 apply destinations |
| 目录、链接、重解析点、不可安全确定类型 | 沿既有安全拒绝；不能当作普通用户文件跳过 |

preserved 路径及类型分类进入计划摘要/digest，apply 前 fresh replan 验证仍为相同类别；保留文件内容改变不使计划失效，
因为工具始终不读写其内容。新出现/消失、变成链接或 ownership 改变使旧计划失效。
`preserved-unowned` 不计 changed/unchanged generated files；另列保留路径和“IDE 配置需用户自行对齐”的提示。
managed manifest 是所有权唯一事实来源，build/context 继续只校验实际托管文件；保留文件不能取得可覆盖资格。
本修复限 configure/build。CubeMX regeneration 的闭域 inventory/unknown-path 规则保留，遇到未纳入其来源集合的编辑器文件仍会拒绝；
指南必须明确这一区别，不能将 configure 成功等同于 regeneration 已就绪。

### 4.3 栈与内存统计

模板 `.stack` 的低地址为 `__StackLimit`，高地址为 `__StackTop`；保留当前 heap/stack 默认容量，不更改用户 native linker。
断言对齐、顺序和与其它分配不重叠；不能通过修改原生脚本假装所有工程都已修复。

ELF section evidence 保留 alloc、VMA、size，并携带是否 `SHT_NOBITS`。容量统计：
alloc section 的 VMA 作为运行/预留容量；仅非 NOBITS section 的不同 LMA 才作为加载容量。
继续按每个 memory region 内的区间并集计量，保留 MAP/ELF 地址和大小一致性、范围/overflow 校验；不依段名猜测。
段间空隙不算 used；一个 section 内实际保留的空间仍算 used，不能把带空隙的 72,440-byte `.stack` 擅自缩为 4KB。
文档区分 linker allocated/reserved 与运行时峰值。报告中的 61,236/128,264 数字没有原始 ELF/MAP，不能作为已经复现的基准。

### 4.4 Doctor、context 与调试错误

Doctor 对 CubeMX/VS Code 等 GUI 工具复用 tool_support 的静态版本读取；无法静态取得版本则明确 unknown，
不能启动 GUI，也不能虚构版本。其它 CLI 工具保持既有有界探测。
VS Code 扩展不再通过启动 Code 枚举：保留现有三项与字段，未实测时为 `installed=false, version=null, status="not-probed"`，
并明确只有 `status=ok` 才表示实际探测到安装；不把未知写作 missing，不新增扩展扫描器或把 profile 配置当安装证明。
`probeCore.registry` 明确为 Probe 租约目录；missing 不等于没有 PyOCD targets，不能因此擅改 safe 判定。
Doctor 成功外层 details 增加 `probeRegistrySemantics="probe-lease-directory"`；
keil-inspect 仅在 includeBaseline=true 的成功外层 details 增加
`baselineSemantics="parseable-historical-artifact-only"`，不修改 KeilBaseline 持久/数据模型。
context 保持无隐式探针访问；成功的外层 details 固定增加 `capabilitySemantics="current-readiness"` 与
`hardwareDiscovery="not-performed"`，不改变 data.hardware 和 capabilities 原结构，明确 hardware 为未探测快照、capabilities 为当前 readiness，
不伪造最近探针数据，不加入新的持久缓存或隐式枚举。

完整 SVD 选择继续先验证每个寄存器的可信范围；`SVD_ADDRESS_OUT_OF_RANGE` details 增加首个失败寄存器完整路径、
地址、宽度/字节数、已配置可信区间。错误不得直接建议信任所有地址；用户需核对设备 SVD 和必要可信区域。
`SVD_SELECTION_REQUIRED` 提示 SVD 放在工程根内并配置相应字段。路径 containment 和读取时逐请求检查继续有效。
`DEBUG_FLASH_MISMATCH` 保持全部原比较条件，在 details 列失配字段名及 `elfContentMatches`；不给重新绑定旧 receipt 的入口。
后者仅比较经原验证流程读取的 receipt ELF 身份与当前 ELF，不是新的板上回读证明；无法可靠比较时为 null，不能猜 true/false。
损坏/不可读 receipt 继续沿原错误路径，不为凑齐诊断绕过验证或额外访问硬件。
相同 ELF 不表示 target/probe/session/授权相同；不能用改元数据或“强制成功”消除失配。
target-unsupported 提示准确的 requested target 和离线 `pyocd list --targets` 核对方法，不自动猜芯片别名、下载 pack 或访问目标。

flash 成功结果在外层 operation details 增加 `postFlash: {targetState: "unknown", runVerified: false}`，
说明只完成原编程/回读验证，尤其 recovery 模式不保证运行；不改 flash receipt/身份摘要，也不额外查询/控制硬件。
`resume-verify` 未达到 running 时保留失败，提示最后已验证状态和需要用户检查的运行/复位条件。
既有 recovery attach 保持 halted 的合同不变；Fault 继续区分运行观察与显式受控停核分析。

### 4.5 Monitor

保留 launcher 先从 `STM32_TOOLKIT_DATA_ROOT` 选择受管解释器的机制；CLI `--data-root` 不被描述成无效。
启动器错误明确缺的是 runtime 定位环境变量，指南提供暂设变量、传同一 CLI 路径、finally 恢复环境的完整示例。
不新写通用 cmd 参数解析器，不回退宿主 Python。前台 `open` 必须运行于可保持的用户终端；Ctrl-C 触发现有 finally/stop，
关闭网页或停止 sampling 不等于关闭服务，不指导删除 lock 文件或杀无关进程。

UI 至少区分缺失/非法 fragment 与 bootstrap 请求失败；网络不可达、服务拒绝可在实际有证据时区分，
不能只凭 fetch 失败断言服务未启动。错误文案为固定白名单文本，提示回到原终端核对并由 `open` 打开新的认证标签。
token、完整 fragment URL、服务端原始错误正文都不进入 DOM、控制台或日志；原有 fragment 清除和授权行为保持。
Host/Origin 只允许原有 `127.0.0.1:<port>`；localhost 仍拒绝，指南解释正确入口，不做危险自动跳转。

### 4.6 文档、schema 和版本来源

新增简短用户约束/故障入口，双语 README 链接配置、迁移、构建/观测、Monitor 和部署；历史设计/报告标明历史时间而不覆盖原事实。
公开当前各阶段规则：configure 的 presets/ELF/managedManifest、模型的路径 containment、SVD 内容验证、native linker/默认栈限制。
不把只属于 configure 的限制全局提升为 manifest loader 的不兼容校验。schema 说明若修改，根和 package 副本必须一致。
技能示例服从核心 CLI/MCP，不绕过 blocker，不把 `recoveryUnderReset` 描述为所有旧固件必须开启。

版本切片统一更新 Toolkit、Monitor、UI、插件、启动器、setup、release builder/policy 和当前用户指南为 1.0.1。
第三方依赖版本、许可证名称、历史版本证据、历史生成器版本不做字符串替换。
runtime Repair 的已知旧版本新增 1.0.0；保持唯一旧 runtime 判定、quarantine/promote/rollback、downgrade/source-conflict 拒绝。
generation producer 白名单保留 1.0.0 和 0.9.0，当前 producer 为 1.0.1；已有工程 generatedBy 不被伪造改写。
旧 managed 文件未被用户修改时经 configure 的显式事务刷新记账/需要的模板；旧用户改动仍先拒绝。
build 必须发布新的真实 1.0.1 身份；旧 receipt/evidence 不改写。数据路径、用户 groups/history 均保留。
release builder/policy 改变后同步 setup 中的可信 SHA256；锁文件只改项目版本及真实必要元数据。

## 5. 验证与发布边界

切片检查围绕上述行为、拒绝分支、旧行为和完整 diff，不在每个切片重复发布矩阵。
实现者和主代理分别对自己的执行负责；测试命令、退出码、CodeHead、原始结果需可定位。
临时文件、TEMP/TMP/TMPDIR、pytest basetemp/cache、UI 输出统一在 `D:\codex-tmp\tk101` 的短子目录。
缺 ELF/MAP、真实工程或硬件时如实记未取得，fixture 不写成原报告实机复现。

最终发布按现有 standard-test-procedure 和 release qualification 规则做新候选适用性判定。
Toolkit 整体/核心 90%、Monitor 整体 90%/核心 95% 的现行门槛不在本规格降低；RC4 的例外不能搬用。
不重新开启已停止的低收益覆盖率路线。若新候选仍未达门槛，提交实际数据与具体取舍，待新的明确决定；不宣布发布完成。
本规格不授权安装、真实硬件访问或远端变更。这些步骤先准备具体候选、证据/执行卡，再按 AGENTS.md 取得所需授权。
所有远端动作执行前再次检查 master/tag；基线变化先审查差异，不强推或覆盖既有标签。

工程经验应用：STM32TK-EL-001/002 保持 probe deadline 和 attach evidence 生命周期；EL-004 保持 recovery prepare 无硬件访问；
EL-007 将三项临时变量统一到短根。GL-001/003/004/005 为 active-provisional，作为合同冻结、独立审查和分层验证指导，不作产品事实。

## 6. 决策状态

本文件连同[实施计划](../plans/2026-10-10-stm32tk-101-patch-plan.md)已获用户批准并进入实现。
批准表示接受上述修复范围及明确保留的限制，不表示所有 22 项都作为缺陷修复，也不表示 v1.0.1 已实现/发布。
