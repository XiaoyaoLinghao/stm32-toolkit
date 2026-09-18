# VS10-B：新 CubeMX 工程真实板卡闭环

状态：DRAFT / OFFLINE_PREFLIGHT。本文不是已通过验收的声明，也不授予硬件、安装或远程权限。

## 1. 基线与责任

- 模块：`STM32TK-1002-CUBEMX-REAL-BOARD-CLOSED-LOOP`，阶段：VS10-B 规格与离线预检。
- 完整 accepted base：`16a6e59dff7fed2999fae611e3d936b0b04bbabd`；已核实为 GitHub `master`，包含 VS10-A 最终 `ACCEPTED` 附录。
- 已接受产品源码：`6e069660e4a5b62598f16637176caf086f82d3c8`；之后至 accepted base 仅文档变化。现有部署能否用于 B，按 release manifest/文件身份及 B 的依赖核对，不因报告提交重部署。
- 规格、计划、调度、集成及验收：主对话框；产品与工程实现、实现测试：一名 Luna/max；完整差异审查：未参与实现的主对话框/独立审查者。
- 设计分支：`codex/STM32TK-1002-CUBEMX-REAL-BOARD-design`；工作树：`D:\codex-tmp\v10b-0918\design`。生成工程、执行证据、cache、build 和后续实现/审查工作树全部位于 `D:\codex-tmp\v10b-0918`。
- 用户已同意推进 B，并确认沿用现有 BSMR-MC04 / STM32F429ZG 板和同一 CMSIS-DAP 探针，以 D4 闪烁验证运行。这是资产选择，不是新的现场状态证明。
- 本阶段无产品所有权例外；无新的 push、PR、merge、tag、Release 授权。VS10-A 截止验收的持续实机授权不自动延伸到 B。

## 2. 三个可运行场景与非目标

1. **新建并运行。** 从真实 CubeMX 请求产生新的 `.ioc` 和原生代码，经过现有 CreationPlan/授权/隔离生成/原子激活、configure 和 ARM Debug build，得到独立项目身份；在命名板上烧录、回读并证明应用运行和 D4 活性。
2. **可解释的受控失败。** 在 B 自己的正常工程中接入现有 Target v2 memory-mailbox。正常 Target run 通过；随后只引入限定的应用层 heartbeat 故障，保持 D4 主循环活性，由真实 failed TestRun 和相关 typed/SVD/Monitor 观测提供诊断依据。
3. **精确修复并复验。** Diagnostic 对真实证据评估，现有单次 source-change 授权绑定精确前后字节；重建、重新烧录后，在同一 B lineage 中得到 Target PASS、Monitor assertion 和 FixVerification，形成独立 bundle。

不重开 VS10-A，不重新实现 Project/Probe/Build/Monitor/Test/Diagnostic/Evidence，不引入第二个 scheduler、backend、transport、协议、授权系统或通用诊断框架。不升级到 50ms，不要求 RTT/UART/semihosting 实体资格，不自动发布 1.0。不用复制 Keil 工程冒充 CubeMX 原生创建，不用 fixture/replay/旧 TestRun 冒充 B 实机证据。

## 3. 资产与工程约束

离线资产已由独立只读核对确认；版本来源和仍缺的执行证据分开记录：

