# Monitor 工作台界面重构

## 身份与授权

Accepted base：`ab274cf8ecde1bfd352419eb49140961818a43ac`；其运行产品 CodeHead 为 `3b449fe365972738389f43f6a63d34a174eacdb3`，含已接受的附加预算、分组目录和采样/CSV修复。分支 `codex/monitor-workbench-refactor`，无PR，未授权远端动作。主代理负责规范、计划、完整差异审查、集成验收及8765更新；唯一实现者workbench_impl、独立审查者workbench_review，均gpt-6-sol/max；无所有权例外。

2026-10-18用户批准此前设计并明确要求实施、保留现有采样/分组目录/CSV，完成测试及独立审查后更新8765；真实浏览器验证继续暂缓。该批准覆盖本规范的落地及派生实施计划，不另设计划审批停点。没有新硬件测试、烧录、reset、安装依赖或GitHub写入授权。

批准设计来自 `D:\codex-tmp\mr1017\design.md` 及离线原型 SHA256 `665DAD168D90377E6D4D89C4EB1A1A833134BC0C71001C60CA4E94665597E636`。仓库内[1366×768参考图](../design-assets/monitor-workbench-2026-10-18/monitor-1366.png)与[1440×900参考图](../design-assets/monitor-workbench-2026-10-18/monitor-1440.png)保存批准视觉。原型仅用于布局参考，不把其模拟状态、内嵌历史CSV或60000ms示例上限移植为生产合同。

## 三个用户场景

1. 1366×768和1440×900桌面首屏以目录、完整波形和最新数值为主体。目录默认可见且可收起，波形随剩余高度伸缩；一个观测项时表格自动缩小，至少三项时首屏具备三行容量。设备信息和组编辑按需打开，不长期挤占画布。
2. 按真实源码文件/外设分组查找变量或寄存器，加入现有组草稿后自动打开组编辑抽屉。关闭、切页、收起目录和重新打开都保留未保存内容与明确保存入口；开始采样仍使用已保存的所选组及revision。运行A时编辑B不会重标A的曲线或数值来源。
3. 使用独立历史页查询、分页及CSV/JSONL导出，保持范围确认、服务端制品核验与下载。普通失败不顶开整块画布；任一页/抽屉中的失败在常驻入口可达，按原scope/requestId重试或刷新。嵌套确认的Escape和Tab只处理最上层，普通关闭不丢草稿。

非目标：更换Preact/ECharts、改协议/后端/固件、重写controller/reducer、放宽采样或访问限制、复制原型的模拟连接/数据/CSV实现、引入路由或新持久化、修改版本号、浏览器或硬件验收、远端发布。

## 展示层和空间合同

- 中文默认、浅色专业工作台。使用canvas #F3F5F8、surface #FFFFFF、ink #15243B、muted #5C6B80、border #D9E1EB、signal #2466D1等语义token；中文系统字体，数字tabular-nums。保留既有错误/过期/新鲜度语义，不靠颜色单独传达。
- 外壳为52px顶栏、minmax(0,1fr)主体、28px底栏。顶栏合并品牌、实时/历史导航、短项目/探针状态与设备详情入口；完整hash/ID进入详情。主体默认约290px目录+弹性主区，min-width/min-height:0、box-sizing:border-box和内部滚动保证窄栏不再承载470px目录表。
- 主区44px采样工具条+弹性波形+数值表。缩放/重置并入图头；保留ECharts resize/datazoom和原缩放数学。数值表一项约108px、三项约180px、多项约208px后滚动，可收起；选中曲线计数/移除入口保持可达和8条限制。
- 1366×768扣顶底与主体上下各12px后为664px：单项约44+512+108；三项约44+440+180。所有额外padding/gap计入该预算。低高度表体滚动，低宽度目录转按需覆盖或堆叠并保留打开入口；支持缩放与触屏目标，不用隐藏溢出掩盖不可达操作。
- 设备、组编辑和诊断按需覆盖抽屉；常规成功/失败信息不增加主区的文档流高度。底栏保留来源/新鲜度、真实速率/丢弃与“操作问题N”入口；原始精度与完整诊断可在详情访问。

## 状态、生命周期和错误唯一来源

