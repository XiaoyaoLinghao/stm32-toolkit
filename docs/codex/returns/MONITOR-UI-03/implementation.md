# MONITOR-UI-03 实现回报

## 身份与交付

- Full accepted base：`261f49027dc1050b35720717a41efba687c72a32`。批准的规范与计划分别为 `docs/superpowers/specs/2026-10-15-monitor-ui03-live-recovery-design.md` 和 `docs/superpowers/plans/2026-10-15-monitor-ui03-live-recovery-plan.md`。
- 产品 CodeHead：`478ebe11f881f408f8e423609333139c20cd92b4`；分支 `codex/monitor-ui-03-live-recovery`；实现树 `D:\codex-tmp\mu31015\impl`。本报告在产品提交后单独提交，不记录报告提交自身的 SHA。
- 实现者负责批准范围内的 UI 源码、测试、生成资产和用户指南；主代理负责完整差异审查与独立验收。未执行 push、PR 变更、服务切换、浏览器访问、安装或硬件操作。

## 已连通行为

- 实时 socket 仅在实际 `onopen` 后标记已连接；构造错误、打开前关闭、错误后关闭、取消及工作台关闭都释放旧句柄，连接代次使旧回调失效。连接阶段为 idle、checking、connecting、open、disconnected；数据时效独立，只有通过原身份、分组、轮次和序号守卫的匹配样本才可解除非最新提示。
- 断流后“重新连接实时数据”先用原 cookie GET 核对初始 workspace/session/project，再按已接受的 `afterEventId` 建立一个订阅。该预检响应仅校验身份，不发布 `status.loaded` 或重基样本与丢弃计数；离线 A→B→A 只按重放事件顺序更新。普通 GET/socket 失败留在 `live.reconnect` 操作提示并重试完整 GET + 订阅；认证或会话变化阻断原工作台。检查和连接期间可取消，迟到的成功、普通失败和致命失败均无效。
- 手动状态刷新与写后刷新捕获开始时的 gapRevision 和 live stateRevision。新缺口或更新的状态使旧 GET 只结算 pending，不覆盖较新的 live 状态，也不提前清除刷新提示；成功的写入不会因后续状态读取被淘汰而重发。探针和采样写入及重复状态读取在检查/连接期间同时由 controller 和按钮阻止。中文顶栏和操作区提供连接、取消、非最新数据及缺口提示；草稿、历史和导出仍保留。
- API wire/codec、bootstrap、Python、依赖/lockfile、版本与构建配置未改。现有构建流程生成 `ui_dist` 并逐字节核验。

## 实现者验证

从 `D:\codex-tmp\mu31015\impl\tools\stm32-monitor\ui` 运行，使用已有 Node `v24.18.0` 和 lockfile 匹配的本地依赖副本，没有下载或安装。每项命令将 `TEMP`、`TMP`、`TMPDIR`、npm cache 与适用的 Vitest cache 设在表中对应的 `D:\codex-tmp\mu31015\run\final3\<check>` 子目录，并设 `npm_config_update_notifier=false`。原始 stdout/stderr 保留在下列日志；六项均在产品 CodeHead 所含源码、测试与生成资产上运行。

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `.\node_modules\.bin\vitest.cmd run` | exit 0；40 文件、351 测试通过 | `run/final3/test/test.log` |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.json --noEmit` | exit 0 | `run/final3/typecheck/typecheck.log` |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.e2e.json --noEmit` | exit 0 | `run/final3/typecheck-e2e/typecheck-e2e.log` |
| `.\node_modules\.bin\eslint.cmd src tests` | exit 0 | `run/final3/lint/lint.log` |
| `.\node_modules\.bin\vite.cmd build` | exit 0 | `run/final3/build/build.log` |
| `node scripts\verify-dist.mjs` | exit 0；7 个文件逐字节一致 | `run/final3/verify-dist/verify-dist.log` |

`ui03-live-recovery.test.ts`、`ui03-recovery-ui.test.tsx`、`reducer.test.ts` 和 `live-coverage.test.ts` 包含关键生命周期、身份、游标、取消、重试、缺口竞态、写后读取和中文操作回归。最初五项行为测试在旧产品上按预期失败；最终结果以上表 CodeHead 检查为准。完整 UI 测试输出带有 jsdom 的 `Not implemented: navigation to another Document` 提示，没有失败测试。Vite 的大于 500 kB chunk 建议没有阻断构建。

## 待独立验证与运行产物

主代理须在精确 CodeHead 的干净树完整审查 accepted-base→CodeHead 差异并执行计划中具名的独立关键复验；实现者不自行接受差异。浏览器页面、axe、截图、视口、关闭重开、真实 HTTP/WS 与物理采样证据尚未取得，分别按既定浏览器暂缓和外部环境边界处理，不能将模拟事件记为这些层的 PASS。8765 服务仅在独立接受后由主代理按现有入口切换。

本实现者仅创建 `D:\codex-tmp\mu31015\run` 下的 `red`、`dev`、`full1`、`focused2`、`focusedui`、`focused3`、`focused4`、`final`、`final2` 与 `final3` 子目录；`final3` 为有效最终日志，`final2/test/test.log` 保留了新测试在连接阶段错误调用状态刷新的测试设置缺陷及修正依据。主代理是清理 owner，可在独立审查证据核对后按精确路径移除不再需要的运行缓存和旧诊断；不得删除源码、用户文件或仍需诊断的最小证据。
