# STM32 Toolkit 1.0 VS10-A 真实 Keil 工程实体板闭环设计

**状态：** 用户已批准；2026-08-25 实施计划映射发现 Target v1 实体固件身份自引用后，
由规格所有者作向后兼容修订并重新冻结

**切片：** `STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP`（VS10-A）

**完整 accepted base：** `9b7839bb01f88a9e3d2c13203f38aa0d11647232`

**规格所有者：** GPT-5.6-sol 主代理

**实现所有者：** 一名 GPT-5.6-luna 子代理，reasoning effort `max`；书面计划批准后分配

**独立审查与接受者：** GPT-5.6-sol 主代理

**规格分支：** `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-spec`

**活动 PR：** 无

**远程授权：** 无 VS10 push、PR、merge、tag、release、close 或远程分支变更授权

**硬件授权：** 用户已明确授权在本文冻结的断载安全边界内，对命名的
STM32F429ZGT6/CMSIS-DAP 反复执行本文所需的读取、复位、烧录、attach、handoff、Target
测试和诊断；每个侵入操作仍必须使用现有公共操作的当次授权：digest 型流程消费 Toolkit
产生的 single-use exact digest，boolean 型 flash/handoff 同时固定 expected build ID、ELF SHA、
Probe、project、data root 和 session。安全拓扑、目标、Probe、工程或固件身份变化即终止
这项授权。

**所有权例外：** 无

## 1. 结果

VS10-A 使用已接受的 0.9.0 Agent-neutral Windows 离线 runtime，把一个真实、未纳入 Git、
没有 Toolkit manifest 的 Keil 工程迁移到独立的 GCC/CMake 工程，并在真实
STM32F429ZGT6 板卡上完成：

```text
只读来源盘点
→ 可恢复本地 Git 基线
→ Keil inspect/baseline
→ digest-guarded convert/configure
→ ARM GCC Debug build 与内存/符号检查
→ 身份绑定的 flash/readback
→ D4/PE4 正常观察
→ 实体 Target test
→ D4 常灭故障
→ 证据驱动诊断
→ 单次授权修复
→ rebuild/reflash
→ Target test + Monitor 验证
```

同一次命名活动还关闭这块板上的历史 0.4 实体证据债务：Probe 身份与独占、
flash/readback、typed variable/register/Fault、真实 Cortex-Debug handoff/reacquire，以及公共
CLI/MCP 对同一工程和固件身份的调用。它复用现有 Project、Build、Probe、Monitor、Test、
Diagnostic 和 Evidence 权威，不增加第二条产品路径。

VS10-A 接受后才为 VS10-B 冻结新 CubeMX 工程的自包含规格。VS10-A 本身不宣称 1.0 完成，
也不产生远程 release。

### 1.1 实体 transport 要求的版本化收敛

2026-08-14 的历史 0.6 release Gate 曾要求 mailbox、RTT、UART、semihosting 四种 transport
各自 real-board PASS。2026-08-22 的集成设计保留了这项债务名称，但同时规定 0.7–1.0 从最小
真实支持集开始、硬件活动必须由命名资产驱动、旧 Gate 结构不再直接执行。

本规格根据 2026-08-25 已发现并经用户批准的真实资产，把 Windows 1.0 reference campaign 的
物理 transport 冻结为 `memory-mailbox`：当前只有 CMSIS-DAP，未发现或授权 UART adapter；
memory-mailbox 能复用唯一 PyOCD backend，且不新增目标写入或第二硬件路径。RTT、UART、
semihosting 的现有软件适配器、协议和 replay 证据保持不变，但本活动和后续 VS10-B 都不得把
它们写成 real-board PASS 或当前 reference hardware compatibility。Compatibility/known-limitations
必须明确标记三者为未在 1.0 命名参考硬件上实体资格化。

这项收敛取代历史“必须为四种 transport 采购或虚构外部资产才能形成 1.0 本地候选”的要求，
不删除 transport、不把 unavailable 结果改写为 PASS。未来若用户提供并
单独授权真实 RTT/UART/semihosting 资产，可在后续版本建立独立资格活动；不扩张当前 VS10。

### 1.2 Target 实体帧的可实现性修订

实施计划的逐文件映射确认，现有 `stm32-target-frame/1` 不能由未接受 host 写入的真实 MCU
诚实地产生：inventory 要求固件上报 workspace/session、Git、input snapshot、build ID、完整
ELF SHA-256 和 UTC，`run_end` 又重复绑定 build ID/完整 ELF SHA-256 和 UTC。把完整 ELF digest
编入 ELF 会改变被散列 bytes，形成不可求解的 SHA-256 自引用；本板应用也没有经同步的可信
UTC。fixture/replay 可以预填这些值，但不能据此宣称实体板 PASS。

VS10-A 因此增加一个最小、通用、Agent-neutral 的 `stm32-target-frame/2` host-bound 模式，并
保留 v1 的全部读取、replay 和验证兼容性。它不是第二 Test runtime/controller/backend，也不
允许 host 写 mailbox：

