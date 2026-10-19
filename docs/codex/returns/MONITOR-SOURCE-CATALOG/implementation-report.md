# Monitor 源码变量目录：实现返回

## 身份与交付

- Accepted base：`1c320d9dc102ca11a280b97e210517ac5a852b63`。
- 产品、测试和生成资产 CodeHead：`26e6b06ecafdc5dcff7488a04ab59df824ef40fb`；分支 `codex/monitor-source-catalog`；独占实现树 `D:\codex-tmp\sc1019\impl`。
- 本报告是单独的后续提交，不自行作软件接受结论。主代理和独立审查者负责对 accepted base 到 CodeHead 的完整差异及精选集成作最终判定。无 push、PR、merge、tag、release、安装、固件编译/烧录、浏览器或新硬件操作。

## 已连接的用户路径

变量页默认从当前项目离线读取源码声明，按项目文件及函数/作用域浏览、搜索和分页。旧固件变量目录和寄存器仍可显式切换。GNU Arm GCC 先按可信有效参数执行有界预处理，以保留真实条件编译分支；ST Arm Clang 只解析预处理结果的 AST。来源为经当前模型语义核对的 Ninja 编译命令或标明来源的 manifest 回退。适配器保留源文件、行列、作用域、跨 TU 声明和明确的 previousDecl 实体链；未知选项、失败单元和资源上限以不完整覆盖呈现，不猜测为完整目录。

离线 DWARF 源归属投影与既有 `DwarfCatalog.lookup`、读范围及类型限制共同决定可加入资格。同名不同实体、无自身源位置、未证明调试归属、自动局部和参数都保留可见并说明原因；聚合根按需有界展开旧 Watch 语法支持的叶项。`GET /api/v1/catalog/source-variables` 与 `GET /api/v1/catalog/source-selection` 使用现有认证/封套及点分隔 operation。选择在后端重核源码、ELF、绑定和目录身份；前端还拒绝旧上下文、旧目录代次及切换草稿后的迟到应答。未登记活动绑定时只读浏览，不能据源码本身启用加入或采样。索引、归属和聚合处理离开事件循环；编译器子进程有共同期限、增量输出上限、串行所有权和关闭清理。

已合入主代理先前接受的探针反馈修复，最终 UI 验证覆盖合并后的产品。公共 Watch 语法、旧目录 API、读/采样门禁、依赖锁及版本未修改。

## 实现者验证

所有检查在该 CodeHead 的相同产品字节上完成；PowerShell 7、Python 3.12、已有 GNU Arm GCC/ST Arm Clang 和从已批准本地树复制的 UI `node_modules`。测试临时根、npm 缓存和日志在 `D:\codex-tmp\sc1019\impl-check`；Python 设置 `PYTHONDONTWRITEBYTECODE=1`，`PYTHONPATH` 指向本树 Toolkit/Monitor `src`。以下离线/fixture 证据都不是实机采样证明。

| 检查 | 命令主体及保留日志 | 结果 |
| --- | --- | --- |
| 受影响 Python 回归 | `python -m pytest -q -o addopts=''`，文件为 Toolkit `test_dwarf.py`, `test_dwarf_declarations.py`, `test_source_adapter.py` 与 Monitor `test_runtime.py`, `test_service.py`, `test_source_catalog.py`；`python-affected-final2.log` | 256 passed、1 条既有 cookie API deprecation warning，exit 0，31.52 s。真实小型 GCC ELF/AST fixture 包含 DWARF4/5 文件索引、头文件、条件编译、唯一/歧义归属、可读叶、局部/参数、部分重试、超限、异步响应与拥有的编译器子树取消。 |
| UI 全量回归 | `npm.cmd test -- --maxWorkers=4 --testTimeout=15000`；`ui-full-final2.log` | 最终 UI 字节 56 文件、471 项通过，exit 0。涵盖真实客户端读取共享后端封套 fixture、目录浏览/失败重试/选择门禁及既有工作台回归。jsdom 的 navigation advisory 不算浏览器验证。 |
| 类型与静态检查 | `npm.cmd run typecheck`, `npm.cmd run typecheck:e2e`, `npm.cmd run lint`；`ui-typecheck-final2.log`, `ui-e2e-types-final.log`, `ui-lint-final2.log` | 均 exit 0。最终控制字符校验只替换等价实现后，另跑 `tests/source-client.test.ts` 2/2 通过；随后重跑上述全 UI。 |
| UI 发布资产 | `npm.cmd run build`, `npm.cmd run verify:dist`；`ui-build-final.log`, `ui-dist-final.log` | 均 exit 0；7 个资产逐字节一致，生成 `ui_dist` 已纳入 CodeHead。Vite 大块提示不是构建失败。 |
| 当前工程只读离线核对 | Python 调用 `SourceCatalogProvider.page`，输入 `D:\codex-tmp\md1016\p`，query `testtime`/`gpio`，binding `None`；`f429-provider-final.log` | 当前代码完整索引 21/21 C 单元、0 issue。`testtime` 的 App C/头文件行可见且 `probe_required`、`canAdd=false`；同名测试声明为 `source_attribution_unproven`；`gpio` 自动局部/参数为 `frame_required`。未写此工程、未触碰硬件。 |
| 提交差异 | `git diff --cached --check` | exit 0；产品提交后工作树干净。 |

首次受影响 Python 运行有 255/256 通过，唯一失败是测试夹具读取刚创建但尚未写入数字的 PID 文件。修正仅让测试等待该独占子进程 PID 写入后重跑，`python-affected-final.log` 留作最小失败证据。第一次 lint 在新增源路径校验上报 `no-control-regex`；改为等价字符码检查后 lint、类型、客户端聚焦和最终全 UI 均通过。两项都未作为最终 PASS 的替代证据。

## 限制与清理

`canAdd` 只证明当前登记绑定与离线源码/ELF 及旧读取规则的本地一致性，不证明物理芯片状态。真实浏览器、认证实际请求和新硬件验证依规格留给主代理后续层；本实现者未更新 8765 服务。某些项目变量仍因缺少唯一 DWARF 源归属、运行栈帧或旧 selector 能力而禁用，页面给出原因。当前工程的上述检查在未绑定状态下进行，不能作为可加入或采样 PASS。

本轮独占 `impl-check` 中的解析大输出、一次性 pytest 根及缓存仅用于验证；拟在保留上述最终日志与最小失败日志后按精确归属路径清理。该明确限定到 `D:\codex-tmp\sc1019\impl-check` 直接子目录的 PowerShell 递归删除命令在执行前被自动策略拒绝（`blocked by policy`），没有目录或文件被删除，也没有重试或绕过。被拒绝的拟清理目标及全部直接子项的精确绝对路径已读盘列于 `D:\codex-tmp\sc1019\impl-check\cleanup-targets.txt`（执行时 19 个目录、55 个文件）；拟保留的最终/最小失败日志包括 `python-affected-final*.log`、`ui-full-final2.log`、`ui-typecheck-final2.log`、`ui-e2e-types-final.log`、`ui-lint-final*.log`、`ui-build-final.log`、`ui-dist-final.log`、`ui-source-client-final2.log`、`f429-provider-final.log`。该根下的日志、解析工件、测试临时根和缓存仍保留；仓库中的测试与共享 fixture 未触及，既有被拒绝的其他轮次清理目标也未触及。此清理限制不改变 CodeHead 或上述门禁结果。
