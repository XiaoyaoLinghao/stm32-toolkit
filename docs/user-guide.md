# STM32 Toolkit 用户指南与排障

本指南同时说明已发布 **v1.0.0** 与当前源码 **v1.0.1 候选**。下列 v1.0.1 行为已进入候选代码，仍待独立集成审查与发布资格验证；版本号和本文都不代表已安装或已发布。支持环境、发布事实及保留限制见[发布状态](release-status.md)，设计边界见[补丁规格](superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)。本文对应用户报告的 1–22 项；报告是核查输入，不是本机新的实机证据。

## 路径、版本和安全入口

使用[双语 README](../README_zh-CN.md) 中的 `Check` 确认 ToolkitRoot、持久 DataRoot、工程根、发行包及受管 runtime。`Bootstrap`/`Repair` 修改 runtime，先审阅 `Check` 结果和对应发行包，再只执行获准的一种动作。Claude Code 的入口为 [skills/setup-stm32-env/SKILL.md](../skills/setup-stm32-env/SKILL.md)；其它 MCP 宿主使用绝对 launcher、显式 project/data root 和 `STM32_TOOLKIT_DATA_ROOT`。`.stm32-project.json` 属于工程，DataRoot 保存机器状态和证据，不能把一次性测试目录当作长期 DataRoot。

## 通用 MCP 配置与公开入口

下例供支持 `mcpServers` 的宿主使用。将三个示例路径换成真实绝对路径；`args` 的 `--data-root` 与 `env` 中的 `STM32_TOOLKIT_DATA_ROOT` 必须指向同一持久目录。cmd 启动器先用环境变量找到受管解释器，Python MCP 入口随后读取这两个显式参数。其它宿主请按其配置格式映射同一 `command`、`args`、`env`，不要改用系统 Python。

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit-1.0.1\\bin\\stm32-toolkit-mcp.cmd",
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

八个 Claude Code Skill 均调用相同的公开合同：[setup-stm32-env](../skills/setup-stm32-env/SKILL.md)、[migrate-keil](../skills/migrate-keil/SKILL.md)、[configure-stm32-project](../skills/configure-stm32-project/SKILL.md)、[build-firmware](../skills/build-firmware/SKILL.md)、[flash-firmware](../skills/flash-firmware/SKILL.md)、[debug-firmware](../skills/debug-firmware/SKILL.md)、[read-var](../skills/read-var/SKILL.md)、[stm32-monitor](../skills/stm32-monitor/SKILL.md)。48 个 MCP 工具名称及八个 Skill 的当前权威清单在 [public_inventory.py](../tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py)；宿主应以实际已安装版本为准。

以下命令中的路径均为示例，须替换为本机真实绝对路径。CLI 工程命令需显式 `--project-root`；`--json` 命令返回结构化 code/details。`--dry-run` 只产生计划，`--apply --plan-id ... --authorized` 是独立写操作，不要直接套用示例 plan ID。

```powershell
stm32-toolkit --project-root C:\work\blinky doctor --json
stm32-toolkit --project-root C:\work\blinky project detect --json
stm32-toolkit --project-root C:\work\blinky keil inspect --uvprojx Project\blinky.uvprojx --target-name Debug --json
stm32-toolkit --project-root C:\work\blinky keil convert --uvprojx Project\blinky.uvprojx --target-name Debug --dry-run --json
stm32-toolkit --project-root C:\work\blinky project configure --dry-run --json
stm32-toolkit --project-root C:\work\blinky build --preset arm-debug --json
```

Keil `inspect`/`convert` 必须指向同一 `uvprojx` 和 `target-name`。确认 plan 无 blocker、diff/路径均符合预期后，以返回的真实 plan ID 调用同一参数链的 `convert --apply --plan-id <plan-id> --authorized --json`。`configure` 同样先 `--dry-run` 再用该次 plan ID `--apply --plan-id <plan-id> --authorized --json`；应用前会重新检查输入与改动。构建报告 `BUILD_OUTPUT_STALE` 时，先判定是哪项输入或身份改变，再根据实际计划决定是否 `build --preset arm-debug --clean --json`；不能靠修改旧 receipt 让产物看似有效。

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

`.vscode/{tasks,launch,c_cpp_properties,settings,extensions}.json` 是编辑器目标集合。v1.0.0 的未托管文件可能触发 `UNOWNED_COLLISION`；不要删掉用户文件来绕过。v1.0.1 候选仅在 configure/build 保留这些路径上的未托管普通文件，计划单列 `preserved-unowned`，不读取、改写或收编其内容，IDE 设置仍需用户自行对齐。目录、链接、重解析点、构建必需文件、已有 managed record 或用户修改仍依合同拒绝。CubeMX regeneration 有独立闭域 inventory，configure 成功不代表 regeneration 能接纳这些编辑器文件。

## 迁移和构建：报告项 1–4、9–10、12–13、15、17、20–22

