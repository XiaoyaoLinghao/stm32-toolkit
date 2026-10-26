# Windows 部署与 IDE 调试前置核对

本文件面向 Windows x86_64、CPython 3.12 发行包的部署。当前公开 Latest 是 [v1.3.2 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2)（发布于 2026-10-26）：其资产可用性、最终发行资格与限制以该 Release 页和[发布状态](../release-status.md)为准。本流程默认使用 v1.3.2，其标识、`runtime/1.3.2` 路径、资产清单与校验和取自该 Release 的 13 个已核验资产；最终安装与 VS Code 独立测试仍由用户负责、待完成。上一公开版本 [v1.3.1 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1) 与显式 legacy 路线 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) 各自按其页面核对。当前范围见[源码交付规范](../superpowers/specs/2026-10-21-monitor-v120-delivery-design.md)、[v1.3.1 集成设计](../superpowers/specs/2026-10-25-v131-integration-design.md)与 [v1.3.2 诊断设计](../superpowers/specs/2026-10-26-v132-diagnostics-design.md)，旧版资格事实见[v1.0.1 执行记录](../codex/returns/STM32TK-101/execution.md)。实际执行顺序、授权、留证和首错停止以[标准测试流程](standard-test-procedure.md)为准；常见工程错误见[用户指南](../user-guide.md)。软件安装或 loopback HTTP 检查不等于真实交互浏览器、IDE/探针验收。

## 固定发行与本机输入

先选定本次安装路线：默认的 **v1.3.2 Release**；[v1.3.1 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1)（上一公开版本）与 [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)（legacy）只能作为另行明确选择的路线，各自核对各自的版本。v1.3.2 路线从[其 Release 页面](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.2)取得同时列出 `stm32-toolkit-1.3.2-windows-x86_64.zip` 与 `CHECKSUMS.sha256` 的资产；下载前确认该页面确实列出这两个资产。显式提供的同版本本地构建只可作为补充来源，且必须附可核对的校验和、source commit 与包内 manifest。不得以旧版包或 GitHub 自动生成的源码归档代替；缺少任一必需资产或来源证据就停止。若改选 1.3.1 或 1.2.0，则按其各自的发行页面、文件名与校验和核对，不能把它作为其他版本的默认命令。依[README 的校验命令](../../README_zh-CN.md)核对所选包的 SHA256 后解压到全新、每版独立的 BundleRoot；若目录已存在，另选新目录，不覆盖或删除。ZIP 的 `stm32-toolkit-1.3.2/` ToolkitRoot 与外层 `release/` 在 BundleRoot 下并列；ToolkitRoot 内另有供 setup 使用的 `release/release-manifest.json`。先记录经过审查的完整 source commit、包内 manifest、bundle SHA256、CPython 版本，以及真实的 ToolkitRoot、长期 DataRoot、ProjectRoot。仅使用与该 source/manifest 匹配的完整离线 wheelhouse，不能混用另一版 setup、wheel 或状态文件。DataRoot 保留 runtime、工程身份、会话和证据，不用可清理的测试临时目录；移动机器或磁盘后重新核对路径和当前绑定，不能复制旧探针 selector、ticket、已消费 action 作为新会话状态。

发行构建所用的专用干净工作树应保证 checkout 与 `git archive` 的实际字节一致。若使用 LF 归档，在创建工作树前确定进程/工作树 Git 配置；仅一次 `git -c core.autocrlf=false worktree add` 不保证后续 builder 沿用。核对 `git ls-files --eol`，不改用户全局 Git 配置。构建 wheelhouse 须包含发行策略固定的 build backend（当前 setuptools 84.0.0、wheel 0.48.0），runtime wheels 本身不构成完整构建输入。现行工具是 `tools/release/build_0900_artifacts.py` 与 `tools/release/release_0900_policy.json`；文件名是历史延续，不表示应安装 0.9.0。二者当前绑定 1.3.2；构建前后必须按发布策略核对实际版本、资产名与校验和，而不是沿用 1.2.0 的文件名。

## runtime Check 在硬件和 handoff 之前

对已核验 bundle 使用 `bin/setup-stm32-env.ps1 -Mode Check`。`Check` 只读；`missing` 只在获准安装时进入 Bootstrap，`repairable`/`broken` 只在获准修复时进入 Repair。成功动作后再 `Check`。同版本不同 source/manifest 返回 source-conflict，记录过更高版本或未知状态按原拒绝处理；不要删除 `runtime-state.json`、降级或手修 EXE 绕过。

