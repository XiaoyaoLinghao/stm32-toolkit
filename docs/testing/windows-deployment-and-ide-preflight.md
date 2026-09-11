# Windows 部署与 IDE 调试前置核对

适用范围：Windows x86_64、CPython 3.12、Toolkit/Monitor 0.9.0、发行策略固定的 PyOCD 0.45.1。IDE 适配经验仅验证到 Cortex-Debug 1.12.1。本文件用于部署方案和执行卡，测试顺序、授权及停止规则以 [标准测试流程](standard-test-procedure.md) 为准。软件安装成功不等于 T9/T10/VS10-A 验收完成。

## 部署者必须固定的输入

记录来源 commit、bundle/manifest SHA256、bootstrap Python 版本，以及本机真实的 ToolkitRoot、DataRoot、ProjectRoot。从包含启动器修正的已审查 commit 构建并分发 bundle；旧 bundle 中的 setup 不会因为仓库更新而自动修复。不要混用新脚本、另一来源 manifest 和另一版产品 wheel。

发布构建还须固定两个已实际遇到的环境条件：打包隔离 checkout 的 `core.autocrlf=false`、`core.eol=lf`，避免 Git archive 的字节转换破坏确定性；构建 wheelhouse 包含策略固定的构建后端（当前 setuptools 84.0.0、wheel 0.48.0），不能把面向用户安装的 runtime wheel 集当成完整构建 wheelhouse。这两项来自已保存的 candidate-preparation 记录，修正的是构建环境，不应更改产品代码。不要因此修改使用者的全局 Git 配置。

DataRoot 必须是长期保留的数据位置；runtime、项目身份、会话及烧录证据不能放入允许随意清理的临时目录。仅一次验证的 stdout/stderr、pytest basetemp 等使用独立且可归属的临时目录。迁移机器或磁盘后重新核对实际路径和 workspace/probe/固件绑定；不复制旧机器的 raw probe ID、ticket、已消费 action 或旧临时目录作为默认配置。

统一使用现有 `bin/setup-stm32-env.ps1`：先 Check；缺失 runtime 才使用获准的 Bootstrap，损坏 runtime 才使用获准的 Repair。同版本 source-conflict、较高版本记录或未知状态按现有契约停止，不删除 runtime-state 绕过限制。升级/重新发布需遵守发行版本契约。

## 最终目录验证，先于硬件和 handoff

1. 校验 bundle 的完整性及闭合 wheel 集。staging 内安装成功只是中间状态。
2. runtime 移至最终路径后，必须用最终 Python 从已验证的 Toolkit、Monitor、PyOCD wheel 重建对应 console launcher。先检查绑定，再运行版本入口，最后才允许写入 healthy runtime state；失败沿用 rollback。
3. Check 必须覆盖实际的 `Scripts/pyocd.exe`。`import pyocd`、`python -m pyocd --version`、文件存在、pip check 或 Toolkit 版本成功，均不能替代它。最终启动器缺失、残留 staging 绑定、退出非零或版本不符，判 broken 并停止 IDE 准备。

下面是最终入口的人工离线核对示例。先把占位路径替换成已确认的本机路径；只查询版本，不枚举或连接板子：

```powershell
$runtimeRoot = 'D:\STM32ToolkitData\runtime\0.9.0'
& "$runtimeRoot\Scripts\python.exe" -I -m pyocd --version
if ($LASTEXITCODE -ne 0) { throw 'PyOCD module failed' }
& "$runtimeRoot\Scripts\pyocd.exe" --version
if ($LASTEXITCODE -ne 0) { throw 'PyOCD executable failed' }
```

两者应与发行 manifest 的 PyOCD 版本一致。安装器还负责最终解释器绑定检查；上面两条命令不替代完整 Check。不要手改 EXE、重建已删除的 staging 路径或改用 PATH 上未经核对的 PyOCD。

Bootstrap/Repair 的最终化要求精确发行 pin。对已有 runtime，Check 保留既有 `>=0.45.1,<0.46` 模块版本范围，并要求启动器报告与已验证模块相同的版本；它不是把所有已安装环境强制改为 0.45.1，也不会自动改装依赖。