| 资产 | 当前事实 | 后续核验边界 |
|---|---|---|
| CubeMX | `D:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe`；文件版本 `6.18.1-RC2`，注册表 `6.18.1` | 支持族为 6.18.x；prepare 时固定真实工具/环境摘要，不抹去 RC2 差异 |
| Java | 同安装目录 `jre\bin\java.exe`，文件版本 `21.0.10.0` | 使用捆绑 Java，不引入 PATH 中另一 Java |
| CubeCLT | `C:\ST\STM32CubeCLT_1.22.0`；现有工具发现入口已返回 GCC `14.3.1`、CMake `4.3.1`、Ninja `1.13.2` 及各 executable SHA256 | 结果来源标记为 `cubeclt-metadata`，不冒充尚未进行的编译/链接；prepare 重新固定实际文件 |
| MCU/native HAL | CubeMX `db\mcu\STM32F429Z(E-G)Tx.xml`、F4 GPIO/RCC/TIM 模板；`C:\Users\ZhangYang\STM32Cube\Repository\STM32Cube_FW_F4_V1.28.3` | 只读共享安装/包；prepare 冻结唯一匹配的描述文件和包目录摘要 |
| 引脚来源 | `D:\workspace\stm32-toolkit\BSMR-MC04.PDF` 与归档 SHA256 `e14a70e9e49f7ce6e0285a687f215f591bb1f53d6322f6d32a5e4052c92f1af1` 一致；既有标准流程确认 D3=PE3、D4=PE4，均 active-low | 不推导其他 GPIO 用途；不重新访问板子来确认同一离线结论 |
| Probe 历史身份 | hash `5157ce5dfaee369c1a49c1acf7a2a58fbcb44be85b5f67d1989e8105290bbe3d`，target `stm32f429zgtx` | 只是 A 归档基线；B 实机前必须取得自己的当前身份和 lease |

SVD 已核实：`C:\ST\STM32CubeCLT_1.22.0\STMicroelectronics_CMSIS_SVD\STM32F429.svd` 与 A 的工程副本一致，SHA256 为 `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`。DFP `Keil.STM32F4xx_DFP.2.17.1` 目前只有 A manifest 的声明，限定的当前安装/归档元数据中未找到可证明该版本的 `.pack/.pdsc` 路径/哈希。B 不照搬该声明；原生创建使用已定位的 HAL 包/MCU XML。实机前须由实际 support profile 证明 PyOCD target/backend 的可用映射；若确实需要 pack，先补齐确切文件事实。不得将这一未知项改写为全局缺失或直接下载安装。

- 板卡选择：现有 BSMR-MC04、STM32F429ZG；具体 MCU package、Probe 选择器、DFP/SVD、工具版本、安装路径与文件指纹在离线预检中固定。下一次物理操作前重新核对现场与板/探针身份。
- 工程必须位于新的 B root，使用新的 workspace/session/data/evidence 名称，保留自己的 no-remote Git 历史、source snapshots、build ID、ELF SHA、CreationPlan 和 ownership manifest。A 的 runtime 可只读复用；A 的 workspace/session/flash receipt/lease/action 不可复用。
- 只配置已证实用于 LED 与 SWD 的引脚。不得驱动电机、继电器、机械负载、电源控制或不明外设；时钟、内存、启动文件和 linker 由实际 `.ioc`/原生输出/ELF 证明。
- CubeMX 管理区、Toolkit 生成区和用户 `App/Tests` 区的所有权分开；不得通过覆盖托管文件回避 regeneration/ownership 冲突。应用逻辑与 Target emitter 进入明确的用户代码区域。

### 创建请求与已执行的最小离线验证

固定使用现有 MCU 模式：`source.kind=mcu`、`source.value=STM32F429ZGTX`、`framework=hal`、`language=c`、`overwrite=refuse`。父工作区为 `D:\codex-tmp\v10b-0918\p`，生成目的地相对路径 `b`，B 工程为其 `b` 子目录；实际写入前建立可恢复 Git HEAD。

2026-09-18 主代理已使用已部署 source `6e069660...` 的真实公共 CLI 执行一次只读 `project create-plan`，返回 `OK`、`mutated=false`、`blockers=[]`，父工作区仍为空。原始 argv/stdout/stderr/exit 位于 `D:\codex-tmp\v10b-0918\evidence\create-plan-*`。这是入口与工具支持计划的离线证据，未调用 `create-prepare/create-apply`、未运行 CubeMX、未构建，也未访问硬件。

现有 prepare 才要求 Git HEAD 并绑定 native environment；apply 消费单次授权，在 sibling staging 生成，验证 native CMake/MCU/内存/包/ownership，依次配置并构建 Debug 与 Release，最后原子激活。本次临时 plan 已有有效期，实施时必须重新 plan/prepare，不能消费此历史 actionDigest。

