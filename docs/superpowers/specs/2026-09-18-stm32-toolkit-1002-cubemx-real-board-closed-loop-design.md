# VS10-B：新 CubeMX 工程真实板卡闭环

状态：APPROVED / IMPLEMENTATION_IN_PROGRESS。用户于 2026-09-18 在审阅规格与计划后指示“开始实施”；该批准覆盖本规格的 B 场景适配与工程级所有权迁移。本文不是已通过产品验收的声明，也不授予硬件、安装或远程权限。

## 1. 基线与责任

- 模块：`STM32TK-1002-CUBEMX-REAL-BOARD-CLOSED-LOOP`，阶段：VS10-B 规格与离线预检。
- 完整 accepted base：`16a6e59dff7fed2999fae611e3d936b0b04bbabd`；已核实为 GitHub `master`，包含 VS10-A 最终 `ACCEPTED` 附录。
- 已接受产品源码：`6e069660e4a5b62598f16637176caf086f82d3c8`；之后至 accepted base 仅文档变化。现有部署能否用于 B，按 release manifest/文件身份及 B 的依赖核对，不因报告提交重部署。
- 规格、计划、调度、集成及验收：主对话框；产品适配与独立工程准备各由唯一 Luna/max 负责，实现者拥有其实现测试；完整差异审查：未参与实现的主对话框/独立审查者。
- 设计分支：`codex/STM32TK-1002-CUBEMX-REAL-BOARD-design`；工作树：`D:\codex-tmp\v10b-0918\design`。生成工程、执行证据、cache、build 和后续实现/审查工作树全部位于 `D:\codex-tmp\v10b-0918`。
- 用户已同意推进 B，并确认沿用现有 BSMR-MC04 / STM32F429ZG 板和同一 CMSIS-DAP 探针，以 D4 闪烁验证运行。这是资产选择，不是新的现场状态证明。
- 本阶段无产品所有权例外；无新的 push、PR、merge、tag、Release 授权。VS10-A 截止验收的持续实机授权不自动延伸到 B。

## 2. 三个可运行场景与非目标

1. **新建并运行。** 从真实 CubeMX 请求产生新的 `.ioc` 和原生代码，经过现有 CreationPlan/授权/隔离生成/原子激活、configure 和 ARM Debug build，得到独立项目身份；在命名板上烧录、回读并证明应用运行和 D4 活性。
2. **可解释的受控失败。** 在 B 自己的正常工程中接入现有 Target v2 memory-mailbox。正常 Target run 通过；随后只引入限定的应用层 heartbeat 故障，保持 D4 主循环活性，由真实 failed TestRun 和相关 typed/SVD/Monitor 观测提供诊断依据。
3. **精确修复并复验。** Diagnostic 对真实证据评估，现有单次 source-change 授权绑定精确前后字节；重建、重新烧录后，在同一 B lineage 中得到 Target PASS、Monitor assertion 和 FixVerification，形成独立 bundle。

不重开 VS10-A，不重新实现 Project/Probe/Build/Monitor/Test/Diagnostic/Evidence，不引入第二个 scheduler、backend、transport、协议、授权系统或通用诊断框架。不升级到 50ms，不要求 RTT/UART/semihosting 实体资格，不自动发布 1.0。不用复制 Keil 工程冒充 CubeMX 原生创建，不用 fixture/replay/旧 TestRun 冒充 B 实机证据。

本切片不验收定制后的 CubeMX regenerate；既有安全重生成的独立软件证据保持其原范围。B 在原生创建完成后作下面明确的工程定制并冻结；不宣称这些增量能被当前 regenerate 合并保留。

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

