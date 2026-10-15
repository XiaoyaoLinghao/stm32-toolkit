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

## 第三场景补充：实时数据归属（主代理与独立契约审查 READY）

2026-10-16 静态链路核实：保存/删除组不会在 ACK 时同步改变 sampler；sampler 下一周期检查旧组 revision/存在性，必要时转 PAUSED_BLOCKED 并发布状态。现有实时表却按 selectedGroup（下次采样/编辑目标）投影，且 fresh 未验证运行组版本，存在表归属误显和 ACK 后短暂错误 fresh。该补充只改变 UI 的数据归属与时效呈现，不改变采样或组写规则。

- `selectedGroup` 仍仅表示编辑与下一次启动目标，不改其语义。允许扩展 `state/selectors.ts`：`activeGroup` 仅在 status.sampling.runId 非 null 时，按 status 的 groupId + groupRevision 精确匹配 groups。不得使用较新 revision 的 items 解释旧 run。
- 有 runId 时，实时表按 activeGroup.items 显示；仅在 live.runId 与 status.runId 相同时取 live.rows，否则显示该组空占位。运行组版本未在列表中核对时，仅当上述 runId 相同时保留现存 live.rows 的已接受旧值，否则为空。没有 runId 时，选中组只提供 emptyRow 预览，不借用上轮 live.rows。
- App 的唯一 fresh 同时要求 RUNNING、transport open、非 stale、不需状态刷新、activeGroup 匹配且 live.runId 与 status.runId 相同。LiveTable 与 StatusStrip 共用。组更新/删除 ACK 改变列表后立即不 fresh，保留已接受的最后时间；不等待后端下一周期状态事件。没有样本仍显示“尚未收到样本”。
- 在 live-main 的图表和数值表共同区域明确显示数据来源：当前/上次采样的 runId、groupId、revision；精确匹配时可加组名。无 run 时标明下次目标预览、尚未开始采样。版本不匹配说明“运行组版本未在列表中核对，仅展示上次样本”，不推断后端故障或宣布已删除。SamplingControls 的 activeGroupName 也仅取精确匹配组名称，不能用较新组名代替旧版本运行身份。
- UI04 的已选曲线和移除行为仍独立于编辑选组；不改 chartSeries/LiveChart/缓存/投影/缩放，不新增运行快照存储，不改后端、API、组编辑或采样控制规则。
- 新增 selector/App 回归覆盖：A 正运行时切换编辑 B/新建，表仍显示 A；组变新 revision 或删除 ACK 后立即非 fresh 且时间保留；无 run 或 live.runId 不匹配不复用旧值；旧版本无列表匹配时仅保留当前 run 已接受行。后端静态证据不冒充本轮物理测试。
