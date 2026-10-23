# STM32 Toolkit 用户指南与排障

本指南面向 **v1.2.0**，说明已验收源码的操作合同。v1.2.0 资产是否可用、最终资格与限制以 [Release 页面](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)为准；[发布状态](release-status.md)保留源冻结前有日期的资格断点。Monitor 工作台与源码目录等行为见[源码规范](superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)；v1.0.1 的历史资格见[执行记录](codex/returns/STM32TK-101/execution.md)。本文对应用户报告的 1–22 项；报告是核查输入，不是接收者机器的安装或实机证据。

## 路径、版本和安全入口

安装前先在 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) 页面确认同版 ZIP 与 `CHECKSUMS.sha256` 均已列出，再按[双语 README](../README_zh-CN.md) 下载并核对哈希；缺少任一资产就停止。之后用包内 `Check` 确认 ToolkitRoot、持久 DataRoot、工程根、发行包及受管 runtime。`Bootstrap`/`Repair` 修改 runtime，先审阅 `Check` 结果和对应发行包，再只执行获准的一种动作，完成后复查到 healthy。Claude Code 的入口为 [skills/setup-stm32-env/SKILL.md](../skills/setup-stm32-env/SKILL.md)；其它 MCP 宿主使用绝对 launcher、显式 project/data root 和 `STM32_TOOLKIT_DATA_ROOT`。`.stm32-project.json` 属于工程，DataRoot 保存机器状态和证据，不能把一次性测试目录当作长期 DataRoot。

解压使用全新、每版专用的 `C:\tools\stm32-toolkit-1.2.0-bundle` 作为 BundleRoot；路径已存在就另选新目录，不覆盖或删除。ZIP 中的 `stm32-toolkit-1.2.0/` 与外层 `release/` 在 BundleRoot 下并列；ToolkitRoot 为 `C:\tools\stm32-toolkit-1.2.0-bundle\stm32-toolkit-1.2.0`，其内部另有供 setup 使用的 `release/`。长期 DataRoot 在 `C:\data\stm32-toolkit`，与 BundleRoot 分离。

## 通用 MCP 配置与公开入口