| # | 看见什么 | 当前候选行为与处置 |
| --- | --- | --- |
| 1 | 子目录 `.uvprojx` 报 `KEIL_PROJECT_NOT_FOUND` | v1.0.0 可用 `--uvprojx Project\xxx.uvprojx` 指明根内路径；v1.0.1 候选在工程根内安全递归发现，多候选要求显式选择。目录不可枚举返回发现不完整，不能冒充“无工程”。 |
| 2 | `ARMCC_SOURCE_ENCODING_UNSUPPORTED` | 先确认原始编码与版本控制状态，工程负责人决定转换副本/源码；Toolkit 不猜 GB2312/GB18030，也不自动转码。字节保真是项目责任。 |
| 3 | `ARMCC_ASSEMBLY_UNSUPPORTED` | 逐个将 ARMCC 汇编适配为 GNU 汇编或等价 C，并核对指令、段、符号和调用约定；若文件是 startup，还须核对向量表、初始 SP 和运行时初始化。不得强行应用旧语法，也不能从旧产物推断适配已正确。 |
| 4, 17, 22 | configure 遇 `UNOWNED_COLLISION` 或编辑器设置已存在 | 核对目标路径与 managed manifest。构建必需文件冲突需工程方决定所有权；v1.0.1 候选只保留上述五个未托管普通编辑器文件，不 merge/adopt。 |
| 9 | Flash used 似乎含 `.bss`/栈 | 核对原始 ELF/MAP。候选按有内容段的 LMA 计加载容量，NOBITS 只计运行地址预留；没有原始 ELF/MAP 不可宣称复现报告数字。 |
| 10 | RAM `free=0`，栈处于区域高端 | 报告按 section 实际占用区间并集，而非区域首尾跨度。若 `.stack` section 自身含大空隙/预留，它仍是 linker 分配；不能当成可用 RAM。运行时峰值需另测。 |
| 12 | `MIGRATION_GIT_DIRTY` 只有 untracked 文件 | 仍是迁移安全阻断。查看 `git status --short`，逐项决定版本控制或项目 `.gitignore`；不要自动删除、stash、忽略或放宽检查。候选 details 区分 index/tracked/untracked。 |
| 13 | `baseline.available=true` | 只表示找到了可解析的历史 AXF/MAP，不证明本次 GCC/Keil 构建、工具链、授权来源或可比身份；候选在结果中明确这一语义。 |
| 15 | Skill 在 capability false 后停止，或 apply 丢参数 | 候选可发现受保护根内的子目录工程；inspect/plan/apply 保持同一 target/path 并严格核对 plan ID。capability 表示当前可进入相应阶段，不保证迁移没有 blocker。 |
| 20 | schema 未写尽跨字段规则 | 以上配置阶段规则是当前合同；不要手工生成错误 manifest 或把 configure 条件升格为 loader 不兼容。根与包内 schema 副本应一致。 |
| 21 | 默认栈容量/`__StackTop` 语义不符工程 | 候选模板的向下增长栈 Top 在高地址、Limit 在低地址；默认容量不新增配置。需要项目特定大小时用受控 native linker 并核对实际 ELF/MAP。 |

## Doctor、context、Probe 与运行态：报告项 5–8、11、14、16

| # | 看见什么 | 当前候选行为与处置 |
| --- | --- | --- |
| 5, 16 | flash 成功后 OBSERVE attach 拒绝 `halted` | flash 的编程/回读 receipt 不证明固件正在运行。核对当前目标状态与原因；如需 reset/resume，应走独立、明确授权的控制流程，不能在观察失败后自动恢复。`--recovery-under-reset` 是受控烧录选项，不是所有旧固件必需；它的 halted 后置不改变此结论。 |
| 6 | `SVD_SELECTION_REQUIRED` / `SVD_ADDRESS_OUT_OF_RANGE` | 将正确设备 SVD 放在工程根，配置 `debug.svd`、设备与可信区域；逐项核对候选返回的首个失败寄存器路径、地址、宽度和区域。不要只放宽为全地址可读。 |
| 7 | `DEBUG_FLASH_MISMATCH` | 比较 workspace/session/build/input/probe/target/receipt 等全部绑定，重新按当前配置 build/flash/授权；旧 receipt 不可 rebind。候选列具体失配字段和经验证读取的 ELF 内容是否相同；ELF 相同也不等于完整身份相同。 |
| 8 | `PROBE_ATTACH_FAILED`，`target-unsupported` | 核对请求的 `debug.target`、实际器件与已安装 pack/PyOCD 支持列表，记录来源。`probeCore.registry` 是 Probe 租约目录，不是 PyOCD target 注册表；缺失不能推断不支持器件。 |
| 11 | `capabilities.*` 与当时人工观测不一致 | `capabilities.build` 表示当前可执行准备状态，managed manifest 失效可使其为 false。context 不枚举探针；`hardware` 是未探测快照，需要独立 `probe list` 才能取得当次探针事实。候选显式返回 readiness/未探测语义。 |
| 14 | doctor 启动 CubeMX GUI 或扩展显示 missing | 候选对 GUI 工具只读静态版本，取不到标 unknown；VS Code 扩展未实际探测为 `installed=false, version=null, status=not-probed`，不等同“未安装”。在 v1.0.0 现场若 GUI 被启动，先退出/记录，不把该次输出当静态版本证明。 |