- Project schema v3 的 `testing.target` 新增可选 `protocol`，只接受
  `stm32-target-frame/1` 或 `stm32-target-frame/2`；缺省为 v1，旧项目 bytes/行为不变；
- v2 使用同一 `ST32` header、kind、sequence、payload 长度、CRC32、stream size 和 recovery
  限制，header `version=2`；一个 decoder 实例只能接受其显式 expected version，禁止混流；
- v2 target payload 不声明 host 权威事实。每种 payload 都带非递减 `monotonic_ms`（unsigned
  63-bit）；inventory/run_start/run_end 使用 `case_inventory_digest`，其唯一公式是对 canonical
  JSON `{"case_ids":<UTF-8 byte order sorted unique ids>,"mode":"target","protocol":"stm32-target-frame/2"}`
  的 SHA-256；
- v2 inventory 是 `{mode,case_ids,case_inventory_digest,monotonic_ms}`；run_start 是
  `{case_ids,case_inventory_digest,monotonic_ms}`；case_start 是 `{case_id,monotonic_ms}`；
  case_result 是 `{case_id,state,monotonic_ms,message}`；log 是
  `{stream,message,monotonic_ms}`；run_end 是
  `{state,case_inventory_digest,counts,event_stream_digest,monotonic_ms}`。所有对象继续 closed，
  case/result/state/count/digest 语义与 v1 相同，stdout/stderr 在 host publication 中为 null；
- v2 discovery 只要求 stream 的第一个完整有效帧是 inventory；同一次 read 已带回的尾随帧
  不属于 discovery，也不触发“必须只有一帧”的 v1 规则。host 只保留第一个 frame 的 exact raw
  bytes，立即关闭 read-only transport；execute 随后总是重新烧录并从复位后的空 mailbox 获取
  新的完整 run，因此不需要 target 接受命令或区分 discovery/run；
- host 在 discovery 时用当前 fresh firmware facts、project/workspace/session、Probe/target 和
  host capture UTC 构造现有 `EvidenceIdentity`/`TestInventory`，并把完整 inventory digest 与
  case-inventory digest 一同固定到 prepare/execute 的 single-use action digest；
- execute 必须在同一 exclusive MODIFY lease 内 guarded-flash exact ELF、逐 segment readback、
  验证 Probe/target/transport 身份后才接受 v2 bytes。host 用 run_start capture UTC 加 target
  monotonic delta 形成现有 TestRun UTC/duration 字段；counter 回退、超时外 delta、inventory
  漂移、v1/v2 混流或 flash/identity/lease 漂移均 fail closed；
- raw-events artifact 保留 exact v2 target bytes；TestRun identity 始终来自上述 host-verified
  flash lineage，绝不伪装成 target 自报 ELF/Git/UTC。`execution_source=physical` 和
  `physical_transport_evidence=true` 仍只在真实 Probe transport 成功后成立。

这项修订替代本规格较早的“不得改变公共协议”字面约束，仅授权上述 v2 扩展和所需的公共
schema/model/runner/CLI/MCP 透传、测试与文档；不得借机改变 v1、增加 transport、backend、
writer、runtime、controller、provider、Agent 分支或 release 范围。

## 2. 可运行用户场景

### 场景 A1：真实 Keil 工程安全迁移并在原板运行

用户保留 `D:\workspace\WDS_CODE\test` 为只读 golden source。实现者创建逐文件哈希的完整
intake snapshot，再从 snapshot 创建无 remote 的本地 Git 工作工程。Toolkit 对工作工程的
`Project\LWIP.uvprojx` / `Target 1` 执行 inspect、baseline、conversion plan/dry-run/apply 和
project configure，使用 CubeCLT ARM GCC/CMake/Ninja 生成 `arm-debug` firmware identity。

在任何硬件动作前，迁移结果必须证明 MCU、可执行内存、入口点、向量表、
`Reset_Handler`、`main`、`TIM3_IRQHandler`、`testtime` 和使用量报告一致且可解释；失败或无法
证明即停止。通过后，公共 flash 工作流烧录迁移后的未插桩固件并完成 readback。用户肉眼看到
D4 约每秒翻转，Toolkit 同时读取 `testtime` 的活动变化和 GPIOE ODR 的 PE4 翻转。

### 场景 A2：可复现 D4 常灭故障被诊断并修复

迁移工程增加最小、项目自有的 `stm32-target-frame/2` memory-mailbox emitter。ring 为 4096
字节；现有 transport 在 ring 前还有 16 字节 producer/consumer header，因此 linker 必须明确
保留合计 4112 字节。只有 P1 MAP/ELF 证明 SRAM1 顶部空闲后，候选区才固定为
`0x2002EFF0..0x20030000`：header address `0x2002EFF0`、ring size `4096`。P2/P3/P4 的最终
linker/MAP/ELF 必须重复证明该范围不与代码、数据、栈、堆或 DMA 重叠；manifest 记录 exact
address/size/protocol，禁止猜测地址。

