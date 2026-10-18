# Monitor 工作台重构实施计划

Accepted base：`ab274cf8ecde1bfd352419eb49140961818a43ac`；规范：[工作台重构](../specs/2026-10-18-monitor-workbench-refactor-design.md)。2026-10-18用户已批准设计及实施、测试、独立审查和8765更新；派生计划无需额外审批。分支codex/monitor-workbench-refactor，无远端授权，无所有权例外。

## 1. 单一实现纵向切片

workbench_impl（gpt-6-sol/max）唯一拥有UI产品实现及测试：tools/stm32-monitor/ui/src/app.tsx、styles.css、presentation/zh.ts、components下受影响展示组件/通用抽屉/焦点辅助、对应UI测试和ui_dist生成物。controller/state/api/chart数学、Python后端、schema、依赖/锁文件/版本号不在写入范围。若确有跨界必要先向主代理提交具体阻断，不擅改。

主代理独占规范/计划/设计参考图、standard-test-procedure当前入口、最终review和部署记录；实现者独占docs/codex/returns/MONITOR-WORKBENCH-REFACTOR/implementation-report.md。独立workbench_review只读完整差异；不得自审、递归委派或执行硬件/浏览器/远端操作。

按一次完整产品路径实现：固定视口壳与常驻目录；窄栏目录叶项；组摘要及稳定挂载的组抽屉；合并采样/图缩放/自适应数值；设备和诊断抽屉及常驻恢复入口；历史/导出独立视图。内部组件props由唯一实现者按规范状态归属收敛，不引入并行写所有权。

## 2. 测试顺序与证据

先补有实际交互价值的App/组件回归，再实现，不写仅镜像CSS常量的测试：

- 目录默认可见，添加→组抽屉→关闭/切页/收起→重开仍dirty，没有暗发保存/采样；未保存组导航确认仍可达。
- 组导入预览、history未提交范围、export手工范围/确认在普通关闭/切页后保留；现有草稿/版本/冲突时序保持。
- 运行A时编辑B、保存A新版本、组缺失时来源与fresh正确；图隐藏/布局变化回显后resize，8曲线限制与缩放保留。
- 关闭/非活动区域的失败仍能经问题入口访问，重试绑定原scope/requestId，write-confirm与GET-only恢复不变；最上层确认独占Escape/Tab并恢复焦点。
- sampleable=false和requiresAccessAcknowledgement=true两类目录叶项；未连接CTA和合法暂停/继续/停止门禁；历史查询/分页/CSV+JSONL服务端导出下载路径。

聚焦集先跑App/errors、ui05 groups、ui06 live/history、groups-import-lifecycle、catalog-tree、sampling-controls、recovery、history/export、chart interaction和新抽屉场景。因共享App装配及全局CSS变化，随后运行一次完整UI unit/a11y、typecheck、typecheck:e2e、lint、build、verify:dist。不运行真实浏览器e2e、硬件或发布矩阵；Python后端未变，仅按dist/静态路由相关现有测试选择验证。

环境为本机PowerShell7/Python3.12/Node现有依赖。所有TEMP/TMP/TMPDIR、pytest basetemp、Vitest缓存/日志和构建临时产物置于D:\codex-tmp\mw1018内独占根。实现者可复制mf1017现有node_modules，不安装、不改共享依赖/缓存。保留argv、完整stdout/stderr和exit；先分类PRODUCT/ENVIRONMENT等再修复。

## 3. 返回、独立审查与集成

产品提交后冻结完整CodeHead；implementation-report记录accepted base、报告前CodeHead、行为/范围、命令和结果、deferred/cleanup，不含自己的最终SHA。最后报告提交作为final head返回。

主代理从精确产品头创建干净review工作树，审完整accepted-base→CodeHead及最终report delta；workbench_review独立审同样差异。主代理跑受影响的新场景及关键保留路径精选集成，不重跑全部实现矩阵。正确性阻断返回同一分支/实现者；同问题两轮不收敛则回到设计。实现者不拥有接受或部署权。

## 4. 更新8765

软件接受后主代理保存部署卡：精确源码/版本/manifest、project D:\codex-tmp\md1016\p、data D:\codex-tmp\md1016\data、session monitor-demo-20261016、授权及进程/端口状态。复用公开python -B -u -m stm32_monitor open ... --port8765；仅输出固定短URL，token不读不回显。启动不得自动连接探针或执行采样。若已有本任务自有旧服务，正常Ctrl+C并核对精确进程退出；未知占用先定位，不强杀。

用启动结果、监听127.0.0.1:8765、PID/创建时间、干净CodeHead与打包静态资源核对完成服务更新。真实浏览器继续DEFERRED，不把源代码/SSR/jsdom或PNG设计稿当浏览器PASS。无需新实机采样；保留原工程、组和历史，旧物理CSV/曲线不被覆盖。

## 5. 收尾

主代理写一个最终验收记录，列完成场景、合同、证据、外部deferred和更新后短入口。按归属清理不再需要的本轮测试临时产物，保留源码/依赖复用、日志/命令/exit、最小失败证据、参考图、用户数据。遇策略拒绝记录具体路径与原因，不换工具绕过。无push、PR、tag或release。
