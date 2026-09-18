# VS10-B 实施计划：真实 CubeMX 工程与物理修复闭环

状态：APPROVED / IMPLEMENTATION_IN_PROGRESS。用户于 2026-09-18 指示“开始实施”，批准已审查的规格与计划；本轮派发两个互不重叠的 Luna/max 实现责任，硬件与远程边界不变。

规格：[VS10-B 设计](../specs/2026-09-18-stm32-toolkit-1002-cubemx-real-board-closed-loop-design.md)。完整 accepted base：`16a6e59dff7fed2999fae611e3d936b0b04bbabd`。主对话框直接拥有集成、分工和验收；没有代理领导层。旧 VS10-A 的 `ACCEPTED`、历史失败及清理保留决定保持原样。

## 1. 当前事实与立即出口

- 已从 accepted base 建立 `D:\codex-tmp\v10b-0918\design`，分支 `codex/STM32TK-1002-CUBEMX-REAL-BOARD-design`。
- 用户确认沿用 BSMR-MC04 / STM32F429ZG / 同一 CMSIS-DAP；这不是连接状态确认。
- CubeMX、捆绑 Java、CubeCLT、HAL F4 包及 MCU 描述文件存在；版本来源及 DFP/SVD 限制见规格。
- 已部署真实 CLI 的 `project create-plan` 已执行一次，HAL/C、STM32F429ZGTX、目的地 `b`，返回 `OK / mutated=false / blockers=[]`；父工程目录仍为空。证据位于 `D:\codex-tmp\v10b-0918\evidence\create-plan-*`。
- 未调用 prepare/apply，未生成/构建 B 固件，未访问硬件，未安装工具或修改远程。
- 当前 physical AcceptanceAttempt 的场景、origin 和路由为 legacy Keil 专属；现有 `new-cubemx-project` 是 software-replay。B 的物理能力不能由替换报告标签获得。

本阶段完成离线事实、最小扩展契约与独立规格审查。规格批准后进入下面的执行波次；未批准前不派发产品或工程实现。

## 2. 固定工作区与所有权

| 责任 | 执行者 | 独占范围 |
|---|---|---|
| 规格/计划/标准流程衔接/集成与判定 | 主对话框 | 本文、规格、接受报告；只有主对话框调度子任务和操作硬件 |
| B 物理场景的最小产品适配 | 一名 Luna/max | 规格冻结的 AcceptanceAttempt policy/model/routing 与必要测试；共享 schema/公共入口仅此一人修改 |
| CubeMX 原生工程和 HAL 用户区 | 另一名 Luna/max | `D:\codex-tmp\v10b-0918\p` 及其独立 no-remote 工程；另独占已确证阻塞的 `native-fix` 工作树 `creation_environment.py`/相关测试，不写 host 适配文件 |
| 独立审查 | 未参与相应实现的主对话框/审查者 | clean review worktree、完整 accepted-base 到实现 head 的差异与证据；实现者不能接受自己的结果 |
| 证据与清理 | 主对话框 | B 的 evidence/bundle/执行卡与一次性产物归属；A 归档和保留路径不可写 |

所有实现者被告知并非独占整个代码库，禁止回退他人修改。禁止递归委派。只读探索完成后不保留同一责任的重复执行者。核心适配与工程准备可并行，因为协议、case、origin、身份和用户区边界已冻结；任何共享契约变化先回主对话框，不能靠增加代理协调修补。

目录均在 `D:\codex-tmp\v10b-0918` 下：`impl` / `review`（Toolkit 工作树），`p`（no-remote 父工作区），`p\b`（真实 CubeMX 工程），`evidence`，`.stm32-toolkit-data`（创建 CLI 实际数据根），`data`（后续服务/验收），短 `t`/`c`（一次性测试/cache）。工具进程同时设置 `TEMP/TMP/TMPDIR`。任何路径不足改短子目录，不写驱动器根目录或旧 C temp/tmp。

## 3. 波次一：软件适配与真实工程准备并行

### 3.1 Luna 产品适配