## IDE 就绪后，才交出探针

先在不按 F5 的情况下打开实际 workspace，核对当前窗口所属 Code.exe、版本、用户 profile 和已激活的 Cortex-Debug。Start-Process 返回、exe 文件存在或另一安装的扩展清单均不证明目标 IDE 已就绪；更新锁或启动退出必须先解决。

逐项核对实际展开后的配置：

| 项目 | 部署要求 |
| --- | --- |
| cwd | workspace 级配置显式使用实际工程绝对路径；不能假设 WorkspaceFolder 回调始终存在 |
| 调试入口 | T9 使用命名明确的 `request=attach` 配置；不误选含烧录/构建任务的 launch 配置 |
| tasks | 每个 preLaunchTask/postDebugTask 都须解析到实际任务；手动交接的 T9 配置没有这些字段，不要求用户忽略缺任务警告 |
| GDB/ELF | 核对绝对 GDB 路径、实际 ELF 及其 build/哈希绑定；不能借更改工程配置破坏验收身份 |
| PyOCD | serverpath 指向已通过最终入口检查的 pyocd.exe；不是 pyocd-gdbserver.exe |
| pack | 从实际 pack 离线确认目标支持，记录版本及来源；已安装 3.1.1 不等于 manifest 声明的 2.17.1 |
| 探针选择 | 只能来自本次授权 handoff 的真实返回；不使用旧机器 selector/raw ID，不自动挑第一个探针 |

Cortex-Debug 1.12.1 会把 boardId 转为旧 `--board`，PyOCD 0.45.1 的主 CLI 不接受它；旧 pyocd-gdbserver.exe 又不接受扩展生成的 `gdbserver` 子命令。本次受限适配是在外置配置中省略 boardId，设置 `serverArgs=["--uid", <本次返回的原始boardId>, "--connect", "attach"]`，并单独完整保留原始 handoff 返回值。它不代表所有扩展版本通用，更不代表产品原始生成配置的兼容缺口已经修复。离线验证实际扩展生成的参数后才能进入获准的 IDE 步骤。

同一版本对还存在**就绪日志匹配差异**：扩展默认匹配 `/GDB server started (at|on) port/`，实际 PyOCD 输出 `GDB server listening on port 50000`。服务虽然已监听，扩展仍可能等到 10 秒超时后主动终止它。外置配置使用扩展已有字段 `overrideGDBServerStartedRegex="GDB server (?:started (?:at|on)|listening on) port [0-9]+"`；离线验证新旧 GDB 就绪行均匹配、STDIO 就绪行不匹配。不要延长超时、改端口、关闭就绪检测或因终端关闭就断言板子故障。该适配仍需独立审查及单独授权的真实 IDE 验证。

## 本次故障资料及后续方案要求

生成配置修正候选及验证范围见 [T9 兼容修正计划](../superpowers/plans/2026-09-11-stm32tk-t9-generated-ide-compatibility.md)。新的 `cortexDebugLaunch.configuration` 含绝对 cwd、UID/attach 参数和兼容就绪正则，launch 无 boardId；原 canonical cortexDebug/内部 companion 身份数据不变。先核对部署 source、新字段 schemaVersion=1 和 profile 声明的 Cortex-Debug 1.12.1/PyOCD 0.45.1 与实际环境一致；缺失或不同则停止，不能把 profile 当作已检测事实或自行套用于未知版本。此修正不自动发现 GDB/pack/IDE 路径，不生成额外任务，也不代表尚未运行的真实 IDE 验收已通过。

Windows 打包还须核对专用工作树与 `git archive` 的实际换行字节一致；仅设置归档 LF 而沿用已有 CRLF 工作树会触发 wheel/source binding 拒绝。应在创建干净打包工作树前设置该进程的 Git LF 参数，不改共享配置。证据 JSON 一律显式 UTF-8 读取；全新 DataRoot 的 session 目录尚不存在时验证其缺省状态，不直接调用要求父目录存在的 `_read_state`。这类离线检查失败应先修正检查前提，不能被计作硬件失败或要求重连。