2026-09-18 实施期只读依赖核对已补齐当前事实：B 使用已安装的 `Keil.STM32F4xx_DFP.3.1.1`，pack 为 `C:\Users\ZhangYang\AppData\Local\cmsis-pack-manager\cmsis-pack-manager\Keil\STM32F4xx_DFP\3.1.1.pack`，SHA256 `345231106fe697df24bbe9133aeeec1b0383d7891c4adf4f47bbb8b478e9f2f0`。当前 index/PDSC 精确列出 `STM32F429ZGTx`、1 MiB Flash、192 KiB SRAM 加64 KiB CCM 及 `STM32F4xx_1024.FLM`；PyOCD内置表没有精确 `stm32f429zgtx`，该名字由pack注册。B明确记录3.1.1，不将其等同于A声明的2.17.1。项目观测SVD仍为上述CubeCLT文件；pack内SVD字节不同，两者分别记录来源和hash。证据为 `evidence/dependencies/vs10b-runtime-target-map-20260918T032434360Z`；没有启动PyOCD/IDE或访问硬件。操作前重新核对实际映射/文件，IDE显式选择该pack；若发现漂移先停止，不安装或静默换版本。

- 板卡选择：现有 BSMR-MC04、STM32F429ZG；具体 MCU package、Probe 选择器、DFP/SVD、工具版本、安装路径与文件指纹在离线预检中固定。下一次物理操作前重新核对现场与板/探针身份。
- 工程必须位于新的 B root，使用新的 workspace/session/data/evidence 名称，保留自己的 no-remote Git 历史、source snapshots、build ID、ELF SHA、CreationPlan 和 ownership manifest。A 的 runtime 可只读复用；A 的 workspace/session/flash receipt/lease/action 不可复用。
- 只配置已证实用于 LED 与 SWD 的引脚。不得驱动电机、继电器、机械负载、电源控制或不明外设；时钟、内存、启动文件和 linker 由实际 `.ioc`/原生输出/ELF 证明。
- CubeMX 管理区、Toolkit 生成区和用户 `App/Tests` 区的所有权分开；不得通过覆盖托管文件回避 regeneration/ownership 冲突。应用逻辑与 Target emitter 进入明确的用户代码区域。

### 创建请求与已执行的最小离线验证

固定使用现有 MCU 模式：`source.kind=mcu`、`source.value=STM32F429ZGTX`、`framework=hal`、`language=c`、`overwrite=refuse`。父工作区为 `D:\codex-tmp\v10b-0918\p`，生成目的地相对路径 `b`，B 工程为其 `b` 子目录；实际写入前建立可恢复 Git HEAD。

2026-09-18 主代理已使用已部署 source `6e069660...` 的真实公共 CLI 执行一次只读 `project create-plan`，返回 `OK`、`mutated=false`、`blockers=[]`，父工作区仍为空。原始 argv/stdout/stderr/exit 位于 `D:\codex-tmp\v10b-0918\evidence\create-plan-*`。这是入口与工具支持计划的离线证据，未调用 `create-prepare/create-apply`、未运行 CubeMX、未构建，也未访问硬件。

现有 prepare 才要求 Git HEAD 并绑定 native environment；apply 消费单次授权，在 sibling staging 生成，验证 native CMake/MCU/内存/包/ownership，依次配置并构建 Debug 与 Release，最后原子激活。本次临时 plan 已有有效期，实施时必须重新 plan/prepare，不能消费此历史 actionDigest。

由于 plan envelope 只保留 toolProfileDigest，主代理另直接调用现有 `discover_tool_support` 保存完整只读结果，未增加诊断脚本/框架。`evidence/tool-support.stdout.json` 的 `VSCODE_INVALID` 已定位为 ENVIRONMENT：HKCU App Paths 指向不存在的 C 盘安装，现有 resolver 在标准候选校验处拒绝该路径；实际程序是 `D:\Program Files\Microsoft VS Code\Code.exe`，PE 版本 `1.129.1`。未修改全局注册表或产品发现规则。

采用现有显式配置入口，在 B 的 `data/tool-path-overrides.json` 中只指定 `vsCode.path`，不手填版本。再次调用同一发现函数，结果 `issues=[]`、`vsCode.source=explicit`，可执行文件 SHA256 为 `552dde73ea97674f00c81ccf3ac6fe369fc272bbcc3b23b67c8186ec9f8c56d9`；原始结果、调用与配置哈希保存于 `evidence/tool-support-override*`。这是工具路径就绪证据；扩展/生成调试配置与真实 IDE 交接仍须检查，未启动 IDE 或硬件。该证明使用公共 Python 发现函数；不能据此假定所有 CLI 子命令都接受 `--support-profile` 或环境变量 data root。