最终目录的验证包括：发行包 hash 与闭合 wheel 集、最终位置的 Toolkit/Monitor/PyOCD wheel、`pip check`、console launcher 绑定及版本。staging 内成功并非最终位置成功。任一已安装版本（默认 v1.3.2；显式选择的 v1.3.1 或 legacy v1.2.0 使用各自的 `runtime\<version>` 路径）的 `Check` 确认 healthy 后，可只读核对以下两个 PyOCD 入口；把路径换成实际 DataRoot 与所选版本，不访问板子（示例为 v1.3.2，1.3.1/1.2.0 分别换成 `runtime\1.3.1`、`runtime\1.2.0`，其余检查相同）：

```powershell
$runtimeRoot = 'C:\data\stm32-toolkit\runtime\1.3.2'
& "$runtimeRoot\Scripts\python.exe" -I -m pyocd --version
if ($LASTEXITCODE -ne 0) { throw 'PyOCD module failed' }
& "$runtimeRoot\Scripts\pyocd.exe" --version
if ($LASTEXITCODE -ne 0) { throw 'PyOCD executable failed' }
```

发行策略当前固定 PyOCD 0.45.1；最终 launcher 应报告与已验证模块一致的版本且绑定最终解释器。`import pyocd`、模块入口成功、文件存在或 Toolkit 版本成功，都不能单独证明 `pyocd.exe` 可供 IDE 使用。安装/Repair 失败时记录原状态与 rollback 证据；旧版 runtime 先隔离，既有事务可恢复分支按规则回滚，原工程及用户数据不改写。旧版回滚已验证范围见[发布状态](../release-status.md)，不能将该历史结果当作 v1.2.0 当前安装资格。

## IDE 配置离线核对

在不按 F5、不连接探针的条件下，打开本次真实 VS Code workspace，确认正在运行的 Code.exe、版本、profile、Cortex-Debug 扩展及其实际行为。旧适配经验限已验证的 Cortex-Debug 1.12.1 / PyOCD 0.45.1 版本对；profile 声明不是本机安装证明。版本不同就先核对配置兼容性，不能假定适配仍有效。

| 检查项 | 必须核对 |
| --- | --- |
| workspace/cwd | 本次工程绝对路径可解析，不能依赖可能为 undefined 的 workspace folder 回调。 |
| 配置与任务 | 手动 handoff 使用明确的 attach 配置。每个 `preLaunchTask`/`postDebugTask` 都有实际任务；无任务依赖的配置不应伪造一个任务。 |
| GDB/ELF | 工具链路径和本次 ELF、build ID、hash 与当前工程身份一致；不通过编辑旧 receipt 重新绑定。 |
| PyOCD | `serverpath` 指向通过最终 Check 的 `pyocd.exe`，不是旧 `pyocd-gdbserver.exe`。 |
| target/pack | 从真实器件与已安装 pack 离线核对 PyOCD target 支持、版本、来源；不把 Probe 租约目录当 target 注册表。 |
| probe/ticket | 只使用本次授权 handoff 的真实返回，不选旧机器 selector/raw ID，也不自动选第一个探针。 |

在上述版本对，Cortex-Debug 可能将 `boardId` 展开成 PyOCD 0.45.1 不接受的 `--board`。核对本次生成的 `cortexDebugLaunch.configuration` 是否给出绝对 cwd、`request=attach`、无 `boardId`、以及 `serverArgs=["--uid", <本次返回的原始boardId>, "--connect", "attach"]`。原始 handoff 返回值需另行完整保留；外置配置只是该版本对的适配，不改变 Toolkit 的 canonical 身份。

同一版本对的 GDB 就绪行可能为 `GDB server listening on port 50000`，而扩展旧默认只识别 `GDB server started at/on port`。确认生成配置的 `overrideGDBServerStartedRegex` 能匹配真实就绪行，且不会误匹配 STDIO 行。不要仅因扩展超时弹窗断言硬件故障；先保存完整服务命令、stdout/stderr、时序及退出码。也不要靠关闭就绪检测、改端口或延长超时掩盖配置失配。

## 授权交接与首错停止

标准流程先核对项目、固件、目标、Probe、session、当前 lease/ticket 归属和最后证实的目标状态；再按实际授权执行 begin → 原样使用本次配置 → attach/观察 → 正常 detach → 原 ticket end → 同绑定 Toolkit/MCP read。IDE 独占期间 Toolkit 不能抢读。flash/readback 成功只证明其原有编程契约，不代表目标已 running；观察、Fault 和显式控制各有不同前置，不能自动 reset/resume。

第一个非预期错误出现后记录原 code/details/cause、有效配置、命令、stdout/stderr、退出码、最后阶段与 lease/ticket 状态，并停止后续硬件。缺少原始输出是证据缺口，不能自动重连补日志。Monitor 历史清理在收到 `MONITOR_STORAGE_BUSY` 后也不能假定事务完全回滚；等待写入结束并通过正常历史查询核对实际数据，再决定下一动作。旧计划和报告已退出当前树，需要审计时用 `git show 694c825d29a55a53052a148efa4cc6720c315a04:<path>` 从 Git 历史读取。