已部署 worker 修正及一次 CLI/MCP 实机等价结果见 [交付记录](../codex/returns/2026-09-11-stm32tk-t9-worker-stdin-delivery.md)。新候选启动/清理已通过，原始 IDE 配置兼容缺口仍在，不应要求后来部署者自行猜测适配参数。

Windows MCP 前置还须覆盖真实 stdio 会话中的 worker 启动/关闭，而不只是 initialize/list_tools：09 的工具清单成功，但 Windows spawn 子进程沿用父 MCP stdin 后在 ready 握手超时。隔离 child 标准输入的离线重放已证明纠正方向；实际发行是否包含并通过该修复，以候选源码及对应测试证据为准。不能全局替换父 stdio/WinAPI，也不能把 worker-only 离线检查称为实机读取 PASS。见 [修正计划与证据](../superpowers/plans/2026-09-11-stm32tk-mcp-worker-stdin-repair.md)。

开发候选版本号相同但 source/manifest 不同时，保留原 DataRoot 的 source-conflict 拒绝。若本次明确使用独立候选安装，应在新的长期 D 盘 DataRoot 执行 Check/Bootstrap；不要复制旧 runtime-state、活动或已消费的 ticket/lease/action 来制造连续状态。相同工程/固件的历史证据可按身份引用，新环境下 CLI/MCP 等价应由同候选的有界检查补齐。

| 观察到的错误 | 已证实的信息 / 证据限度 | 应进入部署验收的检查 |
| --- | --- | --- |
| GDB Server Quit | 最终 PyOCD EXE 内嵌已删除的 staging Python；EXE --version exit 1、最终 Python 模块入口 exit 0。原 IDE 子进程 stderr/完整时序尚缺，不能仅凭弹窗推断硬件阶段 | 真实最终启动器绑定与版本；安装/Repair 的最终化、失败 rollback、只读 Check 回归 |
| undefined reading uri | 实际 Cortex-Debug provider 表达式在缺 cwd、folder undefined 时离线复现；没有恢复原弹窗堆栈 | workspace 级绝对 cwd 和配置解析 |
| 找不到 STM32 Toolkit 任务 | 工程 launch 引用了 tasks.json 不包含的 handoff 任务；后续日志证实用户已选中无该任务依赖的 T9 配置 | 实际选中的配置、任务引用闭合，不用“仍然调试”跳过 |
| IDE 启动未成功 | 请求启动的实例因更新锁退出；实际使用的是另一安装 | 当前窗口/进程/日志证明就绪，不以进程派发成功替代 |
| 旧 PyOCD 参数不兼容 | 当前扩展控制器生成 --board；当前 CLI parser 拒绝。兼容适配仅适用于已核对的版本对 | 扩展、服务命令、pack、目标四者一致，先做离线参数检查 |
| 已监听后 GDB Server 关闭 | 用户终端已证明目标发现和 GDB listen；实际扩展就绪正则不匹配 listening 文案，源码超时会关闭服务；现场完整 timeout/kill DAP 记录尚缺 | 实际服务输出与扩展 ready 正则一致，不能只验证 CLI 参数和启动器版本 |

原始证据及本机路径在 [T9 执行记录](../codex/returns/2026-09-11-stm32tk-1001-t9-ide-attempt-06.md)，启动器修复范围见 [修复计划](../superpowers/plans/2026-09-11-stm32tk-runtime-pyocd-launcher-repair.md)。后续发行方案应引用本文件，并记录该版本已通过哪些检查、哪些兼容项仍有限制；不能仅在聊天中保留这些信息。

打包与既有部署证据见 [软件集成与部署记录](../codex/returns/2026-09-11-stm32tk-1001-t9-t10-local-delivery.md) 引用的 `candidate-preparation-summary.json`。旧记录中的 publicLauncherVersions PASS 当时仅覆盖 Toolkit/Monitor，不能追认其已覆盖 PyOCD。

出现首个非预期错误后保存有效配置、服务命令、stdout/stderr、退出码、最后阶段和 lease/ticket 状态，停止后续硬件。无原始输出时明确证据缺口，不自动重新连接补日志；IDE 独占期间不能让 Toolkit 抢读。现有 Target、历史采样 PASS 按原绑定保留，不被部署报告替代或重写。
