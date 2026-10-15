# MONITOR-UI-02 独立验收

结论：**ACCEPTED，本地 UI02 软件切片**。浏览器与视觉实测继续 **DEFERRED**；本结论不是发布或硬件验收。

## 身份与范围

- Accepted base：`fc9cdbafe696fa3dd95539259b11b8c000de7f2b`；继承的 UI01 产品为 `2af7f3c2f750669b5176503f61d3f14dd11cf8d3`。
- 最终产品 CodeHead：`da7f1e7798ae9120f0eb130ec4286da12e9ef379`；实现回报 head：`4762eb2ee28c495c310f2a2eacf6214772900eb9`。两者之间只有实现回报变更，已核对最终 334 项测试及代码身份。
- 规范、计划、集成、完整差异审查及验收：主对话代理。实现与实现测试：单一 `gpt-6-sol/max` 子代理；另一只读 `gpt-6-sol/max` 子代理独立审查。主代理没有产品代码实现例外。
- 分支 `codex/monitor-ui-02-local-recovery`，无 PR；没有 push、PR mutation、merge、tag 或 release 授权及执行。原始脏工作区未改动。
- 独立审查树 `D:\codex-tmp\mu21015\review`。主代理已完整阅读 accepted-base 到首轮候选的产品/测试/文档差异及之后修订；生成产物通过同源 rebuild 逐字节核对。

## 场景与审查发现

| 场景 | 本地行为与证据 |
| --- | --- |
| 普通操作拒绝 | 中文“操作提示”就地显示多个失败；工作台、选中页和草稿保留。写入重试确认原输入；探针/采样额外核对原目标。 |
| 读取失败 | 保留最后成功数据；按原查询/游标/任务 ID 重试。历史页栈只在成功后改变；目录页不重复追加。 |
| 写入后的刷新与不确定结果 | 确认写入成功后只重试 GET；响应不确定时核对状态，不自动重复 POST。返回的分组回执保持选中 ID 可解析。 |
| 初始化及认证 | 初始化一项普通失败立即可重试，成功才发布完整快照并启动 live；权限失效统一设置可见阻断并停止操作。 |

首轮 `ef64459f6893bf31efcf37458b85e2aae68ddab0` 的五项发现记录在 `D:\codex-tmp\mu21015\round1-review.md`：旧上下文重试无效果、同目录游标重复追加、探针/采样重试目标切换、初始化被另一挂起读取拖住、分组回执后选中 ID 不可解析。修订 `686888622163d05f8d0f1d477b7e9706c2eb0e7b` 关闭后四项，并退休旧普通失败。

第二轮进一步发现：reducer 退休 pending 后，controller 的迟到认证失效通过 `request.failed` 被丢弃，导致无提示的阻断。主代理在 `b5fb34ca9061db83399404b02bf31f25017a69e4` 重审状态所有权，明确 controller 验证会话观察者，致命错误独立通过 `access.blocked` 递送，普通错误仍受请求代次保护。最终候选按统一入口修正；目录、导出两条回归先重现失败，最终通过。主代理和独立审查者确认无未关闭产品发现。

## 最终验证

Windows / 现有 Node 24.18、npm 11；未安装依赖。主代理在最终 CodeHead 的干净独立树执行下列复验，前后 tracked/untracked 状态均干净：

| 主代理命令 | 结果 |
| --- | --- |
| `npm run test -- tests/recovery.test.ts tests/recovery-ui.test.tsx tests/app-errors.test.tsx tests/history-panel.test.tsx tests/export-panel.test.tsx tests/reducer.test.ts tests/catalog.test.ts tests/reducer-coverage.test.ts --cache=false` | exit 0，8 文件 / 85 项通过 |
| `npm run typecheck` | exit 0 |
| `npm run verify:dist` | exit 0，7 文件逐字节一致 |
| `git diff --check <accepted-base> <CodeHead>` | exit 0 |
| 保护路径与回报差异核对 | API/codec/bootstrap、Python、依赖/锁文件、构建配置及版本无变更；回报提交只修改文档 |

主代理命令、时间、完整输出及最终代码身份保存在 `D:\codex-tmp\mu21015\verify-accepted\results.json` 与同目录三个日志。实现者另外在最终产品字节执行两个 typecheck、lint、完整 UI（38 文件 / 334 项）、build、verify:dist，全部退出 0；六份证据是 `D:\codex-tmp\mu21015\run\round2-final-*.log`。主代理核对原始日志，不将实现者执行冒记为自己的执行。jsdom 导航提示和 Vite chunk 大小建议未导致测试/构建失败，不构成浏览器或性能验收。

## 证据边界

主代理先在 `ef64459f` 独立跑 61 项关键测试、typecheck、dist 核对；在 `68688862` 跑 83 项关键测试、typecheck、dist 核对，均退出 0。前述证据属于当时产品，不替代最终修订复验。

浏览器、截图、axe、真实关闭后短地址重新打开及拦截诊断继续 DEFERRED，后续 owner 为主代理。组件/控制器测试不算真实浏览器、物理探针或板卡 PASS。后端协议、API/codec/bootstrap、依赖/锁文件、版本及构建配置没有本轮变更。发布矩阵仍在后续发布层执行。

## 本地服务与清理

最终代码接受后，主代理通过旧受管执行会话停止 PID 19304，核对其退出及 8765 释放，再使用现有公共 `stm32_monitor serve --serve-ui --json` 从最终 CodeHead 的 review 树启动。启动摘要确认 `http://127.0.0.1:8765/`；OS 核对 PID 23916 在 127.0.0.1:8765 监听，受管执行会话 78460。运行源固定在最终产品 CodeHead，不为文档提交切换运行树。未获取页面、未手动删除锁/运行记录、未打印或落盘 token/accessUrl；无凭据记录见 `D:\codex-tmp\mu21015\service.json`。这是服务进程/监听证据，不能替代认证、页面交互或关闭重开验证。

主代理是临时产物清理 owner；所有本轮执行位于 `D:\codex-tmp\mu21015`。在停止验证后，校验全部删除目标位于任务根，再清理 54 个自有依赖副本、缓存、临时目录和中间日志路径，无失败；记录见 `cleanup.json`。源码、Git 对象、跟踪的 dist、运行中 service-temp、最终命令证据和两轮最小失败诊断均保留。历史候选的重复成功日志已不再需要并清理。没有删除用户项目、共享缓存或其他任务目录；此前任务已被策略拒绝的清理未重试。
