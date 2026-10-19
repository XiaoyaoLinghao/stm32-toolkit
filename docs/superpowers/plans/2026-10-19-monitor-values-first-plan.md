# Monitor 数值优先与成功返回计划

Accepted base：`1a9cadb42f9eace2fa173bdd9d5a42e9a4d20742`；[已批准规格](../specs/2026-10-19-monitor-values-first-design.md)。用户于2026-10-19批准实施，派生计划无需另设审批停点。无远端、安装、浏览器自动化或硬件授权。

## 单一UI纵向切片

`values_first_impl`（gpt-6-sol/max）独占App/styles、受影响LiveTable/LiveChart/ProbePanel/焦点辅助、中文展示词条、相关UI测试、生成ui_dist和`docs/codex/returns/MONITOR-VALUES-FIRST/implementation-report.md`。主代理拥有规格/计划、测试流程当前入口、独立审查/验收记录和部署卡；`values_first_review`（gpt-6-sol/max）独立只读审完整差异，不自审或递归委派。

不修改controller/reducer/API/schema/后端/ELF解析/依赖/版本；若薄dispatch观察器无法在冻结合同内证明准确成功，先报告具体反例，由主代理修订设计，不由实现者猜测成功。源码索引只保留独立调查/架构任务，不归本UI实现者写入。

2026-10-19集成澄清：同批次请求的采用证明由App局部纯reducer外壳提供，只保留一个MonitorState并每动作调用既有reducer一次，附加scope/id临时展示回执；不重放reducer、不在reducer写ref/触发副作用、不改公共模型。独立审查覆盖纯度、失效顺序和回执不能跨抽屉代次关闭的约束。

先按三场景补App级交互回归，再实现值表优先、无曲线释放空间和设备按钮的逐请求返回凭据。保留现有业务状态和稳定挂载；不得用Promise resolve或pending消失替代成功，不能把诊断GET核对当写入成功。

## 证据与交付

先跑新场景及workbench/live来源/图交互/采样/恢复/组草稿/导入/历史/导出关键回归。共享App/CSS重排要求一次最终UI unit/a11y；随后两个typecheck、lint、build、verify:dist。失败先分类，已证明的调度/报告问题不随意改产品。所有TEMP/TMP/TMPDIR、缓存、日志和测试产物位于本轮D:\codex-tmp\mv1019的独占根；只复制既有依赖，不安装、不写借用缓存。

冻结产品CodeHead后单独提交实现报告。主代理在精确CodeHead干净review树核对全部accepted-base差异和精选集成，独立审查者审同一完整差异；一轮修订返回原实现者，同一问题两轮不收敛则重新设计。报告列明确切运行者、命令、版本、exit和deferred；不能称jsdom为浏览器验证。

当前冻结已批准合同，尚未执行新实现测试。软件接受后使用原project/data/session公开open入口更新8765，记录源码/资源/进程，认证交付不等于浏览器bootstrap已验证。已知旧服务PID19020、CreatedUtc `2026-10-19T00:54:34.6078230Z`、exec session5332；部署前重新核对服务归属和运行状态，仅正常停止已确认的本轮服务，不强杀未知进程。浏览器和硬件仍按用户暂缓。