冻结创建链为现有 CLI 三步均使用默认发现：其实际 creation data root 是 `D:\codex-tmp\v10b-0918\.stm32-toolkit-data`、session 为 `cli`，不受本轮设置的环境变量 data/session 控制。独立 B data root 仍用于后续服务/验收。默认发现中的 VS Code issue 被创建规则明确排除为 blocker，但仍进入整个 toolProfileDigest；故不能在 plan/prepare 传显式 profile 后让不支持该参数的 apply 回到默认发现。三步保持同一默认事实并重新校验，IDE 阶段通过现有 `discover_tool_support` / `run_doctor(..., support_profile=...)` 单独核验显式 D 盘配置。CLI 显式 profile 传递缺口记录为已知限制，本切片不修改它，也不修改全局注册表来规避。

### 固件用户场景

采用现有 D3 heartbeat 故障模式，保持 D4 作为独立的主循环活性指示：正常状态 D3/PE3 与 D4/PE4 交替闪烁，故障只将周期 D3 翻转替换为写低（D3 常亮），D4 继续翻转。修复只恢复同一周期 D3 翻转语句。三种状态的时基、D4 控制、Target emitter、case ID 与内存布局保持一致。

用户区定义 `volatile uint32_t testtime`；10ms tick 为已有 emitter 提供真实单调时基，500ms LED 周期可产生可观察翻转。Target case 复用 `d3-heartbeat` 的语义和 v2 case-inventory digest 算法，判断真实时基活动及 PE3 变化；不把自身期待值或预先生成 JSON 当采样结果。HAL 用户代码使用 PE3/PE4 实际 ODR，不能照搬 A 的 SPL `GPO.h` 依赖。

无 RTOS、联网外设或新调试 transport。原生 startup/clock/linker 必须通过构建产物检查，不能仅依据 `.ioc` 声称 MCU 已正确运行。正常与故障版本都不得以阻塞延时或 Target 终态结束而停止 D4 主循环。

### 创建后工程定制与链接脚本所有权（本规格新增决策）

独立审查确认，当前 native 创建结果的 `debug={}`、未声明 `testing`，且只登记 CubeMX 原生源码；它不自动具备 B 的实机配置。原生模式也不会渲染 Toolkit 的 `fixedSections`。本规格使用既有 schema-3 配置入口，明确以下一次性工程定制，不能把这些步骤说成创建器已自动完成的行为。