正常插桩构建烧录后，物理 `d4-heartbeat` Target case、D4、`testtime`、PE4 ODR 和 Monitor
全部通过。随后一个独立故障 commit 把周期性 `LED1=!LED1` 改为 active-low LED 的 held-off
状态 `LED1=1`，不停止 TIM3。烧录后必须同时观察到：D4 常灭、`testtime` 仍活动、PE4 ODR
保持高、物理 Target case 失败。

诊断按证据区分并排序至少三类假设：定时器/中断停止、GPIO/板级通路异常、应用逻辑持续
写高。DWARF typed read、SVD register、源代码、原理图和 failed-before TestRun 必须支持最终
结论。Toolkit 的 acceptance/source-change 工作流生成并消费一次性精确摘要后，项目恢复
toggle 逻辑，产生新 Git commit、新 build ID 和新 ELF SHA-256。重新烧录后，全部观察和
fixed-after TestRun 通过，Diagnostic fix verification 绑定前后两个物理 TestRun。

### 场景 A3：同一 Probe 的所有权、handoff 和公共入口一致

Toolkit 使用唯一 Probe Service/PyOCD 获取 probe `0001A0000000`。一次公共 CLI 观察与一次
公共 MCP 观察都从同一 project root、data root、firmware identity 和 probe identity 派生；
调用方不能注入另一 ELF、target、SVD、地址或凭据。

Toolkit 创建一次 Cortex-Debug handoff，实际 VS Code/Cortex-Debug attach 到当前固件，读取
一个命名变量或停机状态，然后正常退出。handoff 期间 Toolkit 不抢占 Probe；结束后 Toolkit
reacquire 并再次读取/观察。若 Probe 已由另一 owner 占用，返回现有稳定 owner/busy 证据，
不得 kill、steal 或自动重启无关 PyOCD 进程。Fault 路径在没有 Cortex-M Fault 的正常固件上
返回真实“无活动 Fault”证据，而不是制造处理器异常。

## 3. 明确非目标

VS10-A 不：

- 修改、格式化、清理、Git 初始化或烧录 `D:\workspace\WDS_CODE\test`；
- 写回 `.uvprojx`，维护 Keil/GCC 双向同步，或把 Keil `OBJ` 变成 GCC 构建输入；
- 进入 VS10-B、新建 CubeMX 项目、形成完整 1.0 verdict 或进入 VS11；
- push、创建/修改/合并/关闭 PR、tag、GitHub Release、上传发行物或修改远程分支；
- 发布 0.9/1.0、签名、安装系统级软件、修改驱动或改变机器全局 MCP 注册；
- 接通或驱动电机、继电器、机械臂、充电回路、24V/12V 负载或其他外部执行器；
- 测试板上与 D4/PE4 闭环无关的业务外设；
- 添加 Agent 专属产品逻辑、第二 runtime/MCP 注册、第二 Project/Probe/Monitor/Test/
  Diagnostic/Evidence/Acceptance 权威、controller、provider 或硬件 backend；
- 添加另一个 Target transport、Python 版本、平台、MCU 系列、Probe 类型、CI 或协作自动化；
- 扩展 VS08 replay-only AcceptanceRecord 使其接受 physical PASS；或
- 把 replay、fixture、fake、跳过、用户口述或 GUI 截图单独标记为物理 PASS。

## 4. 冻结事实与命名资产

### 4.1 Toolkit 与工具环境

| 资产 | 冻结事实 |
|---|---|
| Toolkit accepted base | `9b7839bb01f88a9e3d2c13203f38aa0d11647232`，远程 `master` |
| 产品版本 | `0.9.0`，CPython `>=3.12,<3.13` |
| 本机 Python | CPython 3.12.10 |
| CubeCLT | 1.22.0 |
| ARM GCC | 14.3.1 |
| CMake | 4.3.1 |
| Ninja | 1.13.2 |
| PyOCD | 0.45.1，唯一生产 Probe backend |
| CubeMX | 6.18.1-RC2；VS10-A 不调用它 |
| system Monitor | 0.5.0；禁止进入本活动 runtime |
| 运行环境 | 从 accepted base 构建并校验的干净 0.9.0 Windows offline candidate |

系统已安装的旧 Monitor、系统 Python fallback 或混合源码/安装包不得提供证据。活动开始时
必须证明 Toolkit package、Monitor package、CLI、MCP、launcher、八个 Skills 和 48 个 MCP
工具全部来自同一 0.9.0 candidate，并绑定 accepted base。

### 4.2 Golden Keil 工程

| 资产 | 冻结事实 |
|---|---|
| golden root | `D:\workspace\WDS_CODE\test` |
| 初始 Git | 无 `.git` |
| 初始 Toolkit manifest | 无 `.stm32-project.json` |
| inventory | 529 个文件、53 个子目录、83,846,939 字节、无 reparse point |
| Keil project | `Project\LWIP.uvprojx` |
| Keil target | `Target 1` |
| device | `STM32F429ZGTx`；实体芯片 `STM32F429ZGT6` |
| output | `Project\OBJ\LWIP.axf`、`LWIP.hex`、`LWIP.htm`、`LWIP.build_log.htm`；`Project\LIST\LWIP.map` |
| heartbeat source | `Main\Main.c` |
| LED mapping source | `USER\GPO\GPO.h` |