`read variable`、`read register`、有限采样与 Fault 有不同前置。OBSERVE 的短暂停核与持续观测需分开记证；完整 Fault 需稳定 halted，不能把 running OBSERVE 偷偷升权。[标准测试流程](testing/standard-test-procedure.md)规定实机前置、首错停止与证据归属。

## Target 测试与 transport 资格边界

Target-frame v1 继续兼容已有工程的 v1 fixture、字节和 replay；回放不等于新物理证据。v2 由工程根内的 `testing.target.protocol` 显式选择，host 将工程、固件、Probe、target、session、revision 和 case-inventory digest 绑定。只有受控 flash、readback 与 transport 身份检查通过后，才可按真实结果发布物理 TestRun；CLI/MCP 的 target prepare/execute 从工程配置读取身份，不允许调用方注入另一 ELF、target 或地址。

VS10-A 在具名参考硬件上只有 `memory-mailbox` transport 取得实体资格证据。RTT、UART、semihosting 仍有软件 adapter 和 replay 兼容路径，但不据此称为同一参考硬件上的物理 PASS。新增设备、transport 或当前候选的实体结论都须按[发布资格](testing/release-qualification.md)与[标准测试流程](testing/standard-test-procedure.md)重新取证。

## Monitor：报告项 18–19

`bin/stm32-monitor.cmd` 在 v1.0.0 和 v1.0.1 都先用 `STM32_TOOLKIT_DATA_ROOT` 定位受管 Python；单给 `--data-root` 不能启动 cmd。Python CLI 启动后才读取 `open --data-root`，两处须指向同一 DataRoot。以下命令符合当前 parser，暂设环境变量、打开服务和新浏览器标签、前台保持运行，并在退出时恢复原环境。v1.0.1 不新增后台 daemon/stop 协议。

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit-1.0.1'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$previousDataRoot = [Environment]::GetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', 'Process')
try {
  [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', $DataRoot, 'Process')
  & (Join-Path $ToolkitRoot 'bin\stm32-monitor.cmd') open --project $ProjectRoot --data-root $DataRoot
} finally {
  [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', $previousDataRoot, 'Process')
}
```

| # | 看见什么 | 处置 |
| --- | --- | --- |
| 18 | 启动器报缺少 `STM32_TOOLKIT_DATA_ROOT`、调用超时、想重启 | 先运行只读 `Check` 并确认同一发行包与 DataRoot；按上例暂设环境变量并向 Python CLI 传相同的 `--data-root`。在可保持运行的终端前台调用 `open`，完成后用该前台的 Ctrl-C 正常结束。受限自动化终端超时不能证明服务损坏；没有通用 stop/restart 子命令。 |
| 19 | 手输 `localhost` 得 403，或旧标签提示 bootstrap 失败 | 使用 `open` 本次新开的 `127.0.0.1` 认证标签；不要手输 URL、复用失去 fragment token 的书签或尝试放宽 Host/Origin。候选在缺 token/连接失败时显示无秘密恢复提示；不要打印、复制、保存完整 fragment URL。 |

## 升级与历史材料

已发布 v1.0.0 的标签、发行资产、凭据和数据边界不变。当前候选的 Toolkit、Monitor、UI、插件、启动器与发行身份统一为 1.0.1；已有 1.0.0 runtime 经 `Check` 后只能以获授权的 `Repair` 事务升级，旧目录进入隔离区，失败回滚旧 runtime 和状态。多旧版、未知未来目录、同版本不同来源、降级和锁定提升继续拒绝；不要手动移走状态文件。现有工程 `generatedBy` 保留真实旧版本；1.0.0/0.9.0 工程可计划和应用，只有显式 configure 事务刷新未改动的托管模板与记账，用户改动仍阻断。新 build 生成实际 1.0.1 身份，旧 flash receipt/evidence 不改写。改变 debug 元数据后，完整输入身份合同可能要求重新 configure、clean build 和必要的新烧录；运行观测仍按原完整身份与具名硬件授权，不提供内容等价 rebind。本候选未发布、未安装，也没有新实机资格结论，仍须按[实施计划](superpowers/plans/2026-10-10-stm32tk-101-patch-plan.md)及发布资格验证。

当前源树已退役旧阶段计划、报告、资格工具及其专属测试。需要审计原文时使用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`，不要重建旧机器本地路径。发行构建仍使用现行 `tools/release/build_0900_artifacts.py`、`tools/release/release_0900_policy.json`、许可证和当前测试。部署/IDE 另见 [Windows 前置核对](testing/windows-deployment-and-ide-preflight.md)。
