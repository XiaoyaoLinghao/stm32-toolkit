# STM32 Toolkit 用户指南与排障

本指南面向 **v1.3.0 本地候选源码**，说明其操作合同；v1.3.0 尚无 GitHub Release 或公开下载链接，完整资格验证与发布仍待完成，本地候选的构建与验证记录在交付证据中。**公开下载仍是 v1.2.0**：其资产是否可用、最终资格与限制以 [v1.2.0 Release 页面](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)为准；[发布状态](release-status.md)保留历史断点并单独记录 v1.3.0 候选。Monitor 工作台与源码目录等行为见[源码规范](superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)；v1.0.1 的历史资格见[执行记录](codex/returns/STM32TK-101/execution.md)。本文对应用户报告的 1–22 项；报告是核查输入，不是接收者机器的安装或实机证据。

## 路径、版本和安全入口

**公开下载（v1.2.0，legacy/public download）：** 安装前先在 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) 页面确认同版 ZIP 与 `CHECKSUMS.sha256` 均已列出，再按[双语 README](../README_zh-CN.md) 下载并核对哈希；缺少任一资产就停止。之后用包内 `Check` 确认 ToolkitRoot、持久 DataRoot、工程根、发行包及受管 runtime。`Bootstrap`/`Repair` 修改 runtime，先审阅 `Check` 结果和对应发行包，再只执行获准的一种动作，完成后复查到 healthy。v1.3.0 候选只能由本地官方构建产出，其 `Check` 期望 `runtime/1.3.0`；不要把候选路径、哈希或包名写成公开下载。Claude Code 的入口为 [skills/setup-stm32-env/SKILL.md](../skills/setup-stm32-env/SKILL.md)；其它 MCP 宿主使用绝对 launcher、显式 project/data root 和 `STM32_TOOLKIT_DATA_ROOT`。`.stm32-project.json` 属于工程，DataRoot 保存机器状态和证据，不能把一次性测试目录当作长期 DataRoot。

公开下载的 v1.2.0 包解压使用全新、每版专用的 `C:\tools\stm32-toolkit-1.2.0-bundle` 作为 BundleRoot；路径已存在就另选新目录，不覆盖或删除。ZIP 中的 `stm32-toolkit-1.2.0/` 与外层 `release/` 在 BundleRoot 下并列；ToolkitRoot 为 `C:\tools\stm32-toolkit-1.2.0-bundle\stm32-toolkit-1.2.0`，其内部另有供 setup 使用的 `release/`。长期 DataRoot 在 `C:\data\stm32-toolkit`，与 BundleRoot 分离。

## 通用 MCP 配置与公开入口

下例对应一个**已核验且 `Check` 为 healthy 的本地 v1.3.0 候选**（DataRoot 中确实存在 `runtime/1.3.0`）；它可照抄使用。本文不记录该候选的安装资格：另一用户会话曾安装候选，本次切片未复核该安装，也未安装本补丁。若使用公开下载的 v1.2.0，请把 `command` 换为 `stm32-toolkit-1.2.0` 路径，并按已发布的 48 工具、8 Skill 清单核对。下例供支持 `mcpServers` 的宿主使用。将三个示例路径换成真实绝对路径；`args` 的 `--data-root` 与 `env` 中的 `STM32_TOOLKIT_DATA_ROOT` 必须指向同一持久目录。cmd 启动器先用环境变量找到受管解释器，Python MCP 入口随后读取这两个显式参数。其它宿主请按其配置格式映射同一 `command`、`args`、`env`，不要改用系统 Python。

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit-1.3.0-bundle\\stm32-toolkit-1.3.0\\bin\\stm32-toolkit-mcp.cmd",
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

九个随插件提供的 Claude Code Skill 中，八个工作流 Skill 调用相同的公开合同：[setup-stm32-env](../skills/setup-stm32-env/SKILL.md)、[migrate-keil](../skills/migrate-keil/SKILL.md)、[configure-stm32-project](../skills/configure-stm32-project/SKILL.md)、[build-firmware](../skills/build-firmware/SKILL.md)、[flash-firmware](../skills/flash-firmware/SKILL.md)、[debug-firmware](../skills/debug-firmware/SKILL.md)、[read-var](../skills/read-var/SKILL.md)、[stm32-monitor](../skills/stm32-monitor/SKILL.md)；[normalize-source-comments](../skills/normalize-source-comments/SKILL.md) 是独立的显式编码复制助手，只生成注释级 UTF-8 副本，不属于迁移 apply，也不新增 MCP 工具。当前源码的 52 个 MCP 工具名称及九个 Skill 权威清单在 [public_inventory.py](../tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py)；已发布的 v1.2.0 安装包仍为 48 个工具、8 个 Skill，不包含 `stm32_keil_preflight`、`stm32_firmware_import`、`stm32_firmware_admit` 或 `stm32_flash_imported`。**判断实际可用工具时，请在真正的 MCP 客户端调用 `stm32_doctor`，先检查 `ok`，再读取 `data.runtime.toolkitVersion` 与 `data.publicInventory`，并与客户端真实列出的工具及 input schema 对比。单独启动的启动器/CLI `doctor --json` 只是旁证，不能证明当前 MCP 进程的绑定；不要依据本页或源码清单推断。**

以下命令中的路径均为示例，须替换为本机真实绝对路径。**已发布 v1.2.0 runtime（48 个工具）不含 `keil preflight`/`stm32_keil_preflight`**；第一组只列该发行包已有的入口，必须在 `Check` 返回 healthy 后使用。第二组属于 v1.3.0 源码候选，只有实际运行该源码或本地候选构建时才有这些入口；本文不表示它已公开发布、安装或部署。v1.3.0 已有本地官方构建产物（见[发布状态](release-status.md)），但本切片未产生 GitHub Release、公开下载、安装或完整资格结论（另有用户会话安装过更早候选，本切片不复核）。CLI 工程命令需显式 `--project-root`；`--json` 命令返回结构化 code/details，`uvprojx` 必须使用正斜杠的可移植相对路径。`--dry-run` 只产生计划，`--apply --plan-id ... --authorized` 是独立写操作，不要直接套用示例 plan ID。

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

**仅 v1.3.0 源码候选（未随 v1.2.0 发行）：** 已发布 v1.2.0 安装包（48 个工具）没有 `keil preflight`/`stm32_keil_preflight`，也不接受 `--startup-strategy`/`--startup-source`/`--memory-layout`/`--extra-regions`（MCP `startupStrategy`/`startupSource`/`memoryLayout`/`extraRegions`）。下列入口、startup 与显式内存布局选项属于 v1.3.0 候选的未发布行为，不要对已安装的 v1.2.0 runtime 使用或宣称支持；候选自身的本地 runtime 为 `runtime/1.3.0`。

```powershell
$CandidateCli = Join-Path $DataRoot 'runtime\1.3.0\Scripts\stm32-toolkit.exe'
# Requires a healthy Check for runtime/1.3.0 and a matching reported version.
& $CandidateCli version
& $CandidateCli --project-root $ProjectRoot keil preflight --uvprojx Project/blinky.uvprojx --target-name Debug --json
& $CandidateCli --project-root $ProjectRoot keil convert --uvprojx Project/blinky.uvprojx --target-name Debug --startup-strategy generate-cmsis-gcc --startup-source Startup/startup_stm32f429_439xx.s --dry-run --json
```

Keil `inspect`、`preflight` 和 `convert` 必须指向同一 `uvprojx` 和 `target-name`。`preflight` 只做技术分析：不要求 Git，可在存在 blocker 时仍成功返回 `analysis.complete=true`，并把 `analysis.blockers`、`planReadiness`（取得**可应用**计划并进入 APPLY 所需的技术/Git 前置；Git/root 前置不满足时仍可能无法取得任何 PLAN）与 `applyReadiness`（在有 reviewed/authorized plan 前恒为 `requires-reviewed-plan` 且 `ready=false`）分开；它不产生可用 plan ID、不写文件、不会自动 `git init`、转码或替换 ARMCC startup。缺少 Git、unborn HEAD、非 Git toplevel 或 dirty/untracked 工作区会作为计划前置失败列出，由工程负责人决定是否建立干净基线。确认 plan 无 blocker、diff/路径均符合预期后，以 PLAN 响应的 `data.plan_id` 调用同一参数链的 `convert --apply --plan-id <data.plan_id> --authorized --json`。PLAN 响应字段是 `data.plan_id`，APPLY 请求参数是 `planId`/`--plan-id`，不要混用带命令前缀的展示文本。`configure` 同样先 `--dry-run` 再用该次 `data.plan_id` `--apply --plan-id <data.plan_id> --authorized --json`；应用前会重新检查输入与改动。

### `doctor` 环境就绪证据（当前源码切片）

`doctor` 仍是只读诊断；`ok=true` 只表示**报告已收集**，不表示所有工具或扩展都已就绪。它与其它 MCP 工具一样绑定同一工程/根：`stm32_doctor` 使用绑定 runtime，CLI 必须显式给出已核实的绝对 `--project-root`；不要用另一个目录或另一台机器上的结果替代当前绑定证据。默认会观察本机 VS Code 的推荐扩展；不需要该观察时用 CLI `--skip-vscode-extensions` 或 MCP `probeVscodeExtensions=false`。这些观察选项与字段属于**当前源码切片**；frozen/installed 1.3.0 不包含 `--skip-vscode-extensions`/`--vscode-path`/`--uv4-path`/`--armcc-path`、`vscodeExtensionObservation`、`keilTools`、`readiness`、`diagnostics` 或 `creationSupport.vsCodeExtensionsSource`，在该包中缺失不证明 MCP 过期，需等匹配构建安装后再检查。

```powershell
& $CandidateCli --project-root $ProjectRoot doctor --json
& $CandidateCli --project-root $ProjectRoot doctor --skip-vscode-extensions --json
& $CandidateCli --project-root $ProjectRoot doctor --vscode-path 'C:\Users\<user>\AppData\Local\Programs\Microsoft VS Code\Code.exe' --json
```

- **扩展观察范围。** 选中本机 VS Code CLI 后只执行固定参数 `--list-extensions --show-versions`，不传 `--profile`（可能创建缺失的 profile），不安装/更新扩展、不打开编辑器窗口。`data.vscodeExtensionObservation.scope` 固定为 `local-default-profile`：这是所选安装的**本地默认 profile** 列表，不是当前窗口/远程主机/工作区、不是扩展启用状态或激活证据，也不是成功调试证据。`data.vscodeExtensions` 只含**实时观察值**；`data.creationSupport.vsCodeExtensions` 仍是 support-profile 中声明的值，`data.creationSupport.vsCodeExtensionsSource` 固定为 `support-profile-declared` 以标明该声明来源，两者必须分开阅读，绝不能用声明值伪造实时结果。cortex-debug 仅把观察版本与 handoff 声明的 `1.12.1` 比较为 `profileMatch`（`match`/`mismatch`/`unverified`），不是物理调试验证；cpptools/cmake-tools 只报告观察版本，不推断受支持版本矩阵。
- **完整输出才产生事实。** 只有完整、可解析的列表才给出 `installed=true/false`；空列表是合法的“全部未安装”。超时（10 秒）、非零退出、启动失败、截断（64 KiB）、读取不完整、非法字节、未知/畸形行或推荐扩展的冲突版本一律为 `installed=null`、`version=null`，并在该条目和 `data.diagnostics` 中给出固定 `status`/`code`/`remediation`。不完整输出不会被当作“未安装”，也不会回显原始 stdout/stderr 或无关扩展清单。
- **路径选择。** `--vscode-path`（MCP `vscodePath`）必须是绝对、存在、无重定向的 `Code.exe` 或已安装的 `bin/code.cmd`。VS Code 的 `bin/code.cmd` **只被有界解析**，用于定位同一安装中的 `Code.exe` 与 `resources/app/out/cli.js`（含哈希版本布局），**绝不执行批处理内容**；不支持或歧义的布局直接报告，不搜索任意目录、不挑选过期哈希目录。无效显式值会给出有界诊断，不会静默回退到 PATH/标准目录。未显式给出时，按 trusted support-profile、PATH、受限标准布局顺序选择，并要求可执行文件与 CLI 脚本来自同一安装。
- **UV4/ARMCC。** `data.keilTools.uv4`/`armcc` 报告 `available`/`path`/`source`/`status`/`version`/`returnCode` 及诊断。发现顺序为显式路径（`--uv4-path`/`--armcc-path`，MCP `uv4Path`/`armccPath`）、PATH、受限 `C:/Keil_v5`/`C:/Keil` 布局；ARMCC 还可来自所选 UV4 安装的 `ARM/ARMCC/bin`。UV4 从不执行，只用静态 Windows 文件版本；ARMCC 只执行固定 `--vsn`，从不执行 `--version`、构建或许可证激活。存在/版本不是许可证、工程所选编译器、pack 兼容或成功构建证据；未知安装应由用户显式选择路径修复，`doctor` 不安装软件、不改 PATH。
- **原生 Keil 后端未实现。** `data.keilTools.toolkitNativeBuildSupported` 恒为 `false`，与是否检测到 UV4/ARMCC 无关；检测不会解锁原生构建。可行路线是 `keil-migration`（审查 PLAN 后转换）或 `external-firmware`（导入/准入外部固件），两者仍分别遵守 managed/imported 路线的授权与身份限制，不因 `doctor` 而改变创建/构建准入或自动执行任何操作。

### 构建输出陈旧（`BUILD_OUTPUT_STALE`）诊断

构建返回 `BUILD_OUTPUT_STALE` 时，先完整保存该 `OperationResult`，因为下一次构建会覆盖当前 log/result；再读 `details.reason`：`output-unavailable`（ELF/MAP 不可用）、`prior-evidence-unavailable`（旧 receipt/identity 缺失、不可读或无法解析；既有有界读取器有意合并这些情况）、`prior-build-not-successful`、`input-snapshot-mismatch` 或 `prior-evidence-mismatch`。最后一种用固定 `evidenceField`/`evidenceSource`（`record`/`identity`/`output`）指出首个失败字段；它不回显旧记录值，摘要层面的 digest 差异也不证明某个源码被改动或被恶意篡改。`details` 另含本次实际 `preset`、`cleanRequested` 和可移植 `logPath`/`resultPath`/`identityPath`。

