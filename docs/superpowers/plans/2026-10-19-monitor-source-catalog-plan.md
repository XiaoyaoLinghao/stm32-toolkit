# Monitor 源码变量目录计划

Accepted base `1c320d9dc102ca11a280b97e210517ac5a852b63`；实施依据[冻结规格](../specs/2026-10-19-monitor-source-catalog-design.md)及用户“变量类的你继续完成”的明确指令。原只读调查中未冻结的引擎/DTO/生命周期已在本规格解决，不由实现者自行猜测。

## 责任与隔离

主代理负责设计、公共合同冻结、集成/完整差异审查、SOP和验收部署；`source_catalog_impl`（gpt-6-sol/max）在`D:\codex-tmp\sc1019\impl`、分支`codex/monitor-source-catalog`独占本纵向切片，`source_catalog_review`（同模型/努力）独立只读审查，无递归调度或自审。

实现者拥有：Toolkit源码发现适配器/不可变DTO和必要DWARF源码归属投影、Monitor源码目录提供者/runtime/service新路由、UI新API/类型/controller/reducer/目录展示及必要App/CSS/词条、相应测试与共享封套fixture、生成dist和`docs/codex/returns/MONITOR-SOURCE-CATALOG/implementation-report.md`。公共类型/查询/游标/生成配置只由该唯一实现者整合；不改旧API、selector语法、采样授权、依赖/锁文件或版本。主代理拥有spec/plan/SOP/review；超出冻结边界先报告具体问题。

探针反馈切片在另一已确认隔离树`D:\codex-tmp\mc1019\fix`实施，禁止跨树写入。主代理接受其CodeHead后通知本实现者合并；如App/CSS冲突，由本实现者在自己树内按两份规格整合，主代理不代写产品解决。最终全量验证必须覆盖合并后的产品，避免先跑一遍全量再因合并重复。

## 单一交付顺序

1. 读取AGENTS、标准测试流程和最新验收、工程经验匹配项；核对干净base与已安装ST Clang/Ninja/GNU工具。所有测试输入/缓存/TEMP/TMP/TMPDIR/日志只在`D:\codex-tmp\sc1019`各自独占根，无安装、用户工程写入、构建/烧录或探针访问。
2. 先冻结代码内不可变DTO与v1封套fixture，再实现有界Clang适配器、源位置/作用域与DWARF归属/叶判断；使用真实离线编译器fixture及当前工程读取进行验证。复用唯一provider缓存和既有输入/ELF身份校验，不创建第二采样或认证引擎。

   主代理集成澄清：实际GNU Arm GCC先有界预处理并保留line markers，再由Clang解析预处理C；两者内建宏不同，直接Clang替换GCC不能证明实际条件分支。先验证编译器宏条件fixture及当前21单元两阶段管线，再把该路径作为目录完整性证据。必要的extern/定义归属使用显式AST redeclaration链，不按裸名猜测。
3. 打通新GET列表/子页/选择校验→真实client解析→controller/reducer身份退休→SourceCatalogPanel→原group草稿，随后保留旧变量/寄存器切换与现有工作台状态。接口有任何未明确选择先回主代理，不拆给并行模块猜测。
4. 先针对变化的Python及UI聚焦验证，清理每次不再需要的run工件。合入已接受探针修复后，最终一次全UI unit/a11y（maxWorkers4/testTimeout15000）、两个typecheck、lint、build、verify:dist及受影响Python全选；命令/环境/exit归实际运行者。可复用复制已有node_modules，不写借用缓存。
5. 产品/测试/dist提交冻结完整CodeHead并立即回报；实现报告单独提交、记录base与报告前CodeHead，不能包含自己的报告提交SHA。主代理在精确CodeHead干净review树审完整base差异和必要精选集成，独立审查同一差异。两轮同问题不收敛则回设计。
6. 软件接受后主代理使用原project/data/session公开open更新8765，记录源码、发布资源、进程和监听。浏览器/硬件继续用户暂缓；不得把AST、fixture或历史实机证据称为新版物理PASS。没有远端/版本/安装动作。

证据/清理所有者：实现者清理sc1019/impl-check与自己的parser运行根，主代理清理sc1019/review-check；解析工件仅保留必要汇总/失败最小证据，源码测试和可复用fixture不能删除。旧轮已拒绝的清理目标不重试、不绕过。报告/门禁规模不得超过本跨模块产品风险所需。
