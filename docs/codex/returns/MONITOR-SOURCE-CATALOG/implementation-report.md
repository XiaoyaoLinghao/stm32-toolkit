# Monitor 源码变量目录：实现返回

## 身份与交付

- Accepted base：`1c320d9dc102ca11a280b97e210517ac5a852b63`。
- 产品、测试和生成资产 CodeHead：`423dc766e60233e4e79bd1ed5306e6631c1d3daa`；分支 `codex/monitor-source-catalog`；独占实现树 `D:\codex-tmp\sc1019\impl`。
- 本报告是单独的后续提交，不自行作软件接受结论。主代理和独立审查者负责对 accepted base 到 CodeHead 的完整差异及精选集成作最终判定。先前已接受的探针反馈修复在本地集成；无 push、PR 修改、远程 merge、tag、release、安装、用户固件编译/烧录、浏览器或新硬件操作。

## 已连接的用户路径

变量页默认从当前项目离线读取源码声明，按文件及函数/作用域浏览、搜索和分页，无探针时也能加载。旧固件变量目录和寄存器可显式切换。GNU Arm GCC 以可信有效参数执行有界预处理，保留实际条件编译分支；ST Arm Clang 只解析预处理结果的 AST。来源为经当前模型语义核对的 Ninja 编译命令或标明来源的 manifest 回退。适配器保留源文件、行列、作用域、跨 TU 声明和明确的 previousDecl 实体链；未知选项、失败单元和资源上限显示不完整覆盖，不把缺项解释为完整目录。

离线 DWARF 源归属投影与既有 `DwarfCatalog.lookup`、读范围及类型限制共同决定可加入资格。同名不同实体、无自身源位置、未证明调试归属、自动局部和参数仍可见并说明原因；聚合根按需有界展开旧 Watch 语法支持的叶项。`GET /api/v1/catalog/source-variables` 与 `GET /api/v1/catalog/source-selection` 使用现有认证/封套及点分隔 operation。选择时后端重核源码、ELF、绑定和目录身份；前端拒绝旧上下文、旧请求代次和切换草稿后的迟到应答。未登记活动绑定时只读浏览，不据源码本身启用加入或采样。索引、归属和聚合处理离开事件循环；编译器子进程有共同期限、增量输出上限、串行所有权和 Windows 原生 Job 子树清理。

## R1 七项修正

| 审查发现 | 实现与回归证据 |
| --- | --- |
| 部分索引的 root→child→grandchild 因视图丢失而失效 | 保留最多两个按结果摘要定位的部分视图；不带 catalogId 的根重试仍重新索引未完成 base。`test_source_catalog.py` 的三层导航及 fail-once 重试先红后绿。 |
| 第 6 层仍有后代的聚合项误报不支持 | 返回 `limit_reached` 且 `truncated=true`，禁止不可展开的加入；深度 fixture 先红后绿。 |
| 等待编译器串行锁不计入单位期限 | `_run` 在锁前签发单一单调时钟截止时间，限时获取锁；无启动的排队超时测试先红后绿。 |
| 一个成员加载错误在多个展开行重复显示 | 源码面板只显示一个作用域清楚的成员错误和对应重试；双展开行 UI 测试先红后绿。 |
| 取消等待者会使完成的同 key 索引任务残留 | 拥有者任务在自身 `finally` 清除 inflight，并独立发布完整缓存/消费后台异常；取消后部分结果重试测试先红后绿。 |
| 多个匿名或同名 DWARF 成员共享 ID | 子 ID 纳入稳定成员序位，重复名或无效成员保持不可加入；真实子页 fixture 先红后绿。 |
| 编译器根进程先退出、后代仍持有管道时关闭不完整 | 适配器私有 `source_windows.py` 以 suspended→Job assign→唯一初始线程 resume 建立拥有关系，`TerminateJobObject` 与 `KILL_ON_JOB_CLOSE` 清理已退出根进程的后代；枚举错误/关闭失败封闭适配器且保留未关闭 Job，仍回收本次 suspended 根。根先退出的 timeout/close、原生故障及重叠索引测试通过。 |

另补真实 App + `createMonitorApi` 的 fetch 封套测试，证明无探针自动加载共享后端页、文件/作用域展开、已连接的新鲜选择 ACK 加入草稿及历史页切换后不重开抽屉。同一渲染前连续搜索的失败 fixture 证明旧代次算法会丢弃最新页；现由 controller 同步签发单调 bigint 请求代次，reducer 只采用更高代次，并覆盖旧应答及固件身份失效后的下一次搜索。公共 Watch 语法、旧目录 API、读/采样门禁、依赖锁及版本未修改。