下例供支持 `mcpServers` 的宿主使用。将三个示例路径换成真实绝对路径；`args` 的 `--data-root` 与 `env` 中的 `STM32_TOOLKIT_DATA_ROOT` 必须指向同一持久目录。cmd 启动器先用环境变量找到受管解释器，Python MCP 入口随后读取这两个显式参数。其它宿主请按其配置格式映射同一 `command`、`args`、`env`，不要改用系统 Python。

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit-1.2.0-bundle\\stm32-toolkit-1.2.0\\bin\\stm32-toolkit-mcp.cmd",
      "args": [
        "--project-root", "C:\\work\\blinky",
        "--data-root", "C:\\data\\stm32-toolkit"
      ],
      "env": {
        "STM32_TOOLKIT_DATA_ROOT": "C:\\data\\stm32-toolkit"
      }
    }
  }
}
```

八个 Claude Code Skill 均调用相同的公开合同：[setup-stm32-env](../skills/setup-stm32-env/SKILL.md)、[migrate-keil](../skills/migrate-keil/SKILL.md)、[configure-stm32-project](../skills/configure-stm32-project/SKILL.md)、[build-firmware](../skills/build-firmware/SKILL.md)、[flash-firmware](../skills/flash-firmware/SKILL.md)、[debug-firmware](../skills/debug-firmware/SKILL.md)、[read-var](../skills/read-var/SKILL.md)、[stm32-monitor](../skills/stm32-monitor/SKILL.md)。当前源码的 49 个 MCP 工具名称及八个 Skill 权威清单在 [public_inventory.py](../tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py)；已发布的 v1.2.0 安装包仍为 48 个工具，不包含本源码切片的 `stm32_keil_preflight`。宿主应以实际已安装版本为准。

以下命令中的路径均为示例，须替换为本机真实绝对路径。**已发布 v1.2.0 runtime（48 个工具）不含 `keil preflight`/`stm32_keil_preflight`**；第一组只列该发行包已有的入口，必须在 `Check` 返回 healthy 后使用。第二组属于当前源码/候选切片，只有实际运行该源码或候选构建时才有这些入口；本文不表示它已打包、安装或部署。CLI 工程命令需显式 `--project-root`；`--json` 命令返回结构化 code/details，`uvprojx` 必须使用正斜杠的可移植相对路径。`--dry-run` 只产生计划，`--apply --plan-id ... --authorized` 是独立写操作，不要直接套用示例 plan ID。

```powershell
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$Cli = Join-Path $DataRoot 'runtime\1.2.0\Scripts\stm32-toolkit.exe'
& $Cli --project-root $ProjectRoot doctor --json
& $Cli --project-root $ProjectRoot project detect --json
& $Cli --project-root $ProjectRoot keil inspect --uvprojx Project/blinky.uvprojx --target-name Debug --json
& $Cli --project-root $ProjectRoot keil convert --uvprojx Project/blinky.uvprojx --target-name Debug --dry-run --json
& $Cli --project-root $ProjectRoot project configure --dry-run --json
& $Cli --project-root $ProjectRoot build --preset arm-debug --json
```

**仅当前源码/候选切片（未随 v1.2.0 发行）：**

```powershell
$CandidateCli = '<current-source-or-candidate stm32-toolkit CLI>'
& $CandidateCli --project-root $ProjectRoot keil preflight --uvprojx Project/blinky.uvprojx --target-name Debug --json
```

Keil `inspect`、`preflight` 和 `convert` 必须指向同一 `uvprojx` 和 `target-name`。`preflight` 只做技术分析：不要求 Git，可在存在 blocker 时仍成功返回 `analysis.complete=true`，并把 `analysis.blockers`、`planReadiness`（取得计划所需的技术/Git 前置）与 `applyReadiness`（在有 reviewed/authorized plan 前恒为 `requires-reviewed-plan` 且 `ready=false`）分开；它不产生可用 plan ID、不写文件、不会自动 `git init`、转码或替换 ARMCC startup。缺少 Git、unborn HEAD、非 Git toplevel 或 dirty/untracked 工作区会作为计划前置失败列出，由工程负责人决定是否建立干净基线。确认 plan 无 blocker、diff/路径均符合预期后，以 PLAN 响应的 `data.plan_id` 调用同一参数链的 `convert --apply --plan-id <data.plan_id> --authorized --json`。PLAN 响应字段是 `data.plan_id`，APPLY 请求参数是 `planId`/`--plan-id`，不要混用带命令前缀的展示文本。`configure` 同样先 `--dry-run` 再用该次 `data.plan_id` `--apply --plan-id <data.plan_id> --authorized --json`；应用前会重新检查输入与改动。构建报告 `BUILD_OUTPUT_STALE` 时，先判定是哪项输入或身份改变，再根据实际计划决定是否 `build --preset arm-debug --clean --json`；不能靠修改旧 receipt 让产物看似有效。

`stm32_project_context` 的旧 `capabilities.*` 布尔值继续保留为保守兼容字段；新增 `capabilityDetails` 逐项给出 `available`、`blocked` 或 `not-evaluated` 及原因/下一步。`flash`、`targetTest`、`monitor`、`breakpointDebug` 的旧布尔 `false` 本身不区分“未探测硬件”与“已知 snapshot provenance 阻断”，必须读 `capabilityDetails`；它也不代表工具不存在。需要探针事实时单独调用只读 `probe list` / `stm32_probe_list`。仅询问已连接探针时，不需要 manifest、构建、debug backend、target 或 SVD；发现结果不授予改板权限，也不证明 target 身份或可烧录。有效工程保留 `workspaceId`，缺失或无效 manifest 时返回 `workspaceId: null` 与明确 `discovery.status=unbound`，不要伪造工程 ID。

**无 Git 的构建与来源边界（当前源码切片）。** 有效托管 GCC/CMake 工程可从导出/非 Git 目录、unborn HEAD 或 Git 缺失/无法执行的环境构建；Git 不可用本身不是构建失败。此时 `firmware-identity.json` 与 `build-result.json` 使用 `schemaVersion: 2`，identity 明确写 `sourceBaseline: "input-snapshot-v1"`、`gitHead: null`、`gitDirty: null`，并只携带有界 `gitEvidence: {"status":"unavailable","code":"BUILD_GIT_INVALID","rule":"head"}`（`rule` 为 `head` 或 `status`）；`inputSnapshotSha256`、`targetDevice`、`preset`、实际 `toolkitVersion` 与 ELF/MAP 字段仍完整。null 绝不表示 clean，不要 `git init`、commit、stash 或伪造哈希。Git 可用时继续使用原有 schema-1 字节与 build ID 语义，schema-1 不接受 nullable Git 字段。context 的 `data.build` 新增 `sourceBaseline`、`gitDirty`、`gitEvidence`，schema-2 新鲜度只依赖精确 input snapshot、target/preset/model 与 ELF/MAP 哈希，不再启动 Git。schema-2 只是 build/build freshness 证据：flash、debug、Target 测试、Monitor 与 acceptance 仍要求 Git-shaped provenance，共享 firmware 准入在任何 probe/lease/attach 前返回稳定 `FIRMWARE_PROVENANCE_UNSUPPORTED`；外层封装可按各自既有协议映射该结果（例如 acceptance recovery 映射为 `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID`），不要假定每个入口对外显示同一代码。新构建的 snapshot 证据会令 `capabilityDetails.flash/targetTest/monitor/breakpointDebug` 明确为 `blocked`。`stm32_probe_list` 仍是独立的只读发现，不受该限制。要使用硬件，先恢复带已提交 HEAD 的 Git 基线并重建；迁移计划/应用也继续要求其 Git 基线。

### 不安装 Skill 的 MCP/VS Code 客户端路线

MCP 客户端即使从不加载 `SKILL.md`，也可按工具描述和真实返回字段完成同一流程：

1. **上下文与选择。** 调用 `stm32_project_context()`。读取 `data.project.kind`；Keil 工程从 `data.project.files` 选择项目根相对 `.uvprojx`（使用 `/`）。context **不列出 target 名称**；多项目候选时要求用户选择，不要猜。读取 `data.capabilityDetails` 的 `status`/`reason`/`nextSteps`，不要只看旧布尔值。
2. **检查与预检。** 若 target 未知，先调用 `stm32_keil_inspect(uvprojx)` 并省略 `targetName`；若返回 `KEIL_TARGET_SELECTION_REQUIRED`，把 `details.targets` 交给用户选择，再用该精确值调用 inspect。成功结果的 `data.inspection.target_name` 是后续必须保留的精确 targetName。然后用同一 `uvprojx`/`targetName` 调用 `stm32_keil_preflight(uvprojx, targetName)`。预检成功只表示 `data.analysis.complete=true`；逐项处理 `data.analysis.blockers`，并读取 `data.planReadiness.status`（`ready-for-plan`/`blocked`）、`ready` 与 `prerequisites`。`data.applyReadiness.status` 始终是 `requires-reviewed-plan`，`ready=false`、`planId=null`；预检不授权任何写入。
3. **不可绕过的修复。** 对 encoding、assembly、scoped option、scatter/memory、manifest 冲突按 blocker 的 `code`、路径和消息处理；不要转码、替换 startup、删除未跟踪文件或伪造 manifest/工程 ID。Git 缺失、unborn HEAD、非 toplevel 或 dirty 工作区只阻塞计划，由工程负责人决定基线；不要让客户端自动 `git init`/commit/stash。
4. **计划与授权。** `planReadiness.ready=true` 后调用 `stm32_keil_convert(uvprojx, targetName)`（无 `planId`、无 `authorized`）取得 PLAN 响应；检查 `data.blockers`、`data.plan_id` 和 `data.patches[].unified_diff`。只有用户显式授权该精确计划后，才调用 `stm32_keil_convert(uvprojx, targetName, planId=<data.plan_id>, authorized=true)`。PLAN 响应字段是 `data.plan_id`，APPLY 请求参数是 `planId`。
5. **配置、构建、烧录。** `stm32_project_configure()` 的 PLAN 响应同样用 `data.plan_id`，APPLY 传 `planId` 与 `authorized=true`。构建前读 `capabilityDetails.build.status`；`stm32_build(preset, clean, timeoutSeconds, authorized=true)` 才执行。烧录使用 `stm32_probe_list()` 返回的精确 `probeId`，以及 context 的 `data.build.buildId`/`data.build.elfSha256` 作为 `expectedBuildId`/`expectedElfSha256`，且仅在显式授权后传 `authorized=true`；不要复用旧 pin。
6. **仅发现探针。** 用户只问“有哪些探针”时直接调用 `stm32_probe_list()`，读取 `data.probes`、`data.workspaceId` 和 `data.discovery`。该调用不需要 manifest、构建、backend、target 或 SVD，也不得继续执行 flash；若 `data.workspaceId=null` 且 `data.discovery.status="unbound"`，如实说明 discovery-only，绝不伪造 workspace ID。发现结果不证明 target 身份或烧录就绪。
7. **VS Code 集成。** 生成的 `.vscode/tasks.json`/`launch.json` 只是配置目标；在真实 VS Code、扩展版本和实际调试会话中运行前，不得声称 IDE 路径已验收或部署完成。

## 工程 manifest 的阶段约束

当前 loader 校验 Schema v2/v3、类型、路径 containment 和安全引用；以下额外规则由 **configure 阶段**执行，不能误说成所有 loader 都拒绝的 schema 全局规则。按 [schemas/stm32-project.schema.json](../schemas/stm32-project.schema.json) 和工程实际来源编辑，不手工伪造 `generatedBy` 或 managed ownership。

| 字段/阶段 | 当前有效约束与处置 |
| --- | --- |
| `build.presets` | configure 要求恰好 `["arm-debug", "arm-release"]`，顺序不变。 |
| `build.elf` | configure 要求 `build/arm-debug/<name>.elf`，`<name>` 只是一层文件名。 |
| `generation.managedManifest` | configure 使用 `.stm32-toolkit/generated-files.json`。已有 managed record 仍按 hash/用户改动保护。 |
| `build.sources`、`generation.nativeLinkerScript`、`debug.svd` | 路径须在工程根内且安全；SVD 文件应存于工程根，选择其准确设备名。 |
| `debug.readableRegions` | 只配置经核对的可信范围；选择 SVD 时必须覆盖所选 SVD 中每个解析出的寄存器的完整地址宽度。不要为消除报错而信任所有地址。 |
| 堆/栈 | manifest 不提供堆栈大小字段。内置 linker 模板保留现行默认容量；特殊工程用已有 `generation.nativeLinkerScript`，自行核对启动向量、初始 SP、区域边界和运行时初始化。 |

`.vscode/{tasks,launch,c_cpp_properties,settings,extensions}.json` 是编辑器目标集合。v1.0.0 的未托管文件可能触发 `UNOWNED_COLLISION`；不要删掉用户文件来绕过。自 v1.0.1 起，configure/build 仅保留这些路径上的未托管普通文件，计划单列 `preserved-unowned`，不读取、改写或收编其内容，IDE 设置仍需用户自行对齐。目录、链接、重解析点、构建必需文件、已有 managed record 或用户修改仍依合同拒绝。CubeMX regeneration 有独立闭域 inventory，configure 成功不代表 regeneration 能接纳这些编辑器文件。

## 迁移和构建：报告项 1–4、9–10、12–13、15、17、20–22

| # | 看见什么 | 本版行为与处置 |
| --- | --- | --- |
| 1 | 子目录 `.uvprojx` 报 `KEIL_PROJECT_NOT_FOUND` | v1.0.0 可用 `--uvprojx Project/xxx.uvprojx`（可移植正斜杠）指明根内路径；自 v1.0.1 起在工程根内安全递归发现，多候选要求显式选择。目录不可枚举返回发现不完整，不能冒充“无工程”。 |
| 2 | `ARMCC_SOURCE_ENCODING_UNSUPPORTED` | 先确认原始编码与版本控制状态，工程负责人决定转换副本/源码；Toolkit 不猜 GB2312/GB18030，也不自动转码。需要 UTF-8 副本时走独立 `normalize-source-comments` 技能：逐文件显式声明编码，默认只读预览，再按已审查 plan 复制到项目外新目录；它只转换注释、绝不改写原工程，也不解决 startup、scoped option、scatter/memory、Git/apply、baseline 等其它 blocker。字节保真仍是项目责任。该技能说明与 helper 位于仓库 `skills/normalize-source-comments/`（安装后为对应个人技能目录，含 `SKILL.md`、`references/lexical-and-plan-contract.md` 和 `scripts/normalize_comments.py`）；MCP 客户端没有、也不应臆造规范化工具，应直接按该目录说明用已验证的 Python 调用 helper。 |
| 3 | `ARMCC_ASSEMBLY_UNSUPPORTED` | 逐个将 ARMCC 汇编适配为 GNU 汇编或等价 C，并核对指令、段、符号和调用约定；若文件是 startup，还须核对向量表、初始 SP 和运行时初始化。不得强行应用旧语法，也不能从旧产物推断适配已正确。 |
| 4, 17, 22 | configure 遇 `UNOWNED_COLLISION` 或编辑器设置已存在 | 核对目标路径与 managed manifest。构建必需文件冲突需工程方决定所有权；自 v1.0.1 起只保留上述五个未托管普通编辑器文件，不 merge/adopt。 |
| 9 | Flash used 似乎含 `.bss`/栈 | 核对原始 ELF/MAP。候选按有内容段的 LMA 计加载容量，NOBITS 只计运行地址预留；没有原始 ELF/MAP 不可宣称复现报告数字。 |
| 10 | RAM `free=0`，栈处于区域高端 | 报告按 section 实际占用区间并集，而非区域首尾跨度。若 `.stack` section 自身含大空隙/预留，它仍是 linker 分配；不能当成可用 RAM。运行时峰值需另测。 |
| 12 | `MIGRATION_GIT_DIRTY` 只有 untracked 文件 | 仍是迁移安全阻断。查看 `git status --short`，逐项决定版本控制或项目 `.gitignore`；不要自动删除、stash、忽略或放宽检查。候选 details 区分 index/tracked/untracked。 |
| 13 | `baseline.available=true` | 只表示找到了可解析的历史 AXF/MAP，不证明本次 GCC/Keil 构建、工具链、授权来源或可比身份；候选在结果中明确这一语义。 |
| 15 | Skill 在 capability false 后停止，或 apply 丢参数 | 先读 `capabilityDetails`：`available` 只表示入口适用于当前工程，`blocked` 给出具体前置，`not-evaluated` 表示 context 未检查（尤其硬件布尔值）。inspect/preflight/plan/apply 保持同一 `uvprojx` 与 `targetName` 并严格核对 plan ID；入口可用不保证迁移没有 blocker。 |
| 20 | schema 未写尽跨字段规则 | 以上配置阶段规则是当前合同；不要手工生成错误 manifest 或把 configure 条件升格为 loader 不兼容。根与包内 schema 副本应一致。 |
| 21 | 默认栈容量/`__StackTop` 语义不符工程 | 候选模板的向下增长栈 Top 在高地址、Limit 在低地址；默认容量不新增配置。需要项目特定大小时用受控 native linker 并核对实际 ELF/MAP。 |

## Doctor、context、Probe 与运行态：报告项 5–8、11、14、16

| # | 看见什么 | 本版行为与处置 |
| --- | --- | --- |
| 5, 16 | flash 成功后 OBSERVE attach 拒绝 `halted` | flash 的编程/回读 receipt 不证明固件正在运行。核对当前目标状态与原因；如需 reset/resume，应走独立、明确授权的控制流程，不能在观察失败后自动恢复。`--recovery-under-reset` 是受控烧录选项，不是所有旧固件必需；它的 halted 后置不改变此结论。 |
| 6 | `SVD_SELECTION_REQUIRED` / `SVD_ADDRESS_OUT_OF_RANGE` | 将正确设备 SVD 放在工程根，配置 `debug.svd`、设备与可信区域；逐项核对候选返回的首个失败寄存器路径、地址、宽度和区域。不要只放宽为全地址可读。 |
| 7 | `DEBUG_FLASH_MISMATCH` | 比较 workspace/session/build/input/probe/target/receipt 等全部绑定，重新按当前配置 build/flash/授权；旧 receipt 不可 rebind。候选列具体失配字段和经验证读取的 ELF 内容是否相同；ELF 相同也不等于完整身份相同。 |
| 8 | `PROBE_ATTACH_FAILED`，`target-unsupported` | 核对请求的 `debug.target`、实际器件与已安装 pack/PyOCD 支持列表，记录来源。`probeCore.registry` 是 Probe 租约目录，不是 PyOCD target 注册表；缺失不能推断不支持器件。 |
| 11 | `capabilities.*` 与当时人工观测不一致 | 旧布尔值表示当前阶段就绪/兼容语义，`capabilityDetails` 才区分 `available`、`blocked`、`not-evaluated`。context 不枚举探针；`hardware` 是未探测快照，需要独立 `probe list` 才能取得当次探针事实。`probe list` 不要求 manifest/构建/backend/target/SVD；无有效工程时返回 `workspaceId: null` 和 `discovery.status=unbound`。 |
| 14 | doctor 启动 CubeMX GUI 或扩展显示 missing | 候选对 GUI 工具只读静态版本，取不到标 unknown；VS Code 扩展未实际探测为 `installed=false, version=null, status=not-probed`，不等同“未安装”。在 v1.0.0 现场若 GUI 被启动，先退出/记录，不把该次输出当静态版本证明。 |

`read variable`、`read register`、有限采样与 Fault 有不同前置。OBSERVE 的短暂停核与持续观测需分开记证；完整 Fault 需稳定 halted，不能把 running OBSERVE 偷偷升权。[标准测试流程](testing/standard-test-procedure.md)规定实机前置、首错停止与证据归属。

## Target 测试与 transport 资格边界

Target-frame v1 继续兼容已有工程的 v1 fixture、字节和 replay；回放不等于新物理证据。v2 由工程根内的 `testing.target.protocol` 显式选择，host 将工程、固件、Probe、target、session、revision 和 case-inventory digest 绑定。只有受控 flash、readback 与 transport 身份检查通过后，才可按真实结果发布物理 TestRun；CLI/MCP 的 target prepare/execute 从工程配置读取身份，不允许调用方注入另一 ELF、target 或地址。

VS10-A 在具名参考硬件上只有 `memory-mailbox` transport 取得实体资格证据。RTT、UART、semihosting 仍有软件 adapter 和 replay 兼容路径，但不据此称为同一参考硬件上的物理 PASS。新增设备、transport 或本版的实体结论都须按[发布资格](testing/release-qualification.md)与[标准测试流程](testing/standard-test-procedure.md)重新取证。

## Monitor：报告项 18–19

Monitor 工作台默认使用简体中文和浅色界面。打开授权标签后，顶栏可展开“连接与固件详情”来刷新、连接、重新连接或释放探针，并查看项目和固件身份。连接成功后仍需单独选择观测组并点击“开始采样”；实时页将采样状态、波形、最新数值和实际采样率放在同一工作区，也可按按钮显示或隐藏曲线。左侧“新建观测组”或“编辑组配置”保存草稿；“浏览变量与寄存器”可搜索并加入草稿。切换到“历史记录”再返回不会清掉未保存的组和目录输入，也不会新建采样连接。

编辑观测组时，点击当前组不会清掉未保存内容。带有未保存修改的草稿切换到别的组或新建组，会先要求选择“继续编辑”或“放弃修改并继续”；确认前原稿和下次采样目标不变。新建稿标为“未保存”，下次采样只能选已保存的组；采样区分别显示“下次开始采样”和服务端“当前运行”的组，切换编辑目标不会改变已经运行的采样。保存、删除、导入或列表刷新进行中，组编辑与选择暂时停用，采样暂停和停止仍可操作。删除确认绑定当时的组版本，列表或编辑目标变化后需重新确认。

组版本或名称发生冲突时，“操作提示”提供只读的“刷新观测组”，不会自动重发保存、删除或导入；草稿保留。即使关闭错误提示，也须等列表刷新成功后才能再次保存、删除或导入；刷新失败仍可编辑草稿、切换目标和预览导入。刷新后可明确放弃草稿并载入最新版本，或选“保留为新组”，核对名称后再保存。原组已删除时，旧 ID 不能再保存。目录输入可留空，再点“搜索/加载”浏览；切换变量或寄存器类型后可各自加载。不可采样寄存器会显示服务端给出的访问与读取原因，添加按钮停用。导入预览列出组名和对象数量；导入不会覆盖已有组，名称冲突以服务端检查为准，失败不丢当前草稿。

实时波形按每条记录自己的采集时刻放在共同的“相对时间（ms）”横轴上，图下显示起点 UTC；提示中可查看该点原始 UTC、数值和纳秒值。晚加入的曲线不会借用先前曲线的时间，读取空缺与数据间断不会补成数值或跨越连接。没有选择、已选择但尚无样本、只有采集时间而无可绘制数值时，页面分别给出提示。图内滑块或内部缩放与工具栏使用同一百分比范围；放大最窄为 1%、缩小最宽为 100%，重置回全幅。该百分比针对当前缓存时间域，新样本进入或旧点淘汰时，绝对时间范围可能随之移动。数值区显示“已选择 N / 8 条曲线”并列出已选项；满 8 条时未选项的显示按钮停用，可先移除已选曲线，即使它已不在当前观测组的数值表里。

历史页的时间输入均按 **UTC** 解释，查询范围起点包含、终点不含。初次打开不自动查询全部历史；输入起止时间并点击“查询历史”，然后可逐页查看。查询进行中会单列正在查询的范围；如果已有结果，结果区仍标明上次成功范围。此时可编辑下一次查询的输入，完成或失败的请求不会覆盖新草稿。失败可在“操作提示”重试原范围和分页；翻页只推进已成功的结果。每条记录显示 UTC 采集时间、观测项、数值或读取错误，以及轮次、序号和值序位。导出默认跟随已成功查询的范围；手工修改导出范围后，新查询会保留这份草稿并提供“使用查询范围”按钮。没有查询时也可手工指定范围独立导出。导出格式是 CSV 或 JSONL，已生成任务显示其提交时的范围；修改当前输入不会改写已提交任务。遇到采样中断时，“非最新数据”和状态文字提示旧数值；展开“诊断详情”可查看原始代码与消息。

实时连接在浏览器收到打开事件前显示“正在连接实时数据”，连接状态和最新数值的时效分别显示。断流后可点“重新连接实时数据”：工作台先读取当前状态、核对原会话与工程，再用已接收的事件游标恢复订阅；这一步不连接探针、不启动或停止采样，也不发送写入。核对或连接进行中可点“取消连接”，未保存草稿、历史查询和已有数据保持可用。普通失败会留在“操作提示”中，重试将重新执行整个状态核对与实时连接；若服务会话或工程已变化，须重新打开工作台。出现“需要刷新状态”时可手动点“刷新状态”；刷新完成后，只有新的匹配样本能解除保留数值的“非最新数据”提示。该入口不自动重连或轮询。

实时数值每行显示自己的 UTC 采集时间。图表与数值表上方标明当前或上次采样的轮次、运行组和版本；切换左侧的编辑组不会将另一组的对象误标为当前运行组。运行组版本尚未从列表核对时，只保留同一轮次已接受的旧值并标明其来源。尚未收到样本时，状态栏的速率和延迟会显示“尚未收到样本”；暂停、断流、状态待核对或运行组版本变化时，既有速率和延迟标为“上次样本”并显示其 UTC 时间。丢弃计数仍是单独的累计数据。观测绑定或采样轮次变化后，上轮样本时间会清除。

以下 UI02/UI03 就地恢复、固定端口、书签与会话恢复行为属于 v1.2.0 已验收源码；取得并核验 v1.2.0 发行包、安装且 `Check` 确认 healthy 后，才能按本版启动器使用。v1.0.1 发布包不支持 `--port`，也不包含这些就地恢复操作。

已打开的工作台内，普通操作失败会在导航下方的“操作提示”就地显示原因；多个提示可分别查看、关闭或按提示重试，当前页面、最后成功的数据和未保存草稿保留。读取重试使用失败时的原查询、页游标或导出任务 ID。除上述组冲突外，写入被明确拒绝时，须先核对原目标和内容并确认，才会重试上次操作；编辑按钮仍提交当前草稿。写入结果未知时不盲目重复提交：能核对的操作只刷新状态或列表，导出创建若没有任务 ID 则说明结果未知。若写入已成功而随后刷新失败，只重试读取，不重复写入。无效的导入文件须重新选择。初次读取普通失败可重试初始化；真正的认证或访问失效仍整页阻断，按提示重新打开授权标签。

`open --port 8765` 成功后，终端显示不带 token 的 `http://127.0.0.1:8765/`，可将这个短地址加入书签。服务保持运行、同一浏览器配置的会话 cookie 有效时，关闭标签页后打开书签可回到工作台。关闭整个浏览器后是否保留会话取决于浏览器配置；新浏览器配置不会自动继承原会话。若短地址提示“当前会话已失效”，在**原 `open` 前台交互终端**按 Enter，启动器会把同一服务的授权页面再次交付系统默认浏览器。该浏览器配置完成认证后，在原短地址页面点“重新检查会话”；只有状态核对成功才进入工作台。交付请求本身不证明浏览器已完成认证。非交互启动时，须由启动方重新交付授权页面；不要保存或手输包含 fragment token 的授权链接。403“访问被拒绝”须检查入口、请求来源与浏览器配置，不能当作会话过期处理或放宽访问限制。