关键 intake SHA-256：

| 相对路径 | SHA-256 |
|---|---|
| `Project/LWIP.uvprojx` | `8efeec8cbe9366a8451d5bd59a00bf1dc11b5cff6e837a5ef12e005d609caa47` |
| `Main/Main.c` | `c816be580a7d9ece9321cde2f7218032201bed34829664fb0d057cac4cec0c58` |
| `USER/GPO/GPO.h` | `53a137cb7d48adbb0fbe7192aea353183ffece4a6b79245c369297edb81fb0a5` |
| `Project/OBJ/LWIP.axf` | `65f5b98c970befbea2c7fd529f54a51438b3c635d794e20519d284c33976c225` |
| `Project/OBJ/LWIP.hex` | `1a18daaa9d608f41d21a4a41d14fea852c2f978053f3dff44383c38e3c643a84` |
| `Project/OBJ/LWIP.htm` | `8b757644a351ea3a5e196f42117138e69106b786c101aae85b89b91b8c95bb7e` |
| `Project/OBJ/LWIP.build_log.htm` | `7e362b1bb1ca32ba77d08dd2eb5b28b813da9c06057eefba5c000bbb0f4b2934` |
| `Project/LIST/LWIP.map` | `6fca9fc30bd964f81da0c2417d46fe6930f6317ce96ee30d63fbf2981e8bbe9f` |

完整 intake manifest 必须重新读取 snapshot 中的所有文件并记录相对路径、大小和 SHA-256；
上述值是来源漂移的早期拒绝条件，不替代完整 manifest。

已知迁移风险：`USER\TIMER\timer.c` 当前以普通 `u32 testtime` 定义该变量，`timer.h` 以普通
`extern u32 testtime` 声明；TIM3 ISR 写它而 main loop 读写它。ARMCC 现有产物不能证明 GCC
对这项未声明为 `volatile` 的异步共享状态保持同样行为。P1 必须先保留原逻辑并用编译/ELF/
实体证据判断；不得预先静默改写。若真实失败证明这是根因，它属于 `PRODUCT/project` 的移植
缺陷，只能在独立、精确 diff digest 绑定、最小 project commit 中修正声明/定义并重新执行受
影响的 H1/H2，不能伪装成 Toolkit 自动 conversion 成功或用编译选项掩盖。P1c 的 digest 由
本活动 ledger 记录并落在用户已批准的 bounded portability correction 内；它不伪装成尚未进入
failed-before checkpoint 的 VS08 acceptance authorization。P4 则必须使用现有 Toolkit
acceptance source-change authorization。

### 4.3 板、原理图与可观察行为

- 用户已在实体板上看到 D4 闪烁，证明当前 golden firmware 正在运行。
- `GPO.h` 定义 `LED1` 为 `PEout(4)`。
- `Main.c` 的 TIM3 周期约 10 ms；`testtime > 100` 时执行 `LED1=!LED1` 并清零计数，
  因而 D4 约每 1.01 秒翻转一次。
- 用户提供的 `BSMR-MC04.PDF` 原理图确认 MCU PE4 net 为 `LED1`；该 net 连接 D4，之后经
  R13 1 kΩ 接 VCC3.3，因此 LED active-low：PE4 低为亮，高为灭。
- 本活动仅以 D4/PE4、`testtime`、无活动 Fault 和 mailbox 为被测板级路径。

### 4.4 Probe 与安全拓扑

- 只读枚举已发现 `jixin.pro CMSIS-DAP_QM`，Probe ID `0001A0000000`。
- PyOCD pack 已提供精确 target `stm32f429zgtx`；打开会话后必须从芯片读取并验证身份，
  不能仅信调用方字符串。
- 电机、继电器、机械臂、充电硬件、24V/12V 负载和其他外部执行器均已物理断开。
- 任何外部负载重新接入、供电拓扑变化、板/Probe 更换、target 身份不一致或异常发热/气味
  都会立即停止活动；已有重复烧录授权不再适用。

## 5. 唯一状态权威与目录隔离

活动根使用一个新的、经过不存在/空目录检查的绝对路径，例如
`C:\tmp\stm32tk-vs10a-legacy-campaign`。实现计划在首次动作前冻结实际绝对路径。其逻辑布局为：

```text
campaign-root/
  runtime/          # exact 0.9.0 offline candidate and its install data
  intake/           # full immutable copy of golden root
  project/          # second copy; local Git work project, no remote
  data/             # VS10-A Toolkit data root only
  evidence/         # retained campaign evidence, outside both Git repositories
  scratch/          # disposable build/test/run products
```

权威关系固定为：

