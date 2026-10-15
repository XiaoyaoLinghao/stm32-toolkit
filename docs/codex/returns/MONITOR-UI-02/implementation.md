# MONITOR-UI-02 实现回报

## 身份与边界

- Full accepted base：`fc9cdbafe696fa3dd95539259b11b8c000de7f2b`。冻结的规范和计划分别为 `docs/superpowers/specs/2026-10-15-monitor-ui02-local-recovery-design.md` 与 `docs/superpowers/plans/2026-10-15-monitor-ui02-local-recovery-plan.md`。
- 产品 CodeHead：`da7f1e7798ae9120f0eb130ec4286da12e9ef379`；本地分支 `codex/monitor-ui-02-local-recovery`，实现树 `D:\codex-tmp\mu21015\impl`。首轮候选 `ef64459f6893bf31efcf37458b85e2aae68ddab0` 按五项独立审查发现修订为 `686888622163d05f8d0f1d477b7e9706c2eb0e7b`；第二轮仅修正致命权限递送。主代理分别以 `33c78e65` 和 `b5fb34ca` 记录集成决策。本报告在最终产品提交后单独提交，不记录报告自身提交号。
- 本实现者负责 UI 代码、测试和下述验证；完整差异审查与验收归主代理。本轮没有远端操作、工具安装、浏览器/页面请求、实机操作、凭据或配置变更。

## 已连通行为

- `ui/src/controller.ts`、`ui/src/state/model.ts` 和 `ui/src/state/reducer.ts` 以 scope 和单调 requestId 管理 pending、失败、成功提交及关闭。旧成功和旧失败不能覆盖较新的请求或认证阻断；关闭、认证阻断及同 scope 新读取还会停止旧的分组分页链。初始 status、probes 和完整 groups 列表只在全部成功后作为一个快照发布，并且只开启一次实时连接；任一普通失败先到时立即结束可见等待并允许重试，同一最新尝试的迟到致命错误仍阻断，已被重试取代的旧尝试不再生效。
- 普通操作失败留在中文浅色工作台。导航下方的 `OperationRegion` 显示各 scope 的错误、原因、诊断详情、关闭及适用恢复动作；初始读取失败始终保有重试入口。真实认证/访问拒绝仍走阻断路径。分组、探针、采样和导出组件呈现 pending 状态并限制重复提交；controller 也保护同家族写入及过期确认。
- 读取重试捕获原查询、游标、绑定、导出任务 ID 等输入。完整 `groups.list` 分页成功才替换列表，失败保留旧列表与编辑草稿；目录新查询失败继续展示上次成功的条目并标明其查询来源，同一已接受页游标不能重复追加。目录绑定或当前导出任务改变时，旧状态读取的失败/pending 失效，迟到结果也不能重新建立旧失败；旧任务的下载仍可按原 ID 重试。历史页栈只在页面读取成功时变更。
- 明确拒绝的写入只能经原内容摘要确认后重试；探针和采样摘要包含原目标，并且重试前核对原 workspace、session、project、probe、binding epoch 以及适用的 group/run，目标改变即撤销旧重试且不发 POST。不确定写入仅用 GET 核对，导出创建结果未知时不重复 POST。成功写入后的刷新失败单独归属 GET，重试不会重发写入。
- controller 判断回调仍属于当前会话和请求后，精确致命权限 code 统一以 `access.blocked` 递送；它不依赖已可能撤销的 pending ID。普通 `request.failed` 仍经 scope/requestId 守卫。由此目录绑定或导出任务改变后，迟到的致命权限结果仍显示阻断并停止后续 API 调用，而迟到的普通失败继续被撤销。
- 已确认的分组服务端回执被写入已接受列表；新增分组即使后续列表刷新失败仍可由选中 ID 解析，不会被当作待创建草稿再次发送。用户在保存期间切换或编辑的草稿不被回执覆盖。导出提交范围由 reducer 与任务 ID 绑定；过期的状态响应不能覆盖新任务。导出状态和下载失败均释放忙碌并可按捕获的任务 ID 重试。
- 现有 UI 构建生成 `src/stm32_monitor/ui_dist/` 并通过逐字节核对。上述 `ui/` 与 `src/` 路径相对 `tools/stm32-monitor/`；未修改 API、codec、bootstrap、Python、package/lock 或构建配置。

## 验证证据