由于 plan envelope 只保留 toolProfileDigest，主代理另直接调用现有 `discover_tool_support` 保存完整只读结果，未增加诊断脚本/框架。`evidence/tool-support.stdout.json` 确认上述工具版本/哈希，同时返回 `VSCODE_INVALID`、`vsCode=null`。此问题未阻断本次 create-plan；不能因此宣称 IDE 环境 READY。后续若执行 B 的真实 IDE 场景，必须先独立修复并核验此入口，不在本轮凭旧 A 的 VS Code 成功记录抹去它。

### 固件用户场景

采用现有 D3 heartbeat 故障模式，保持 D4 作为独立的主循环活性指示：正常状态 D3/PE3 与 D4/PE4 交替闪烁，故障只将周期 D3 翻转替换为写低（D3 常亮），D4 继续翻转。修复只恢复同一周期 D3 翻转语句。三种状态的时基、D4 控制、Target emitter、case ID 与内存布局保持一致。

用户区定义 `volatile uint32_t testtime`；10ms tick 为已有 emitter 提供真实单调时基，500ms LED 周期可产生可观察翻转。Target case 复用 `d3-heartbeat` 的语义和 v2 case-inventory digest 算法，判断真实时基活动及 PE3 变化；不把自身期待值或预先生成 JSON 当采样结果。HAL 用户代码使用 PE3/PE4 实际 ODR，不能照搬 A 的 SPL `GPO.h` 依赖。

无 RTOS、联网外设或新调试 transport。原生 startup/clock/linker 必须通过构建产物检查，不能仅依据 `.ioc` 声称 MCU 已正确运行。正常与故障版本都不得以阻塞延时或 Target 终态结束而停止 D4 主循环。

## 4. 唯一权威与冻结契约

| 状态 | 唯一权威 | B 的限制 |
|---|---|---|
| 创建请求、工具事实、生成输入 | 现有 CreationPlan 与 native tool inventory | 只读 plan；授权后重新校验 input/tool/destination；隔离 staging，验证原生输出后原子激活 |
| 工程配置及生成所有权 | Project schema / ownership manifest | 不私改生成指纹，不复用 A 的 project identity |
| 可执行固件与符号 | BuildResult、ELF/MAP、FirmwareIdentity | 每次源修改产生新的事实；先验证内存/入口/符号再做硬件动作 |
| Probe 状态与互斥 | 现有 Probe service/registry/lease | 串行持有；不抢占 IDE、不 kill 外部进程，不用枚举作为离线检查 |
| Target 结果 | 现有 TestRun 与原始 v2 bytes | `physical` 只能由真实 transport 得到；host 绑定身份，target 不自报 ELF/Git/UTC |
| 观察与断言 | 现有 Monitor history/snapshot/assertion | 两项同批、同一 firmware/project/probe identity；不把用户灯态当机器采样 |
| 诊断、授权修复与验收进度 | 现有 Diagnostic / FixVerification / AcceptanceAttempt | B 使用自己的 scenario/policy 与前后证据，CAS、single-use、closed schema 与不可变 checkpoint 不变 |
| 人工目视 | 用户现场反馈 | 只作明确署名的质性佐证，不伪造光学周期或采样数据 |

依赖方向保持 `CLI/MCP → 现有领域服务 → 唯一 Probe/native adapter`。Cortex-Debug 通过已有一次性 handoff ticket 交接所有权；不增加 Agent 专用领域逻辑。

### Target 与连续观察