1. 归档真实 create/apply 的原始 `.stm32-project.json`、原生 linker、CubeMX inventory/ownership、生成和构建结果，先提交无定制基线。后续原生库存继续表示该次生成来源，不伪改其哈希来冒充仍是原始字节。
2. 用户源码位于 `App/`、`Tests/`；在 `build.sources` 显式追加每个 `.c`，在 `build.includePaths` 登记所需目录。`Core/Src/main.c` 仅修改明确的 USER CODE hook，其前后字节单独纳入工程 Git/diff；不以源目录存在推断它已编译。构建 MAP/ELF 必须证实 emitter、testtime 和唯一 mailbox 已链接。
3. 补全 `debug.backend=pyocd`、`debug.target=stm32f429zgtx`，将已验证 SVD 复制到 B 的 `svd/STM32F429.svd` 并校验哈希，配置 `debug.svd`、`svdDevice=STM32F429` 和已有只读区域契约允许的 GPIOE ODR 范围。配置本身不授予访问硬件权限，也不证明实际 backend target/pack 映射已可用。
4. 补全 `testing.target`：`executable` 取 B 激活后实际 Debug BuildResult 的相对 ELF 路径，`timeout_seconds=60`、`protocol=stm32-target-frame/2`、`transport.kind=memory-mailbox`、`options.address=537063408`（`0x2002EFF0`）、`options.size=4096`。先有原生 Debug ELF 再登记此字段，避免把不存在的路径交给模型验证。之后重新 configure/提交/构建，所有字段在正常、故障、修复三个固件间保持不变。
5. 原始 CubeMX linker 及其 inventory/ownership 记录不删除、不改写。以该文件的精确字节派生项目自有 `App/Linker/vs10b.ld`，记录来源路径/哈希及完整差异。只允许把实际 `0x20000000..0x20030000` 普通 SRAM 顶部划出 `MAILBOX`，保留其他原生运行时段/符号；普通 RAM 结束和 `_estack` 必须降到 `0x2002EFF0`。加入一个 NOLOAD/KEEP/对齐16/大小4112的 mailbox 段，以及普通数据/heap/stack 与该区域不重叠的 ASSERT。实际原生内存不符合此边界则停止，不猜测或添加容量。
6. `memory.regions` 必须与新 linker 的完整 MEMORY 表逐项同序一致，保持 `memory.source=cubemx` 并用新工程提交证明该容量内的保留区修改。将 `generation.nativeLinkerScript` 指向此项目自有副本，由既有 `load_project_model → plan_project_configuration → apply_project_configuration → build` 接入一个完整 linker 文件；不称为现有 overlay 功能，不添加第二个链接器或修改模板。
7. 这是 B 特定的显式所有权决策：仅在完成真实原生创建之后，取代 0702 设计要求持续引用原 CubeMX linker 的限制，需随本规格批准；不是对旧 A 授权的复用。原生生成证明、修改后项目/固件证明分开归属。定制后的 B 不执行 regenerate；未来如需重生成，必须先定义并实现增量保留/链接所有权契约，不能靠更新库存哈希或跳过冲突检查实现。

现有 managed model hash 未覆盖 `testing`，本切片不扩张为该独立机制的修复；B 的实际 manifest 原始 SHA256、Git commit 和 Build InputSnapshot 必须单独留证并在操作前核对，不能用 managed hash 独自证明 Target 配置未变。正常/故障/修复仅允许 D3 语句差异，若测试配置或链接/时钟/入口再变，停止并重新确认对应身份。

初始 `.vscode/launch.json` 为空不算 IDE 就绪。实际 IDE 步骤使用既有 `debug handoff begin` 返回的 B `cortexDebugLaunch` 与当前 companion/一次性 ticket 按标准流程配置；不得猜测端口、复用 A launch 或把普通 configure 当作 handoff。

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
- B 的 mailbox 固定候选布局为 `0x2002EFF0..0x20030000`：16-byte header 加 4096-byte ring。项目 transport 配置必须是 `address=0x2002EFF0`、`size=4096`；`size` 指 ring，不是总长 4112。linker 必须有 `NOLOAD`、16-byte aligned、KEEP 和 exact-size ASSERT。B 的实际 native 内存图、linker/MAP/ELF 必须证明该 SRAM 范围、普通 RAM/stack/heap 不重叠及唯一对象；不满足则停止并返回规格决策，不能静默改地址或只依据 A 的 MAP 宣称通过。
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
| attempt schema | `stm32-acceptance-attempt/4` |
| recovery policy schema | `stm32-acceptance-recovery-policy/3` |
| scenarioId / version | `new-cubemx-physical-repair` / `1` |
| projectOrigin | `cubemx` |
| executionSource / transport | `physical` / `mailbox` |
| physicalTransportEvidence | 实际物理证据到达后按原 stage/revision 条件成立；不得在 begin 阶段伪造 |

沿用六个阶段及 timeout（秒）：`project-materialized:60` → `firmware-built-before:900` → `target-failure-observed:300` → `diagnosis-completed:900` → `firmware-built-after:900` → `target-fix-verified:300`。stage outputs、sourceChangeIntent/1、Evidence root/CAS、失败终态、精确授权消费及 FixVerification 规则不变。scenario digest 使用现有 canonical JSON 算法，对 B 的 scenario/version/origin/source/transport/stages 文档求 SHA256；policy digest 使用相同现有算法绑定 `/3` schema、B scenario digest、上述 timeout 和既有 intrusive-action 规则。B 的硬件授权仍由 Target/Probe 层产生，acceptance adapter 不访问硬件。

