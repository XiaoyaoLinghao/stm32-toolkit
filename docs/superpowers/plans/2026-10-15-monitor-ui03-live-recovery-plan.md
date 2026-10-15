# MONITOR-UI-03 实施计划

日期：2026-10-15。状态：待用户同时批准本计划与同日 `monitor-ui03-live-recovery-design.md`。Accepted base：`261f49027dc1050b35720717a41efba687c72a32`。本计划不将“继续推进”解释为已批准新增的实时恢复状态契约。

## 有界交付与 ownership

一个 `gpt-6-sol/max` 实现 owner 交付三条场景，不递归委派，不自行验收。主代理负责规范、计划、集成决策、完整 diff 与最终验收；独立只读审查者可并行复核。没有主代理产品代码例外或远端操作授权。

实现范围限于 `tools/stm32-monitor/ui/src/api/live.ts`、`api/contract.ts` 中 LiveHandlers/OpenLive 内部接口、controller、state、app、TransportStatus/相关工作台提示、必要的中文词条/样式、对应 tests/e2e 源、现有流程生成的 ui_dist，以及用户指南 Monitor 段。API wire/codec、bootstrap/cookie/入口、Python、版本/依赖/lockfile、构建与发布配置均不改。

1. 读 applicable AGENTS、标准测试流程与现有接受断点。先以可控 socket 和延迟 GET 重现提前 open、断流无入口、heartbeat 清旧值与新缺口被旧 GET 清除的问题。
2. 按已冻结契约连通真实 onopen、连接代次、手动恢复/取消、同会话游标与访问阻断；处理连接状态和样本新鲜度，接入现有就地错误恢复，不增加自动策略。
3. 连通缺口状态刷新与 GET/live 竞态保护；验证 probe/sampling 写后刷新仍只读、不重放。保持分组/历史/导出与未提交草稿，更新用户指南，生成 dist。
4. 提交 Product CodeHead，再独立提交 implementation.md（只记录 base 与产品提交，不写报告自身 SHA）。主代理在独立干净 review 树完整审查 base→CodeHead，按风险复验；可纠正发现返原 owner，同一问题两轮不收敛则重审集成契约。

## 验证与证据

实现者使用已有 Windows Node/npm 与匹配依赖副本，不下载/安装。先运行受影响回归；共享 controller/reducer/adapter 变化触发完整 UI 单元、typecheck、typecheck:e2e、lint、build 和 verify:dist。必须覆盖：

- 构造不是 open；close-before-open、error+close 只结算一次、constructor 抛错、取消/关闭后的迟到事件、重复点击最多一个 socket。
- 恢复 GET 普通失败和原意图重试、认证失败的可见阻断；不发生探针/采样 POST；与在途 status/probe/sampling 的守卫及取消释放一致。
- 相同会话 afterEventId、不同会话拒绝复用、重放去重；恢复 GET 仅校验身份，离线 A→B→A 回归中不抢先发布无事件版本的 HTTP 状态；保留草稿/历史，仅真实 binding/run 转移按原规则重置数据。
- open/hello/heartbeat/status 不会把保留样本标新，匹配 sample 才恢复就绪；身份不匹配后 heartbeat 不清 stale。
- 缺口可见、GET 失败可重试、GET 期间新 gap/stateRevision 不被旧快照抹掉；写后刷新被更新状态淘汰时不重放写入。
- 中文连接/取消/刷新动作与非最新提示；UI02 普通错误和授权阻断无回归；生成资产与源码逐字节一致。

主代理在精确 CodeHead 独立树拥有关键 lifecycle/组件/状态回归、typecheck、verify:dist、完整差异与报告复核证据。只复跑受风险影响的集合，不跑全产品 release matrix。浏览器、axe、截图、视口与关闭重开 DEFERRED 给主代理；模拟网络事件不算 HTTP/WS 实测或物理采样资格。

## 环境、服务与清理

任务根 `D:\codex-tmp\mu31015`，实现 `/impl`，独立审查 `/review`，执行 `/run` 与 `/verify`。TEMP/TMP/TMPDIR/npm/测试缓存均绑定该根；主代理是 cleanup owner，保留最终证据和最小失败诊断，按精确校验路径清理自有输出，不重试其他任务已被策略拒绝的删除。

当前 8765 服务继续使用 UI02 `da7f1e7798ae9120f0eb130ec4286da12e9ef379`，不得修改运行源。只有 UI03 产品接受后才通过既有公共 serve 命令切换，核对进程/监听，过滤凭据；不借此访问受阻页面。原工作区脏状态保留。

采用 GL-001 的单一状态所有权、GL-004 的比例验证、GL-005 的故障分类和 EL-007/008 的短临时根与真实命令证据。本轮未派发实现、未执行产品测试、未改变服务或浏览器策略。