仅当 `remediation.action=clean-rebuild`（输出未变且本次 `clean=false`）时，才把 `remediation.cli.arguments` 或 `remediation.mcp.tool`/`arguments` 当作**建议**：它们保留 preset 与 timeout，MCP 参数不含 `authorized`，建议本身不是授权；其中 CLI 的 `arguments` 只是**命令尾部**，不是可独立执行的调用：必须在同一绑定工程根（`remediation.cli.workingDirectory=project-root`）中，先给出调用方核实的 Toolkit 可执行文件，再给出 `remediation.cli.projectRoot` 声明的 `--project-root` 选项和同一绑定的已核实**绝对**工程根；即使当前目录就是工程根，显式绝对 `--project-root` 也是必需的，仅传命令尾部会被 CLI 拒绝。`remediation.cli.executable` 的取值是符号标签，不是真实可执行文件路径；建议中不含绝对根或 shell 字符串，MCP 调用也必须发往同一绑定服务器/工程；只有在用户已授权该次 clean 构建时，才以同一工程根、预设和超时执行，且 `--clean` 只是 CMake `--clean-first`：CMake 会先调用 `clean` 目标再重新构建，因此可能删除生成的构建产物；它不是对整个构建目录、缓存、receipt 或 identity 的递归删除，也不保证修复。

`remediation.action=inspect-build-log`（输出不可用或本次已 `clean=true`）时先检查构建日志与配置，不要重复 clean 循环。`BUILD_PROJECT_INVALID`（含受管文件漂移或片段 provenance）不是 stale：应按受支持的 configure/fragment 修复路径处理，不能靠 clean 或改 hash 绕过。不得通过修改旧 receipt、identity 或 managed hash 让产物看似有效。这些 `reason`/`evidenceField`/`remediation` 字段属于当前源码切片；frozen/installed 1.3.0 不包含，重启 VS Code 也不会安装，需等后续获授权安装。

### ARMCC 浮点 ABI 证据（当前源码/候选切片）

