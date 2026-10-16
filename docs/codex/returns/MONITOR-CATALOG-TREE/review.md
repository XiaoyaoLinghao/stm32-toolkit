# MONITOR-CATALOG-TREE 独立验收

结论：**ACCEPTED**，仅覆盖所列离线软件场景；2026-10-16。

- Full accepted base：`c836df30de046e2d630157caeaa5a006eb870ce2`。
- 最终产品 CodeHead：`c5f38e76a568e51cbb420ea46e24be0d78a47083`。
- 实现报告提交：`6c6e7e9e0cecb034cfa45b20b81a94f85099805e`；分支 `codex/monitor-catalog-tree`，无 PR 或新远端授权。
- 主代理负责规范、计划、集成和验收；单一 `ui03_impl`（gpt-6-sol/max）实现产品和测试；主代理及只读 `ui02_contract_review`（gpt-6-sol/max）独立审阅完整 base→CodeHead。无实现所有权例外，无自我批准。

## 已验收行为

变量按实际定义 CU 的源文件分组，寄存器按实际展开的 SVD 外设分组；同名文件不混组、点号外设不误拆。空查询默认折叠，搜索默认展开，分页保留用户选择并标注已加载数量。页内和跨页矛盾仍按原响应错误整页拒收、保留旧结果并可重试；绑定、旧查询、草稿及寄存器访问保护保持。Toolkit 原 descriptor/CatalogPage JSON 不变，Monitor 目录通过同一个纯适配器添加 group，当前 Python 输出由严格 TS guard 验证。

## 审查发现与闭合

初版 `67c22e4c33a2a145401f9e5175418513df1da7ce` 为 REVISION_REQUIRED。R1 全部归类 PRODUCT，由同一实现者修订一次后关闭：

1. `CatalogPanel.tsx` 的普通对象展开状态误读 `__proto__`、`constructor`、`toString` 继承属性，导致空查询误展开；改为 Map，回归覆盖初始折叠、独立切换、跨页及搜索重置。
2. `debug/dwarf.py` 将跨盘路径和异常 comp_dir 编码误归为无源名；分开处理容错并回退安全 basename，Windows 跨盘及异常编码回归通过。
3. 主代理真实演示 ELF 离线检查观察到 `testtime` 标签被改成 `app/vs10_app.c`；大小写归一化改为仅用于包含关系比较，显示保留源路径。合成 ELF 与现有演示 ELF 均返回 `App/vs10_app.c`。

两名审查者完成 base→最终产品头的源码、测试、协议 fixture、清单及生成资源对应审查；`git diff --check` 通过，最终无遗留产品阻断。生成资源以独立重建逐字节一致为证据。

## 验证归属

实现者在最终冻结字节上完成相关 Python 284 项、完整 UI 50 文件/429 项、双 TypeScript、lint、build、verify:dist，均通过；其命令及初次失败见 implementation.md。未把提交前同字节测试描述成提交后运行。

主代理在干净 detached `D:\codex-tmp\mct1016\review` 的精确最终 CodeHead 执行 `D:\codex-tmp\mct1016\verify.ps1 -ExpectedHead c5f38e76a568e51cbb420ea46e24be0d78a47083`。环境为 Windows、Python 3.12.10、既有 Node/锁匹配依赖，临时文件限制在本轮根。`v/results.json` 记录完整命令、退出码、时间及代码头：

- 现有 `md1016/p/build/arm-debug/b.elf` 的 hash/绑定验证及实际 DwarfCatalog 分页：PASS，`testtime` → `cu:3a9a` / `App/vs10_app.c`；ELF SHA256 `364655a7b7f77558d7102d95a60157b2109b689d56fcb9bfff240e108968fca9`。仅离线读取，没有连接或操作板子。
- 当前 Python 重新生成目录及连接 wire，与跟踪 fixture SHA256 一致；严格前端协议回归通过。
- `test_dwarf_declarations.py`、`test_svd.py` 和两个 Monitor 目录/连接边界节点：exit 0。
- 目录树、目录/图表、协议、controller、reducer 共 5 文件/67 项：PASS。
- TypeScript：exit 0；`verify:dist OK (7 files byte-identical)`。

独立 reviewer 未运行测试，不归属上述执行证据。真实浏览器、关闭重开交互及新硬件采样仍 DEFERRED；现有物理样本和 ELF 不被重新标为新界面实机 PASS。此次没有固件、依赖、版本或权限变更，没有远端动作。

## 服务与清理边界

接受后由主代理通过既有公开 `monitor open` 更新 8765，保留 `md1016/p`、`md1016/data` 和 `monitor-demo-20261016`。只核对源身份、启动进程和监听；不读取受限浏览器页面，不以认证 HTTP 绕过策略。遗留失活 owner 的租约保留给正常 acquire 的既有身份/健康验证回收，不手改锁、不为清理连接硬件。

`D:\codex-tmp\mct1016\cleanup.json` 记录已完成测试临时目录和审查依赖副本的精确路径清理。保留源码、最小红绿日志、wire、真实 ELF 检查结果以及服务启动证据；用户工程、历史和既有共享缓存不在清理范围。
