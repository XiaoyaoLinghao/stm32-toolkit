# Monitor 来源分组目录实施计划

2026-10-16；依据[冻结规范](../specs/2026-10-16-monitor-catalog-tree-design.md)和[标准测试流程](../../testing/standard-test-procedure.md)，Full accepted base `c836df30de046e2d630157caeaa5a006eb870ce2`。主代理已沿用户连续本地授权作出设计决定；无需重复审批，无新增远端授权。

1. 主代理确认 clean `codex/monitor-catalog-tree` 位于隔离树 `D:\codex-tmp\mufin1015\impl`，提交规范/计划与测试断点。当前8765保留已接受连接修复源码 `D:\codex-tmp\mcr1016\review`，project/data/session保留 md1016 演示身份，不操作探针。
2. 单一 gpt-6-sol/max 实现者拥有本切片：Toolkit debug/types.py 中的非序列化分组值、dwarf.py/svd.py 的真实来源保存与descriptor传递；Monitor runtime.py 中的严格列表适配；UI api类型/guard/client、state/controller/model/reducer 中必要的有界分页合同及 CatalogPanel、中文文案、样式；对应现有目录/运行时/UI测试和生成ui_dist。其他源码、公开授权/身份/采样/导出逻辑、依赖和版本不在范围。主代理独占规范、计划、集成与验收文档；无并行产品写入。
3. 实现者先完成端到端最小路径：真实CU/SVD元数据→现有CatalogPage→Monitor逐item group→严格UI guard→折叠组→原selector加草稿。冻结合同中cross-page矛盾整页拒收、旧结果保护、分页计数/展开状态和访问限制一起完成，不能交付只有静态树的中间态。不递归委派，不自我接受，不触碰服务/浏览器/用户DB/硬件或远端。
4. 临时输出仅 `D:\codex-tmp\mct1016` 各owner独立子目录；TEMP/TMP/TMPDIR都绑定，Python禁止bytecode；可复用当前实现树已有依赖，不安装或修改共享缓存。主代理为最终清理owner。记录实际命令、退出码与最小失败证据。
5. 实现者执行相关DWARF/SVD目录和descriptor/Monitor运行时回归，使用合成fixture覆盖至少两个CU（含重名文件/未知来源/歧义符号）、项目内/外部路径和带点外设/簇；旧Toolkit JSON保持精确相等。UI运行目录/合同/控制器/分页定向回归和一次完整UI套件、双TS、lint、build、verify:dist；现有Python wire生成器现场生成，不能用旧fixture替代当前协议。无需完整Toolkit发布或硬件矩阵。
6. 产品提交后固定CodeHead。实现报告独立提交到 `docs/codex/returns/MONITOR-CATALOG-TREE/implementation.md`，注明完整base、报告前CodeHead、命令/证据owner、环境与限制、清理目录；不写自身SHA。交回clean head，不能push。
7. 主代理在 `D:\codex-tmp\mct1016\review` 建精确CodeHead的干净detached树，独立gpt-6-sol/max只读reviewer与主代理审阅完整base→CodeHead；主代理运行独立关键Python跨层/前端回归、typecheck与dist校验。最多两轮同问题后回设计，不进行无边界修补。接受只覆盖实际离线证据，浏览器与新实机继续DEFERRED。
8. 接受后主代理经原公开open入口更新8765并核对本机源身份、进程和监听。关闭旧服务后记录实际进程退出与租约状态；若进程退出而遗留active租约，按既有dead-owner/health验证机制留待下一次用户正常连接，不手改锁、不为清理触碰硬件。保留用户工程、观测组、历史数据库。清理已不再需要的本轮测试缓存、依赖副本和中间文件，保留源码及最小证据；最终反馈分组用法与限制，不推送GitHub。