```text
golden root (read-only source)
        |
        v
intake snapshot + intake-manifest.json (immutable provenance authority)
        |
        v
local project Git baseline P0 (project source authority)
        |
        +--> Toolkit convert/configure/build --> FirmwareIdentity
        |                                      |
        |                                      v
        +-----------------------------> Probe Service / PyOCD
                                               |
                                               v
                           physical TestRun / Diagnostic / Monitor evidence
```

规则：

1. golden root 只允许 metadata/hash/read/copy；copy 后重新计算 snapshot manifest 并与来源匹配。
2. intake 设置为只读；后续所有 Toolkit/project/build 动作只指向 `project/`。
3. `project/` 初始化一个本地 Git repository，禁止 remote；P0 包含完整 intake bytes，包含历史
   AXF/HEX/MAP/build log 作为 baseline evidence，但这些文件不得作为 GCC build input。
4. `.stm32-project.json` 是 project model 权威；Git 是项目源码/修订权威；Toolkit data root 是
   workspace/session/lease/evidence 权威；FirmwareIdentity 是可烧录字节权威。
5. 正式 evidence 不写入 golden、intake、project Git 或 Toolkit Git。一次性 scratch 不作为
   结论权威。
6. VS10-A 的 project/data/evidence/session 名称不得被未来 VS10-B 复用。

## 6. 工程提交与生成所有权

本地 project 至少形成下列有序提交；实际完整 SHA 进入 campaign ledger：

| 项目提交 | 内容 | 硬件状态 |
|---|---|---|
| P0 | 完整 intake baseline，尚无 Toolkit 迁移 | 不烧录 |
| P1 | digest-guarded Keil conversion、Toolkit configure、原逻辑 GCC build | 迁移未插桩 firmware 候选 |
| P1c（仅触发时） | H1/H2 证实且绑定 exact diff digest 的最小 project portability correction | 修正后的未插桩 firmware 可烧录 |
| P2 | 项目自有 v2 mailbox emitter、4112-byte linker region、schema-v3 Target test 配置 | 正常插桩 firmware |
| P3 | 单一故障：heartbeat 分支写 `LED1=1` | D4 常灭 expected-failed |
| P4 | 经过 Toolkit 单次 source-change authorization 恢复 toggle | fixed-after |

P1 不删除或重写 Keil 输入。P1c 不得预建；没有真实失败证据时不存在。P2 的 emitter 和测试
case 位于项目自有源目录，不得把测试业务逻辑放入 Cube/vendor 生成文件。mailbox section
通过项目自有 native linker 配置保留，必须在 P2/P3/P4 每个最终 MAP/ELF 中重新证明
`0x2002EFF0..0x20030000` 合计 4112 字节范围；manifest 的 `address=0x2002EFF0`、`size=4096`。

项目必须使用本文冻结的 `stm32-target-frame/2` 和现有 `memory-mailbox` transport，且
`testing.target.protocol` 必须显式为 `stm32-target-frame/2`。case ID 固定为
`d4-heartbeat`，它验证应用层 heartbeat 周期推进与 PE4 输出状态；用户肉眼 D4 观察提供独立
板级佐证。固件不得通过 mailbox 接受 host 控制，不得开放 host memory write，也不得新增
UART/RTT/semihosting fallback。

### 6.1 已知风险的预先处置

| 风险 | 冻结处置 |
|---|---|
| ARMCC 扩展、汇编或启动文件不能直接被 GCC 接受 | convert/build 在无硬件 H1 暴露；只做可审查的 project portability correction，不扩展 Toolkit 为任意 Keil 兼容层 |
| ISR 共享 `testtime` 非 volatile | 先保留并取证；仅在确认根因后做摘要授权的最小 project 修正 |
| 工程包含多个 STM32F4 startup 候选 | 以 Keil `Target 1`、实际向量引用和 F429ZG target 选择唯一 startup；多定义或错误向量在 H1 停止 |
| historical AXF/MAP 与 GCC 使用量不同 | 报告真实差异；地址/容量/关键符号不明时不烧录，不设置无依据百分比容差 |
| mailbox 与 stack/heap/DMA 重叠 | linker 显式保留 header+ring 4112 bytes，P2/P3/P4 每个 MAP/ELF 重证；无法证明则不运行 Target test |
| target 自报 host/ELF/UTC 导致伪证或自引用 | 仅 v2 host-bound 模式；exact flash/readback/lease/Probe 形成 identity，target 只报 case/monotonic 事实；任何 v1/v2 混流拒绝 |
| D4 肉眼现象不能证明应用路径 | 必须与 `testtime`、PE4 ODR、physical TestRun 和 Monitor 联合判断 |
| Cortex-Debug 或 Probe owner 未正确释放 | 返回 busy owner evidence 并停止；不 kill/steal，只有已证明正常 detach 后 reacquire |

## 7. 顺序工作流与硬件门

### 7.1 H0：运行时与来源前置检查

尚未打开目标会话且尚未烧录时必须完成：