- 使用既有 `stm32-target-frame/2`，host-bound identity、frame/CRC/sequence/digest/monotonic 规则保持不变；v1 兼容不变。参考物理 transport 仅 `memory-mailbox`，禁止 host 写入 mailbox。
- B 的 mailbox 固定候选布局为 `0x2002EFF0..0x20030000`：16-byte header 加 4096-byte ring，`NOLOAD`、16-byte aligned、KEEP 和 exact-size ASSERT。B 的实际 native 内存图、linker/MAP/ELF 必须证明该 SRAM 范围、普通 RAM/stack/heap 不重叠及唯一对象；不满足则停止并返回规格决策，不能静默改地址或只依据 A 的 MAP 宣称通过。
- 正常 prepare 与显式 recovery 是不同产品路径。若选用现有 recovery，prepare 仅绑定静态事实；execute 单次消费授权、重新校验、创建唯一 MODIFY owner、attach/证实身份后至多烧录一次。失败终态，不退回另一策略盲试。
- flash/readback 与应用运行是不同结论；有限操作必须通过已接受的公共启动/状态验证入口证明最终 running，并记录 lease/worker/进程退出。
- 连接时短暂停核可接受；连续采样期间不得 halt/reset/resume。有限 activity smoke 与 100ms 周期资格分开，不以 standalone `read sample` 的 scheduled slots 代替 delivered batches。
- B 的 failed-before/fixed-after 各保留一个完整 30 秒、100ms 测量窗口。既有实用门槛：至少 297 个完整有效 batch、9.9 batch/s；相邻 capture P95 ≤110ms、P99 ≤150ms；scheduled-to-captured P95 ≤100ms；deadline drops ≤3，service/history/subscriber drops 为 0。保留全部窗口和最大间隔，不修剪失败样本；不承诺硬实时。
- 两侧每个完整 batch 同时含 `testtime` 与 `GPIOE.ODR`：testtime 至少两个不同有效值、PE4 同时出现 0/1；failed-before 的 PE3 仅为 0，fixed-after 的 PE3 同时出现 0/1。周期统计使用相同窗口中全部单调 capture 时间与 nearest-rank；目视只验证灯态，不代替这些机器判定。

### 诊断修复顺序

先保留 B 的真实 failed TestRun 和故障表现，再创建 Diagnostic、依据观测评估假设；固定 source intent 的路径/前后哈希/派生 InputSnapshot/intentDigest，单次授权后才写入修复。after build/ELF 必须为新事实，使用新的 Target/flash action，不能由 source-change 授权代替。FixVerification 只在 B 的 before/after project、workspace、Probe、target 与约定 lineage 匹配时通过。

### B 的最小产品扩展（本规格新增行为）

源码核对已确认：`acceptance/recovery.py` 的 `/2` 模型和 policy、`recovery_workflows.py` 的 physical begin/chain 路由绑定 `legacy-keil-physical-repair` 与 `projectOrigin=keil`；`new-cubemx-project/1` 属于 v1 software-replay。B 无法直接使用这些身份形成真实 physical attempt。

冻结以下唯一新增组合；这些值是待实现方案，不是当前已存在能力：

| 字段 | B 固定值 |
|---|---|
| attempt schema | `stm32-acceptance-attempt/3` |
| recovery policy schema | `stm32-acceptance-recovery-policy/3` |
| scenarioId / version | `new-cubemx-physical-repair` / `1` |
| projectOrigin | `cubemx` |
| executionSource / transport | `physical` / `mailbox` |
| physicalTransportEvidence | 实际物理证据到达后按原 stage/revision 条件成立；不得在 begin 阶段伪造 |

沿用六个阶段及 timeout（秒）：`project-materialized:60` → `firmware-built-before:900` → `target-failure-observed:300` → `diagnosis-completed:900` → `firmware-built-after:900` → `target-fix-verified:300`。stage outputs、sourceChangeIntent/1、Evidence root/CAS、失败终态、精确授权消费及 FixVerification 规则不变。scenario digest 使用现有 canonical JSON 算法，对 B 的 scenario/version/origin/source/transport/stages 文档求 SHA256；policy digest 使用相同现有算法绑定 `/3` schema、B scenario digest、上述 timeout 和既有 intrusive-action 规则。B 的硬件授权仍由 Target/Probe 层产生，acceptance adapter 不访问硬件。

只通过 schema/scenario 的固定配对选择 A、B 两组封闭 profile；不增加配置驱动的注册器、插件或任意 origin。A `/2` 输出、digest、读取兼容和旧记录验证保持原样；v1 `new-cubemx-project` 继续 replay，不能得到 physical flags。错误复用现有 input-invalid、identity-mismatch、stage/expiry、authorization/consumed、CAS 语义，不为本次准备泛化新错误码。