`App`只拥有当前页、目录可见、表格收起、图最大化、单一activeDrawer及焦点返回这些布局状态。`MonitorState`/controller继续唯一持有groups、selectedGroupId、groupDraft/baseline/generation/navigation、冲突门禁、pending/failures/reconciling、history/export、live/run/series/zoom。不得移植原型local saved/dirty/history/CSV状态，也不得重建第二个controller。

有未提交或本地状态的GroupPanel（含导入预览/异步读取代次/删除确认）、CatalogPanel（搜索/分页/展开）、HistoryPanel（未提交范围）、ExportPanel（未提交范围/确认）、OperationRegion（写入重试确认）保持稳定挂载，或者先明确提升到唯一所有者后才改变挂载；本切片优先保持挂载与hidden。切换页面/关闭抽屉本身不得清除这些状态或重复loadInitial。LiveChart在收起、图最大化或页切回后正常resize。

工作台模式的组抽屉开合以App为唯一控制源；如GroupPanel保留独立使用回退，受控模式不可再有第二个editorOpen真值。目录添加先走原group.watch.added，再打开/聚焦组抽屉；关闭仅隐藏。侧栏常驻dirty数量及“编辑并保存”；选择/新建/重载触发现有groupNavigation时确认必须可见，明确放弃才走原navigation确认。保存仍用原草稿、revision、generation及冲突门禁，不因布局改变提交/重试时序。

图表/表格/来源名称及fresh计算继续使用exact runId/groupId/groupRevision及已接受样本；组版本失配明确显示上次样本/未核对。新草稿项不进入旧run。完整运行ID可移至详情，但来源核对文字不得丢失。

目录保留bindingEpoch/key、当前查询代次、分页和旧结果禁加；sampleable=false禁加，requiresAccessAcknowledgement=true只提示且可加草稿，不自动授权。采样间隔沿用真实100..5000ms合同。未连接时主CTA打开设备详情供用户明确选择探针；暂停/继续/停止按原采样状态和busy门禁，不能因布局隐藏合法Stop或暗中发起连接。

失败仍只存原failures，以scope+requestId索引；状态栏计数直接派生，不复制错误。诊断抽屉保留一个OperationRegion实例，任何页/关闭抽屉后都可打开定位；pending/写入二次确认/GET刷新恢复/组冲突门禁及dismiss保持。Bootstrap/fatal阻断规则不变；普通错误不升级为整页阻断，失败不自动消失。

抽屉与已有导航、导入、导出、写入确认构成同一焦点层级：只有最上层处理Escape/Tab，下层不得重复消费；关闭回到仍可见可用的触发按钮。若触发按钮隐藏或消失，回到同区域可见入口。键盘与鼠标均可完成操作，图标按钮有中文aria-label，焦点明显，减少动态偏好受尊重。

历史继续区分已接受查询、未提交输入、导出手工范围与已提交制品；切页不能把草稿当查询。UTC/BigInt纳秒、分页、明确导出确认、CSV/JSONL、制品刷新/核验/下载全保持，不从可见行直接拼生产CSV。低频组新建/删除/刷新/JSON导入导出和探针刷新/连接/重连/释放/复制身份、实时流重连/取消/状态刷新都须有清楚入口，不能为简洁删功能。

## 验收和风险

实现者完成三场景App级回归和原UI全量unit、a11y、双typecheck、lint、build、verify:dist；保留已有group时序、采样状态、catalog身份、live来源、history/export和错误恢复回归。增加抽屉关闭保持草稿/导入/未提交范围、嵌套确认焦点、隐藏失败可达、图resize、目录需确认标记测试。不能用jsdom或静态尺寸断言冒充浏览器真实排版证据。

主代理在精确CodeHead的干净review树审完整差异并跑精选集成；独立审查者审同一完整差异。浏览器与新候选硬件由用户继续暂缓，作为明确DEFERRED外部证据；旧F429物理PASS只作为原后端/数据的既有证据，不重新标成新UI实机PASS。

软件接受后主代理更新8765，复用原project/data/session及固定短入口。仅公开CLI启动、静态版本/manifest与OS进程/端口核对，不调用浏览器、恢复token或读认证Monitor接口。当前预检无8765监听；若部署时已被占用先核归属，不杀未知进程。源码、原工程、组和历史保留，远端操作仍需另行授权。