只通过 schema/scenario 的固定配对选择 A、B 两组封闭 profile；不增加配置驱动的注册器、插件或任意 origin。A `/2` 输出、digest、读取兼容和旧记录验证保持原样；v1 `new-cubemx-project` 继续 replay，不能得到 physical flags。错误复用现有 input-invalid、identity-mismatch、stage/expiry、authorization/consumed、CAS 语义，不为本次准备泛化新错误码。

B 首个切片使用 fresh `/4` attempt，不扩展 A-only continuation。原草案的 attempt `/3` 编号在实施预检中发现已被 `continuation.py:71` 的 A 续接记录占用，且现有工作流按该 schema 分流；因此只纠正 B attempt 编号为未占用的 `/4`，B recovery policy 仍为 `/3`，不得重解释 A continuation `/3` 或修改其 policy `/1`、序列化和路由。测试必须同时覆盖 A `/2`、A continuation `/3`、B `/4` 与 replay `/1` 的读回/路由隔离，不能只测 B 自身 round-trip。

CLI 使用现有 `scenario attempt` 命令及新 scenario（operation 名为 `acceptance.attempt.*`）；MCP 只扩 `AcceptanceAttemptScenarioId`，不修改软件 AcceptanceScenarioId/AcceptanceRecord。创建授权、`.ioc`、native inventory 和 ownership provenance 仍由创建/工程 manifest 持有，并在 B bundle 引用；不向 attempt 添加 `creationAuthorizationDigest` 或自由字段。

最小产品文件：`acceptance/recovery.py`、`acceptance/recovery_workflows.py`、必要的 `acceptance/__init__.py` 导出，以及 `mcp_server.py` 的 attempt enum。不修改 CubeMXAdapter/creation_apply、replay model、Diagnostic pair validator 或 Probe/Monitor 协议。若出现这些边界以外的真实阻塞，由主对话框先给出原因与新边界，不能让实现者自行扩张。

### 实施中确认的创建阻塞：索引映射到分组 MCU 描述文件

首次真实 `create-prepare` 在授权生成前以 `CUBEMX_MCU_DESCRIPTOR_INVALID` 终态停止；未运行 apply、CubeMX 或构建。源码 `creation_environment.py:186-234` 仅接受请求型号同名 XML 及相同 RefName。当前安装的 `families.xml` 第 14061 行却明确记录 `RefName=STM32F429ZGTx`、`Name=STM32F429Z(E-G)Tx`，后者对应存在的 descriptor，且 descriptor 自身 RefName 等于分组 Name。这是 PRODUCT：现有解析器缺少当前官方数据库的精确索引映射支持，不是更换 MCU、板卡或安装包的理由。原失败保留于本轮 `evidence/firmware`。

冻结修正边界为 `creation_environment.py` 及现有相关测试，由工程准备的同一 Luna/max 在独立 `native-fix` 工作树负责，不与 host 适配重叠：