Arm 的 Compiler 5 文档区分硬件浮点**计算**与参数传递 **ABI**；官方迁移表把 `--cpu=Cortex-M4.fp` 映射到 hard linkage，但这说明的是编译器规则，不是本项目原始二进制实际使用的 ABI（参见 [Arm Compiler 5 文档](https://documentation-service.arm.com/static/5f721c6c1b758617cd950f6f)、[ARMCC→ARMCLANG 架构/处理器名迁移](https://support.arm.com/documentation/100068/0609/migrating-from-armcc-to-armclang/migrating-architecture-and-processor-names-for-command-line-options)、[Keil FPU 硬件选择](https://www.keil.com/support/man/docs/uv4/uv4_dg_adstarg.asp) 与 [GCC ARM 选项](https://gcc.gnu.org/onlinedocs/gcc/ARM-Options.html)）。本切片不解析 AXF/对象/库或真实编译命令行，因此 `baselineVerified` 恒为 false。

`stm32_keil_inspect` 额外记录选中 target 的原始 `ArmAdsMisc/RvdsVP`（inspection 字段 `rvds_vp`）。`stm32_keil_preflight` 的 `data.analysis.floatAbi`、PLAN 的 `data.floatAbi` 与成功 apply 的 `conversion-report.json` 中 `floatAbi` 是同一份确定性证据，字段为 `compiler`/`compilerVersion`/`cpu`/`rawFpu`/`rawFloatAbi`/`rawRvdsVp`、`fpu`（GCC 拼写或 null）、`selectedAbi`、`origin`（`inferred`/`declared`/`blocked`/`not-applicable`）、`ruleId`、`reason`、`baselineVerified`、`warning`、`nextStep`。

- Keil 的数值 `uFloatingPoint`（0/1/2 等）不是已证明的 ABI 声明，不再自动映射为 soft/softfp；它们与未知值一样产生稳定 blocker，不伪造替换字段。
- 只有字面量 `soft`/`softfp`/`hard` 作为**工程声明**保留，`origin=declared`；声明只表示工程意图，不证明原二进制使用同一 ABI。
- 仅 `ARMCC + Cortex-M4 + FPU2` 且无显式 ABI 时保留窄推断 `origin=inferred`、`selectedAbi=hard`；这是未验证的兼容候选，不是 blanket 规则或 Linux 默认。
- 选中 target 的 `RvdsVP` 缺失/为空或为 `2` 时允许上述历史候选；其它非空值（即使同时存在字面量 ABI）以 `MIGRATION_FPU_SELECTION_UNSUPPORTED` 阻断 FPU/ABI 推断。数值 `2` 只是本兼容规则允许的历史选择器，不证明二进制等价。
- 其它 compiler/CPU/FPU 组合仍 fail closed；`--apcs`、`--fpu` 与 response-file 等 target/group/file misc controls 的既有 blocker 保持不变，不得为清除 blocker 改写证据或删除控件。
- 被阻断的 ABI/硬件选择证据停止的是向 APPLY 的推进，而不是诊断性只读 PLAN：当 Git/root 前置满足时，PLAN 仍可能成功返回并携带 blocker，该 `plan_id` 不可应用；不要断言被阻断工程无法生成任何 PLAN（Git/root/选择前置不满足时仍会阻止 PLAN）。
- 请检查实际编译器命令行、对象与库的调用约定。没有新增 ABI override 参数或 CLI/MCP 标志，也不得手工编辑 `plan_id`、digest 或工程证据。本补丁仍在 1.3.0 源码候选；待其余改进一并集成为 1.3.1，frozen/installed 1.3.0 不包含此源码行为。

### 受支持的 CMSIS startup 生成（显式 opt-in）

仅有常规 ST/CMSIS Cortex-M3/M4/M7 ARMCC5 startup 可走此路线；其它 ARMCC 汇编仍然阻断。本节参数属于 **v1.3.0 候选的未发布行为**：已发布 v1.2.0 安装包（48 个工具）不含 `stm32_keil_preflight` 及这两个选项，须以宿主实际安装版本为准。公开参数名固定为：

| 操作 | MCP 参数 | CLI 参数 | 值 |
| --- | --- | --- | --- |
| 预检/计划/应用 | `startupStrategy` | `--startup-strategy` | 唯一支持值 `generate-cmsis-gcc`；省略表示保留现有 dispatch |
| 预检/计划/应用 | `startupSource` | `--startup-source` | 精确的工程相对、已包含、非空 `.s` 路径，使用 `/`；仅当只有一个非空候选时可省略 |

同一组 `startupStrategy`/`startupSource` 必须用于 `stm32_keil_preflight`、`stm32_keil_convert`（PLAN）和最终 `stm32_keil_convert`（`planId` + `authorized=true`）；省略或改动不会被 apply 接受：合法但不同的值会使新计划摘要不同并返回 `PLAN_CHANGED`，而格式或策略本身非法时返回结构化校验错误（如 `MIGRATION_STARTUP_OPTIONS_INVALID`、`MIGRATION_STARTUP_STRATEGY_UNSUPPORTED`）。preflight 的 `planReadiness.nextSteps` 会重复需要保留的精确 startup 选项。若省略 `startupSource` 且存在多个候选，会返回 `MIGRATION_STARTUP_SELECTION_REQUIRED`，从 `details.candidates` 让用户选择。托管生成目标固定为 `Startup/stm32tk_startup_gcc.S`；原 ARMCC 文件不改不删；目标已存在且字节不同则返回 `MIGRATION_STARTUP_TARGET_COLLISION`，不覆盖用户文件。

VS Code / MCP 客户端的审查路径：

1. `stm32_keil_preflight(uvprojx, targetName, startupStrategy="generate-cmsis-gcc", startupSource="<path-or-omitted>")`，读取 `data.analysis.startup`：`source_path`/`source_sha256`、`vectors`（含 `reserved` 索引）、`stack_size`/`heap_size`、`reset_pattern`、`generated_path`/`generated_sha256`、`warnings`、`diagnostics`。任何诊断都应先处理，不能靠改写规则通过。
2. 用完全相同的两个参数调用 `stm32_keil_convert(..., startupStrategy=..., startupSource=...)` 取得 PLAN 响应；核对 `data.plan_id`、`data.startup`、`data.patches[].unified_diff`，特别是向量顺序/保留零槽、weak handler/alias、`SystemInit` → `.data/.bss` → `__libc_init_array` → `main` 的 reset 路径，以及 manifest 中 `memory.stackSize`、`memory.heapSize`、`generation.runtimeInitialization="cmsis-gcc-v1"` 和 `build.assemblySources` 只替换选中项。
3. 用户显式授权该精确 `data.plan_id` 后，以同一组参数传 `planId` 和 `authorized=true`。apply 会用同一选项重规划并核对 Git/digest/输入漂移，失败不写文件。
4. apply 后按常规 `stm32_project_configure`（先 PLAN 再授权 apply）与 `stm32_build` 流程构建；托管 linker 会使用记录的精确 stack/heap 字节并保留构造数组。GCC/newlib 运行时替换不是 ARMCC、ABI 或 Microlib 等价，仍须自行审查向量表、RAM 假设和实际运行行为。显式多 RAM 分区见下一节；任意额外初始化/清零节仍需独立 startup 表契约，不在本切片范围。

### ARMCC 常用语法迁移（当前源码/候选切片）

本节规则属于当前源码/候选行为，不是通用 ARMCC 转译器，也不证明固件行为等价。新增的函数/声明变换只作用于已包含的 C 源文件（C++ 保留旧有的纯数字绝对地址形式，不新增函数/对齐规则）；精确 `#pragma import(__use_no_semihosting)` 的删除对 C 与 C++ 均生效。未被重写的文本、字符串、字符字面量、BOM 与 CRLF/LF 约定保持原样，但被替换范围不保证逐字节不变：重写后的 asm 函数体内注释可能被重排或重新缩进，原型内注释一律 blocker；受支持的 pragma 删除本身即是有意改写。未知或不确定形式一律保留 blocker。

| 规则 ID | 触发（只接受精确形式） | 结果与限制 |
| --- | --- | --- |
| `ARMCC_NAKED_ASM_FUNCTION` | `__asm void name(void)` 或 `()`，函数体恰为 `WFI`/`CPSID I`/`CPSIE I` 加显式 `BX LR`/`BX R14`；或 `__asm void name(<32 位标量>)`，函数体恰为 `MSR MSP, R0` 加显式 `BX LR`/`BX R14` | 改写为 `__attribute__((naked))` + 单条 GNU basic asm 指令串，不生成普通 C `__set_MSP` 包装，不加栈操作；32 位标量仅接受 `uint32_t`、`u32`、`unsigned int`、`unsigned long`。缺少 `BX`、额外指令、未知/多参数/指针原型、原型内注释一律 blocker。 |
| `ARMCC_ALIGN_ATTRIBUTE` | 单个未初始化普通对象声明上的 `__align(n)`（前缀或后缀），`n` 为正 2 的幂且不超过 4096，可来自目标 define 或受支持的宏 | 改为 `__attribute__((aligned(n)))`；非法/未解析边界、`extern`/`typedef`、多声明符、零长数组、与未知属性组合一律 blocker（符号边界求值失败时消息附带稳定有界原因），绝不把未识别 `__align` 带入 GNU 源。 |
| `ARMCC_ABSOLUTE_PLACEMENT` | 单个未初始化标量或固定大小数组、前缀或后缀 `__at(EXPR)`/`__attribute__((at(EXPR)))`，并可与受支持的 `__align` 组合 | `EXPR` 由禁用 `eval` 的有界求值器解析：十进制/十六进制整数与标准后缀、括号、标识符和受限运算符；结果必须为非负 uint32。浮点、八进制样式、`sizeof`、强转、函数宏、未定义/条件/冲突/`#undef` 宏、除零、移位越界、溢出、指针/初始化器/多声明符/函数/位域/混合属性均为 blocker；同一文件任一不支持放置会取消该文件全部放置改写。地址落在所有已声明内存区域之外时报告 `MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY`（`needs-user-input`），绝不臆造外部 SRAM。与受支持 `__align(n)` 组合时，解析出的固定地址必须是 `n` 的整数倍（按同一有界表达式求值，不猜测任意类型的自然对齐）；不满足时报告 `ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED`，不产生该文件任何固定节/放置改写。符号地址求值失败时 blocker 消息附带稳定有界原因（如 conditional/undefined/cycle/unavailable/limit），不含绝对路径。 |
| `ARMCC_NO_SEMIHOSTING_PRAGMA` | 精确独立 `#pragma import(__use_no_semihosting)`，可带保留的尾随注释，不允许续行或额外 token | 删除该指令本体（保留尾随注释与 CRLF/LF），并在清单提议中显式加入 `build.newlibSpecs=["nosys.specs"]`；受管 CMake 链接仅额外输出一次 `--specs=nosys.specs`，不隐式加入 `nano.specs`，原生 linker 默认不变。其它不受支持的 ARMCC `import`/pragma 仍为 blocker，通用 pragma（如 `pack`/`once`）保持原有行为；不添加 I/O stub，也不宣称运行时 I/O 等价。 |

词法边界遵循 C 翻译阶段 2：以反斜杠续行的 `//` 注释拥有其续行，续行中的伪 `#define`/`#include`/`__at`/`__asm` 不会被当作代码或宏证据；嵌套引号包含路径逐级解析，搜索基路径从工程根起的每一级父目录都会检查重解析点，任一级重定向都 fail closed。符号求值只读取显式 target define 与源文件目录/合并 include 路径内可解析的引号包含头文件（支持有界包含链、嵌套相对路径和结构完整的普通 include guard）。被使用的宏若来自条件分支、被重复定义、被 `#undef`、是函数式宏，或包含链中有缺失的引号头文件，都返回保守的不可用证据而不是猜值；未解析被当作未定义/不可用报告。所有实际使用的头文件字节（包括未列入工程的忽略头文件）会作为计划输入绑定摘要，头文件变化或新出现的遮蔽解析会使 apply 的输入复核/重规划失败。

审查路径：preflight 的 `analysis.sourceChanges` 给出每个**计划提议**（尚未写入）的 `path`、精确 `ruleIds` 与 `beforeSha256`/`afterSha256`（仅用于区分已支持变换与 blocker，不授予写权限）；PLAN 仍返回完整 `data.patches[].unified_diff`，`data.blockers` 非空时不得 apply。apply 后按常规 configure 审查：确认 `build.newlibSpecs` 与受管 `CMakeLists.txt` 的 `--specs=nosys.specs` 仅出现一次、固定地址节按审查地址进入 linker 脚本。离线 GCC/objdump/ELF 证据只说明语法与镜像层面符合切片契约，不证明与 ARMCC 构建或真实板卡行为等价。

### 显式多 RAM 内存布局（当前源码/候选切片）

托管生成的 `.data`/`.bss`/`.heap`/`.stack` 可以显式分配到不同 RAM 区域。参数属于 **v1.3.0 候选的未发布行为**：已发布 v1.2.0 runtime 不接受它们，使用前必须检查所连 MCP 服务器的真实工具与 input schema（`memoryLayout`/`--memory-layout`）。

| 操作 | MCP 参数 | CLI 参数 | 值 |
| --- | --- | --- | --- |
| 预检/计划/应用 | `memoryLayout` | `--memory-layout '<json>'` | 恰好含 `flash`、`data`、`bss`、`heap`、`stack` 五个字符串键，每个值必须是已声明区域名 |

规则：

- `flash` 区域必须可读、可执行且不可写（如 `r-x`）；`data`/`bss`/`heap`/`stack` 必须可读可写（如 `rw-`/`rwx`）。可写且可执行的 RAM 绝不会被推断为 Flash；CCM/外部 SRAM 不会被自动选用，也不推断 DMA 可达性。
- 不传 `memoryLayout` 时，仅当恰好存在一个非可写可执行 Flash 与一个可读可写 RAM 时按旧行为解析（`status=implicit`），并保持历史生成字节与 model hash。存在多个 RAM（如 IRAM1 + IRAM2/CCM）时：preflight 在 `data.analysis.memoryLayout` 返回 `status=requires-selection`、`layout=null` 和实际的 `candidates.flash`/`candidates.ram`（名称/起始/长度/属性）；PLAN 在 `data.memory_layout` 返回同样的决定证据。两者都会附带普通 `MEMORY_LAYOUT_REQUIRED` blocker 以及其它 blocker。configure 在缺少布局时失败，不会默认选择第一个 RAM。
- 显式映射必须完全相同地传给 preflight、PLAN 与 apply。省略与“显式把所有节放在主 RAM、故意不用 CCM”是两种不同的 reviewed 选择；它们产生不同 `data.plan_id`，apply 会返回 `PLAN_CHANGED`。`status=explicit` 的计划会把映射写入 `memory.layout` 并纳入计划身份。
- CLI `--memory-layout` 接收一个 JSON 对象字符串：JSON 语法错误、重复键（如两个 `flash`）以及缺失/未知角色、非字符串或空字符串值都会在 inspect/plan 之前以 `MEMORY_LAYOUT_INVALID` 的 `field`/`rule`/`remediation` 失败；重复的 `--memory-layout` 选项则属于现有 sanitized 参数解析错误，不是 `MEMORY_LAYOUT_INVALID`。MCP 的 `memoryLayout` 是对象参数（不是 JSON 字符串），注册 input schema 为 `dict[str, str]`：字符串、数组等非对象值，以及角色值不是字符串的对象，都会在 Toolkit 运行前由 MCP 框架以 `ToolError`（如 `memoryLayout.flash` 的 `string_type` 校验）拒绝，不会得到 Toolkit 的 `MEMORY_LAYOUT_INVALID`。只有 schema 已接受的对象才交给 Toolkit：未知/缺失角色、空字符串值以及逻辑上的区域/权限错误由 Toolkit 返回结构化 `MEMORY_LAYOUT_INVALID`。不要把 MCP 框架的类型错误描述成 Toolkit 的结构化结果。
- `generation.nativeLinkerScript` 存在时布局由用户原生脚本拥有：不允许同时声明显式布局（拒绝而非忽略）。固定地址节仍按原地址以 `NOLOAD` 放入所属区域或保留原有 blocker，不会被当作初始化数据复制/清零。
- 托管 linker 将 `.data` 的 VMA 放入所选 RAM、LMA 放入所选 Flash，并保持 `_sidata`/`_sdata`/`_edata`/`_sbss`/`_ebss` 与 `cmsis-gcc-v1` 断言；stack/heap 精确字节与 8 字节栈对齐保持不变。区域越界、重叠或过小由实际链接失败暴露。成功链接只是离线镜像证据，不证明 CCM/外部 SRAM 或真实板卡运行时行为。

### 显式外部 RAM 区域（当前源码/候选切片）

迁移可以显式声明 Keil/设备事实之外的**可写 RAM**（例如外部 SRAM），用于固定地址缓冲或显式内存布局。该输入属于 **v1.3.0 候选的未发布行为**：已发布 v1.2.0 runtime 不接受 `extraRegions`/`--extra-regions`；**已冻结/已安装的 1.3.0 也不包含本源码补丁**，因此两者都必须先核对实际绑定的 MCP 工具与 input schema，不能仅凭版本号宣称支持。

| 操作 | MCP 参数 | CLI 参数 | 值 |
| --- | --- | --- | --- |
| 预检/计划/应用 | `extraRegions` | `--extra-regions '<json>'` | JSON 数组，最多 32 个对象；每个对象恰好含 `name`、`origin`、`length`、`attributes` |

规则（所有容量必须由工程负责人给出，Toolkit 不猜测）：

- `name` 是 1–64 字符 ASCII linker 标识符（`[A-Za-z_][A-Za-z0-9_]*`），大小写不敏感地唯一，且不得与已声明 base 区域重名。
- `origin` 必须是 JSON 整数 `0..0xffffffff`；`length` 必须是 JSON 整数 `1..0x100000000`；半开区间结束地址不得超过 `0x100000000`。布尔、字符串、浮点、零长度都不接受；显式零容量不是省略。相邻区域允许，重叠（与 base 或其它 extra）拒绝。
- `attributes` 只能是 `rw-` 或 `rwx`。该入口不能声明新的可编程 Flash，`rwx` 外部 RAM 也绝不会被当作 Flash 候选。
- 省略或空数组是同一个“无额外区域”请求，保持历史 manifest 字节、model hash、plan ID 与生成输出。非空请求写入 manifest 的 `memory.extraRegions`；`memory.regions` 保持从 Keil/模型得到的 base 列表不变，类型化 `ProjectModel.memory.regions` 只组合一次为 base+extra，供 fixedSections、linker、ELF/MAP、构建身份等所有消费者共用。
- 同一精确请求必须用于 preflight、PLAN 和 APPLY。preflight 返回 `data.analysis.extraRegions`，PLAN 返回 `data.extra_regions`（并绑定进 `data.plan_id`），成功 apply 的 conversion report 记录 `extraRegions`。省略、缩短、删除或修改任一项都是不同的 reviewed 请求，apply 返回结构化校验错误或 `PLAN_CHANGED`，不会写文件；手工篡改类型化计划会在首次写入前被拒绝。`planReadiness.nextSteps` 会重复需要保留的精确请求。
- extra RAM 只增加 RAM 候选。已有多个 RAM 时仍返回 `MEMORY_LAYOUT_REQUIRED`；若唯一的可写 RAM 是外部区域，也不会被隐式选为 `.data`/`.bss`/`.heap`/`.stack`。只有显式 `memoryLayout` 可以命名合法 extra RAM，语义与 startup 不变（不会新增 copy/zero 表或初始化代码）。
- `MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY` 在缺少额外区域时保持可操作：按实际硬件提供精确 origin/字节长度，不得猜长度。固定节仍以 `NOLOAD` 放置，不承诺已初始化；owner 必须在任何访问前完成外部存储器初始化（若把 stack 放在外部 RAM，可能需要早于 `SystemInit` 的引导）。外部 SRAM 的运行时正确性不由离线链接证明。
- `generation.nativeLinkerScript` 仍由用户拥有，不会被改写，也不能同时声明托管 `memoryLayout`。该声明不授予任何硬件访问，也不添加 Flash 算法或绕过芯片 Flash 映射检查。
- CLI `--extra-regions` 接收 JSON 数组字符串：语法错误、重复对象键、深层嵌套、超大 JSON、重复选项（现有 sanitized parser 错误）以及非法字段都在 inspect/plan 之前失败；Toolkit 侧错误使用结构化 `EXTRA_REGIONS_INVALID` 的 `field`/`rule`/`remediation`。MCP 使用真实数组（注册 schema 为 `list[dict[str, Any]]`，保留原始标量类型）：非数组/非对象项由 MCP 框架先行拒绝；schema 可接受但语义非法的值（布尔 origin、越界长度、`r-x`、重叠等）返回 `EXTRA_REGIONS_INVALID`。

```powershell
$Extra = '[{"name":"EXT_SRAM","origin":1744830464,"length":65536,"attributes":"rw-"}]'
$Layout = '{"flash":"IROM1","data":"IRAM1","bss":"EXT_SRAM","heap":"EXT_SRAM","stack":"EXT_SRAM"}'
& $CandidateCli --project-root $ProjectRoot keil preflight --uvprojx Project/blinky.uvprojx --target-name Debug --extra-regions $Extra --memory-layout $Layout --json
& $CandidateCli --project-root $ProjectRoot keil convert --uvprojx Project/blinky.uvprojx --target-name Debug --extra-regions $Extra --memory-layout $Layout --dry-run --json
```

（示例中的区域名、数值与容量都只是**审阅示例，非板级事实**，也不表示外部存储器已初始化；必须按实际器件和 owner 提供的精确 origin/字节长度给出。）

### 用户自有 NOLOAD 链接片段（当前源码/候选切片）

工程负责人可以用 `generation.linkerFragment` 指定一个**自己拥有的**、工程相对的 UTF-8 GNU ld 片段，由 configure 校验后渲染进托管 `linker/stm32tk.ld`。这是**当前源码/候选的未发布行为**：已发布 v1.2.0 runtime 与已冻结/已安装的 1.3.0 都不包含本补丁；**没有新增 MCP 工具或参数**，仍使用既有的 `stm32_project_configure` / CLI `project configure`。工具清单与 input schema 本切片没有变化，因此它们**无法**区分未打补丁的旧 1.3.0 与本补丁运行时；不能仅凭工具数量、版本号或 schema 宣称支持。必须使用**确认由本补丁源码构建并部署**的 runtime（安装/升级须另行授权），再用一个已审阅的 manifest 执行**只读 configure PLAN**，确认 `data.inputs[]` 出现片段 `path`/`sha256`、`linker/stm32tk.ld` 的 `unified_diff` 含片段内容且 `data.blockers` 符合预期；PLAN 失败或没有这些证据就停止，不要继续 APPLY。

**所有权与位置。** 片段是用户拥有的普通文件，Toolkit 只读取、从不改写或纳入 managed records。路径必须是非空、可移植的工程相对路径（`/`，不得含反斜杠、盘符、UNC、`.`/`..` 分量）；任一路径分量是符号链接/重解析点、文件缺失/是目录/超过 64 KiB/非 UTF-8 都 fail closed。片段不得与 `build.sources`/`assemblySources`/`includePaths`、SVD、CubeMX IOC、`generation.managedManifest`、原生 linker 脚本、九个托管生成目标（如 `CMakeLists.txt`、`linker/stm32tk.ld`、`.vscode/settings.json`）、`build/`、`artifacts/migration/` 或 `.stm32-toolkit/generated-files.json` 冲突（大小写不敏感），也不能与 `generation.nativeLinkerScript` 同时声明。原生脚本路线保持原有的独立所有权，片段不会接管它。

错误代码不承诺单一优先级：`generation.linkerFragment` 为 `null`、空串或非字符串时由 packaged schema 以 `PROJECT_SCHEMA_INVALID` 拒绝；绝对路径、盘符、UNC 或 `..` 遍历等 manifest 路径 containment 也在片段语义之前按既有合同返回 `PROJECT_SCHEMA_INVALID`（`field=generation.linkerFragment`，`rule=pathWithinProjectRoot`）。只有通过这些检查后，原生脚本/声明输入/生成输出冲突、重定向、缺失/目录/超限/非 UTF-8、语法与区域错误才返回 `LINKER_FRAGMENT_INVALID`。失败细节包含 `path`、`field`、`rule`、`remediation`；部分语法/数值错误另带 `line`/`column`。先按返回的 `code`/`details` 处理，不要假定每种错误都得到同一个代码。修复方式是改片段位置或内容，不是修改 managed 文件或 digest。

只添加 `generation.linkerFragment` 一个键，保留 manifest 中既有的其它 `generation` 字段（示例仅为形状，不表示这些值必须如此）：

```json
"generation": {
  "cubeMxIoc": null,
  "nativeLinkerScript": null,
  "managedManifest": ".stm32-toolkit/generated-files.json",
  "generatedDirectories": [],
  "userDirectories": [],
  "runtimeInitialization": "cmsis-gcc-v1",
  "linkerFragment": "linker/user.ld"
}
```

**受支持的语法子集（不是通用 GNU linker-script 解释器）。** 每个输出节必须是：

```ld
.sram2 0x20000000 (NOLOAD) :
{
  . = ALIGN(8);
  *(.sram2 .sram2.*)
} > RAM
```

- 只接受自定义可写 RAM `NOLOAD` 输出节，最多 32 节、原文最多 64 KiB；地址可选，必须是精确 uint32（十进制或 `0x` 十六进制），且必须满足 `origin <= address < origin + length`（可以等于区域起点，但不能等于或超过结束地址）。未给地址时由 GNU ld 在所选区域游标处放置。
- 每节至少一个 selector；语句仅 `. = ALIGN(n);`（正 2 的幂且不超过 4096）、`*(selectors)`、`KEEP(*(selectors))`。每节最多 64 条语句、全文最多 256 条；每条语句最多 64 个 selector、全文最多 256 个。selector 只能是该输出节自己的精确名字或 `name.*`；不得跨出本输出节家族，也不得重复或重叠。
- C 块注释与空白可接受，但注释内容永远不会被当作指令；整个输入必须被消费，残留或未终止语法 fail closed；空文件/仅注释文件拒绝。
- 区域名必须精确解析到 `fixedSections`、linker、ELF/MAP 共用的同一 canonical 区域 map，且只能是可写区域；不会推断新区域、容量或 DMA 可达性。多个 RAM 需要显式 `memoryLayout`（见上一节），片段不能代替该选择。
- 拒绝托管/标准 GNU 节家族，包括向量/`text`/`rodata`/`data`/`bss`、small-data（`.sdata`/`.sbss`）、TLS（`.tdata`/`.tbss`）、动态元数据（`.dynamic`/`.dynsym`/`.dynstr`/`.hash`）、构造/析构、ARM unwind、heap/stack、`.stm32tk.abs.*` 及其它标准元数据；比较按 casefold 进行。这是为了不让片段“偷走”托管模板通配符或标准初始化数据。
- 渲染顺序固定为：既有 fixed sections → 片段 sections（按源码顺序）→ 托管 `.data`/`.bss`/`.heap`/`.stack`。`NOLOAD` 节**不会被自动复制或清零**：不要把需要初始化器的 C 对象放进这些节；外部 RAM 必须由 owner 在访问前完成初始化（若把 stack 放在外部 RAM，可能需要早于 `SystemInit` 的引导）。本切片不改 startup 表、编程资格或控制器配置。

**配置 PLAN/APPLY（既有入口，无新参数）。**

```powershell
# 必须替换为“已确认由本补丁源码构建并部署”的 runtime 的完整绝对路径。
# 已知的已安装 runtime\1.3.0 不含本补丁；本文不授权或执行任何安装/升级。
$PatchedCli = '<absolute path to a runtime built from this patch>\Scripts\stm32-toolkit.exe'
# 1) 只读 PLAN：核对 data.plan_id、data.inputs、data.files、data.blockers
& $PatchedCli --project-root $ProjectRoot project configure --dry-run --json
# 2) 用户显式授权该精确 data.plan_id 后 APPLY（写操作）
& $PatchedCli --project-root $ProjectRoot project configure --apply --plan-id <data.plan_id> --authorized --json
```

CLI 中的 `--project-root <abs>` 是全局选项，放在 `project configure` 之前；子命令位置也接受 `--project <abs>`/`--project-root <abs>`，但 PLAN 与 APPLY 必须使用同一个工程根。

MCP 客户端用同一合同：先调用 `stm32_project_configure()`（省略 `planId`，`authorized` 为 false/省略）取得 PLAN；核对 `data.plan_id`（64 位小写十六进制）、`data.model_sha256`、`data.inputs[]`（含 `path`/`sha256`/`size`，片段摘要必须出现）、`data.files[]`（尤其 `linker/stm32tk.ld` 的 `path`/`status`/`unified_diff`）、`data.blockers[]` 与 `data.managed_manifest_path`。只有用户显式授权该精确 `data.plan_id` 后，才调用 `stm32_project_configure(planId="<data.plan_id>", authorized=true)`。APPLY 成功响应的 `data` 使用既有 camelCase 字段：`planId`、`modelSha256`、`createdPaths`、`updatedPaths`、`unchangedPaths`、`preservedPaths`、`warnings`、`managedManifestPath`、`managedManifestSha256`、`templateVersion`。不要手工修改 `linker/stm32tk.ld`、`.stm32-toolkit/generated-files.json` 或任何 digest 来“修复”配置；apply 会以同一字节重新校验并拒绝计划后的片段编辑、路径变化或删除，且不写文件。

**失败与构建新鲜度。** 进入片段层后的语法/区域/所有权失败返回 `ok=false`、`code=LINKER_FRAGMENT_INVALID`，`details` 含 `path`、`field`（如 `sections[0].region`）、`rule`、`remediation`，适用时含 `line`/`column`；较早的 schema/路径问题则按上文返回 `PROJECT_SCHEMA_INVALID`。无论哪种，都按实际 `code`/`details` 修复后重新走 PLAN/APPLY，不要假定单一代码或单一检查顺序。片段路径和**精确原始字节**参与 model hash、managed manifest 的 `linkerFragment = {path, sha256}` provenance 和 build input snapshot。片段被编辑（即使是注释）、删除、路径改变，或整个选项被移除，都会使旧配置/构建证据失效；build 在 spawn 编译器之前拒绝，但具体表现并不唯一：

- 片段文件被删除/变得不可读时，模型加载先失败，build 返回 `BUILD_PROJECT_INVALID`，`details.rule` 为 `missing`（或该层实际返回的规则），并带片段 `remediation`；configure 同样失败且不写文件。
- 选项被移除、managed manifest 缺少 provenance、片段路径/摘要改变或 model hash 改变时，build 返回 `BUILD_PROJECT_INVALID`，`details.rule` 分别为 `linkerFragmentRemoved`、`linkerFragmentMissing`、`linkerFragmentChanged`、`modelChanged`。
- 计划之后输入发生变化时，APPLY 返回既有 `GENERATION_INPUT_CHANGED`/`GENERATION_PLAN_INVALID` 合同。

修复后重跑 configure PLAN/APPLY，再按需 `build --preset arm-debug --clean`。不要编辑旧 receipt 或 managed hash 来绕过。生成 `CMakeLists.txt` 仅在片段路线下加入 `LINK_DEPENDS` 指向合并后的 `linker/stm32tk.ld`；直接使用 CMake/Ninja 不会重新解析片段，必须先通过 Toolkit 重新 configure。省略片段时历史 model hash、manifest 字节与生成字节保持不变。

**与其它入口的区别。** `fixedSections` 是迁移证据决定的固定绝对地址 `NOLOAD` 节；`memory.layout` 是托管 `.data`/`.bss`/`.heap`/`.stack` 的区域选择；`extraRegions` 只声明可写 RAM 区域；`nativeLinkerScript` 是用户完全自有的原生脚本。`generation.linkerFragment` 只贡献上述受限的自定义 `NOLOAD` 输出节，不改变其它任何语义，也不是任意 GNU ld 脚本、初始化数据或硬件可达性的证明。

### 迁移后的显式 PyOCD 调试配置（PLAN/APPLY）

（`$PatchedCli`、`$ProjectRoot` 语义同上节：必须替换为实际工程根与本补丁构建的 runtime；frozen/installed 1.3.0 不支持。）

普通迁移只写出 `"debug": {}`，仍是合法的 build-only 工程。无 Git 的 preflight 会额外返回 `data.debugConfiguration`（`phase=post-migration`、`blocking=false`、`status=needs-user-input`、`missingFields=["debug.backend","debug.target"]`、`diagnostics[]`、`targetSupport="not-checked"`、`hardwareVerified=false`、`nextSteps`）：该诊断不新增 technical blocker，不进入 `planReadiness`/`applyReadiness`，不创建 `planId`，也不引入 Git 依赖。普通转换的 PLAN/APPLY 仍保留既有的 Git 基线、`planId` 与显式授权要求；不要把该诊断当作迁移失败、就绪结论或授权依据。需要在迁移后显式记录调试 backend/target 时，使用**既有** `project configure`（MCP 仍是 `stm32_project_configure`，无新工具、无迁移参数）：

```powershell
# 1) 只读 PLAN：项目与参数对子必须与 APPLY 完全一致
& $PatchedCli --project-root $ProjectRoot project configure --dry-run --json `
  --debug-backend pyocd --debug-target <pyocd-target>
# 2) 用户显式授权该精确 data.plan_id 后 APPLY（写操作）
& $PatchedCli --project-root $ProjectRoot project configure --apply --json `
  --debug-backend pyocd --debug-target <pyocd-target> `
  --plan-id <data.plan_id> --authorized
```

MCP 使用同一对参数：`stm32_project_configure(debugBackend="pyocd", debugTarget="<pyocd-target>")` 取得 PLAN，再以 `stm32_project_configure(debugBackend="pyocd", debugTarget="<pyocd-target>", planId="<data.plan_id>", authorized=true)` APPLY。两个参数必须**同时给出**；省略两者保留旧 configure 行为。只给一个、非字符串、空/仅空白值或 backend 不是精确的 `pyocd` 都会在写入前返回 `DEBUG_CONFIGURATION_INVALID`，`details` 含首个 `field`/`rule`、完整 `diagnostics[]`（`code`/`field`/`rule`/`message`/`remediation`，remediation 指向真实 CLI/MCP 入口与成对参数）和 `missingFields[]`。值不做 trim、大小写折叠或类型转换；target 只做语法检查，不代表已安装、受支持或与板上器件一致。

PLAN 只读，除既有 `data.files[]` 外还返回 `data.debug_configuration`（`backend`/`target`）与 `data.manifest_edit`：`path`、`status`（`update` 或 `unchanged`）、`before_sha256`/`after_sha256`、`before_size`/`after_size` 和完整 `unified_diff`；原始字节不进入协议。核对 diff 只改 `debug.backend`/`debug.target`，并保留 `svd`、`svdDevice`、`readableRegions`、`memory`、`generation`（含 `linkerFragment`）等其它字段。若 pair 已等于当前值，`status=unchanged` 且 manifest 精确字节不变，不重排格式。APPLY 必须带同一项目、同一参数对、精确 `data.plan_id` 和真实布尔 `authorized=true`；省略/改动参数对或计划后输入变化会在写入前返回 `PLAN_CHANGED`/结构化失败。`.stm32-project.json` 归用户所有，其它受支持字段仍可按各自合同自行维护；不要手工修补 managed hash、generated 文件或 build receipt，本切片的 debug 对子应通过上述 PLAN/APPLY 记录，以免与受管证据不一致。

该编辑会自然使旧 build/firmware 身份失效；需要时按 `build --preset arm-debug --clean` 重新构建，再走各自的授权流程。配置记录只是元数据：不会发现、安装或验证 PyOCD target，也不会创建调试会话；`.vscode/launch.json` 仍为空，真实调试交接（handoff）是独立的显式授权步骤。此能力属于当前源码补丁，frozen/installed 1.3.0 不包含它；安装/升级需另行授权。

### VS Code 任务、可执行绑定与 `ide task` 适配器（当前源码切片）

生成的 `.vscode/tasks.json` 包含五个**互相独立**的 `process` 任务：`STM32 Toolkit: Build Debug`、`Build Release`、`Flash Debug`、`Handoff Begin Debug`、`Handoff End Debug`。每个任务都用 argv（绝不拼接 shell 字符串）、显式 `--project-root ${workspaceFolder}` 和 `options.cwd=${workspaceFolder}`；没有 `dependsOn`、自动构建/烧录/调试序列、`group`、auto-run、恢复、reset 或重试。Build 任务沿用既有 build CLI 契约（CLI 调用本身就是该次构建的显式动作）。`.vscode/launch.json` 仍为空：只有成功 handoff 才提供活的 Cortex-Debug 配置。生成的硬件任务用 `${input:...}` 提示 data root、session、**精确 probe**、handoff ticket 和确认值；不预填 probe、不持久化 ticket、不自动枚举探针。三个确认提示的默认值都是 `deny`；硬件任务设置 `runOptions.reevaluateOnRerun=true`，重跑会重新询问，而不是复用上次输入。已经存在的用户自有 `.vscode/*` 文件仍按既有 `preserved-unowned` 合同保留：不读取、不改写、不合并、不收编；IDE 设置需用户自行对齐。

**先绑定用户级可执行路径。** 默认渲染使用用户设置的变量（不是宿主机发现结果）：任务 command 为 `${config:stm32-toolkit.executablePath}`，`c_cpp_properties.json` 的 `compilerPath` 为 `${config:stm32-toolkit.compilerPath}`。请只在 **User Settings**（用户设置）里写成已核对的**绝对原生可执行文件**路径，例如（以下为占位示例，必须替换成本机实际路径）：

```json
{
  "stm32-toolkit.executablePath": "C:/tools/stm32-toolkit-1.3.0-bundle/stm32-toolkit-1.3.0/bin/stm32-toolkit.exe",
  "stm32-toolkit.compilerPath": "C:/ST/STM32CubeCLT/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe"
}
```

生成器不会写入空的 workspace 覆盖，也不会回退到裸 PATH 名称；未绑定这两项时生成结果**不可直接运行**（${config:...} 无法解析），这既不是安装证据也不是运行证据。`compilerPath` 只配置 IntelliSense，**不会**静默选择 CMake 构建工具链；构建工具链仍由 `cmake/arm-none-eabi-gcc.cmake` 与 preset 决定，并应与 `stm32_doctor` 的工具证据一致。VS Code 变量本身不证明当前 runtime/MCP 身份：用 `stm32_doctor` 及真实客户端列出的工具/input schema 核对。候选可执行文件是否就是本源码切片，先检查 `version`，再检查 `ide task --help`（帮助里必须出现 `flash`、`handoff-begin`、`handoff-end`）：只有 `version` 输出无法区分 frozen/installed 1.3.0 与当前源码，不能单独当作能力证明。

也可以选择**成对**传入绝对原生路径（二者必须同时给出）。下面的 PLAN 与 APPLY 必须使用**同一对选项**和 PLAN 返回的精确 `data.plan_id`：

```powershell
$ToolkitExe = 'C:\tools\stm32-toolkit\bin\stm32-toolkit.exe'   # 示例，替换为已核实的本机绝对路径
$GccExe     = 'C:\ST\STM32CubeCLT\GNU-tools-for-STM32\bin\arm-none-eabi-gcc.exe'

# 1) 只读 PLAN：检查 data.plan_id、data.files 中 tasks.json/c_cpp_properties.json 的 diff
& $CandidateCli --project-root $ProjectRoot project configure --dry-run --json `
  --vscode-toolkit-path $ToolkitExe --vscode-gcc-path $GccExe

# 2) 用户显式授权该 PLAN 后 APPLY：同一对选项 + 同一 plan_id
& $CandidateCli --project-root $ProjectRoot project configure --apply --json `
  --plan-id '<PLAN 返回的 data.plan_id>' --authorized `
  --vscode-toolkit-path $ToolkitExe --vscode-gcc-path $GccExe
```

MCP 对应参数为 `stm32_project_configure(..., vscodeToolkitPath="...", vscodeGccPath="...")`；不新增工具，清单仍是 52。校验是静态的：值必须是绝对路径、存在的普通原生文件；Windows 上必须是 `.exe`（拒绝 `.cmd`/`.bat` 脚本），不得含 `${...}`/`$(...)`/`%VAR%` 变量，不得是目录、链接或重解析点；**路径上的每一级父目录也必须是真实目录，不能经过链接/重解析父级**；允许空格和 Unicode。它**不是**二进制信任或版本证明。失败返回 `VSCODE_CONFIGURATION_INVALID`，`details` 含首个 `field`/`rule`、完整 `diagnostics[]`（`code`/`field`/`rule`/`message`/`remediation`）与 `missingFields[]`，且在任何写入前拒绝。这对路径进入不可变计划：参与 `plan_id`、序列化和重放校验；APPLY 必须带**同一对**选项，省略或改动即 `PLAN_CHANGED`，不会写入；路径不会写进工程模型。可执行文件被移动、删除或父级变为重定向后，原计划重放也会在写入前失败，应重新 PLAN。不要手工改 `plan_id`、managed digest 或已生成文件。

`ide task` 是给生成任务用的窄 CLI 适配器，**不是** MCP 替代。以下是**不可执行的文本语法**（尖括号、方括号与 `|` 只是占位说明，不是 shell 语法）：

```text
stm32-toolkit --project-root <absolute-project-root> ide task <flash|handoff-begin|handoff-end> \
  --data-root <absolute-data-root-outside-project> --session-id <session> \
  --probe <exact-probe-id> [--ticket <original-ticket>] \
  --confirmation deny|authorize --json
```

下面是一个**可复制的拒绝示例**：`$ToolkitExe`、`$ProjectRoot`、`$DataRoot` 使用前文已核实的值，`$SessionId`/`$ProbeId` 使用本会话已核实的值。它设置 `--confirmation deny`，不会接触硬件，只会返回 `AUTHORIZATION_REQUIRED`（本页不执行它）：

```powershell
& $ToolkitExe --project-root $ProjectRoot ide task flash `
  --data-root $DataRoot --session-id $SessionId --probe $ProbeId `
  --confirmation deny --json
```

`--confirmation` 默认 `deny`；只有精确的 `authorize` 才执行**这一次**调用，没有可继承的授权。CLI 的 `--confirmation authorize`/MCP `authorized=true` 只覆盖该次调用，本身**不会**给 AI 授权，也不会把权限自动带到下一次；应复用用户已经给出的、适用于这些具体步骤的明确指令，不要重复索取同一授权。flash/handoff-begin 在确认与上下文校验之后、调用任何硬件工作流之前，使用既有只读 fresh-firmware 准入取得当前完整的 arm-debug 证据（buildId 与 ELF SHA-256），并保留其原始错误码/`details`（包括 snapshot provenance 拒绝与 build/input/artifact 失败）；随后把精确 pin 与绑定转交既有 flash/handoff 工作流，后者保留自身检查。没有 release 回退、自动构建、导入或直接后端调用。

handoff-end **不额外增加**适配器侧准入，并原样转发原始 ticket；但既有 end 工作流本身仍会在重新接管前后重新校验当前 firmware/flash 证据。因此源码、ELF 或构建证据陈旧时，end 仍可能拒绝，并返回其精确错误码/`details`。ticket 本身不证明 reclaim 成功；失败时按返回值报告实际所有权状态并停止，不做自动重建、烧录、重试或清理承诺。所有动作结果、错误和 handoff 配置/ticket 原样返回；失败仍是带非零退出码的有界结构化 JSON。UI 里的确认提示不会给 AI 授权，也不能替 AI 制造授权；AI 调用方必须已经被用户显式授权该精确操作，且不得把一次 `authorize` 复用于下一次。

**托管 flash → handoff-begin → handoff-end 的连续性。** 三个调用必须保持同一 `--project-root`、`--data-root`、`--session-id` 和同一精确 `probe`。`handoff-begin` 成功结果里的 `data.ticket` 必须原样保留给之后的 `handoff-end`；不要改写、猜测或复用别的会话/探针的 ticket，也不要把它持久化到任务文件。`handoff-begin` 返回的 `data.cortexDebugLaunch.configuration` 是给**独立的外部 IDE 工作区**使用的活配置：把它复制到该外部工作区的 launch 配置里，**不要**在构建后改写受管的 `.vscode/launch.json`。真实 IDE 必须先 detach，之后才能执行 `handoff-end` 归还原始 ticket。即使 ticket 完全正确，它也**不是** reclaim 成功的证明：end 会重新校验同一会话、探针和当前 firmware/flash 身份；任一不匹配（包括源码/ELF/构建证据陈旧）都必须按返回的 `code`/`details` 报告并停止，不得静默重试、自动 rebuild/flash 或宣称清理完成。任何一步失败都停止并按完整 `OperationResult` 处理。

**snapshot / 无 Git 工程。** 有效的 schema-2 snapshot 构建证据仍会被托管硬件准入以 `FIRMWARE_PROVENANCE_UNSUPPORTED` 在任何 probe/lease/attach 前拒绝，因此托管 Flash/Handoff 任务不会工作；不要用任务或手工改 receipt/identity 绕过。若确实要烧录这类固件，只能显式选择导入路线（`stm32_firmware_import` → `stm32_firmware_admit` → `stm32_flash_imported`）：其中 import PLAN 和 ADMIT 是只读的，不需要额外审批；import APPLY（在外部位置创建副本）与 flash 需要各自适用的用户授权，但一条已有的明确用户指令可能已覆盖其中多个指定步骤，应按实际适用范围复用，不要额外制造审批停顿。导入固件不提供 handoff 身份，不能解锁 debug/Monitor/Target 测试，也不能拿 imported receipt 冒充托管 buildId。

这些能力只在**当前源码**中；frozen/installed 1.3.0 不包含，也不会因重启 VS Code 而安装。真实 VS Code 进程、扩展、IntelliSense、`reevaluateOnRerun` 行为与实际 handoff UI/调试会话仍未验收；不要用真实硬件来测试任务，也不要手工编辑 managed digest。

`stm32_project_context` 的 `data.debugConfiguration` 使用同一字段语义：`backend`/`target`（不可用时为 null）、`status`（`configured`/`needs-user-input`）、`missingFields`、`diagnostics`（每项含 `code`/`field`/`rule`/`message`/`remediation`）、`targetSupport` 恒为 `not-checked`、`hardwareVerified` 恒为 false、`nextSteps`。`configured` 只表示字段已记录；缺少或无效时，`capabilityDetails.flash`/`targetTest`/`monitor`/`breakpointDebug` 为 `blocked` 并列出全部原因（与既有 snapshot/Git 阻断并存），即使 pair 有效也不会把硬件布尔值改为 true。`build`/`configure` 的可用性不受该检查影响，`stm32_probe_list` 仍是独立的只读发现。

`stm32_project_context` 的旧 `capabilities.*` 布尔值继续保留为保守兼容字段；新增 `capabilityDetails` 逐项给出 `available`、`blocked` 或 `not-evaluated` 及原因/下一步。`flash`、`targetTest`、`monitor`、`breakpointDebug` 的旧布尔 `false` 本身不区分“未探测硬件”与“已知 snapshot provenance 阻断”，必须读 `capabilityDetails`；它也不代表工具不存在。需要探针事实时单独调用只读 `probe list` / `stm32_probe_list`。仅询问已连接探针时，不需要 manifest、构建、debug backend、target 或 SVD；发现结果不授予改板权限，也不证明 target 身份或可烧录。有效工程保留 `workspaceId`，缺失或无效 manifest 时返回 `workspaceId: null` 与明确 `discovery.status=unbound`，不要伪造工程 ID。

**无 Git 的构建与来源边界（当前源码切片）。** 有效托管 GCC/CMake 工程可从导出/非 Git 目录、unborn HEAD 或 Git 缺失/无法执行的环境构建；Git 不可用本身不是构建失败。此时 `firmware-identity.json` 与 `build-result.json` 使用 `schemaVersion: 2`，identity 明确写 `sourceBaseline: "input-snapshot-v1"`、`gitHead: null`、`gitDirty: null`，并只携带有界 `gitEvidence: {"status":"unavailable","code":"BUILD_GIT_INVALID","rule":"head"}`（`rule` 为 `head` 或 `status`）；`inputSnapshotSha256`、`targetDevice`、`preset`、实际 `toolkitVersion` 与 ELF/MAP 字段仍完整。null 绝不表示 clean，不要 `git init`、commit、stash 或伪造哈希。Git 可用时继续使用原有 schema-1 字节与 build ID 语义，schema-1 不接受 nullable Git 字段。context 的 `data.build` 新增 `sourceBaseline`、`gitDirty`、`gitEvidence`，schema-2 新鲜度只依赖精确 input snapshot、target/preset/model 与 ELF/MAP 哈希，不再启动 Git。schema-2 只是 build/build freshness 证据：flash、debug、Target 测试、Monitor 与 acceptance 仍要求 Git-shaped provenance，共享 firmware 准入在任何 probe/lease/attach 前返回稳定 `FIRMWARE_PROVENANCE_UNSUPPORTED`；外层封装可按各自既有协议映射该结果（例如 acceptance recovery 映射为 `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID`），不要假定每个入口对外显示同一代码。新构建的 snapshot 证据会令 `capabilityDetails.flash/targetTest/monitor/breakpointDebug` 明确为 `blocked`。`stm32_probe_list` 仍是独立的只读发现，不受该限制。要使用受管硬件工作流，先恢复带已提交 HEAD 的 Git 基线并重建；迁移计划/应用也继续要求其 Git 基线。

### 不安装 Skill 的 MCP/VS Code 客户端路线

MCP 客户端即使从不加载 `SKILL.md`，也可按工具描述和真实返回字段完成同一流程：

1. **上下文与选择。** 调用 `stm32_project_context()`。读取 `data.project.kind`；Keil 工程从 `data.project.files` 选择项目根相对 `.uvprojx`（使用 `/`）。context **不列出 target 名称**；多项目候选时要求用户选择，不要猜。读取 `data.capabilityDetails` 的 `status`/`reason`/`nextSteps`，不要只看旧布尔值。
2. **检查与预检。** 若 target 未知，先调用 `stm32_keil_inspect(uvprojx)` 并省略 `targetName`；若返回 `KEIL_TARGET_SELECTION_REQUIRED`，把 `details.targets` 交给用户选择，再用该精确值调用 inspect。成功结果的 `data.inspection.target_name` 是后续必须保留的精确 targetName。然后用同一 `uvprojx`/`targetName` 调用 `stm32_keil_preflight(uvprojx, targetName)`。预检成功只表示 `data.analysis.complete=true`；逐项处理 `data.analysis.blockers`，并读取 `data.planReadiness.status`（`ready-for-plan`/`blocked`）、`ready` 与 `prerequisites`。`data.applyReadiness.status` 始终是 `requires-reviewed-plan`，`ready=false`、`planId=null`；预检不授权任何写入。
3. **不可绕过的修复。** 对 encoding、assembly、scoped option、scatter/memory、manifest 冲突按 blocker 的 `code`、路径和消息处理；不要转码、替换 startup、删除未跟踪文件或伪造 manifest/工程 ID。Git 缺失、unborn HEAD、非 toplevel 或 dirty 工作区只阻塞计划，由工程负责人决定基线；不要让客户端自动 `git init`/commit/stash。
4. **计划与授权。** `planReadiness.ready=true` 后调用 `stm32_keil_convert(uvprojx, targetName)`（无 `planId`、无 `authorized`）取得 PLAN 响应；检查 `data.blockers`、`data.plan_id` 和 `data.patches[].unified_diff`。若使用受支持的 CMSIS startup 路线，在 preflight、plan、apply 三次调用中传相同的 `startupStrategy="generate-cmsis-gcc"` 与 `startupSource="<精确工程相对 .s 路径>"`（单候选时可省略 source），并额外检查 `data.startup`、`Startup/stm32tk_startup_gcc.S`、`memory.stackSize`/`memory.heapSize` 和 `generation.runtimeInitialization`。只有用户显式授权该精确计划后，才调用 `stm32_keil_convert(uvprojx, targetName, planId=<data.plan_id>, authorized=true, startupStrategy=<同值>, startupSource=<同值>)`。PLAN 响应字段是 `data.plan_id`，APPLY 请求参数是 `planId`；省略或改动 startup 选项不会被接受，合法但不同的值返回 `PLAN_CHANGED`，非法的选项值返回结构化校验错误。startup 补丁与常规 manifest/源码补丁一起出现在 `data.patches` 中，而不是唯一输出文件。若 `data.analysis.memoryLayout.status=requires-selection`，先按 `candidates` 让用户选择布局，再把同一 `memoryLayout` 对象传入 preflight、PLAN 和 apply；plan 响应中的 `data.memory_layout` 显示 `status`、解析后的五角色布局（或 `null`）与实际候选。若 PLAN 返回 `data.include_merges`，逐项核对其 `scope`/`owner`/`path`/`decision` 与清单摘要，确认 `added` 目录只出现在 `build.includePaths` 末尾、原有 target 顺序不变、重复的物理目录是 `already-present`，并报告仍未解决的 blocker；不要手工修改计划、补丁、`plan_id` 或清单哈希，也不要删除 Define/MiscControls 或作用域来强行迁移。
5. **配置、构建、烧录。** `stm32_project_configure()` 的 PLAN 响应同样用 `data.plan_id`，APPLY 传 `planId` 与 `authorized=true`。构建前读 `capabilityDetails.build.status`；`stm32_build(preset, clean, timeoutSeconds, authorized=true)` 才执行。若返回 `BUILD_OUTPUT_STALE`，先保存完整响应，再按 `details.reason`/`evidenceField`/`evidenceSource` 判定；只有 `remediation.action=clean-rebuild` 且用户已授权该次 clean 构建时，才把 `remediation.mcp.arguments`（不含 `authorized`）发往同一绑定服务器/工程，或按 `remediation.cli.projectRoot` 的必需 `--project-root` 绑定，在同一 `workingDirectory=project-root` 下把同一已核实**绝对**工程根与仅作命令尾部的 `remediation.cli.arguments` 追加到 `remediation.cli.executable` 后执行（即使当前目录就是工程根也必须显式给出绝对根）；它们都保留 preset/timeout 且不是授权。`inspect-build-log` 时先看日志/配置，不重复 clean，也不修改 receipt/identity。托管烧录使用 `stm32_probe_list()` 返回的精确 `probeId`，以及 context 的 `data.build.buildId`/`data.build.elfSha256` 作为 `expectedBuildId`/`expectedElfSha256`，且仅在显式授权后传 `authorized=true`；不要复用旧 pin。`capabilities.flash` 只覆盖这条托管路线。对于没有托管工程模型的固件，若绑定服务器实际列出 `stm32_firmware_import`、`stm32_firmware_admit` 与 `stm32_flash_imported`，可按上一节的外部固件路线先离线导入/准入，再单独授权烧录；不要为此伪造 manifest、`buildId` 或 Git 状态，也不要把 admission 成功当成烧录成功。
6. **仅发现探针。** 用户只问“有哪些探针”时直接调用 `stm32_probe_list()`，读取 `data.probes`、`data.workspaceId` 和 `data.discovery`。该调用不需要 manifest、构建、backend、target 或 SVD，也不得继续执行 flash；若 `data.workspaceId=null` 且 `data.discovery.status="unbound"`，如实说明 discovery-only，绝不伪造 workspace ID。发现结果不证明 target 身份或烧录就绪。
7. **VS Code 集成。** 生成的 `.vscode/tasks.json`/`launch.json` 只是配置目标；`launch.json` 保持为空，任务中的硬件动作默认 `deny` 且一次授权只覆盖一次调用。在真实 VS Code、扩展版本和实际调试会话中运行前，不得声称 IDE 路径已验收或部署完成。

### AI 调用：版本绑定、完整结果与两条固件路线（当前源码切片）

AI 客户端只使用现有证据核对绑定，不新增绑定检查工具：

- `stm32_doctor` 的 `data.runtime.toolkitVersion` 与 `data.publicInventory` 描述**实际绑定的服务器**；还要对比客户端真实列出的工具及 input schema，并保留 `stm32_project_context.data.project.root` 为根权威。启动器/CLI 版本和 doctor 的工具数量都不是“客户端已注册这些工具”的证明。
- 升级后重启 VS Code 一次再验证；工具/字段缺失或根不一致时，保存完整 JSON 并停止依赖该能力的操作，不要在启动器间回退、伪造会话或绕过 root 校验。
- 先保存/读取完整 `OperationResult`（`ok`、`code`、`message`、`data`、`details`），再作总结；不要用 `head`/`grep` 或旧布尔值丢掉诊断。`ok=false` 时保留 `details`；`capabilityDetails` 的 `status`/`reason`/`nextSteps`、`planReadiness`/`applyReadiness` 与原始 preflight blocker 字段含义不变。

成功 context 新增的 `data.firmwareRoutes` 只是**描述，不执行任何发现、导入或后端操作**：

| 路线 | context 中的状态 | 工具 | 边界 |
| --- | --- | --- | --- |
| managed | 与 `capabilityDetails.flash` 的 `status`/`reason`/`nextSteps` 完全一致 | `stm32_probe_list` -> `stm32_flash` | 使用 `data.build.buildId` 与 `data.build.elfSha256`；要求 Git-shaped provenance。已知 managed blocker 只停止该路线。 |
| imported | 始终 `not-evaluated` | `stm32_firmware_import` -> `stm32_firmware_admit` -> `stm32_flash_imported` | 不需要 Git 或托管模型；import PLAN 与 ADMIT 只读，不需要额外审批；import APPLY（外部副本）与 flash 需要各自适用的用户授权，一条已有的明确用户指令可能已覆盖其中多个指定步骤；回执不解锁 debug、Monitor、Target 测试、旧式 flash 证据或 reset/recovery。 |

工具存在不等于镜像就绪。managed 失败不会自动切换路线；imported 路线必须由用户显式选择，并校验该路线自己的输入；context 的模型/绑定错误不证明该入口不存在，也不能用来绕过无效 root、绑定错误或工具错误。debug/Monitor/Target 路线不得把 imported 回执当作补救。

`stm32_keil_preflight` 的每个 `analysis.blockers[]` 新增 `remediation`：`category` 为 `needs-user-input` 或 `unsupported`，附简明 `summary`、适用的真实工具/Skill 引用和 `requiredInputs`；`blockerSummary.byRemediation` 保留分类计数，`total`/`byCode` 与原始 blocker 字段不变。可选 `tool` 只命名真实 MCP 工具，可选 `skill` 单独命名 Skill，两者不混用。`uvprojx`/`targetName` 是基本选择参数；与 remediation 相关的可选补充参数只有 `memoryLayout`（以及独立的 `startupStrategy`/`startupSource`）。没有 framework、FPU 或 ABI 覆盖参数，不得臆造，也不得为了清除 blocker 而改证据或删除控件；应检查并保留实际工具链/构建语义，必要时用另行审阅的工程自有移植。编码 blocker 只有在每个受影响文件的 charset 明确声明且改动仅限注释时，才可建议独立的 `normalize-source-comments` 审阅副本；其它字节序列或非注释内容仍不受支持。若用户明确要求把不可解码单元，或注释内的私有使用、C1 控制、U+FFFD、非字符码点，在副本中显式换成字面 `?`，则该显式意图与已声明 charset 即可授权生成只读的替换预览（`preview --replace-invalid-with '?'`，唯一支持值）；严格 `DECODE_ERROR` 尚未把这些字节分类为注释内容，不能据此宣称它们可替换，替换预览本身负责逐条分类并可阻断。只有实际被证明属于注释内容、且逐文件审查过的记录才允许复制；复制时按已审查的逐文件选择显式传入 `--confirm-file`，不得遍历 `lossyFiles` 自动生成确认，若拒绝某个有损失文件则重新生成缩小选择范围的预览，而不是编辑计划或复制未批准文件。该预览逐条记录原始字节偏移、长度、十六进制、行列、原因和替换值。非注释字节、字符串/字符字面量/头文件名、未终止结构、DBCS/反斜杠歧义、源码已有或替换产生的 `??/`、`??=` trigraph 仍阻断（其它 trigraph 序列只作审查警告），且不会改写原工程。未知汇编、选项、绝对放置语法和未知未来代码仍是 `unsupported`，没有自动修复。

**Scope 级 IncludePath（当前源码切片）。** 当 include 分析产生决定证据（存在可合并或已再次暴露的 scoped 目录）时，preflight 额外返回 `data.analysis.includeMerges[]`：每项含 `scope`（`group`/`file`）、`owner`（组名或工程相对源路径）、规范化 `path`、`decision`（`added` 或 `already-present`）；`added` 项还带目录清单摘要 `inventorySha256` 与 `inventoryFiles`（PLAN 的 `data.include_merges` 使用 snake_case 的 `inventory_sha256`/`inventory_files`）。只有其参与编译的源文件全部是被加入构建的 C/C++ 的作用域才参与；列出的头文件与预编译库不会执行编译器，因此不影响该判定（C/C++ 组同时列出头文件仍可合并）；被排除文件、仅含头文件/库的组或文件、以及没有任何被加入构建源文件的组都被忽略。同时带 Define 或 MiscControls 的作用域仍按单个 `ARMCC_OPTION_UNSUPPORTED` 整体拒绝，同时参与编译被加入构建的汇编或未知语言的作用域也保持该 blocker，绝不只取出其中的 include，也不得为迁移删除这些控件或作用域。`MIGRATION_INCLUDE_*` blocker（missing、not-directory、escaping、unreadable、redirect、limit、collision）表示整次 include 分析不成立：不产生任何部分合并，`build.includePaths` 保持原 target 列表，按 blocker 处理真实工程语义。冲突检测按大小写不敏感的 include 相对完整键（含嵌套路径）比较：同一键在不同搜索目录解析到不同文件才是冲突，即使字节相同；同一物理文件通过重叠目录（例如 target 已有 `USER`，scoped 再暴露 `USER/IWDG`）暴露不构成冲突，包含关系本身也不拒绝。同一物理目录只出现一次，扫描前先按规范化目录去重；所有目录共享一个聚合遍历/哈希预算（条目、文件、目录、深度、字节），超限即整体拒绝而不是采样猜测。PLAN 以 `data.include_merges` 暴露同一决定，成功 apply 的 `conversion-report.json` 增加 `includeMerges`；`added` 目录按 inspection 顺序追加到 target 列表末尾，原有顺序不变。该证据（含清单摘要）只在存在相关作用域时绑定进计划身份，因此普通无 scope 工程的历史 `plan_id` 不变；apply 会重新规划，Git 忽略目录中头文件内容变化或新增同名文件会使 apply 以 `MIGRATION_PLAN_INVALID`（`rule=freshPlan`）失败而不是沿用旧判断。不要手工修改计划、补丁、`plan_id` 或清单哈希来强行迁移。

**可复制 PowerShell 核对（保留未过滤 JSON，并处理 ok/error）：**

这些命令启动**独立的 CLI 进程**；它们不能证明当前 VS Code 中实际绑定的 MCP 进程注册了哪些工具。真正的绑定证明必须在实际 MCP 客户端重复 `stm32_doctor` 与 `stm32_project_context`，并对照客户端列出的工具/input schema。`data.firmwareRoutes` 与 preflight `remediation` 属于本源码切片；冻结的 v1.3.0 ZIP/runtime 没有这些字段，因此在该包中缺失**不是** MCP 过期的证据，需等后续匹配构建安装后才可检查。

```powershell
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$CandidateCli = Join-Path $DataRoot 'runtime\1.3.0\Scripts\stm32-toolkit.exe'

& $CandidateCli version
$DoctorText = & $CandidateCli --project-root $ProjectRoot doctor --json | Out-String
$DoctorText
$Doctor = $DoctorText | ConvertFrom-Json
if (-not $Doctor.ok) { throw "doctor failed: $($Doctor.code): $($Doctor.message)" }
$Doctor.data.runtime.toolkitVersion
$Doctor.data.publicInventory

$ContextText = & $CandidateCli --project-root $ProjectRoot project context --data-root $DataRoot --session-id verify-1 --json | Out-String
$ContextText
$Context = $ContextText | ConvertFrom-Json
if (-not $Context.ok) { throw "context failed: $($Context.code): $($Context.message)" }
$Context.data.project.root
$Context.data.capabilityDetails
$Context.data.firmwareRoutes
```

**MCP 调用示例（伪代码，沿用真实参数名；替换所有审阅值，勿当作默认值）：**

```text
# 两条路线是独立分支：managed 分支的失败不会进入 imported 分支；
# 但无效工程根、无效绑定或该入口自身的错误对任一路线仍然权威。
# 所有值均为需用户审阅的示例，不是默认值。

# --- Managed 分支（用户已选择）---
ctx = stm32_project_context()
if not ctx.ok: report(ctx.code, ctx.message, ctx.details); stop this branch
# not-evaluated 表示 context 未检查硬件，并非拒绝；不要用旧 capabilities 布尔值判断就绪。
managed = ctx.data.firmwareRoutes.managed
if managed.status == "blocked": report(managed.reason, managed.nextSteps); stop
if (ctx.data.build.buildId is None or ctx.data.build.elfSha256 is None
        or not ctx.data.build.elfFresh):
    report("no current managed build identity"); stop
probes = stm32_probe_list()
if not probes.ok: report(...); stop
# 用户选择确切 probe，并为该次精确操作单独显式授权后：
stm32_flash(probeId="<user-selected data.probes[].probeId>",
            expectedBuildId=ctx.data.build.buildId,
            expectedElfSha256=ctx.data.build.elfSha256,
            authorized=true)

# --- Imported 分支（用户已显式选择文件；独立于上面的 model/context 门）---
# 不需要 stm32_project_context；只校验本路线自己的声明输入。
plan = stm32_firmware_import(              # 只读 PLAN
    firmwarePath="<user-declared project-relative firmware path>",
    expectedSha256="<lowercase SHA-256 of that original file>",
    format="<elf|hex|bin reviewed for this file>",
    target="<pyOCD target reviewed for this image, not a default>",
    flashRegions=[{"start": 134217728, "length": 1048576}],  # 十进制 JSON；审阅示例，非默认
    baseAddress=134217728)                 # 仅 BIN；审阅示例，ELF/HEX 时省略
if not plan.ok: report(...); stop          # -> data.planId, data.importId, data.source.sha256
# PLAN 是只读的；先取得用户对不可变离线副本的显式授权，再 APPLY。
apply = stm32_firmware_import(             # 第一个写授权边界
    firmwarePath="<the same path>", expectedSha256="<the same original SHA-256>",
    format="<the same format>", target="<the same target>",
    flashRegions=[{"start": 134217728, "length": 1048576}],  # 同一审阅列表
    baseAddress=134217728, planId=plan.data.planId, authorized=true)
if not apply.ok: report(...); stop         # 仅授权不可变离线副本，不授权硬件
# ADMIT 是只读的，没有 authorized 参数，不需要写授权。
admit = stm32_firmware_admit(importId=apply.data.importId,
                             expectedSha256=plan.data.source.sha256)
if not admit.ok: report(...); stop
if admit.data.offlineReady is not true: report(...); stop
probes = stm32_probe_list()
if not probes.ok: report(...); stop
# 用户选择确切 probe；复述镜像/probe/target，并为这次硬件操作取得新的独立授权后：
stm32_flash_imported(probeId="<user-selected probe>", importId=apply.data.importId,
                     expectedSha256=plan.data.source.sha256, authorized=true)
```

写授权只有两个边界：固件 APPLY（不可变离线副本）和 `stm32_flash_imported`（一次精确硬件操作）。PLAN 与 ADMIT 都是只读的，ADMIT 没有 `authorized` 参数，不要要求用户为它授权。两套 PLAN/APPLY 字段不同：Keil convert/configure（`stm32_keil_convert`/`stm32_project_configure`）的 PLAN 响应字段是 `data.plan_id`，固件 import 的 PLAN 响应字段是 `data.planId`；两者的 APPLY 请求参数都是 `planId`。固件 import 的 `data.source.sha256`（原始文件）与 `data.image.sha256`（规范化镜像）是两个独立字段，admission/flash 结果中对应扁平的 `sourceSha256`/`imageSha256`。任一失败都不会自动切换路线。

**显式烧录频率与恢复建议（当前源码切片）。** `stm32_flash` 与 `stm32_flash_imported` 新增可选参数 `frequencyHz`（StrictInt，含端点 `100000..50000000`，或 `null`）；CLI 对应 `flash`/`flash-imported` 的 `--frequency`，只接受十进制整数 Hz，重复、小数、越界或其它格式在解析阶段拒绝。省略时保持既有 worker 配置：生产正常 CMSIS-DAP 默认仍为 `1000000` Hz。频率是**选定的配置**，不是实测/生效频率，也不证明 attach 或编程发生。

- 托管正常烧录：显式 `frequencyHz` 选定该值。恢复策略固定 `100000` Hz：`recoveryUnderReset=true`/`--recovery-under-reset` 时可省略频率或恰好传 `100000`；其它显式值在创建目录、lease、supervisor、backend 或执行 flash 之前以 `HARDWARE_INPUT_INVALID`（`details.field=frequencyHz`，`details.rule=conflict`）失败。类型错误为 `rule=type`，越界为 `rule=range`。
- 导入烧录：只接受正常频率，不支持 under-reset recovery，也不应给出该路线的恢复建议。
- 成功与失败结果在配置选定后都会带 `details.flashOptions`：`requestedFrequencyHz`（省略时为 `null`）、`configuredFrequencyHz`、`connectionPolicy`、`automaticRetry=false`。早期输入/授权/准入失败可以没有该字段。托管成功仍保留 `details.postFlash.targetState=unknown` 与 `runVerified=false`。
- 仅托管正常烧录在自有清理完成后返回 `PROBE_PROGRAM_FAILED`，或返回带有效闭合 `attachDiagnostic` 且 `primary.stage` 为 `session-open`/`halt-verify`、`primary.reason` 属于可恢复连接类别的 `PROBE_ATTACH_FAILED` 时，才可能附加 `details.recoverySuggestion`（`kind=under-reset`、`frequencyHz=100000`、`requiresNewAuthorization=true`、`automaticRetry=false`）。它只是提示：先停止、保留完整诊断、核对目标供电/复位接线与清理结果，再由用户另行授权一次性恢复；恢复可能让目标保持 halted，不证明其已运行。频率或恢复选项应在这一次授权调用前选定；失败建议不是第二次调用，也不构成自动重试。
- 清理失败、身份/stale/provenance/输入/授权/回读/receipt 失败、成功结果、已选择 recovery、导入路线、取消或任意其它错误都不附加该建议；不要把它当作自动重试、路线切换或既有 `attachDiagnostic`/一般 guidance 的替代。原有失败字段与清理优先级保持不变。
- 这些频率选项和 `flashOptions`/`recoverySuggestion` 只存在于本源码切片；冻结/已安装的 v1.3.0 没有它们，重启 VS Code 也不会安装。生成的 IDE 任务模板保持原样；不要通过修改模板 digest 设置频率，也不要在原授权之外自动执行恢复。

**状态：**以上 AI 调用指引是当前源码切片，**不在**冻结的 v1.3.0 本地构建源码 `1e6ea849c21fb3786d60dba0254acb375d016a62` 及其 runtime/ZIP 中。重启 VS Code 只会刷新已安装服务器，不会安装本补丁。本切片未安装、未重启、未记录安装资格（另有用户会话安装过更早的候选，本切片不复核）。本切片不提升版本、不改变 52 工具/9 Skill 清单、不改写既有 runtime/缓存，也不构成公开发布或资格结论。

## 工程 manifest 的阶段约束

当前 loader 校验 Schema v2/v3、类型、路径 containment 和安全引用；以下额外规则由 **configure 阶段**执行，不能误说成所有 loader 都拒绝的 schema 全局规则。按 [schemas/stm32-project.schema.json](../schemas/stm32-project.schema.json) 和工程实际来源编辑，不手工伪造 `generatedBy` 或 managed ownership。

| 字段/阶段 | 当前有效约束与处置 |
| --- | --- |
| `build.presets` | configure 要求恰好 `["arm-debug", "arm-release"]`，顺序不变。 |
| `build.elf` | configure 要求 `build/arm-debug/<name>.elf`，`<name>` 只是一层文件名。 |
| `build.newlibSpecs` | 可选、有界：当前仅允许 `["nosys.specs"]`（无重复）；缺失时保持历史字节与原生 linker 默认。受管 linker 额外输出一次 `--specs=nosys.specs`，不隐式加入 `nano.specs`，也不是通用 linker 自定义入口。 |
| `generation.managedManifest` | configure 使用 `.stm32-toolkit/generated-files.json`。已有 managed record 仍按 hash/用户改动保护。 |
| `build.sources`、`generation.nativeLinkerScript`、`debug.svd` | 路径须在工程根内且安全；SVD 文件应存于工程根，选择其准确设备名。 |
| `debug.readableRegions` | 只配置经核对的可信范围；选择 SVD 时必须覆盖所选 SVD 中每个解析出的寄存器的完整地址宽度。不要为消除报错而信任所有地址。 |
| 堆/栈 | `memory.stackSize`/`memory.heapSize` 是可选的精确字节数（stack 为正且 8 字节对齐，heap 为非负且 8 字节对齐）。缺省时内置 linker 模板保留历史默认 4 KiB heap/1 KiB stack；存在时使用精确值（如 `_Min_Heap_Size = 0x400;`、`_Min_Stack_Size = 0x1000;`），不得被 4K/1K 静默替换。`generation.runtimeInitialization` 仅支持 `cmsis-gcc-v1`，且只能与托管 linker 模板一起使用；它增加构造/析构数组和初始 SP/堆兼容符号。特殊工程仍可用已有 `generation.nativeLinkerScript`，此时 runtime 字段会被拒绝而非忽略，并须自行核对启动向量、初始 SP、区域边界和运行时初始化。 |

`.vscode/{tasks,launch,c_cpp_properties,settings,extensions}.json` 是编辑器目标集合。v1.0.0 的未托管文件可能触发 `UNOWNED_COLLISION`；不要删掉用户文件来绕过。自 v1.0.1 起，configure/build 仅保留这些路径上的未托管普通文件，计划单列 `preserved-unowned`，不读取、改写或收编其内容，IDE 设置仍需用户自行对齐。目录、链接、重解析点、构建必需文件、已有 managed record 或用户修改仍依合同拒绝。CubeMX regeneration 有独立闭域 inventory，configure 成功不代表 regeneration 能接纳这些编辑器文件。

## 迁移和构建：报告项 1–4、9–10、12–13、15、17、20–22

| # | 看见什么 | 本版行为与处置 |
| --- | --- | --- |
| 1 | 子目录 `.uvprojx` 报 `KEIL_PROJECT_NOT_FOUND` | v1.0.0 可用 `--uvprojx Project/xxx.uvprojx`（可移植正斜杠）指明根内路径；自 v1.0.1 起在工程根内安全递归发现，多候选要求显式选择。目录不可枚举返回发现不完整，不能冒充“无工程”。 |
| 2 | `ARMCC_SOURCE_ENCODING_UNSUPPORTED` | 先确认原始编码与版本控制状态，工程负责人决定转换副本/源码；Toolkit 不猜 GB2312/GB18030，也不自动转码。需要 UTF-8 副本时走独立 `normalize-source-comments` 技能：逐文件显式声明编码，默认只读预览，再按已审查 plan 复制到项目外新目录；它只转换注释、绝不改写原工程，也不解决 startup、scoped option、scatter/memory、Git/apply、baseline 等其它 blocker。严格预览报 `DECODE_ERROR`，或注释内出现私有使用/C1/U+FFFD/非字符码点时，先向用户展示具体逐文件证据；严格 `DECODE_ERROR` 尚未把这些字节分类为注释内容。只有用户明确要求把这些单元换成字面 `?`，该显式意图与已声明 charset 才授权追加 `--replace-invalid-with '?'` 生成只读替换预览（其它值在创建预览目录前即失败）；该预览负责分类并可阻断，只有被证明属于注释内容且逐文件审查过的记录才允许复制。审查 `mode`、`replacementValue`、每个 `lossy` 文件的 `replacementRecords`（原始字节偏移/长度/十六进制/行列/原因/替换值）与字节 diff，然后按已审查的逐文件选择各传一个 `--confirm-file '<相对路径>'`，不得遍历 `lossyFiles` 自动生成确认；若有文件被拒绝，重新生成缩小选择范围的预览，而不是编辑计划或复制未批准文件；用户请求若已足够具体地授权输出已审阅副本，复用该授权，不额外增加重复许可停顿。缺失、重复、未知、非损失或严格计划上的确认都会在创建输出目录前拒绝。替换模式仍会阻断非注释字节、未终止结构、DBCS/反斜杠歧义、源码已有的 `??/`/`??=` 和替换产生的 `??/`/`??=` trigraph（其它 trigraph 序列只作审查警告），且 manifest 只记录模式、确认文件与损失，不宣称迁移完成；`?` 是已审阅的内容丢失，不是修复或编码结论。字节保真仍是项目责任。该技能说明与 helper 位于仓库 `skills/normalize-source-comments/`（安装后为对应个人技能目录，含 `SKILL.md`、`references/lexical-and-plan-contract.md` 和 `scripts/normalize_comments.py`）；MCP 客户端没有、也不应臆造规范化工具，应直接按该目录说明用已验证的 Python 调用 helper。本页描述的能力只在当前源码中；重启 VS Code 不会安装这份源码补丁。 |
| 3 | `ARMCC_ASSEMBLY_UNSUPPORTED` | 默认仍阻断任意 ARMCC 汇编。仅当文件是受支持的常规 ST/CMSIS Cortex-M3/M4/M7 startup 时，可显式使用 `startupStrategy="generate-cmsis-gcc"`（CLI `--startup-strategy generate-cmsis-gcc`）并通常配合 `startupSource="<工程相对 .s 路径>"`（CLI `--startup-source`）；工具生成并审查 `Startup/stm32tk_startup_gcc.S`，保留原文件，只替换 `build.assemblySources` 中选中的那一项。其它 `.s` 仍逐个阻断。识别器整文件校验语法，不执行代码、不猜测未知指令/宏/条件分支/自定义 reset 或 handler；返回 `analysis.startup`/`data.startup` 的源哈希、有序向量与保留槽、stack/heap 字节、reset 模式、生成摘要、警告和诊断。preflight、plan、apply 必须使用相同选项（或都省略），apply 重规划并拒绝被改动的 strategy/source：合法但不同的值返回 `PLAN_CHANGED`，非法的选项值返回结构化校验错误；目标已存在且字节不同时报告 `MIGRATION_STARTUP_TARGET_COLLISION`，绝不覆盖。生成的是经审查的 GCC 迁移补丁，不是 ARMCC、ABI 或 Microlib 的二进制/行为等价物。 |
| 4, 17, 22 | configure 遇 `UNOWNED_COLLISION` 或编辑器设置已存在 | 核对目标路径与 managed manifest。构建必需文件冲突需工程方决定所有权；自 v1.0.1 起只保留上述五个未托管普通编辑器文件，不 merge/adopt。 |
| 9 | Flash used 似乎含 `.bss`/栈 | 核对原始 ELF/MAP。候选按有内容段的 LMA 计加载容量，NOBITS 只计运行地址预留；没有原始 ELF/MAP 不可宣称复现报告数字。 |
| 10 | RAM `free=0`，栈处于区域高端 | 报告按 section 实际占用区间并集，而非区域首尾跨度。若 `.stack` section 自身含大空隙/预留，它仍是 linker 分配；不能当成可用 RAM。运行时峰值需另测。 |
| 12 | `MIGRATION_GIT_DIRTY` 只有 untracked 文件 | 仍是迁移安全阻断。查看 `git status --short`，逐项决定版本控制或项目 `.gitignore`；不要自动删除、stash、忽略或放宽检查。候选 details 区分 index/tracked/untracked。 |
| 13 | `baseline.available=true` | 只表示找到了可解析的历史 AXF/MAP，不证明本次 GCC/Keil 构建、工具链、授权来源或可比身份；候选在结果中明确这一语义。 |
| 15 | Skill 在 capability false 后停止，或 apply 丢参数 | 先读 `capabilityDetails`：`available` 只表示入口适用于当前工程，`blocked` 给出具体前置，`not-evaluated` 表示 context 未检查（尤其硬件布尔值）。inspect/preflight/plan/apply 保持同一 `uvprojx` 与 `targetName` 并严格核对 plan ID；入口可用不保证迁移没有 blocker。 |
| 20 | schema 未写尽跨字段规则 | 以上配置阶段规则是当前合同；不要手工生成错误 manifest 或把 configure 条件升格为 loader 不兼容。根与包内 schema 副本应一致。 |
| 21 | 默认栈容量/`__StackTop` 语义不符工程 | 候选模板的向下增长栈 Top 在高地址、Limit 在低地址；未设置 `memory.stackSize`/`memory.heapSize` 时保留默认 4 KiB heap/1 KiB stack。startup 生成路线会记录源文件中的精确字节数并在托管 linker 输出精确值；其它工程可显式设置这两个可选字段。若改用受控 native linker，`generation.runtimeInitialization` 必须移除，并核对实际 ELF/MAP。 |

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

## 外部固件导入与独立烧录（当前源码/候选切片）

这条路线与托管构建/烧录完全分开，已集成进 **v1.3.0 本地候选源码**但尚未发布；已发布 v1.2.0 的 48 工具包没有这些入口。它用于没有 `.stm32-project.json`、Git 或构建 receipt，但持有可用固件文件的工程。使用前先核对实际启动器版本，并对实际绑定服务器执行 `doctor --json`：确认 `data.publicInventory.mcpTools` 列出这三个工具、`skills` 为九个，并检查真实工具 input schema 的字段名与类型；只按实际返回调用，不要按本页推断。

- `stm32_project_context` 的 `capabilities.flash` 只描述**托管构建路线**；它不评估、也不阻止外部导入路线。未托管工程只要实际绑定的服务器暴露 `stm32_firmware_import`、`stm32_firmware_admit`、`stm32_flash_imported`，就可以使用本路线。
- **导入计划**：`stm32_firmware_import(firmwarePath, expectedSha256, format, target, flashRegions, baseAddress?)`。`firmwarePath` 是工程根内正斜杠相对路径；`expectedSha256` 是**原始文件**的精确小写 SHA-256；`format` 为 `elf`、`hex` 或 `bin`（AXF 按 ELF 解析）；`target` 是明确的受支持 pyOCD target 标识；`flashRegions` 是 1–32 个 `{start,length}` 内部应用 Flash 区间（`0x08000000 ≤ start < end ≤ 0x10000000`），这是用户复核的声明，不是芯片容量测量。BIN 必须显式给 `baseAddress`，其它格式禁止该参数；BIN 没有调试符号，也不推断启动地址。不传 `planId` 时返回只读 PLAN：`data.planId`、`data.importId`、`data.source`（原始路径/SHA-256/大小）与 `data.image`（规范化 ARM ELF 的 SHA-256/大小/段/入口）。计划中 `data.source.sha256` 与 `data.image.sha256` 是**两个独立字段**（准入/烧录结果中则是扁平的 `sourceSha256`/`imageSha256`）；它们通常不同，但原始 ELF 若已与规范化镜像逐字节相同，二者也会相同，不能把“不相等”当作校验规则。
- **只读源哈希**：在工程内读取原始文件并计算 SHA-256，不修改文件：`(Get-FileHash -LiteralPath <path> -Algorithm SHA256).Hash.ToLowerInvariant()`。人工核对结果后再填入 `expectedSha256`；不要用会改写源文件的工具。
- **导入应用**：用该次 `data.planId` 加 `authorized=true` 重发同一请求。写操作前的失败要按来源区分：`expectedSha256` 与当前原始文件不符时先返回 `FIRMWARE_INPUT_CHANGED`，不会进入计划比较；相同 `expectedSha256` 下路径、格式、base、target、Flash 区间或项目/数据根绑定发生变化时，重新分析成功后返回 `FIRMWARE_PLAN_CHANGED`。若新请求本身无效（例如格式、区间、类型或参数组合不合法），会在计划比较前返回对应的结构化校验错误；不能保证每种改动都得到同一个代码。`authorized=true` 而没有 `planId` 是错误。成功后在外部数据根保存不可变快照；相同输入重复应用是幂等成功，冲突的既有导入绝不覆盖。该授权只覆盖离线导入副本，**不授权任何硬件操作**。
- **离线准入**：`stm32_firmware_admit(importId, expectedSha256)` 只读且离线。`expectedSha256` 始终钉住被导入的**原始文件**，不是规范化镜像。它会从保存的源文件与参数**重建**镜像并比对全部段/入口/记录，返回 `offlineReady=true`、`hardwareVerified=false`、扁平的 `sourceSha256`/`imageSha256`、target 与段摘要，以及仍需的硬件授权/身份条件。它不创建 service、lease、worker 或 receipt，也不是可复用授权令牌；**不要把 admission 成功当成烧录成功或当前构建身份**。
- **独立烧录**：先 `stm32_probe_list` 取得精确 `probeId`，再单独取得用户对**该探针与该导入**的明确授权，调用 `stm32_flash_imported(probeId, importId, expectedSha256, authorized=true)`。调用方不能覆盖 target、Flash 区间、路径、根、backend 或来源。工作流在创建 supervisor/lease/worker 前、attach 后与发出编程 RPC 前都会重新校验存储；backend 在第一次驱动调用前要求规范化镜像的**每个字节**都被连接的 target 原生 Flash 区间并集覆盖（允许跨越相邻 64 KiB 区间，拒绝空洞、非 Flash 区间或重叠的畸形 map）；随后回读全部计划字节。只有回读、最终完整性检查、所有权清理成功，且在清理后再次确认快照未变化，才在数据根写入独立的 external-flash receipt；清理失败或清理期间快照被改动都不会产生成功 receipt。成功烧录结果的 `details.postFlash` 为 `{"targetState":"unknown","runVerified":false}`；早期失败（例如探针、认证、准入或参数错误）可能不包含该字段，应按实际返回报告。
- CLI 对应 `firmware import`（显式 `--dry-run` 或 `--apply --plan-id … --authorized`）、`firmware admit`、`flash-imported`，参数为 `--firmware-path`、`--expected-sha256`、`--format`、`--target`、`--flash-regions '<json>'`、`--base-address`、`--import-id`、`--probe`、`--authorized`（`flash`/`flash-imported` 还可选 `--frequency <decimal Hz>`），并沿用 `--project-root`/`--data-root`/`--session-id`/`--json`。例如：

```powershell
$CandidateCli = Join-Path $DataRoot 'runtime\1.3.0\Scripts\stm32-toolkit.exe'
# Requires a healthy Check for runtime/1.3.0 and a matching reported version.
& $CandidateCli version
# 1) Read-only PLAN. Keep the exact reviewed planId and original SHA-256.
& $CandidateCli firmware import --project-root $ProjectRoot --data-root $DataRoot --session-id ext-1 --firmware-path firmware/app.bin --expected-sha256 <original-sha256> --format bin --target stm32f407vg --flash-regions '[{"start":134217728,"length":1048576}]' --base-address 134217728 --dry-run --json
# 2) Apply that exact reviewed plan (separate authorization for the copy only).
& $CandidateCli firmware import --project-root $ProjectRoot --data-root $DataRoot --session-id ext-1 --firmware-path firmware/app.bin --expected-sha256 <original-sha256> --format bin --target stm32f407vg --flash-regions '[{"start":134217728,"length":1048576}]' --base-address 134217728 --apply --plan-id <data.planId> --authorized --json
# 3) Offline admission of the stored snapshot.
& $CandidateCli firmware admit --project-root $ProjectRoot --data-root $DataRoot --session-id ext-1 --import-id <data.importId> --expected-sha256 <original-sha256> --json
# 4) Optional, separately authorized hardware operation. Omit unless the user
#    explicitly authorizes this exact probe and import.
& $CandidateCli flash-imported --project-root $ProjectRoot --data-root $DataRoot --session-id ext-1 --probe <data.probeId> --import-id <data.importId> --expected-sha256 <original-sha256> --authorized --json
```

边界：不要为这条路线伪造 `.stm32-project.json`、`buildId`、Git 提交或托管 receipt。导入快照不代表原始工程当前的构建；原始文件之后被删除或重建也不会自动替换已导入字节，重新构建后应重新导入取得新身份。该 receipt 不解锁 debug、Monitor、Target 测试、旧式 flash-result，也不提供 under-reset 恢复、reset、resume、handoff 或自动调试准入。本切片不实现原生 UV4、自动“快照转托管”或迁移基线比较。

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

以下 UI02/UI03 就地恢复、固定端口、书签与会话恢复行为属于 v1.2.0 已验收源码，并在 v1.3.0 候选中保持；取得并核验对应发行包或本地候选、安装且 `Check` 确认 healthy 后，才能按该版本启动器使用。v1.0.1 发布包不支持 `--port`，也不包含这些就地恢复操作。

已打开的工作台内，普通操作失败会在导航下方的“操作提示”就地显示原因；多个提示可分别查看、关闭或按提示重试，当前页面、最后成功的数据和未保存草稿保留。读取重试使用失败时的原查询、页游标或导出任务 ID。除上述组冲突外，写入被明确拒绝时，须先核对原目标和内容并确认，才会重试上次操作；编辑按钮仍提交当前草稿。写入结果未知时不盲目重复提交：能核对的操作只刷新状态或列表，导出创建若没有任务 ID 则说明结果未知。若写入已成功而随后刷新失败，只重试读取，不重复写入。无效的导入文件须重新选择。初次读取普通失败可重试初始化；真正的认证或访问失效仍整页阻断，按提示重新打开授权标签。

`open --port 8765` 成功后，终端显示不带 token 的 `http://127.0.0.1:8765/`，可将这个短地址加入书签。服务保持运行、同一浏览器配置的会话 cookie 有效时，关闭标签页后打开书签可回到工作台。关闭整个浏览器后是否保留会话取决于浏览器配置；新浏览器配置不会自动继承原会话。若短地址提示“当前会话已失效”，在**原 `open` 前台交互终端**按 Enter，启动器会把同一服务的授权页面再次交付系统默认浏览器。该浏览器配置完成认证后，在原短地址页面点“重新检查会话”；只有状态核对成功才进入工作台。交付请求本身不证明浏览器已完成认证。非交互启动时，须由启动方重新交付授权页面；不要保存或手输包含 fragment token 的授权链接。403“访问被拒绝”须检查入口、请求来源与浏览器配置，不能当作会话过期处理或放宽访问限制。

`bin/stm32-monitor.cmd` 先用 `STM32_TOOLKIT_DATA_ROOT` 定位相同版本的受管 Python；单给 `--data-root` 不能启动 cmd。Monitor 入口启动后才读取 `open --data-root`，两处须指向同一 DataRoot。v1.2.0 启动器只使用已安装的 `runtime/1.2.0`，v1.3.0 候选启动器只使用 `runtime/1.3.0`；不要把另一版本的解释器、`PYTHONPATH` 源码覆盖或不同版 wheel 混入。以下命令要求**本版发行包已核验、安装且 Check 为 healthy**：它打开服务和新浏览器标签，并在前台保持运行；用该终端的 Ctrl-C 正常结束，不存在通用后台 daemon/stop 协议。

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

已发布 v1.0.0/v1.0.1/v1.2.0 的标签、发行资产、凭据和数据边界不变。v1.3.0 源码候选的 Toolkit、Monitor、UI、插件、启动器与发行身份统一为 1.3.0；已有 1.2.0、1.1.2、1.0.1 及更早获批 runtime 经 `Check` 后只能以获授权的 `Repair` 事务升级，旧目录进入隔离区；只有既有事务可恢复分支才按其规则回滚旧 runtime 和状态，具体证据范围见[发布状态](release-status.md)。多旧版、未知未来目录、同版本不同来源、降级和锁定提升继续拒绝；不要手动移走状态文件。现有工程 `generatedBy` 保留真实旧版本；1.2.0/1.1.2/1.0.1/1.0.0/0.9.0 工程可计划和应用，只有显式 configure 事务刷新未改动的托管模板与记账，用户改动仍阻断。新 build 生成实际 1.3.0 身份，旧 flash receipt/evidence 不改写。工程 producer 可读不代表旧固件身份可供新版观测：现有 flash 合同要求 build 的 Toolkit 版本与当前 1.3.0 精确一致，1.2.0/1.1.2 build/flash receipt 不能直接绑定 1.3.0 运行观测，旧 build 会以 `FIRMWARE_IDENTITY_MISMATCH` 被拒绝；后续须经授权重建、烧录并建立新观测身份。旧 1.2.0/1.1.2/1.0.1 导出清单的 Toolkit/Monitor 版本不符合 1.3.0 精确校验；需使用原版本读取旧导出，或在新版本重新创建，不自动迁移或重签。改变 debug 元数据后，完整输入身份合同可能要求重新 configure、clean build 和必要的新烧录；运行观测仍按原完整身份与具名硬件授权，不提供内容等价 rebind。本指南不代替 Release notes 的最终资格结论；v1.3.0 候选已有本地官方构建产物（源 `1e6ea849c21fb3786d60dba0254acb375d016a62`，见[发布状态](release-status.md)），但本切片未产生公开发布、公开下载、安装或完整资格结论（另一用户会话安装过更早候选，本切片不复核），源冻结前断点没有新的实机资格证据；v1.0.1 的历史资格事实见[执行记录](codex/returns/STM32TK-101/execution.md)与[发布状态](release-status.md)。

当前源树已退役旧阶段计划、报告、资格工具及其专属测试。需要审计原文时使用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>`，不要重建旧机器本地路径。发行构建仍使用现行 `tools/release/build_0900_artifacts.py`、`tools/release/release_0900_policy.json`、许可证和当前测试。部署/IDE 另见 [Windows 前置核对](testing/windows-deployment-and-ide-preflight.md)。
