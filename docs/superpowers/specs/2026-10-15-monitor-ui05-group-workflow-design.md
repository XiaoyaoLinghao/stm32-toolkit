# MONITOR-UI-05 观测组编辑与冲突恢复规范

2026-10-15 设计，2026-10-16 主代理审定实施。Full accepted base：`acf6953221f87b0e7951e5c0db4d9a57a381313e`（已接受 UI04，产品 `19acd9bd9f944f4072490e7571563d2593f59eb3`）。当前行为审计来源为 `d1d9c36ba1b1a695ab68d6969506725dfbe360aa`，UI04 未改变组流程。独立契约审查已闭合孤立稿保存防线和同 revision 名称冲突恢复两项决策，结论 READY；按用户整体本地授权直接实施，无需再次审批。

## 四条用户场景

1. 修改观测组后点击同一组不丢失草稿；切到其他组或新建时，就地选择“继续编辑”或“放弃修改并继续”。未确认前原稿和采样选组不变。保存期间不能启动第二个组操作或改变编辑目标。
2. 新建稿明确显示“未保存”，不能被误当作已保存采样目标。正常保存后选中返回的组和 revision；删除当前组后不能继续向已删除 ID 保存。运行中的采样仍按服务端 run/group 身份显示，停止/暂停继续可用。
3. 另一页面修改或删除组导致冲突时，当前稿保留，提示刷新组列表。刷新后可明确放弃稿并载入最新版本，或把稿保留为新组再命名保存；不重复旧 revision 写入，不自动合并或覆盖服务端版本。
4. 浏览目录可显式加载空搜索结果；切换目录种类后可加载对应结果。不可采样寄存器的添加按钮禁用并解释原因。导入预览列出组名及对象数量，确认后仍由服务端权威检查名称冲突，失败保留当前编辑稿。

## 唯一状态来源与生命周期

- 服务端组列表是持久组和 revision 的唯一权威；`selectedGroupId` 是下一次开始采样的已保存目标。编辑内容仍只有 reducer 的 `groupDraft` 一份。
- 增加 reducer 所有的编辑基线（加载/成功保存时的完整 GroupDraft 快照）和单调 editor generation；逻辑导航/另存/重载使 generation 增加，提交捕获 generation。脏状态仅比较可编辑字段及有序 watch key，不比较 ID/revision 元数据，不能通过刷新后的组列表倒算。不新增本地存储、自动保存或跨页持久化。
- 编辑目标由 `groupDraft.sourceGroupId` 表示；new 时 source/expectedRevision 和 selectedGroupId 均为 null。初始加载可以选择第一组；普通刷新不把空选组自动改为第一组。现有 active run 的目标来自 `status.sampling`，与下一次开始采样的选择分开说明。
- 编辑导航请求（选择、新建、重新载入）及待确认目标由 reducer 管理。选择当前编辑组是无操作，脏稿不变；其他破坏性导航遇脏稿生成一个确认状态，按钮选择继续编辑或放弃后切换，复用已有焦点管理。确认时重新校验目标存在；消失则保留原稿并提示，不静默选择其他组。确认出现时冻结编辑控件，避免确认内容漂移。
- 刷新成功：干净编辑稿可更新至同 ID 最新组；脏稿保持其内容、原 expectedRevision、基线。源已删除时无论是否 dirty 都清除指向该 ID 的 selectedGroupId；脏稿保留为可恢复的孤立稿并显示“原组已删除”，干净稿则清为新稿。不存在的 source ID 或已知 revision 不匹配时，保存按钮及 controller 的直接保存入口禁止 UPDATE，直到显式导航/载入最新或另存为新稿。显式另存保留 name/description/interval/items，清 source/revision/selected，基线为空稿，要求用户审阅名称再保存。
- 冲突标记可由最新列表中同 ID 的 revision 与草稿 expectedRevision 差异、或缺失情况派生；尚未完成刷新时不能把旧列表称为最新。明确失败码也必须显示恢复提示，不等刷新后才告诉用户。
- 成功保存总是 upsert 服务端规范组；只有提交捕获 generation 与当前编辑 generation 相同才更新选组、编辑内容和基线，不能只靠内容相等推断身份。交互锁阻止在途编辑；迟到确认仍须有 generation 防线。保存成功而后续列表读取失败只重试读取，不能再次 POST。删除确认成功立即移除捕获目标并清理对应编辑状态，后续列表失败也不能留下可保存到已删 ID 的稿。导入成功立即合并返回的组数组，保持现有编辑稿/基线/选组，不能丢弃成功返回值等 GET 后才显示。

