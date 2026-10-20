# Monitor ENTRY02 实施计划

Accepted base `095a81e48e5e0cf698b23da12cd02dbe71a3f9a1`，规范`2026-10-20-monitor-session-recovery-design.md`。分支codex/monitor-session-recovery，隔离树D:\codex-tmp\ma1020\impl。原8765由mp1020/review产品011c1b50运行，owned exec18912/PID27460；先保持服务。既有修复授权无需再审批，无远端/硬件/安装授权。

1. 主已重建当前base/服务/所有权并完成server/client只读审计。按默认系统浏览器、原终端Enter无停机交付、严格认证边界冻结设计。一个gpt-6-sol/max实现者负责完整垂直切片；不同agent独立完整差异审查。主不能实现产品。
2. 实现者先加RED用例：401与403被混淆、plain-root无重查、fragment不得cookie回退、原TTY Enter无法重开。实现最小终端适配及UI恢复；不引入新IPC、持久secret或公开mint。明确监听所有权/关闭取消、无凭据日志、单次重查/挂载与不重放写操作。
3. 所有temp/cache/TEMP/TMP/TMPDIR与测试输出归ma1020的唯一run根，显式Python/Node/source paths；复用已存在且匹配lock的依赖，不联网安装。跑相关Python CLI/auth/service与UI bootstrap/main tests、类型/lint、生成dist和dist一致性。浏览器场景可更新测试但真实运行DEFERRED；不读live受阻页面、secret文件、原工程或硬件。
4. 冻结产品/tests/docs/dist CodeHead，提交一份简短tracked implementation报告到docs/codex/returns/MONITOR-ENTRY-02/；报告记录完整base与报告提交之前CodeHead，不能写自身FinalHead或移动commit总数。报告单独提交，返回full FinalHead和clean状态，无push/PR等动作。
5. 主创建clean exact-head review树并重跑适用检查；独立reviewer查看完整base→FinalHead差异，重点认证边界、生命周期、输入监听、分类、fragment降级、并发、日志/凭据、生成dist。发现正确性问题同branch返修；同问题两轮不收敛则回设计。
6. 非deferred软件gate全过后主ACCEPTED，再核实旧服务身份、正常停止其owned会话、检查资源释放，按新clean root启动相同project/data/session/8765并记录service card。可向系统默认浏览器交付初始/Enter认证链接但不宣称浏览器已认证。记录浏览器验证暂缓、内置profile边界以及未完成的真实证据；不得以端口监听代表UI可用。清理未受hold且无诊断价值的run临时文件，遵守自动策略拒绝，不旁路。
