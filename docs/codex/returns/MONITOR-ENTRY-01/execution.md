# MONITOR-ENTRY-01 执行账本

- 日期：2026-10-15；模块/阶段：Monitor 固定入口，本地实现。
- Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`，用户已明确批准规范中此 UI01 本地基线；不自动改用旧工作区 HEAD 或远端 master。
- 规范、计划、集成与验收 owner：主对话代理；实现 owner：主代理直接派发的单一 `gpt-6-sol/max`；完整差异审查 owner：主对话代理，独立 reviewer 可辅助。
- 用户授权：2026-10-15 明确“批准这份规范和计划，开始实施固定入口”；包括关闭标签页后通过固定短地址、有效会话恢复，不要求保存或手动输入 token。
- 分支：`codex/monitor-entry-01-fixed-url`；PR：无；远端动作授权：无。无所有权例外，无硬件/发布授权。
- 实现树：`D:\codex-tmp\men1015\impl`，在完整 accepted base 验证 clean 后创建；review 树将在精确 CodeHead 返回后另建。
- Git 存储复用 `D:\codex-tmp\mui1015\store`，本次 ref/index/worktree 元数据与产品提交均在任务目录；原 Git 对象只读引用，原脏工作区不写入。
- 全部本轮临时/测试/缓存目录：`D:\codex-tmp\men1015`；cleanup owner：主对话代理。保留源代码、有效 fixtures、Git 与最小证据，只清理可归属的本轮输出。
- 实现文件 ownership：Monitor cli.py/models.py/runtime.py/service.py；UI bootstrap.ts/presentation/zh.ts；相应既有 Python/UI/e2e 测试、构建 ui_dist 与用户指南、implementation.md。auth.py、API schema、controller/reducer、依赖/CI/版本等不改。
- 主代理 ownership：本规范、计划、execution.md、review.md；不实现产品代码。单一产品写 owner，不递归委派。
- 已冻结：4 个场景、port 默认/显式校验、单一监听值、按实际端口命名 cookie、URL scrub 前严格分类、typed status 恢复、失效/错误语义、runtime 生命周期与不支持 reopen 的边界。
- 经验采用：GL-001/003/004（active-provisional，契约先行/独立审查/比例验证）；STM32TK-EL-007/008（active-provisional，TEMP/TMP/TMPDIR 同根/精确提交证据）。不将候选经验当作产品事实，无经验或 native memory 写入。
- 既有 ENVIRONMENT 边界：UI01 的 Python socketpair/loopback、Chromium 启动和浏览器本机访问授权问题。复用最小失败证据，不改全局策略、不重复已知阻塞或通过替代浏览器/代理绕过权限。可运行的非浏览器检查继续执行；服务/浏览器实测仍由主代理在获准可用环境补验。