1. 现有精确文件模式保持原行为、序列化和 digest；精确文件歧义、unsafe 或 RefName 不符时直接拒绝，不借索引回避错误。仅当没有精确文件候选时使用同数据库内固定 `families.xml`。
2. 索引只接受安全普通文件、UTF-8 XML、有限大小（16 MiB）和无 DTD/entity 声明；匹配本次请求的 `Mcu.RefName` 必须唯一且 case-insensitive 完全相等，不做前缀、通配、正则扩展或推测 E/G 变体。其 `Name` 必须是最多128字符的 `STM32` 开头安全文件名 token，仅含 ASCII 字母数字、括号、连字符或下划线，不允许目录、扩展或命令字符。
3. 以该 Name 加 `.xml` 在原受限数据库库存中定位唯一安全 descriptor；descriptor 的 RefName 必须与索引 Name 完全对应。原 inventory/reparse/descriptor 大小限制不放宽；缺失、歧义、越界、无效编码/结构/映射均复用 `CUBEMX_MCU_DESCRIPTOR_INVALID`。
4. 返回给既有 CubeMXAdapter 的 `native_source_token` 是索引中的精确 `STM32F429ZGTx`，不是带括号的分组 Name；既有 `load` token 正则、脚本及执行边界保持不变。
5. 分组路径须把索引相对路径与真实文件 SHA256 一并绑定到执行环境 digest，和 descriptor 路径/hash、精确 source token 共同重验。使用可选内部事实字段 `native_index_path/native_index_sha256`；仅索引模式在 native digest 中增加 `indexPath/indexSha256`，公开事实增加 `nativeIndexPath/nativeIndexSha256`。无索引的旧路径不新增空字段、不改旧 digest。prepare 与 apply 之间索引或 descriptor 漂移必须在 native 进程执行前拒绝。
6. 复用现有环境、adapter 和 creation workflow 测试：既有精确匹配兼容；G 与 E 各自经真实格式索引映射得到自身 token；非索引成员拒绝；索引/descriptor 不符和重复映射拒绝；危险路径/重定向/oversize/DTD 拒绝；索引字节变化影响 digest；生成脚本仍发出精确 leaf MCU token。再对当前安装只读调用现有环境函数证明映射，不把它当作真实生成或实机 PASS。

该修正是已批准真实创建场景的必要阻塞修复，保持已批准 MCU、原生 engine、权限和用户场景。独立审查通过后才使用修正后的公共源码 CLI 重新进行一次 fresh plan/prepare/apply，记录实际 code head/解释器/dependencies；这是候选源码执行，不冒充已安装部署。首个非预期错误继续停止，不能改输入型号或改共享数据库绕过。无需修改 Toolkit schema、CubeMXAdapter、creation_apply、全局注册表或原安装数据库。

## 5. 验证范围与停止条件

| 层级 | 本轮要求 | 证据责任 |
|---|---|---|
| 规格/离线资产 | 明确真实 native tool、创建 request、支持的 MCU、实际入口、可写目录及未决项 | 主对话框 + 有界只读审查 |
| 实现 | 只测试新增/改变的场景映射、工程用户区与必要回归；不重跑未变全矩阵 | Luna/max，保留 exact command/stdout/exit/commit |
| 原生生成与构建 | 真 CubeMX 输出、manifest ownership、可重复构建、ELF/MAP/向量/入口/符号/内存资格 | Luna/max 实现，主对话框独立核对 |
| 实机 B | 新项目正常→故障→诊断→授权修复→fixed-after，Target/Monitor/退出状态全部关联 | 主对话框串行；独立证据审查 |
| 入口绑定 | B 的 CLI/MCP project/firmware 行为；正常 B 固件上用新生成配置完成一次真实 IDE attach/Watch/detach/reacquire | 实际执行者，不借用 A 的 UI 结果 |
| 归档 | request/.ioc、CreationPlan、生成库存、ownership、build/firmware、Target/Monitor/Diagnostic/修复、完整身份与 sorted SHA256 manifest | 主对话框归档，独立审查 |

A 的共享协议、Probe/handoff、0.9 安装/升级/安全/包、UI 和既有硬件证据按原身份与版本范围保留。B 的原生生成调试配置与工程身份是新输入，因此一次 B IDE 交接是必需的集成检查；不重跑 T9 完整矩阵，也不在故障/修复版本重复该交接。其余只有相关源码、依赖、配置、环境或契约发生变化时前移受影响检查；B 的新工程生成与物理结果必须实际产生。完整 1.0 发布矩阵、tag/Release 是后续独立阶段。

首个非预期错误停止当前执行卡，不继续烧录/连接/恢复；保存原始错误、阶段、身份、stdout/stderr 与清理终态，先分类 PRODUCT/ENVIRONMENT/INFRASTRUCTURE/HARDWARE/REPORT。预设应用 heartbeat 断言失败仅能继续预先规定的诊断链；超时、身份错误、transport 错误或目标不运行不是预期故障。