- Toolkit Git accepted base、干净 checkout、0.9.0 candidate checksums 和 runtime-state 检查；
- Python/Toolkit/Monitor/PyOCD/ARM GCC/CMake/Ninja 的 exact version 与来源检查；
- golden path、三个关键 source/config hashes、完整 copy 和 snapshot rehash；
- local project P0、无 remote、干净 worktree；
- probe passive inventory 与 target pack inventory；以及
- 断载安全拓扑的当次确认。

任一不一致均分类后停止；不得用 system Monitor 或 source import 混合补齐 candidate。

### 7.2 H1：迁移与无硬件构建门

按公共行为顺序执行：

1. `keil inspect`，包含真实 AXF/MAP baseline；
2. `keil convert --dry-run`，保存 plan、input digests 和 diff；
3. 使用同一未漂移 plan 执行授权 apply；
4. `project configure --dry-run` 后授权 apply；
5. `build --preset arm-debug`，在没有 source 变化时重复一次并证明 firmware identity 可复现；
6. 生成 `memory-comparison.json`。

进入 H2 前必须满足：

- target/device 是 F429ZG，debug target 是 `stm32f429zgtx`；
- ELF 只包含声明的 executable/readable/writable memory；
- `.isr_vector`、初始 SP、Thumb entry、`Reset_Handler` 互相一致；
- `main`、`TIM3_IRQHandler`、`testtime` 可由 ELF/DWARF 解析；
- 无 unresolved strong symbol、region overflow 或 stale build input；
- Keil/GCC code/RO/RW/ZI 与 region 使用差异逐项报告，无未解释的地址或容量越界；
- mailbox 尚未加入 P1，P1 的 D4 逻辑与 golden source 相同。

### 7.3 H2：Probe 身份与迁移固件 smoke

Toolkit 通过公共 `probe list` 看到 exact Probe；建立目标会话后读取芯片/target 身份。只有
project model、firmware identity、target 和 probe 全部匹配，才能以 exact expected build ID、
ELF SHA、Probe 和 `--authorized` 执行当次公共 flash。

对 P1 执行一次公共 flash；若 H1 已证明 P1 无法形成安全 firmware，则在无烧录状态处理已确认
的 project portability defect，生成 P1c 后重跑 H1，并只烧录 P1c。flash 必须校验 ELF、每个
可编程 segment、build ID、ELF SHA、Git
状态、Probe/target 和 readback。随后收集：

- 用户当场 D4 闪烁观察；
- typed `testtime` 活动采样；
- SVD GPIOE ODR/PE4 翻转；
- 正常无活动 Cortex-M Fault 证据；
- Monitor 的同一 identity snapshot。

任何一项失败都不得继续加 instrumentation 掩盖迁移问题。

### 7.4 H3：正常物理 Target test 与 handoff

在 P2 的 MAP/ELF/mailbox 地址重新通过 H1 适用检查后：

1. v2 discovery 在 read-only transport 上取得 case inventory；host 从 fresh firmware facts 和
   capture UTC 构造 TestInventory，`test target prepare` 把 protocol、case/full inventory
   digests、current project/build/probe 一并派生 single-use action digest；
2. `test target execute` 消费 digest，以同一 MODIFY lease 完成 guarded flash、readback、
   mailbox 读取和 physical TestRun publication；
3. `d4-heartbeat`、D4、`testtime`、PE4 ODR、Monitor 全部 PASS；
4. 执行真实 Cortex-Debug handoff/attach/detach；
5. Toolkit reacquire 后再次读取 `testtime`，证明 handoff 未遗留 owner 或 stale session；
6. 通过另一公共入口做一次等价只读观察，证明 CLI/MCP 不分叉产品行为。

handoff 只在 P2 normal firmware 上执行，不在故障修复中重复，除非 handoff 自身失败且重试有
明确根因。

### 7.5 H4：失败、诊断与修复

P3 与 P4 每次都重新构建，生成不同的 build ID/ELF hash，并分别执行新的 prepare/execute；
旧 action digest 不得复用。

P3 必须形成一个 `execution_source=physical`、`physical_transport_evidence=true` 的 failed
TestRun。Diagnostic 读取失败 TestRun、typed/SVD/Monitor/source/schematic 证据，形成 ranked
hypotheses 和结论。然后 acceptance attempt 在正确 checkpoint 产生 source-change authorization；
其摘要只用于 P4 的 toggle 恢复，不授权其他文件或行为。

P4 fixed-after 必须形成新的 physical passed TestRun。Diagnostic verification 只有在 before/
after project/workspace/probe/target lineage、故障/修复 revisions 和 expected states 全部匹配时
完成。VS08 software AcceptanceRecord 保持 replay-only；VS10 结论由 physical TestRun、Diagnostic
verification 和本活动 campaign ledger 共同表达。

## 8. 公共行为与禁止的便利路径

实现者优先使用现有 generic CLI；MCP parity 使用同一 48-tool server。所有 project-bound 调用
使用 explicit absolute `--project-root`，所有 stateful/hardware/testing 调用使用 explicit
`--data-root` 和 `--session-id`。禁止依赖当前目录、Claude 环境变量、system Python 或调用方
提供的派生 target/ELF/SVD/address。

