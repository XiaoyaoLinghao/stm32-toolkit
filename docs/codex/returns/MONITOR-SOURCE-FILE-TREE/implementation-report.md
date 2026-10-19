# Monitor 完整源文件目录树：实现返回

## 身份与边界

- Accepted base：`3c4e2594bafc8d7ca2f1b00c1efe6683639cf05c`。
- 产品、测试与生成资产 CodeHead：`41b5cc37f60d26da2ed323dd7b934fc980b3df61`；分支 `codex/monitor-source-file-tree`；独占实现树 `D:\codex-tmp\st1019\impl`。
- 本报告是 CodeHead 之后的独立提交，不含报告提交自身的 SHA，也不作作者自验收。主代理负责完整 accepted-base→CodeHead 差异和最终接受；独立只读审查者为 `file_tree_review_sol`。
- 无 push、PR 修改、远程 merge、tag、release、安装、版本修改、用户工程构建/烧录、新硬件或浏览器操作。旧 8765 服务未由实现者触碰。

## 已连接的用户路径

首次源码导航复用一个有界离线索引，保留同一权威快照中的模型源/汇编、C/头文件以及确属快照的其他 AST 声明文件。根目录独立分页列出全部纳管文件，包括无变量文件；文件展开列出文件级和真实 AST 函数作用域，包括空函数；作用域展开后才读取其变量页，单个 `main.c` 的前 100 个变量不会遮蔽 `safe.c` 或空文件。函数体 `#include` 中的局部声明按声明文件与真实 `function_id` 投影到该文件作用域，既保留真实词法函数身份，也不按名字猜归属。未纳管 AST 文件及缺失有效函数身份的局部/参数明确标记 partial 并过滤，不误称已验证输入或挂到 global。

新增 `GET /api/v1/catalog/source-tree` / `monitor.catalog.source.tree`，文件与作用域 metadata 每页最多 1000 项且受 900 KiB data 预算约束；既有 source-variables 增加与 aggregate `parentId` 互斥的 `scopeId`，每页最多 100 个声明根。两域游标均有 HMAC，绑定目录、查询、父/作用域与域标识，统一上限 2048 字符并预留页预算；128 字符中文查询跨页可回读。原选择资格、Watch 语法、聚合成员、DWARF 归属、采样与认证规则保持原合同。

前端在一次 read 内自动取尽根或文件 metadata 页并复核身份、总量、父子关系、唯一 ID 与游标进展后一次采用；变量页仅在对应 scope 内加载更多。reducer 独占树、文件分支、scope 页和聚合子页；节点各用 `catalog.source-node.${nodeId}` 请求域，使两个展开分支与局部失败重试互不替换。查询、上下文和目录代次变化退休旧页、展开、错误与迟到选择 ACK。文件夹按完整相对路径呈现并可折叠，未展开的后代不进 DOM；搜索覆盖文件、真实函数和变量索引。

本切片未修改 `build.identity` 公共合同、通用 `process.py`、依赖锁、版本、DWARF 资格判断或采样/认证授权。

## 实现者验证

所有检查在上述 CodeHead 的同一产品字节上执行。完整 argv、合并 stdout/stderr 和 exit code 保存在独占 `D:\codex-tmp\st1019\impl-check`；`TEMP`、`TMP`、`TMPDIR` 同绑其 `temp`，Python 使用 `-B`、`PYTHONDONTWRITEBYTECODE=1`、本实施树两包 `src` 的显式 `PYTHONPATH`，pytest 使用私有 `--basetemp` 与禁用缓存插件。UI 使用从批准的本地树复制到实施树的私有 `node_modules`，没有安装或变更共享缓存。

| 检查及证据日志 | 结果 |
| --- | --- |
| `python -B -m pytest -o addopts= -p no:cacheprovider -q --basetemp D:\codex-tmp\st1019\impl-check\pytest-affected-ucn-final` 加 Toolkit `test_source_adapter.py`、Monitor `test_source_catalog.py`、`test_runtime.py`、`test_service.py`；`python-affected-final.log` | 143 passed，exit 0；1 条既有 aiohttp cookie API deprecation warning。含真实 GNU Arm GCC→Clang body-include 与 Unicode/UCN 函数 AST、未纳管/孤儿 partial、游标错域/错scope与中文长查询、runtime/service 鉴权封套。 |
| `vitest.cmd run --maxWorkers=4 --testTimeout=15000`；`ui-full-test-final.log` | 57 文件、474 项通过，exit 0；含共享后端目录封套→真实 client 及 App、metadata 自动分页、两个节点独立失败重试、旧代次退休和既有工作台回归。jsdom navigation 提示不是浏览器验证。 |
| `npm.cmd run typecheck`、`npm.cmd run typecheck:e2e`、`npm.cmd run lint`；`ui-typecheck.log`、`ui-typecheck-e2e.log`、`ui-lint.log` | 均 exit 0。 |
| `npm.cmd run build`、`npm.cmd run verify:dist`；`ui-build.log`、`ui-verify-dist.log` | 均 exit 0；7 个 `ui_dist` 文件逐字节一致并纳入 CodeHead。Vite 大块提示不是构建失败。 |
| 只读 `SourceCatalogProvider.tree`，项目 `D:\codex-tmp\md1016\p`，空查询和 `testtime` 查询，binding `None`；`project-tree-testtime-readonly.log` | 空查询 21/21 C 单元、coverage complete、184 文件、0 issue，36.544 s；`testtime` 查询 2.571 s，命中 `App/vs10_app.c`、`App/vs10_app.h`、`Tests/vs10_target.c`。未写该项目、未使用硬件；无绑定不构成可加入或采样证明。 |
| `git diff --cached --check` 与提交后 `git status --short` | exit 0，产品 CodeHead 工作树干净。 |

首次全 UI 测试为 464 passed/10 failed，失败来自旧 App 测试 stub 缺少新增 `sourceTree` 方法及两个旧标签断言；更新测试 fixture 后，聚焦 29/29 与最终全量 474/474 通过。失败日志 `ui-full-test.log` 保留，不计作最终 CodeHead PASS。聚焦验证和最终结果有独立日志，未将旧结果冒称最终检查。

## 交接与限制

本证据来自离线索引、测试自有 C fixture、服务 fixture 和 jsdom。真实浏览器、实际服务认证 HTTP 与新实机验证按规格留给后续主代理；更新 8765 须在独立审查和主代理接受后由主代理执行。没有外部探针绑定的目录为只读；函数局部/参数仍受原栈帧规则限制。

一次仅针对 `D:\codex-tmp\st1019\impl-check` 下 9 个已只读盘点的 `pytest-*` run 目录、含绝对路径归属与 ReparsePoint 校验的 `Remove-Item` 递归清理命令，在执行前被自动 policy 以 `blocked by policy` 拒绝。未重试、未换方式绕过；这些 run 目录、最小失败日志及最终验证日志保留在本次独占根，不影响产品 CodeHead 或通过结果。