所有本轮进程同时固定 `TEMP/TMP/TMPDIR` 和 pytest/cache/build/output 根到 B 短目录。只清理已归属的 B 一次性产物，保留工程源码、当前构建/恢复镜像、有效证据与最小失败证据。A 的保留例外不外推到 B；策略拒绝就记录保留，不绕过。

## 6. 本阶段出口

当前工作完成的条件是：资产和入口事实具名、最小产品缺口明确定义、自包含规格/计划及文件所有权写明并经独立审查。规格获批后才能交 Luna/max 开始实施；实机前另有具体操作卡和 B 的授权边界。`DRAFT/OFFLINE_PREFLIGHT`、`SOFTWARE_READY`、`HARDWARE_PENDING` 与 `ACCEPTED` 不混用。

本规格采用的本地工程经验：GL-001（active-provisional，先冻结共享契约）；STM32TK-EL-004（active，recovery prepare 不访问硬件）；STM32TK-EL-007（active-provisional，三项临时目录变量同时绑定）；STM32TK-EL-008（active-provisional，测试结论必须有实际执行证据）。这些经验决定预检、实现和留证边界，不替代项目当前源码与本次实机证据。

## 7. 已确证的 indexed MCU 原生身份修正（2026-09-18）

证据为 `evidence/firmware/native-capture/run-20260918T041200Z/native-root/b.ioc`，SHA256 `c3d31d0dbe513e7ca2e6d92207e81e238f9f777b767b87ef1780391b82ac6a40`。真实输出为 `Mcu.Name=STM32F429Z(E-G)Tx`、`Mcu.UserName=STM32F429ZGTx`、`Mcu.CPN=STM32F429ZGT6`、`ProjectManager.DeviceId=STM32F429ZGTx`。现有 `cubemx_project.py:431-434` 只读取 Mcu.Name，随后仅接受字母数字而拒绝括号，触发 `CUBEMX_NATIVE_OUTPUT_INVALID: native MCU identity is missing`。执行到原生校验，尚未配置、构建或激活。这是 PRODUCT 身份解析错误，不是板卡或程序运行结论。

最小产品范围仅 `cubemx_project.py`，工程实现者仍为原 Luna/max。仅对 `request.source.kind=mcu` 且已有环境绑定 native index path/hash 的新 indexed 模式：读取唯一 Mcu.Name 和 Mcu.UserName；前者必须匹配环境已校验的 `native_descriptor_path` 文件 stem，后者必须是字母数字组成的精确 STM32 leaf，且同时匹配请求值与 `native_source_token`。按既有型号比较语义忽略大小写，禁止分组展开、通配、前缀猜测或从 CPN 剪切推导。ProjectManager.DeviceId 若存在，须唯一且匹配相同 leaf；不靠缺省值掩盖冲突。缺失、重复、格式错误或与受授权环境不符，均使用既有 `CUBEMX_NATIVE_OUTPUT_INVALID` 拒绝。

旧 exact MCU 模式和既有 board/ioc 路由保持原行为。没有已绑定索引环境时不能仅凭新字段放行分组名。目标 model.device 使用精确 leaf，原 IOC、库存 hash、环境绑定和 generation ownership 不改写。其余 CMake、source/linker/package/parser 校验和所有创建授权/原子激活契约保持原样。

验证复用 `test_cubemx_project.py`，必要时使用既有 `test_creation_apply.py`：支持匹配的 G/E leaf；拒绝错误 group、错误 leaf、缺失/重复字段、冲突 DeviceId，以及无索引环境的分组名；保留既有 exact/parser 回归。使用已保留的真实 native root 调用现有 `parse_native_project` 作只读全解析，核对实际 model 及旧错误已消失；不改原件、不重新生成来诊断同一结论。完整 diff 经独立审查通过后，才允许继续下一次正常公开 create/apply 与正常/故障工程准备。此修正不新增部署、硬件或远程权限。