## 实现者验证

以下检查在 CodeHead 的相同产品字节上完成。运行环境为 PowerShell 7、Python 3.12、已安装的 GNU Arm GCC/ST Arm Clang 与批准本地树复制的 UI `node_modules`；测试临时根、npm 缓存和日志位于 `D:\codex-tmp\sc1019\revision-check`，Python 禁用字节码并将 Toolkit/Monitor `src` 加入 `PYTHONPATH`。离线及 fixture 证据均不是实机采样证明。

| 检查 | 命令主体及保留日志 | 结果 |
| --- | --- | --- |
| 受影响 Python 回归 | `python -m pytest -q -o addopts=''`，Toolkit `test_dwarf.py`、`test_dwarf_declarations.py`、`test_source_adapter.py` 与 Monitor `test_runtime.py`、`test_service.py`、`test_source_catalog.py`；`python-full.log` | 266 passed，1 条既有 cookie API deprecation warning，exit 0。含真实小型测试自有 GCC ELF/AST fixture、DWARF4/5 归属、部分索引重试、聚合深度/序位、并发取消与仅拥有的 Windows Job 进程子树。 |
| UI 全量回归 | `npm.cmd test -- --maxWorkers=4 --testTimeout=15000`；`ui-full.log` | 57 文件、475 项通过，exit 0；包含真实客户端共享封套 App 路径和既有工作台回归。jsdom navigation advisory 不算浏览器验证。 |
| 类型与静态检查 | `npm.cmd run typecheck`、`npm.cmd run typecheck:e2e`、`npm.cmd run lint`；`ui-typecheck.log`、`ui-e2e-types.log`、`ui-lint.log` | 均 exit 0。 |
| UI 生成资产 | `npm.cmd run build`、`npm.cmd run verify:dist`；`ui-build.log`、`ui-dist.log` | 均 exit 0；7 个资产逐字节一致，生成 `ui_dist` 已纳入 CodeHead。Vite 大块提示不是构建失败。 |
| 当前工程只读离线核对 | Python 调用 `SourceCatalogProvider.page`，输入 `D:\codex-tmp\md1016\p`，query `testtime`/`gpio`，binding `None`；`f429-readonly.log` | 当前代码完整索引 21/21 C 单元、0 issue。`testtime` 的 App C/头文件行可见且 `probe_required`、`canAdd=false`；同名测试声明为 `source_attribution_unproven`；`gpio` 自动局部/参数为 `frame_required`。未写该工程或触碰硬件。 |
| 提交差异 | `git diff --cached --check`，提交后 `git status --short` | exit 0，CodeHead 工作树干净。 |

先红后绿的最小证据保留为 `python-red.log`、`python-red2.log`、`python-red7.log`、`python-red8.log`、`ui-red.log` 和 `rapid-search-red.log`；原生故障路径的最终 focused 结果在 `nativefault2.log`。早期 UI 测试选择器文字及异步断言修正只涉及测试夹具，最终全 UI 重新运行。旧 CodeHead 的 256/471 结果不计作此 CodeHead 的 PASS。

## 限制与清理

`canAdd` 只证明当前登记绑定与离线源码/ELF 及旧读取规则的本地一致性，不证明物理芯片状态。真实浏览器、认证实际请求和新硬件验证依规格留给主代理后续层；本实现者未更新 8765 服务。某些变量因缺少唯一 DWARF 归属、运行栈帧或旧 selector 能力而禁用。当前工程检查在无绑定状态下进行，不能作为可加入或采样 PASS。小型测试自有 C/ELF fixture 编译与用户 F429 固件构建不同。

先前 `D:\codex-tmp\sc1019\impl-check` 的精确子项清理已被自动策略在执行前拒绝，目标记录在其 `cleanup-targets.txt`；未重试。R1 的 `D:\codex-tmp\sc1019\revision-check` 中，已读盘盘点 18 个直接子目录（pytest、npm/Node 缓存等）及日志；一次仅针对该根直接子目录、带绝对路径归属校验的递归清理命令也在执行前被自动策略以 `blocked by policy` 拒绝，没有删除任何内容，且未重试或绕过。两处验证残留均不改变 CodeHead 或上述门禁结果；仓库源码、共享 fixture 和其他树未被清理命令触及。