`bin/stm32-monitor.cmd` 先用 `STM32_TOOLKIT_DATA_ROOT` 定位相同版本的受管 Python；单给 `--data-root` 不能启动 cmd。Monitor 入口启动后才读取 `open --data-root`，两处须指向同一 DataRoot。v1.2.0 启动器只使用已安装的 `runtime/1.2.0`；不要把另一版本的解释器、`PYTHONPATH` 源码覆盖或不同版 wheel 混入。以下命令要求**本版发行包已核验、安装且 Check 为 healthy**：它打开服务和新浏览器标签，并在前台保持运行；用该终端的 Ctrl-C 正常结束，不存在通用后台 daemon/stop 协议。

```powershell
$BundleRoot = 'C:\tools\stm32-toolkit-1.2.0-bundle'
$ToolkitRoot = Join-Path $BundleRoot 'stm32-toolkit-1.2.0'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$env:STM32_TOOLKIT_DATA_ROOT = $DataRoot
& (Join-Path $ToolkitRoot 'bin\stm32-monitor.cmd') open --project $ProjectRoot --data-root $DataRoot --port 8765
```

| # | 看见什么 | 处置 |
| --- | --- | --- |
| 18 | 启动器报缺少 `STM32_TOOLKIT_DATA_ROOT`、调用超时、想重启 | 先运行只读 `Check` 并确认同一 Toolkit 根目录与 DataRoot；按上例向已安装 v1.2.0 启动器同时提供相同的环境变量和 `--data-root`。在可保持运行的终端前台调用 `open`，完成后用该前台的 Ctrl-C 正常结束。受限自动化终端超时不能证明服务损坏；没有通用 stop/restart 子命令。 |
| 19 | 手输 `localhost` 得 403、书签会话失效，或端口已占用 | 只使用终端显示的 `127.0.0.1` 短地址作为书签；不要改成 `localhost` 或放宽 Host/Origin。会话失效时，在原交互 `open` 终端按 Enter，再在完成认证的同一浏览器配置中点“重新检查会话”。403 为访问拒绝，应先检查入口与来源。端口占用不会静默改用随机端口，检查并分配各工程独立端口。短书签指向该端口当前服务，重新分配给另一工程后应在工作台顶栏核对工程身份。不要打印、复制、保存完整 fragment URL。 |