在 exact accepted base 的新 clean worktree 上，只实现 `new-cubemx-physical-repair/1`、`cubemx`、attempt `/4` / recovery policy `/3` 的固定配对。实施预检发现 A continuation 已占用 attempt `/3`，故 B 使用 `/4`；这是防止覆盖已有合同的编号纠正，不新增行为。保留 legacy Keil `/2`、A continuation `/3` 各 profile/digest/旧记录字节和软件 `new-cubemx-project/1` replay 的行为。只复用已有六阶段物理链，不增加 B continuation。

允许修改的产品文件（前缀为 `tools/stm32-toolkit/src/stm32_toolkit/`）：`acceptance/recovery.py`、`acceptance/recovery_workflows.py`、必要的 `acceptance/__init__.py`、`mcp_server.py`。`cli.py` 的 scenario 参数没有封闭 allowlist，预计无需更改；若确需更改，先给出现有入口不足的最小证据。`acceptance/model.py`、`continuation.py`、CubeMX adapter/creation apply 和 Diagnostic pair validator 保持其现有边界。

复用并扩展的测试（位于 `tools/stm32-toolkit/tests/`）：`test_acceptance_recovery_model.py`、`test_acceptance_physical_recovery.py`、`test_acceptance_recovery_cli.py`、`test_acceptance_recovery_mcp.py`；必要时在现有 CubeMX creation seam 加一个 origin=cubemx 与 B profile 的集成案例。A-only continuation 的现有测试增加 B 拒绝覆盖，不能为此重写 continuation。无新通用测试框架。

必要验证必须直接调用现有模型/工作流/CLI/MCP 测试入口：

1. 新 B profile 的合法生成、序列化、存储重载和公共入口路由；非法 scenario/schema/origin 配对拒绝。验证 A `/2`、A continuation `/3`、B `/4`、replay `/1` 共存且不会误分流，保留旧版有效 payload/digest 作为兼容性断言。
2. 相同 source/build/firmware identity 下，正常、failed-before、Diagnostic/source-intent、fixed-after、FixVerification 的现有物理链可用于 B。
3. A 与 B 跨项目/场景/构建/授权混用拒绝；expired/single-use/CAS/并发 winner 与 cleanup 契约不变。
4. 现有 replay 场景仍是 software/replay，不获得 physical flags；A 的现有回归按触及文件补最小集合。

测试替身证明软件契约，不能计为 B 实机 PASS。不要增加新的 controller、Evidence store、临时 CLI 子命令、诊断框架或另一套 JSON schema 家族。实现返回源码 head、完整 diff、实际 argv/stdout/exit、环境和已清理/保留项，不提供无原始记录支持的累计测试数。

### 3.2 Luna CubeMX 工程准备

首次 prepare 已终态拒绝真实 CubeMX 的分组 descriptor，apply 未调用。先按规格新增的“索引映射到分组 MCU 描述文件”边界修复现有环境解析器：同一工程实现者独占 `native-fix` 工作树（accepted base 不变）中的 `creation_environment.py`、`test_creation_environment.py`，必要时仅扩现有 `test_cubemx_adapter.py` / `test_creation_workflows.py` 的 token 与授权环境漂移用例。独立完整 diff/受影响验证通过后，以此已冻结 source CLI 而非修改已部署文件再执行以下创建步骤。原失败、parent Git `13735e863f5680d8a5ff0665e6b1ad0f559008e3` 与空目的地保持；不得重用前次 action。