以下现有边界保持权威：

- conversion/configuration 是 plan/dry-run/apply，输入或 Git 漂移拒绝；
- flash 和 target execute 只接受当前 build identity 的 exact pins；
- target prepare/execute digest 单次、限时、跨进程只有一个 winner；
- one Probe/one owner，handoff 期间不并发 Toolkit 硬件操作；
- mailbox 只有 bounded read，地址必须位于 project profile；
- Monitor 只绑定 loopback dynamic port/random token；
- Diagnostic source change、before/after verification 和 Evidence lineage 使用现有 stores；
- 现有稳定错误码与清理语义不因 campaign script/report 改写。

若现有公共接口无法完成本文场景，这是待分类的问题，不是新增私有脚本直接调用 PyOCD、
手工 flash、第二 MCP tool 或证据拼接的理由。唯一允许的外部 PyOCD 直接调用是 H0 的被文档
允许的 passive inventory；一旦 project manifest 可用，所有目标会话都必须经过 Toolkit。

## 9. 失败分类、停止与证据失效

每个失败先记录为以下之一，再决定下一步：

- `PRODUCT`：Toolkit 公共行为、契约、安全、身份或清理错误，或迁移后的 project/firmware
  行为缺陷；每项再记录 `owner=toolkit|project`；
- `INFRASTRUCTURE`：本地 runner/终端/文件系统/进程设施错误；
- `ENVIRONMENT`：缺失或错误的 runtime、tool、pack、extension、权限或路径；
- `PLATFORM`：Windows/driver/USB/工具平台差异；
- `HARDWARE`：Probe、供电、MCU、连接、板卡行为或物理观察错误；
- `REPORT`：结论正确但序列化、文字、路径或归档错误。

规则：

1. `PRODUCT` 缺陷立即停止受影响硬件路径并冻结最小失败证据。`owner=toolkit` 由同一切片的
   Luna/max 在 Toolkit 分支按 TDD 修复，Sol 审查完整 accepted-base-to-CodeHead diff；
   `owner=project` 使用同一 Luna/max、与当前阶段相符的 exact change binding（P1c campaign diff
   digest 或 P4 Toolkit source-change authorization）和 project regression，Sol 审查
   P0-to-final project diff。不得把 project 缺陷修成 Toolkit 专属 workaround。
2. 若产品修复改变 schema/protocol/version/path/token/lease/authorization/package/Probe/flash/
   transport 行为，只前移集成设计中对应的风险触发检查；不自动运行完整 release matrix。
3. Toolkit bytes、依赖、project source/config、Git revision、ELF、mailbox address、target、Probe
   或安全拓扑变化，会使其后的相关证据失效；无关且仍绑定相同 bytes/contracts 的 PASS 保留。
4. Probe 断开、芯片身份不符、供电异常、外部负载接回或 readback mismatch 不自动重复烧录。
5. 同一产品 finding 两轮不收敛，停止修补，返回接口/设计；不进入 VS10-B。
6. REPORT 缺陷不自动取消未受影响产品/物理 PASS，但报告必须修正后才能接受切片。

## 10. 证据契约

正式 bundle 至少包含：

```text
campaign-manifest.json
intake-manifest.json
inspection.json
conversion-report.json
build-result.json
memory-comparison.json
flash-result.json
handoff-result.json
typed-observation.json
monitor-snapshot.json
target-test-normal.json
target-test-failed.json
diagnostic-session.json
source-change-authorization.json
portability-correction.json        # 仅当 P1c 存在
target-test-fixed.json
migration-summary.md
CHECKSUMS.sha256
```

这不是新的产品 Evidence store 或 schema；它是发行所有者对现有不可变 outputs/roots 的本地
封装。每个物理结论必须能追溯到：

- Toolkit accepted base/CodeHead、0.9.0 candidate manifest 和 runtime package hashes；
- project P0/P1/可选 P1c/P2/P3/P4 完整 commit、clean/dirty 状态和 input snapshot SHA；
- build preset、build ID、ELF/HEX SHA-256、entry/vector 和 MAP memory usage；
- board/MCU、Probe ID、PyOCD target、firmware identity 和 transport config digest；
- workspace/session、TestRun、Diagnostic session、Evidence root 和 authorization digest；
- 操作开始/结束时间、operator/evidence owner、terminal state 和 failure classification；以及
- 用户 D4 观察与 Toolkit `testtime`/PE4/Monitor 观察的明确区分。

截图或用户观察只能支持 D4 板级现象；physical TestRun 必须由 Toolkit 对真实 Probe/transport
执行并发布。失败时保留最小可诊断 raw evidence，删除其余 run-scoped disposable artifacts。

## 11. 比例化验证预算与证据所有者

