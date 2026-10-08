# RC4 本地候选版交付说明

状态：候选版交付材料，`releaseAccepted=false`。包内版本号 `1.0.0`
不代表正式 1.0 验收通过。本文是冻结发行包的配套说明，不属于已接受的
13 项发行输出，不修改原包、校验和或验收结论。

## 固定版本与文件

- 产品及 RC4 源提交：`968cbb69b1f54b95a8fdc18a550481f6ff7c1268`。
- 本机候选目录：`D:\codex-tmp\v10b-0918\r10\rc4\build-a`，共 13 个文件。
- Windows 包：`stm32-toolkit-1.0.0-windows-x86_64.zip`。
  已接受的 SHA-256：`ba242f2d1d79b625e42ac32306a3f854fa50c15a5bcb64e944d80ef833f22cc6`。
- 配套源码：`stm32-toolkit-1.0.0-source.zip`。
  已接受的 SHA-256：`4038f6e6c1cf402c25c3050f0f8ee3db78003dcaddc510935a45396b95518c91`。
- 文件清单与其余哈希：同目录的 `release-manifest.json` 和 `CHECKSUMS.sha256`。
  本次只是整理既有证据，没有重新构建或执行包校验。
- 接收副本时应按外层 `CHECKSUMS.sha256` 核对实际文件。保留配套源码包、
  兼容说明、许可证和故障处理资料，不把单个 wheel 当成完整 Windows 发行包。

## 支持范围与部署入口

现有候选支持 Windows x86_64、CPython 3.12、Toolkit/Monitor/UI 1.0.0，
冻结依赖包括 PyOCD 0.45.1。完整边界和依赖见发行目录 `compatibility.md`。

部署前由接收者记录实际值，不套用原测试机目录：

| 项目 | 要求 |
| --- | --- |
| ToolkitRoot | Windows 包的实际解压目录，包含 `bin/setup-stm32-env.ps1` |
| DataRoot | 明确的长期保留目录，不能依赖会被清理的测试临时目录 |
| ProjectRoot | 本次操作的真实工程目录 |
| Bootstrap Python | 实际 CPython 3.12 解释器路径 |
| 包版本 | 上述源提交、实际包哈希与接收位置 |

Windows 包内入口为 `stm32-toolkit-1.0.0/bin/setup-stm32-env.ps1`。
按包内 `README_zh-CN.md` 和 `skills/setup-stm32-env/SKILL.md` 操作：
先执行只读 `Check`；确需建立 runtime 时才选择 `Bootstrap`，受支持旧版或
损坏 runtime 才选择 `Repair`；一次只执行一种修改，随后再次 `Check`。
该说明本身不授予安装、恢复、硬件或远程操作权限。

Repair 的隔离目录和失败恢复须按原指南保留；同版本不同来源、降级或未知
状态被拒绝时，保留原目录与证据并停止，不用手工覆盖来绕过拒绝。
IDE 使用前确认最终 runtime 中真实 `pyocd.exe`、目标工作区和版本配对。
完整步骤见包内及配套源码中的
`docs/testing/windows-deployment-and-ide-preflight.md`；故障入口为外层
`troubleshooting.md` 或包内 `release/troubleshooting.md`。

## 证据和限制随包保留

本机证据根为 `D:\codex-tmp\v10b-0918\r10\e`。下列路径相对于该根；
交付到其他机器时，应随交接保留这些记录或注明可访问的证据存放位置。

| 事项 | 现有证据与可用范围 |
| --- | --- |
| RC4 两次构建及 13 项输出 | `rc4/primary-admission.json`、`rc4/comparison.json` |
| RC4 安装/Check、Monitor 启动认证停止复用 | `rc4/primary-admission.json`；不扩大为未执行的 RC4 CLI/Ctrl+C 场景 |
| 0.9 升级、失败回滚、安全拒绝 | `release-matrix.json` 保留 RC2/RC3 原执行身份；RC2 回滚实验证明 promotion 后 state replacement 被锁拒绝时的恢复，不扩大为 state 已成功或部分替换后的恢复 |
| Windows 七项原生检查 | `python-final/windows-symlinks-rc4-current/primary-admission.json`，实际 7 PASS、0 skip |
| 实机历史验收 | `physical-release-reconciliation.json` 及 `python-final/physical-scope-reuse-a270.json`；按原场景复用，不宣称本次有 RC4 实机运行 |
| 部署文档适用性 | `rc4/deployment-docs-binding.json`，五份文档字节一致与引用目标复用，不等于新部署执行 |

历史 Monitor retention 操作曾出现 180 ms 超时，随后出现 `SQLITE_INTERRUPT`，
且512个值已实际删除；精确中断阶段和根因仍未知。操作开始后的
`MONITOR_STORAGE_BUSY` 不保证回滚或完成，应沿已有公开查询/恢复流程核对
实际结果。当前规定配置的性能检查已通过，但未解释该历史故障；不能概括为
所有取消和存储操作已无风险。细节保留在矩阵的 `historical-retention-timeout`
及 `retention-cancellation/release-disposition-final-review.md`。

U64 已接纳结果：Toolkit 整体 `12047/13592`（88.6330%），risk-core-v2
`11429/12918`（88.4734%）；Monitor 整体及核心 `2770/2956`（93.7077%）。
当前覆盖记录 SHA-256 为
`E232E8C2CE82F73109D05E3B6F3E811B56949CEC50553CECFD2C4B2112E6C5D2`。
Toolkit 两项 90% 与 Monitor 核心 95% 仍未满足，Monitor 整体 90% 已满足。
尚缺186、198（Toolkit缺口重叠）和39个分支；未执行的异常组合仍有不确定性。
现有资源释放证据不涵盖直接取消运行中的子进程/硬件会话及 stale-owner health
reclaim；历史回滚仅证明已记录的锁拒绝场景，不扩展为所有部分写入都可恢复。
本地候选交付不修改这些要求，也不代表批准发布例外。正式取舍见
[发行计划中的待审批方案](../superpowers/plans/2026-09-19-stm32tk-1.0-local-release.md)。

若用户明确批准方案中的三项一次性数值例外，并完成其余条款核对，最终说明
将记为“按用户批准的覆盖率例外验收”，而不是“原覆盖门槛全部通过”。例外仅
适用于本页固定RC4身份，不自动适用于后续产品、依赖或支持范围变更，也不授予
远程发布权限。当前仍为未批准、未完成1.0验收。
