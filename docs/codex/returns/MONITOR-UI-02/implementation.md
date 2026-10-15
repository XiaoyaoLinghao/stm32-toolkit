# MONITOR-UI-02 实现回报

## 身份与边界

- Full accepted base：`fc9cdbafe696fa3dd95539259b11b8c000de7f2b`。冻结的规范和计划分别为 `docs/superpowers/specs/2026-10-15-monitor-ui02-local-recovery-design.md` 与 `docs/superpowers/plans/2026-10-15-monitor-ui02-local-recovery-plan.md`。
- 产品 CodeHead：`ef64459f6893bf31efcf37458b85e2aae68ddab0`；本地分支 `codex/monitor-ui-02-local-recovery`，实现树 `D:\codex-tmp\mu21015\impl`。本报告在产品提交后单独提交，不记录报告自身提交号。
- 本实现者负责 UI 代码、测试和下述验证；完整差异审查与验收归主代理。本轮没有远端操作、下载、浏览器/页面请求、实机操作、凭据或配置变更。

## 已连通行为

- `ui/src/controller.ts`、`ui/src/state/model.ts` 和 `ui/src/state/reducer.ts` 以 scope 和单调 requestId 管理 pending、失败、成功提交及关闭。旧成功和旧失败不能覆盖较新的请求或认证阻断；关闭、认证阻断及同 scope 新读取还会停止旧的分组分页链。初始 status、probes 和完整 groups 列表只在全部成功后作为一个快照发布，并且只开启一次实时连接。
- 普通操作失败留在中文浅色工作台。导航下方的 `OperationRegion` 显示各 scope 的错误、原因、诊断详情、关闭及适用恢复动作；初始读取失败始终保有重试入口。真实认证/访问拒绝仍走阻断路径。分组、探针、采样和导出组件呈现 pending 状态并限制重复提交；controller 也保护同家族写入及过期确认。
- 读取重试捕获原查询、游标、绑定、导出任务 ID 等输入。完整 `groups.list` 分页成功才替换列表，失败保留旧列表与编辑草稿；目录新查询失败继续展示上次成功的条目并标明其查询来源；历史页栈只在页面读取成功时变更。明确拒绝的写入只能经原内容摘要确认后重试；不确定写入仅用 GET 核对，导出创建结果未知时不重复 POST。成功写入后的刷新失败单独归属 GET，重试不会重发写入。
- 已确认的新增分组保存服务端返回的身份与 revision，即使后续列表刷新失败也不会被当作待创建草稿再次发送。导出提交范围由 reducer 与任务 ID 绑定；过期的状态响应不能覆盖新任务。导出状态和下载失败均释放忙碌并可按捕获的任务 ID 重试。
- 现有 UI 构建生成 `src/stm32_monitor/ui_dist/` 并通过逐字节核对。上述 `ui/` 与 `src/` 路径相对 `tools/stm32-monitor/`；未修改 API、codec、bootstrap、Python、package/lock 或构建配置。

## 验证证据

环境为 Windows PowerShell、已有 Node 24.18/npm 11。将已匹配 lockfile 的 `node_modules` 从上一接受树复制到本实现树，未安装或联网。所有 `TEMP`、`TMP`、`TMPDIR` 指向 `D:\codex-tmp\mu21015\run\temp`，npm cache 指向 `D:\codex-tmp\mu21015\run\npm-cache`，vitest cache 保存在本轮 run 根。命令均从 `D:\codex-tmp\mu21015\impl\tools\stm32-monitor\ui` 运行；以下原始 stdout/stderr 位于 `D:\codex-tmp\mu21015\run`，并在精确 CodeHead 上复验：

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `npm run typecheck` | exit 0 | `codehead-typecheck.log` |
| `npm run typecheck:e2e` | exit 0 | `codehead-typecheck-e2e.log` |
| `npm run lint` | exit 0 | `codehead-lint.log` |
| `npm run test` | exit 0；38 文件、320 测试通过 | `codehead-test.log` |
| `npm run build` | exit 0 | `codehead-build.log` |
| `npm run verify:dist` | exit 0；7 个产物文件逐字节一致 | `codehead-verify-dist.log` |

新增 `ui/tests/recovery.test.ts` 的 12 个行为测试覆盖初始化重试和致命优先级、分页关闭/抢占、旧响应、新分组与草稿、明确和不确定写入、历史前后翻页，以及导出任务与范围；`ui/tests/recovery-ui.test.tsx` 的 4 个组件测试覆盖多错误呈现、精确关闭/过期确认、初始化入口/核对忙碌和目录旧条目。已有相关测试按新的受保护提交动作调整。提交前的聚焦复验 `recovery-final.log` 为 3 文件、34 测试通过；其余开发中日志仅供诊断，以 CodeHead 日志为最终验证证据。

完整 UI 测试输出含 jsdom 的 `Not implemented: navigation to another Document` 提示，但没有失败测试；Vite 构建有超过 500 kB chunk 的建议，构建成功。这两项不是本轮新增的阻断。最终产品构建后工作树无未提交产品差异。

## 待后续所有者处理

浏览器交互、截图、axe、真实关闭重开和受阻页面诊断依照本轮授权继续暂缓，后续 owner 为主代理；本地组件测试不充当浏览器或视觉验收。后端、硬件与发布矩阵不在此切片重新归属。本实现者不自行接受产品差异。

主代理是清理 owner。独立审查不再需要后，可依据精确路径处理 `D:\codex-tmp\mu21015\impl\tools\stm32-monitor\ui\node_modules`、`D:\codex-tmp\mu21015\run\temp`、`npm-cache`、`vitest-cache` 及 run 根日志；在证据核对完成前保留 CodeHead 六项日志和必要失败诊断。没有删除其他任务的目录或共享缓存。

本实现者的全部运行输出均在 `D:\codex-tmp\mu21015\run`。除上表六份 CodeHead 日志外，诊断日志为 `final-build.log`、`final-lint.log`、`final-typecheck-e2e.log`、`final-typecheck.log`、`final-ui-test.log`、`final-verify-dist.log`、`focused-first.log`、`focused-second.log`、`lint.log`、`recovery-final.log`、`recovery-first.log`、`recovery-ui-first.log`、`typecheck-e2e.log`、`typecheck-eighth.log`、`typecheck-fifth.log`、`typecheck-first.log`、`typecheck-fourth.log`、`typecheck-ninth.log`、`typecheck-second.log`、`typecheck-seventh.log`、`typecheck-sixth.log`、`typecheck-third.log`、`ui-test.log`；同根下只有前述 `temp`、`npm-cache`、`vitest-cache` 三个运行目录。