省略 `--port` 时继续由系统分配临时端口；`serve --json` 也可指定 `--port`，其 JSON 字段保持不变。服务停止后，短书签不能自行启动服务；重复执行第二个 `open` 也不能重新打开已经运行的同一工作区服务。Enter 恢复只属于仍在运行的原 `open` 进程，不提供跨进程命令或跨浏览器配置的会话共享。

## 升级与历史材料

已发布 v1.0.0/v1.0.1 的标签、发行资产、凭据和数据边界不变。v1.2.0 源码的 Toolkit、Monitor、UI、插件、启动器与发行身份统一为 1.2.0；已有 1.1.2、1.0.1 及更早获批 runtime 经 `Check` 后只能以获授权的 `Repair` 事务升级，旧目录进入隔离区；只有既有事务可恢复分支才按其规则回滚旧 runtime 和状态，具体证据范围见[发布状态](release-status.md)。多旧版、未知未来目录、同版本不同来源、降级和锁定提升继续拒绝；不要手动移走状态文件。现有工程 `generatedBy` 保留真实旧版本；1.1.2/1.0.1/1.0.0/0.9.0 工程可计划和应用，只有显式 configure 事务刷新未改动的托管模板与记账，用户改动仍阻断。新 build 生成实际 1.2.0 身份，旧 flash receipt/evidence 不改写。工程 producer 可读不代表旧固件身份可供新版观测：现有 flash 合同要求 build 的 Toolkit 版本与当前 1.2.0 精确一致，1.1.2 build/flash receipt 不能直接绑定 1.2.0 运行观测，旧 build 会以 `FIRMWARE_IDENTITY_MISMATCH` 被拒绝；后续须经授权重建、烧录并建立新观测身份。旧 1.1.2/1.0.1 导出清单的 Toolkit/Monitor 版本不符合 1.2.0 精确校验；需使用原版本读取旧导出，或在新版本重新创建，不自动迁移或重签。改变 debug 元数据后，完整输入身份合同可能要求重新 configure、clean build 和必要的新烧录；运行观测仍按原完整身份与具名硬件授权，不提供内容等价 rebind。本指南不代替本版 Release notes 的最终资格结论；源冻结前断点没有新的实机资格证据；v1.0.1 的历史资格事实见[执行记录](codex/returns/STM32TK-101/execution.md)与[发布状态](release-status.md)。

当前源树已退役旧阶段计划、报告、资格工具及其专属测试。需要审计原文时使用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`，不要重建旧机器本地路径。发行构建仍使用现行 `tools/release/build_0900_artifacts.py`、`tools/release/release_0900_policy.json`、许可证和当前测试。部署/IDE 另见 [Windows 前置核对](testing/windows-deployment-and-ide-preflight.md)。