1. 在 `p` 建立最小可恢复 Git HEAD/no remote；记录空目的地 `b`。复用现有 tool discovery，固定 CubeMX 文件/Java/MCU XML/HAL package 与 GCC/CMake/Ninja 的实际版本和哈希。IDE 工具发现已有 B `data/tool-path-overrides.json` 绑定 D 盘 VS Code；不能将 Python 发现函数的 profile/data root 参数直接视为 CLI 各命令均支持。不安装/升级缺失项，不改共享包或全局配置。
2. 创建 CLI 三步统一使用默认发现，不传 `--support-profile`；实际 data root 为 `p` 的父目录下 `.stm32-toolkit-data`、session 固定 `cli`。重新调用 `project create-plan`，不得使用前期已过期或不同 tool-profile 的 plan/action；再使用其精确 `plan-id/action-digest` 调用 `create-prepare`，核对 environment digest，最后单次 `create-apply --authorization-digest ... --authorized`。VS Code 的默认发现错误不是 creation blocker；显式 IDE profile 留到独立 IDE 预检使用，不在缺少该参数的 apply 前混换 profile。所有命令保存 stdout/stderr/exit；无需手写 CubeMX 启动脚本，因为现有 adapter 已拥有这个责任。
3. apply 必须真实运行 CubeMX，native inspection、configure、Debug/Release build 和原子激活全部成功才算原生创建完成。失败先分类并保留 staging 最小证据，不复制 fixture 伪造成功，不自动改用导入 Keil 路线。
4. 建立 B 的独立工程 Git 基线；保留 `.ioc`、CreationPlan、GenerationResult、ownership manifest、project origin=cubemx、logicalProjectId、工具/输入指纹及生成库存。apply 的 staging build 只证明创建门通过；激活与工程源码提交后重新构建，用实际最终 project root/Git/input snapshot 产生后续固件身份，不能将 staging 或提交前身份用于烧录。
5. 按规格“创建后工程定制”完成唯一配置提交：补全 debug/backend/target/SVD/只读区域、testing.target 的实际 ELF/60秒/v2/mailbox 字段；在 `build.sources/includePaths` 显式登记 `App/Tests`；在 USER CODE hook 接入 HAL LED/timebase/emitter，D3 为唯一故障。原始生成库存保留作来源，不伪改其哈希；定制 manifest、hook 和所有用户源码完整进入工程 Git。仅通过现有 configure plan/apply 更新 Toolkit 管理清单，实际构建证明用户源码已链接。
6. 执行规格明确要求用户批准的 B 工程级 linker 所有权迁移：保留原 CubeMX linker，按其精确字节派生 `App/Linker/vs10b.ld`，仅作普通 RAM/stack 顶部到 `0x2002EFF0` 的保留区调整及 mailbox 段/ASSERT，同步完整 `memory.regions` 与 `generation.nativeLinkerScript`。transport 为 `address=0x2002EFF0`、`size=4096`，总对象为4112。经现有 configure/build，逐项核对 ELF/MAP/startup/vector/SP/reset/main、testtime、ODR、唯一段/对齐/大小/非重叠与内存余量。独立审查来源哈希和完整差异。当前没有 overlay 功能；定制后不运行 regenerate，不声明自动保留这些增量。
7. 建立可恢复的正常/故障提交，预先审查唯一修复 diff；故障只改变周期 D3 toggle 为写低，修复只恢复该语句。此阶段只保存修复方案，不提前落地 actual fixed-after source/build。真实诊断与单次 source-change 授权消费后才写入修复、提交并构建，以保证 before/after 时间和身份链真实。保留各自实际产生的 input snapshots/build IDs/ELF hashes；固定后不再修改入口、时钟、case 或 mailbox。

任何代码修复必须有最小可复现差异和对应验证。若真实 CubeMX 生成暴露另一个核心模块缺陷，先由主对话框冻结该独立问题的文件/行为/测试边界，仍使用 Luna/max 实现；不让两位执行者同时修改核心配置或公共类型。

## 4. 波次二：集成审查与实机准备

- 独立审查完整产品适配 diff 和完整 B 用户区 diff；源代码、项目 provenance、工具链和依赖与事实一致才进入下一阶段。
- 如 Toolkit 产品字节变化，仅部署已审查新候选；使用 B 的 runtime/data 根，核对 package/manifest/sourceCommit/启动器。保持 A runtime、receipt、workspace 和 bundle 原样。产品字节未变则复用已核实部署，不为了报告重打包。
- 先通过公共 B 物理入口的离线集成检查，再填一张执行卡：完整 toolkit/runtime/firmware/tool/probe identities、B session、target 前置、精确动作及次数、预算、成功/失败停止条件和 cleanup owner。
- 将实际 `.stm32-project.json` SHA256/Git/InputSnapshot 列入身份核对；managed model hash 未包含 testing，不能独自充当 Target 配置完整证明。IDE 预检用现有显式 profile/doctor 入口；实际 handoff 使用当次 `cortexDebugLaunch` 与 companion/ticket，初始空 launch 不是 READY。
- 此时才申请 B 的明确有限实机授权与现场状态确认。A 截止验收的授权不延用。旧 ticket/action/lease 不复活，prepare/execute 参数必须来自当次新事实。
- 阶段 READY 只代表入口、资产、候选与授权准备完成；没有硬件结果就保持 HARDWARE_PENDING。

