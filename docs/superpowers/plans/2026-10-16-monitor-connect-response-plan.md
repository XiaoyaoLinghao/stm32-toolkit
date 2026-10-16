# Monitor 连接响应与实时提示修复计划

依据同日[规范](../specs/2026-10-16-monitor-connect-response-design.md)与[标准测试流程](../../testing/standard-test-procedure.md)。Full accepted base `dcd0a21f605782929051c26773a01e18c02ff55f`。主代理制定并接受规范，沿用户既有连续本地开发授权执行，无新增远端授权。

1. 主代理记录源代码/分支、运行服务和用户数据边界，提交本规范/计划。当前本机服务先保留。所有本轮新临时输出放 `D:\codex-tmp\mcr1016`，各检查单独子目录；主代理为最终清理 owner。实现源码沿用 `D:\codex-tmp\mufin1015\impl` 干净隔离树。
2. 单一 gpt-6-sol/max 实现者修复规范内 API field、严格 guard、notice 去重及对应测试/生成资源，先以当前 Python 模型 fixture 证明旧校验失败，再修复。可复制现有 `D:\codex-tmp\muf1015\impl\tools\stm32-monitor\ui\node_modules` 至本轮独立目录，不安装依赖或修改借用源。TEMP/TMP/TMPDIR 一起绑定本轮专用子目录，PYTHONDONTWRITEBYTECODE=1。
3. 实现者运行当前 Python fixture 生成、connect/reconnect/client/contract/state/UI 定向回归；共享 fixture 会影响全 UI，因此允许一次完整 UI 单元回归、typecheck、lint、build 与 verify:dist。保存完整命令和退出码及日志。浏览器 e2e只可静态 typecheck，不启动浏览器；不操作运行中的服务、用户 DB 或探针。
4. 实现者提交产品及测试，记录完整 CodeHead；独立报告提交放 `docs/codex/returns/MONITOR-CONNECT-RESPONSE/implementation.md`，包含 accepted base、报告前 CodeHead、原因、证据、限制与可清理路径，不写报告自身 SHA、不自我接受。交回完整 final head，不推送。
5. 主代理在 `D:\codex-tmp\mcr1016\review` 创建精确 CodeHead 的干净 detached 审查树；主代理与独立 gpt-6-sol/max 审查者审阅 base→CodeHead 完整差异，核对 fixture 来源与生成资源。主代理重跑当前 Python fixture及关键契约/状态回归与 dist 校验，不重复发布矩阵。发现问题回同一实现者，最多两轮后重新审视设计。
6. 接受后主代理记录 verdict。以受控 Ctrl+C 关闭旧 8765 服务，核对所属 worker/lease 和监听退出；不终止无关进程、不删锁。新 accepted source 使用同 `D:\codex-tmp\md1016\p`、`D:\codex-tmp\md1016\data`、`monitor-demo-20261016` 经公开 `stm32_monitor open --port 8765` 启动。只核对本机进程/监听/源码身份，不把它描述成浏览器或实机验证。
7. 保留演示工程、数据库、历史样本及最小检查证据。清理本轮可归属测试临时目录、复制依赖等可再生成文件，核实绝对路径在批准根内且无 reparse；任何不能移除项如实记录。汇报修复、导出操作、测试和本地版本入口，不执行 push/PR/merge/tag/release。