## 异步与错误合同

- 沿用 controller 的 groups 写 family 串行锁和 requestId 过滤。组写/列表在途时组选择、新建、编辑输入、增删 watch、保存、删除、导入及冲突解决按钮禁用，reducer/控制器同样防御重复调用。正在进行的独立采样/实时恢复不因编辑锁改变。
- 写开始前退休可能在途的旧 groups.list 请求/重试，防止旧快照覆盖写确认；公开刷新在组写期间不启动，写成功的内部 follow-up 可启动一次读取。写成功确认后至 follow-up 列表完成期间仍保持组工作流互斥。旧请求迟到不得清新 pending 或覆盖列表/基线。
- 组写的 `MONITOR_GROUP_CONFLICT`、`MONITOR_GROUP_NOT_FOUND`、`MONITOR_IMPORT_CONFLICT` 进入专门的 `groups-refresh` 恢复，“刷新观测组”，GET only，保留草稿；不得沿用 generic write-confirm 重播原请求。GROUP_CONFLICT 也可能来自名称重复，文案不能一律断言版本变化。其他确定性输入错误提供“修改草稿/重新选择导入文件”的准确提示，不把它们说成未知写结果。API 不携带当前 revision，必须真正 GET。
- 刷新证实 source 仍存在且 revision 与稿基线相同时，不应强制丢稿或另存；提示可能为名称冲突，允许用户修改名称后点击保存发起一个全新的提交。禁止的是自动/通用重试重播失败请求；不禁止同 revision 下用户修正内容后的新提交。source 已改变或消失则遵守上条 UPDATE 防线。
- 组写传输/响应不确定失败继续遵守 UI02：只允许先核对服务端状态，不自动重发。刷新失败可以就地重试读取。离开旧编辑目标后该目标的旧写重试不能再执行；重试有效性至少绑定编辑身份、内容、source/revision 和服务端同 ID revision。删除重试绑定捕获 ID/revision。新建/导入的未知结果不产生隐式重复创建。
- 成功刷新或离开失败所对应编辑目标后，旧冲突操作提示不再提供失效写重试；可关闭的诊断保留也必须准确表述。`OperationRegion` 所需新恢复文案/种类属于内部 UI 契约，不改 API wire/error codes。
- 所有常规失败仍在当前工作台内，鉴权致命错误沿用既有阻断。不得改变 UI03 reconnect/status generation 语义。

## 目录与导入

目录结果仍绑定当前 binding 和 query；提供明确“搜索/加载”按钮，空字符串是合法浏览请求。切种类不显示或添加不匹配 binding 的旧记录；在途和编辑锁下不能添加。寄存器以服务端 `sampleable` 为准；false 禁用添加，中文显示 access/readAction 等已有原因，不猜测硬件权限。`requiresAccessAcknowledgement` 只呈现既有能力说明，不新开授权或绕过流程。

导入预览展示名称与每组数量及总数，并说明不覆盖已有组、名称冲突以服务端检查为准；不在 JS 自创不等价的 Unicode casefold 规则，不扩大导入格式或后端。文件读取 generation 与取消逻辑保持。

## 范围与边界

允许 UI 内部 group model/actions/selectors/reducer、controller 的组 CRUD/refresh/retry、GroupPanel、CatalogPanel、SamplingControls 的目标标签、app 接线、OperationRegion 恢复文案、zh/styles、相关测试及确受影响 e2e 源、构建 ui_dist、指南组编辑段。纯 helper 可新增；公开 API/codec/Python、鉴权/固定端口、采样协议、图表算法、历史/导出、依赖/版本/构建配置不改。实现者独占产品及实施报告，主代理独占本规范/计划/验收。无远端动作。

浏览器/真实硬件/发布检查继续 DEFERRED；本片要求有意义的 reducer/controller/组件自动化证据，不以 jsdom 冒充真实浏览器。
