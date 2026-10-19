# Monitor 完整源文件目录树实施计划

Accepted base：`3c4e2594bafc8d7ca2f1b00c1efe6683639cf05c`。依据[冻结规格](../specs/2026-10-19-monitor-source-file-tree-design.md)及用户本次完整目录树、测试/独立审查/更新8765的明确授权；不增加审批停点。浏览器与新版实机验证由主代理在用户恢复时执行，本轮DEFERRED。远端动作、安装、版本变化和用户固件覆盖均未授权。

主代理拥有spec/plan、SOP、集成审查、验收与部署；file_tree_impl（gpt-6-sol/max）唯一实现产品/测试/生成dist及实现报告；file_tree_review_sol（显式gpt-6-sol/max通用只读代理）独立完整差异审查。先前file_tree_review仅合同预检，不计作最终产品审查；避开模型固定的内置reviewer角色以严格遵守用户模型要求。两名只读explorer仅核对旧后端/前端路径，不接管集成设计、不递归委托。一个纵向切片，不拆成并行共享schema写入。

1. 实现者在`D:\codex-tmp\st1019\impl`、`codex/monitor-source-file-tree`核对干净base与规格。所有产物在`st1019\impl-check`，三种temp变量及缓存明确绑定；可复制现有node_modules，不安装。保留所有旧轮拒绝清理目标。
2. 先扩展不可变函数元数据和真实AST归属、快照纳管文件事实、单provider树节点/按scope预索引；冻结DTO fixture并接通新tree路由/旧变量scope过滤及cursor域。不得改build.identity、DWARF归属、采样/认证或通用进程引擎。未明确决策回主代理，不自行补架构。
3. 一次打通实际client→controller自动取全metadata→reducer唯一树/分支/叶状态→Panel按路径展示→原selection草稿。动态节点request scope使多开并发与局部重试独立；保留所有完整上下文/代次/草稿门禁。
4. 先跑针对性回归，然后最终一次受影响Python文件全选、全UI（maxWorkers4/testTimeout15000）、typecheck/typecheck:e2e/lint/build/verify:dist；只读当前项目tree及testtime路径。新原生进程生命周期没有变更时不额外重复无关平台/发布矩阵。保存实际argv/stdout/exit及精确运行根；故障先分类，清理不再需要产物且不重试任何拒绝目标。
5. 冻结产品/测试/dist CodeHead后立即发主代理，另提交`docs/codex/returns/MONITOR-SOURCE-FILE-TREE/implementation-report.md`（base与报告前CodeHead，不自写报告commitSHA、不自接受）。主代理建立精确CodeHead干净review树，独立审查者审完整base→head；主代理精选source/client/state/panel/App及受影响工作台集成、静态资产/dist一致性，避免重复全发布矩阵。正确字节通过证据不因报告排版问题失效。
6. 软件接受后主代理按规格更新8765和运维卡，写`docs/codex/returns/MONITOR-SOURCE-FILE-TREE/review.md`与SOP当前断点。无远端动作。最终说明目录完整性、叶分页、资格限制、测试归属及浏览器/硬件DEFERRED。

主代理负责`st1019\review-check`清理，实现者负责`st1019\impl-check`和自己的parser临时根；运行中的服务树及service-temp不清理。两轮同一问题不收敛则回集成设计；实现者不得递归调度或自我验收。
