# Monitor 数值优先与成功返回计划

Accepted base：`1a9cadb42f9eace2fa173bdd9d5a42e9a4d20742`；[待批准规格](../specs/2026-10-19-monitor-values-first-design.md)。先批准规格，派生计划无需另设审批停点。无远端、安装、浏览器自动化或硬件授权。

## 单一UI纵向切片

批准后由一个gpt-6-sol/max实现者独占App/styles、受影响LiveTable/LiveChart/ProbePanel/焦点辅助、中文展示词条、相关UI测试、生成ui_dist和该切片implementation-report。主代理拥有规格/计划、测试流程当前入口、独立审查/验收记录和部署卡；另一gpt-6-sol/max独立审完整差异，不自审或递归委派。

不修改controller/reducer/API/schema/后端/ELF解析/依赖/版本；若薄dispatch观察器无法在冻结合同内证明准确成功，先报告具体反例，由主代理修订设计，不由实现者猜测成功。源码索引只保留独立调查/架构任务，不归本UI实现者写入。

先按三场景补App级交互回归，再实现值表优先、无曲线释放空间和设备按钮的逐请求返回凭据。保留现有业务状态和稳定挂载；不得用Promise resolve或pending消失替代成功，不能把诊断GET核对当写入成功。

## 证据与交付

先跑新场景及workbench/live来源/图交互/采样/恢复/组草稿/导入/历史/导出关键回归。共享App/CSS重排要求一次最终UI unit/a11y；随后两个typecheck、lint、build、verify:dist。失败先分类，已证明的调度/报告问题不随意改产品。所有TEMP/TMP/TMPDIR、缓存、日志和测试产物位于本轮D:\codex-tmp\mv1019的独占根；只复制既有依赖，不安装、不写借用缓存。

冻结产品CodeHead后单独提交实现报告。主代理在精确CodeHead干净review树核对全部accepted-base差异和精选集成，独立审查者审同一完整差异；一轮修订返回原实现者，同一问题两轮不收敛则重新设计。报告列明确切运行者、命令、版本、exit和deferred；不能称jsdom为浏览器验证。

本次只是规格/计划，未执行新测试、未更新服务。规格批准且软件接受后，再使用原project/data/session公开open入口更新8765，记录源码/资源/进程，认证交付不等于浏览器bootstrap已验证。用户当前正在测试，部署需先核对服务归属和运行状态，不强杀未知进程；浏览器和硬件仍按用户暂缓。