| 层级 | 检查 | 所有者 | 环境/触发器 |
|---|---|---|---|
| Intake | full manifest、hash equality、P0/no remote/clean | Luna/max | golden 只读；无硬件 |
| Slice software | inspect/convert/configure/build、identity、memory/symbol/mailbox checks | Luna/max | exact 0.9 runtime；无硬件 |
| Physical A1 | P1 flash/readback、D4、typed/SVD/Fault、Monitor | Luna/max | 命名板/Probe和断载拓扑 |
| Physical A2 | P2 normal、P3 failed-before、Diagnostic、P4 fixed-after | Luna/max | 每次 exact authorization |
| Physical A3 | handoff/reacquire、CLI/MCP parity、lease conflict behavior | Luna/max | 同一 project/firmware/probe |
| Review | 两个 Git diff、证据 lineage、受影响重复验证 | GPT-5.6-sol | clean exact heads |

默认不运行完整 Python suite、coverage、UI E2E、package/install/security/license/SBOM matrix、其他
Python/平台、其他板卡/Probe 或业务外设。只有发现对应产品风险触发器时，计划才加入命名检查
及原因。Sol 的独立验证不无条件重复整个烧录循环；至少复核 final fixed physical identity 和一个
关键只读观察，并审查 Luna 产生的完整不可变物理 evidence。若产品字节发生硬件相关修复，Sol
运行受影响 physical smoke。

## 12. 实施、审查、报告与清理

书面规格由用户确认后，Sol 使用 `writing-plans` 编写一份 VS10-A 详细顺序计划。之后仅创建
一名 `gpt-5.6-luna`/`max` 实现者。该实现者拥有 Toolkit 产品修复、隔离 project 实现和初次
物理证据，但不得自我接受、push 或进行远程操作。

Sol 在新的 clean review worktree 中审查：

1. Toolkit `9b7839bb01f88a9e3d2c13203f38aa0d11647232..CodeHead` 完整 diff；
2. project `P0..P4` 完整 diff；
3. intake/golden equality、生成/用户/派生文件所有权；
4. P1/可选 P1c/P2/P3/P4 build/ELF/mailbox/probe/Test/Diagnostic lineage；
5. 所有 PRODUCT/INFRASTRUCTURE/ENVIRONMENT/PLATFORM/HARDWARE/REPORT 记录；
6. 禁止范围、硬件安全和未授权远程状态。

tracked implementation report 位于
`docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/implementation-report.md`。
它记录 accepted base、规格/计划、实现者、Toolkit CodeHead（report commit 前）、project P0/P4、
命令与结果、物理资产、证据 bundle hash、失败分类、清理和本地/远程状态；不写自己的最终
report commit SHA 或滚动 commit 数量。ignored SDD ledger 与 report 必须一致。

每次验证后清理 scratch、构建中间件、一次性日志、截图、下载、临时 data roots、probe
subprocess 和 run artifacts；清理前解析并验证精确绝对路径。保留 source-controlled tests、
P0–P4 project source、intake snapshot、正式 evidence、当前故障诊断所需最小 raw evidence 和
0.9 candidate。绝不清理 golden root、用户文件、共享 cache 或仍需诊断的证据。

## 13. 接受条件

VS10-A 只有同时满足以下条件才是 `ACCEPTED`：

- exact 0.9.0 offline runtime 来自 Toolkit accepted base，版本/inventory 无混用；
- golden 未被写入，完整 intake snapshot 与来源匹配，project P0 clean/no remote；
- P1 完成真实 Keil inspect/baseline、guarded conversion/configure、可重复 GCC build 和通过的
  memory/symbol/entry/vector 检查；
- P1（或经真实证据触发的 P1c）在命名板上 flash/readback 成功，D4、`testtime`、PE4 ODR、
  Fault 和 Monitor 结果一致；
- P2 的 v2 mailbox header/ring 地址由 MAP/ELF 证明，normal physical Target test PASS；
- P3 只引入 held-off 故障，并得到 D4 off、timer alive、PE4 high 和 physical Target FAIL；
- Diagnostic 以真实 evidence 排序假设并把结论绑定 P3；
- P4 source fix 消费 single-use authorization，new build/reflash 后 D4/typed/SVD/Monitor 与
  physical Target test PASS，fix verification 绑定 P3/P4；
- Cortex-Debug 真实 handoff/reacquire、one-owner 与 CLI/MCP 同一公共行为得到证据；
- bundle 完整、checksummed、无 fake/replay physical claim，报告/SDD 账本准确；
- 两个完整 diff 无未解决产品、安全或范围缺陷；
- disposable artifacts 按 `AGENTS.md` 清理，Toolkit/project 最终候选工作树干净；以及
- 本地未推送状态和远程 `master` 状态明确，无未授权外部操作。

缺少任一必须硬件结果不得降级为软件接受；结论保持 `REVISION_REQUIRED`、
`REWRITE_REQUIRED` 或明确的 HARDWARE/ENVIRONMENT blocker。VS10-A 接受后停止，下一步仅是由
Sol 基于已接受 A 的实际接口和证据编写 VS10-B 规格；不得自动实现 VS10-B、形成 1.0 release、
push、PR、merge、tag 或进入后续版本。
