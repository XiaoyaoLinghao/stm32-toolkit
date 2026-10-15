# MONITOR-UI-03 执行账本

- 模块/阶段：Monitor UI03 实时连接恢复，本地实现。用户明确批准规范/计划及独立审查后的 8765 服务切换；浏览器拦截与真实浏览器验证暂缓。
- Accepted base：`261f49027dc1050b35720717a41efba687c72a32`，产品继承 UI02 `da7f1e7798ae9120f0eb130ec4286da12e9ef379`。规范审查已在 `9748df98e108af32291ac69b390ec8fabf36ea8f` 关闭预检 GET 与 replay 所有权歧义。
- 主对话代理拥有规范、计划、集成、风险、完整差异审查及接受；一个 `gpt-6-sol/max` 实现 owner 拥有批准范围产品/测试/指南和 implementation.md；独立只读 reviewer 辅助。主代理没有产品实现例外；子代理不得递归派工或自验收。
- 分支 `codex/monitor-ui-03-live-recovery`；无 PR，远端动作授权为空。没有 push/PR mutation/merge/tag/release、安装或硬件授权。
- 实现树 `D:\codex-tmp\mu31015\impl` 在派工前 clean；独立审查树按精确 CodeHead 建于 `/review`。原始 `D:\workspace\stm32-toolkit` 的未提交用户状态保留，不作为产品源。
- 当前运行源为 `D:\codex-tmp\mu21015\review` 的 UI02 Product CodeHead；已知受管会话 78460、PID 23916、127.0.0.1:8765。切换前核对实际进程/端口，停止已知旧会话、确认释放，再以公共 serve 启动新接受源；不手删锁/运行记录，不输出 token/accessUrl。
- 当前 shell 为 PowerShell 7.6.6，Node 位于既有 Program Files 安装，Python 3.12 位于既有用户安装。仅复用锁文件匹配的本地依赖副本，不下载。
- 执行根仅 `D:\codex-tmp\mu31015`；run/verify 和全部 TEMP/TMP/TMPDIR/npm/测试缓存归此根。主代理为 cleanup owner，保留源码、有效 fixtures、最终检查/最小失败证据及运行服务所需数据；已被策略拒绝的其他任务删除不重试。
- 已回顾标准测试流程、UI02 接受证据与适用经验 GL-001/004/005、EL-007/008；本切片按影响面执行 UI 矩阵与独立关键复验，不重复无关后端、发布或硬件矩阵。产品、环境与报告失败分开归类。