## 5. 波次三：串行实机闭环

在一张冻结执行卡内预先列明整条顺序及所有预算，避免临场逐条拼接测试：

1. 新工程基本运行资格：公共 flash/readback/start、最终 running、D4 活性、testtime 与 PE4；确认真实 CubeMX 生成的程序能运行。
2. 正常 B Target：新 inventory/prepare/execute，真实 mailbox `physical` PASS；声明物理资格只基于 B 的新身份。同一正常固件上用 B 生成配置完成一次真实 IDE attach/Watch/detach/reacquire，确认能查看 testtime，并在退出后证明程序恢复活动；不在故障/修复版本重复交接。
3. failed-before：部署唯一故障版本，预期仅 D3 heartbeat failed，D4 与时基持续活动；30 秒/100ms 同批 Monitor 留证，实际窗口/功能/速率分别判定。
4. 现有 Diagnostic/AcceptanceAttempt：从真实失败创建/绑定诊断，评估证据，精确 source intent 单次授权修复；after build 与新动作贯通到 fixed-after Target PASS、30 秒/100ms Monitor 和 FixVerification。
5. B 的 CLI/MCP 身份绑定采用最小有限只读检查。所有硬件入口使用 B 的当次新 ticket/action，Probe 一次只有一个 owner，正常退出后证明 released/所属进程退出/应用活动。IDE 原生操作由实际操作人留证，无法获得该操作时保持对应验收项 PENDING，不以旧 A 结果代替。

所有非预期失败立即停止整张卡，保留原始错误/阶段/终态。只允许预先声明的 D3 应用失败继续诊断，禁止把 hardware timeout、identity drift、Fault、attach 或释放错误当作该预期失败。诊断修正后的下一次运行使用新卡/新授权事实，不能盲重试。

## 6. B 验收及后继

独立 B bundle 包含创建链和正常/失败/修复链，各条引用确切代码、工程、固件、工具、Probe、session、TestRun、Diagnostic、授权摘要、时间与实际 owner；原始日志与终态明确，checksum manifest 采用确定顺序。实现者不接受自己的结果。

验收条件是三个用户场景通过、缺口闭合且完整差异审查无未解决问题；不是测试数量或文档数量。没有真实 CubeMX 生成/构建、物理链或必要恢复/退出证明，不得给 `ACCEPTED`。

VS10-B `ACCEPTED` 后另行决定整合 A+B 的 1.0 发布级验证。VS09-B/VS10-A 未变证据按原 scope 复用；只对变化或明确风险运行 Python/UI/package/install/upgrade/security/license/SBOM/compatibility 对应检查。远程 push/PR/merge/tag/Release 逐项授权。

## 7. 设计审查记录（2026-09-18）

独立审查者 `/root/vs10a_target_review` 已审查 accepted base 至草案 `e13dd69a3cc87b0128d577cfcf7b143f888aa694`，以及该草案至修订稿 `c9d99e8ce4cb0114e0c4d3397a2de8d7a13f9b41` 的连续完整文档差异。首轮配置、native linker、用户源码接入、mailbox size 四项 finding 均已闭合，结论为 `ACCEPTED（仅针对本次 B 设计决策）`。未运行实现测试或硬件；这个结论不代替用户批准，不是 VS10-B 产品验收。

实施仍须真实 create/apply 后保存原始生成库存，定制后执行公共 configure/build，并冻结定制工程不进行 regenerate。这三项是实施门槛，不能在报告中预先标为完成。

实施预检发现首版 B attempt `/3` 与已发布 A continuation `/3` 冲突，已将 B attempt 唯一改为 `/4`，policy 仍 `/3`。同一独立审查者已核对占用和入口路由，结论为 `ACCEPTED（仅针对编号修订和路由设计）`；begin 按 scenario、checkpoint/authorize/show/resume 按精确 schema 分流，未知 schema 拒绝。此修订保持用户批准的 B 行为和旧契约，未扩张模块或权限。
