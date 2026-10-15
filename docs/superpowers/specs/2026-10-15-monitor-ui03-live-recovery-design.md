# MONITOR-UI-03 实时连接与旧数据恢复

日期：2026-10-15。状态：用户已明确“批准 UI03 的规范和计划，开始实施”，并授权独立审查通过后更新 8765 服务；浏览器拦截及真实浏览器验证继续暂缓。

## 基线、责任和已核实问题

Accepted base：`261f49027dc1050b35720717a41efba687c72a32`，产品字节继承已接受 UI02 `da7f1e7798ae9120f0eb130ec4286da12e9ef379`，另含已接受用户指南。规范/计划/集成/独立验收由主对话代理负责；批准后一个 `gpt-6-sol/max` 实现者交付，另一只读审查者辅助主代理。分支 `codex/monitor-ui-03-live-recovery`，规划树 `D:\codex-tmp\mu31015\impl`，无 PR 或远端动作授权，无主代理产品实现例外。

只读审计确认：controller 在 socket 构造后立即标为 open，而 live adapter 没有 onopen；断流后没有重开入口；hello/heartbeat 会抹掉旧值的 stale 标志；needsStatusRefresh 没有 UI 消费者且任意 status.loaded 都清掉它。证据为上述 accepted base 的 `ui/src/controller.ts:232`、`api/live.ts:5`、`state/reducer.ts:28`、`app.tsx:60`（均相对 `tools/stm32-monitor/`）。这些是产品缺口，与浏览器访问策略分开处理。

## 三个用户场景

1. 初始工作台已读完但实时握手未完成：显示“正在连接实时数据”，不提前显示已连接；已有值仍标为非最新。socket 真正 open 后显示连接状态，只有接受匹配样本后才允许解除数据视图的非最新提示。
2. 实时连接断开：工作台、历史页、图表和编辑草稿保留，明确提示断流，提供“重新连接实时数据”。点击后先读取当前状态并核对同一会话，再建立一个实时订阅。普通失败就地显示并可重试完整恢复操作；认证失效仍按 UI02 阻断。不触发探针连接、采样启停或任何 POST。
3. 连接仍在但收到事件缺口/订阅丢弃提示：显示“需要刷新状态”和手动刷新入口。成功只确认本次读取覆盖的缺口；读取期间的新缺口或更新的 live 状态不能被旧 GET 擦掉。仍保留草稿和可用功能。

非目标：自动重连/轮询/backoff、后台常驻、页面重载、探针抢占/重置、写操作自动重放、认证/固定入口/后端协议变更、跨会话自动迁移、跨客户端观测组配置同步、逐行数据时效算法重做、浏览器/硬件/发布验收。

## 状态所有权与生命周期

- reducer 是可见连接状态、数据非最新标志、缺口代次和错误的唯一来源；controller 持有 socket 关闭句柄、单调连接代次和一次恢复意图。依赖保持组件 → controller → adapter/API；不增加第二个状态库。
- 连接 phase 为 idle / checking / connecting / open / disconnected。checking 是手动恢复的 GET 阶段，connecting 是已创建 socket 但未收到 onopen。连接状态与数据新鲜度独立；创建、open、hello、heartbeat、状态读取本身均不能把保留样本标为最新。断开、缺口、身份不匹配或 binding/run 改变使数据视图非最新；只有通过既有身份/序号守卫的匹配 sample 才能恢复样本就绪，且存在未确认缺口时仍保留非最新提示。保持现有单元格错误/时间语义，不把控制状态事件解释为新测量。
- 所有 socket callback 绑定连接代次；替换、取消、close 或 access.blocked 后，旧 onopen/message/error/close 都失效。每次最多一个 socket，清理幂等。连接失败和关闭释放句柄；constructor 抛错也进入可恢复的 disconnected。adapter 增加打开/失败通知并解绑所有 handler；wire schema 不变。
- checking/connecting 不接受第二次恢复。提供“取消连接”退出这两个阶段，释放 UI 忙碌并使迟到 GET/socket 回调失效；无自动超时或重试。关闭工作台和认证阻断使用同一代次淘汰规则。
- UI02 请求代次、不可变重试及全局 access.blocked 合同保留。实时恢复增加独立的内部 `live.reconnect` 请求 scope，普通 GET/连接失败归该 scope；通用重试重做 GET + 一次 socket 连接，不仅重试 GET。取消不产生错误、不留下可重试的旧操作。

## 状态读取、游标与竞态

- 手动恢复仅在初始化已成功、非阻断、非 checking/connecting 时可用；open 时不用该按钮，缺口走状态刷新。
- 开始恢复前必须没有在途 status、probe 或 sampling 操作；checking/connecting 期间也禁止新的 probe/sampling 写入和重复 status 刷新。UI 禁用与 controller 同步守卫一致；“取消连接”始终可用。目录、历史、导出和编辑草稿不因此整页锁住。
- 旧 socket 在恢复 GET 前退休，GET 使用原 same-origin cookie API。精确致命错误统一通过 UI02 的 access.blocked 处理，关闭实时资源；普通失败不卸载工作台。
- GET 成功必须与原 workspaceId/sessionId/logicalProjectId 相同。若服务身份变化，停止自动恢复，以会话已变化的中文说明进入原会话失效处理，要求重新打开工作台；不带旧游标进入新会话，不把旧草稿作用到新工程。
- 恢复前的 GET 只作权限与会话身份校验，不发布 status.loaded、不重基样本或丢弃计数。该 HTTP 响应没有 stateRevision，不能将它误作重放终点；连接后的状态仍由有序 replay 或 gap state 快照发布。仅重连本身不重置数据；离线期间真实发生的 binding/run 变化仍按重放顺序触发既有重置。
- 同一会话保留 lastAcceptedEventId，使用既有 afterEventId 重放；无有效游标则省略。保留现有 eventId 去重、binding/run 校验及服务器 gap 快照语义，不伪造补点。服务端 API 和事件 schema 不变。
- reducer 为缺口维护单调 gapRevision。每次 GET 捕获开始时的 gapRevision 和 live stateRevision；GET 完成时，只有相同代次才清 needsStatusRefresh。期间收到更高 stateRevision 时不得用旧 GET 覆盖更新的 live 状态；完成可解除该请求 pending，但保留刷新提示，等待下一次手动操作，不自动补发。
- 状态 GET 的保护规则集中应用于 controller 的状态读取路径，包括写后刷新；成功的写操作不能因读取快照被新状态淘汰而重新发送。gap 期间仍可接收有效数据，但不能由 heartbeat 或较旧 GET 提前清除非最新提示。
- 接受回归须包含离线 A→B→A 的状态重放：预检 GET 返回当前 A 不能先发布一个没有事件版本的快照，再让旧 B 回退覆盖；应仅由已有事件顺序决定 B、A 的合法转移。不得为维持图表外观而忽略真实绑定变化。

## 呈现与验收边界

沿用中文浅色专业工作台；顶栏/实时区显示明确的连接阶段、非最新数据和缺口提醒。“重新连接实时数据”与“重新连接探针”名称和入口分开，前者只做读取和订阅。普通失败进入现有操作提示区域，错误诊断不包含 token 或完整授权 URL。

本地验收通过可控 socket、controller、reducer 和组件测试证明生命周期及用户动作；不将模拟事件标为真实浏览器或硬件 PASS。真实浏览器截图、不同视口、无障碍、短地址关闭重开继续按用户指示暂缓；后续 owner 为主代理。