环境为 Windows PowerShell、已有 Node 24.18/npm 11。将已匹配 lockfile 的 `node_modules` 从上一接受树复制到本实现树，未安装依赖，也未执行页面访问。所有 `TEMP`、`TMP`、`TMPDIR` 指向 `D:\codex-tmp\mu21015\run\temp`，npm cache 指向 `D:\codex-tmp\mu21015\run\npm-cache`，vitest cache 保存在本轮 run 根。命令均从 `D:\codex-tmp\mu21015\impl\tools\stm32-monitor\ui` 运行；以下原始 stdout/stderr 位于 `D:\codex-tmp\mu21015\run`，并在修订产品 CodeHead 的同一产品字节上验证：

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `npm run typecheck` | exit 0 | `round2-final-typecheck.log` |
| `npm run typecheck:e2e` | exit 0 | `round2-final-typecheck-e2e.log` |
| `npm run lint` | exit 0 | `round2-final-lint.log` |
| `npm run test` | exit 0；38 文件、334 测试通过 | `round2-final-test.log` |
| `npm run build` | exit 0 | `round2-final-build.log` |
| `npm run verify:dist` | exit 0；7 个产物文件逐字节一致 | `round2-final-verify-dist.log` |

`ui/tests/recovery.test.ts` 的 25 个行为测试覆盖初始化重试/迟到致命错误、分组分页与权威回执、原写入输入及目标安全、历史翻页、目录失效/重试/延迟状态提交、导出任务范围与下载；其中新增的两项分别重现目录、导出状态在 pending 被上下文变化撤销后收到致命错误。`ui/tests/recovery-ui.test.tsx` 的 4 个组件测试覆盖多错误呈现、精确关闭/过期确认、初始化入口/核对忙碌和目录旧条目。`reducer.test.ts` 对变量和寄存器两类目录验证同一游标只接受一次。第一轮 `round1-red.log` 显示 10 项预期失败，`round1-focused-third.log` 为 4 文件、55 测试通过；第二轮 `round2-red.log` 显示两项预期失败，`round2-focused.log` 为 3 文件、56 测试通过。此前候选的 `codehead-*.log` 与 `round1-final-*.log` 只归属当时版本，不能代替最终 CodeHead 的复验。

完整 UI 测试输出含 jsdom 的 `Not implemented: navigation to another Document` 提示，但没有失败测试；Vite 构建有超过 500 kB chunk 的建议，构建成功。这两项不是本轮新增的阻断。最终产品构建后工作树无未提交产品差异。

## 待后续所有者处理

浏览器交互、截图、axe、真实关闭重开和受阻页面诊断依照本轮授权继续暂缓，后续 owner 为主代理；本地组件测试不充当浏览器或视觉验收。后端、硬件与发布矩阵不在此切片重新归属。本实现者不自行接受产品差异。

主代理是清理 owner。独立审查不再需要后，可依据精确路径处理 `D:\codex-tmp\mu21015\impl\tools\stm32-monitor\ui\node_modules`、`D:\codex-tmp\mu21015\run\temp`、`npm-cache`、`vitest-cache` 及 run 根日志；在证据核对完成前保留修订 CodeHead 六项日志和必要失败诊断。没有删除其他任务的目录或共享缓存。

本实现者的全部运行输出均在 `D:\codex-tmp\mu21015\run`。除上表六份最终 CodeHead 日志外，第二轮诊断为 `round2-red.log`、`round2-focused.log`、`round2-typecheck.log`。首轮候选证据为 `codehead-build.log`、`codehead-lint.log`、`codehead-test.log`、`codehead-typecheck-e2e.log`、`codehead-typecheck.log`、`codehead-verify-dist.log`；第一轮修订证据为 `round1-final-build.log`、`round1-final-lint.log`、`round1-final-test.log`、`round1-final-typecheck-e2e.log`、`round1-final-typecheck.log`、`round1-final-verify-dist.log`。第一轮诊断为 `round1-red.log`、`round1-focused-first.log`、`round1-focused-second.log`、`round1-focused-third.log`、`round1-lint-first.log`、`round1-typecheck-e2e.log`、`round1-typecheck-first.log`、`round1-typecheck-second.log`、`round1-typecheck-third.log`。更早诊断为 `final-build.log`、`final-lint.log`、`final-typecheck-e2e.log`、`final-typecheck.log`、`final-ui-test.log`、`final-verify-dist.log`、`focused-first.log`、`focused-second.log`、`lint.log`、`recovery-final.log`、`recovery-first.log`、`recovery-ui-first.log`、`typecheck-e2e.log`、`typecheck-eighth.log`、`typecheck-fifth.log`、`typecheck-first.log`、`typecheck-fourth.log`、`typecheck-ninth.log`、`typecheck-second.log`、`typecheck-seventh.log`、`typecheck-sixth.log`、`typecheck-third.log`、`ui-test.log`；同根下只有前述 `temp`、`npm-cache`、`vitest-cache` 三个运行目录。