B 首个切片使用 fresh `/3` attempt，不扩展 A-only continuation。CLI 使用现有 `acceptance attempt` 命令及新 scenario；MCP 只扩 `AcceptanceAttemptScenarioId`，不修改软件 AcceptanceScenarioId/AcceptanceRecord。创建授权、`.ioc`、native inventory 和 ownership provenance 仍由创建/工程 manifest 持有，并在 B bundle 引用；不向 attempt 添加 `creationAuthorizationDigest` 或自由字段。

最小产品文件：`acceptance/recovery.py`、`acceptance/recovery_workflows.py`、必要的 `acceptance/__init__.py` 导出，以及 `mcp_server.py` 的 attempt enum。不修改 CubeMXAdapter/creation_apply、replay model、Diagnostic pair validator 或 Probe/Monitor 协议。若出现这些边界以外的真实阻塞，由主对话框先给出原因与新边界，不能让实现者自行扩张。

## 5. 验证范围与停止条件

| 层级 | 本轮要求 | 证据责任 |
|---|---|---|
| 规格/离线资产 | 明确真实 native tool、创建 request、支持的 MCU、实际入口、可写目录及未决项 | 主对话框 + 有界只读审查 |
| 实现 | 只测试新增/改变的场景映射、工程用户区与必要回归；不重跑未变全矩阵 | Luna/max，保留 exact command/stdout/exit/commit |
| 原生生成与构建 | 真 CubeMX 输出、manifest ownership、可重复构建、ELF/MAP/向量/入口/符号/内存资格 | Luna/max 实现，主对话框独立核对 |
| 实机 B | 新项目正常→故障→诊断→授权修复→fixed-after，Target/Monitor/退出状态全部关联 | 主对话框串行；独立证据审查 |
| 入口绑定 | B 的 CLI/MCP project/firmware 行为；若声明 IDE 验证，使用 B 新生成配置执行真实 handoff | 实际执行者，不借用 A 的 UI 结果 |
| 归档 | request/.ioc、CreationPlan、生成库存、ownership、build/firmware、Target/Monitor/Diagnostic/修复、完整身份与 sorted SHA256 manifest | 主对话框归档，独立审查 |

A 的共享协议、Probe/handoff、0.9 安装/升级/安全/包、UI 和既有硬件证据按原身份与版本范围保留。只有相关源码、依赖、配置、环境或契约发生变化时前移受影响检查；B 的新工程生成与物理结果必须实际产生。完整 1.0 发布矩阵、tag/Release 是后续独立阶段。

首个非预期错误停止当前执行卡，不继续烧录/连接/恢复；保存原始错误、阶段、身份、stdout/stderr 与清理终态，先分类 PRODUCT/ENVIRONMENT/INFRASTRUCTURE/HARDWARE/REPORT。预设应用 heartbeat 断言失败仅能继续预先规定的诊断链；超时、身份错误、transport 错误或目标不运行不是预期故障。

所有本轮进程同时固定 `TEMP/TMP/TMPDIR` 和 pytest/cache/build/output 根到 B 短目录。只清理已归属的 B 一次性产物，保留工程源码、当前构建/恢复镜像、有效证据与最小失败证据。A 的保留例外不外推到 B；策略拒绝就记录保留，不绕过。

## 6. 本阶段出口

当前工作完成的条件是：资产和入口事实具名、最小产品缺口明确定义、自包含规格/计划及文件所有权写明并经独立审查。规格获批后才能交 Luna/max 开始实施；实机前另有具体操作卡和 B 的授权边界。`DRAFT/OFFLINE_PREFLIGHT`、`SOFTWARE_READY`、`HARDWARE_PENDING` 与 `ACCEPTED` 不混用。

本规格采用的本地工程经验：GL-001（active-provisional，先冻结共享契约）；STM32TK-EL-004（active，recovery prepare 不访问硬件）；STM32TK-EL-007（active-provisional，三项临时目录变量同时绑定）；STM32TK-EL-008（active-provisional，测试结论必须有实际执行证据）。这些经验决定预检、实现和留证边界，不替代项目当前源码与本次实机证据。
