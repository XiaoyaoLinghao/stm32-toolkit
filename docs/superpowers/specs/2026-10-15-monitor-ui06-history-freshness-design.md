# MONITOR-UI-06 历史查询与采集时效规范

2026-10-16；主代理设计并审定，已通过独立契约审查。Full accepted base：`3ee0bc2180047b45bbf3d2dae2dd2deed4e46e6a`（UI05 已接受）。按用户整体本地完成授权实施，无需再次审批。主代理负责规范/计划/接受，单一 gpt-6-sol/max 实现者负责产品，独立 gpt-6-sol/max 审查者不实现产品；无 ownership override、无远端修改权限。

## 三条用户场景

1. 用户提交范围 A 后可继续编辑范围 B。A 返回时结果区明确属于 A，输入框仍保留 B。查询中按钮和翻页禁用，有查询中提示；同一界面事件连续点击不重复 GET。查询失败保留上次成功结果，并明确结果范围，不产生整页阻断。
2. 失败 A 的重试始终读取 A，包括其 cursor/filters，成功后正确推进页栈，不能改成后来输入的 B。B 仍可作为下一次新查询；分页只使用已成功查询范围。结果每条显示 UTC、观测项、值或读取错误及 runId/sequence/ordinal，来源可分辨。
3. 实时值显示采集时间。速率和延迟在尚无样本时显示“尚未收到样本”，暂停、断流或状态待核对时标明“上次样本”及 UTC 时间，不被误读为当前速率。不同 binding/run 重置后不显示上轮样本时间。

## 历史状态与并发

- `history.query/page/projection/cursorStack/nextCursor` 仍只保存成功应用的结果，GET pending/失败不修改；ExportPanel 继续只接收成功查询的时间范围，分页、在途请求和草稿不得提前影响导出。
- HistoryPanel 本地 start/end 是唯一可编辑草稿；上次同步范围只是比较基线。新的成功结果到来，仅当当前草稿仍等于上次同步值时跟随更新，否则原样保留用户草稿。无条件 useEffect 覆盖必须移除。失败查询的 retry 成功也使用同一规则；不能清掉更新草稿的验证提示。
- reducer 中为历史 GET 维护只读在途上下文 `{requestId, query, navigation}`，对应已有 pending.history。请求开始捕获克隆查询；新请求替换上下文，只有相同 requestId 的成功/失败/retire 才清理。controller 的当前请求/生命周期守卫继续存在，迟到请求不能清掉新在途状态或覆盖结果。retry 重新建立本次 id 的在途上下文，query 仍为失败时不可变快照。
- 界面同时展示“正在查询范围（UTC）”及“当前结果范围（UTC，起点包含/终点不含）”，有旧结果时说明查询期间仍显示上次成功结果；只有成功空页才说“该范围没有记录”，初次在途不能假称空结果。
- 查询、下一页、上一页共享组件同步 ref 锁，调用开始即占用，直到回调 Promise 结算才释放，配合 controller pending 的禁用状态。保留 controller 对显式新调用的 latest-wins 契约，不把它改成静默丢弃新查询；旧返回继续被过滤。草稿输入不锁定。
- 新查询从草稿构造范围，沿用当前 query 的其他筛选条件与 limit，上限 10000，并清 cursor；分页仅从已成功 query 和 cursorStack 派生。范围 UTC 毫秒输入转 bigint ns，验证 `0 <= start < end <= 9223372036854775807`；不把绝对 ns 转 Number，不改变 wire 或引入任意日期/时区猜测。
- 普通失败仍在 OperationRegion 就地呈现并提供 UI02 的原操作重试；其 summary 和在途范围可对应，不能用旧 HistoryPanel.failure 独立注入代替 App 的真实错误路径验证。

## 采集时效唯一来源

- 在 LiveState 增加 `lastSampleCapturedAtUtc: string | null`，只由成功通过 binding/group/run 守卫的样本写入其 batch.capturedAtUtc。emptyLive 为 null，binding/run 重置清空；断线、gap、hello、heartbeat、普通 status GET 不伪造更新时间。
- App 已有 fresh（RUNNING + transport open + 非 stale + 不需刷新）为唯一时效判断来源，LiveTable 和 StatusStrip 共用它。最后时间仅是已接受样本的采集时间，不用 Date.now/浏览器时钟推断新鲜度，不做超时策略。
- LiveTable 每行展示自己的 `capturedAtUtc` 并标 UTC，非 fresh 时保留既有旧值样式及说明。StatusStrip 无样本时 rate/latency 不冒充真实 0，有样本且非 fresh 显示“上次样本”；fresh 时显示当前值和采集时间。
- 丢弃计数保留既有累计/权威重基语义，单独标注，不将其与 rate/latency 混成一个样本快照。不改 sample/drop 算法、缓存 600/8、zoom 或 UI03 reconnect/gap 恢复规则。

## 范围和证据

允许 HistoryPanel、StatusStrip、LiveTable 的时间呈现；model/reducer/controller 的历史在途上下文和样本时刻字段；series.ts 仅维护该字段；app/zh/styles/必要展示 helper；相关 tests、确受影响 e2e 源、生成 ui_dist、指南历史/时效段和实施报告。不改 API/wire/codec/Python/导出行为/图表投影/组编辑规则/依赖/版本/构建配置。

浏览器拦截、真实视口/手势/关闭重开和硬件证据继续 DEFERRED。完成本片后进行本地集成、独立验收、服务切换和推送前清单，停止在任何远端修改之前。
