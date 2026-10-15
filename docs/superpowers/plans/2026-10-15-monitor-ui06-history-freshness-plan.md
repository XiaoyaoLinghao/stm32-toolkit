# MONITOR-UI-06 实施计划

Full accepted base：`3ee0bc2180047b45bbf3d2dae2dd2deed4e46e6a`，2026-10-16 主代理已审定实施，分支 `codex/monitor-ui-06-history-freshness`，执行根 `D:\codex-tmp\mu61015`。单一 gpt-6-sol/max 实现者、独立只读审查者，主代理独占规范/集成/完整差异审查/接受。用户已授权，无需后续审批，无远端权限。

1. 先红回归：慢 A 查询期间编辑 B，A 成功/失败重试成功后 B 不丢；同事件连点和查询/翻页互斥；旧结果范围与在途范围分明；失败 cursor 重试仅成功推进栈；迟到旧结果不能清新 pending。
2. 实现历史只读在途元数据及组件草稿同步/提交锁，显示 UTC 半开范围和 run/sequence/ordinal；保留 API、export 已接受范围和 UI02 error 路径。
3. 通过既有样本接受路径维护最后采集时间；覆盖未有样本、样本后断流/暂停/gap、heartbeat/status 不改时间、binding/run reset、被拒绝样本不更新时间。状态条复用 App fresh，累计 drop 逻辑不变。
4. 实现者跑新增 + history-panel/export-panel/recovery/controller/reducer/series/live-table/presentation 受影响回归，然后两个 typecheck、lint、完整 UI unit、build、verify:dist（共享 controller/reducer 的明确风险）。不运行无关 release/hardware/browser 矩阵。
5. 固定 CodeHead，单独实施报告。主代理独立干净树完整 base→CodeHead 审查，定向历史/时效/恢复检查、typecheck、verify:dist；并行只读审查。问题返回原实现者，同问题两轮不收敛重审设计。

全部 TEMP/TMP/TMPDIR、缓存/证据在本片短根；主代理清理自有运行产物并保留最小最终证据。接受需三场景闭合、全部非 deferred 检查通过及独立完整差异审查无未闭合问题。集成后统一更新 8765，不推送 GitHub。

工作树：D:\codex-tmp\mu61015\impl；独立审查树：D:\codex-tmp\mu61015\review。实现证据 owner 为实现者；精确 CodeHead 独立检查/完整 diff/接受 owner 为主代理，另一只读审查者复审。环境为本机 Windows PowerShell、既有 Node/npm 与锁文件匹配依赖；不安装，不启动浏览器，不改 8765，报告放 MONITOR-UI-06/implementation.md。
