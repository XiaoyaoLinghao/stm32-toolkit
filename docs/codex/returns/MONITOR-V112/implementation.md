# Monitor v1.1.2 源码版本同步实现回报

## 身份与范围

- Full accepted base：`b257c7e2ebb757c5228d5176d813e14573c4403e`；固定产品 CodeHead：`42669f7bfedbb2b197aad33efca9ad8e84cdd0ac`；分支 `codex/monitor-workbench-local-complete`；实现树 `D:\codex-tmp\mufin1015\impl`。本报告在产品提交后单独提交，不记录报告自身 SHA。
- 按冻结的 v1.1.2 规范和计划，只同步插件、Toolkit/Monitor/UI、入口脚本、release builder/policy/schema 的产品身份及必要的 1.0.1 历史兼容入口。`tools/stm32-monitor/src/stm32_monitor/exports.py` 的导出清单精确版本校验未修改；旧 1.0.1 导出须在新版本重新创建。没有修改 API/wire/protocol/schema 语义、第三方依赖图或 UI 源码；`ui_dist` 与 accepted base 的树对象相同。
- 文档区分最新已发布 v1.0.1 与未发布 v1.1.2 源码候选。未安装工具、操作浏览器/硬件/服务或执行远端写入。主代理负责完整 diff 审查、接受与后续授权推送。

## 行为和回归

1. 当前版本入口统一指向 1.1.2；`setup-stm32-env.ps1` 将 1.0.1 加入已有 legacy runtime 列表，`managed_files.py` 将 1.0.1 加入历史生成者列表。旧 runtime 的 Check 报告待修复，显式 Repair 的事务隔离和用户/工程数据保护仍按原合同执行；历史 `generatedBy` 不被读取时改写。
2. setup 的 `ReleaseUtilitySha256` 与 `ReleasePolicySha256` 取自固定产品提交中 builder/policy 的 Git blob 字节，分别是 `e1136a1578fdec2ed0c530b8014841c73b445aa59572e5847d679ecbfce47e15` 和 `96f4bbaa29153c4b6985982163955d2e8b8c2bf9f32eeb12dad21e5f19af8ede`；归档字节锚点测试在产品提交后通过，没有以 CRLF checkout 替代归档字节。
3. 测试明确覆盖 1.0.1 旧 runtime、旧工程 producer、旧导出拒绝与当前 1.1.2 导出成功。当前版本固定断言按语义适配；历史 1.0.1 fixture 和已发布资格事实保留。

## 实现者证据

所有命令和完整原始输出见 `D:\codex-tmp\mv11216\r\<子目录>\command.txt` 与 `output.log`。Python 命令使用既有 `py -3.12 -m pytest -q -o addopts= --basetemp ... -o cache_dir=...`，按子目录隔离 `TEMP/TMP/TMPDIR`、pytest 缓存并设置 `PYTHONDONTWRITEBYTECODE=1`；UI 命令使用既有 Node/npm 与复制的依赖，按子目录隔离临时目录、npm/Vitest 缓存并关闭更新通知。以下提交前启动的检查针对与 CodeHead 完全相同的产品及测试字节；提交后没有修改这些字节，最终工作树干净。要求 HEAD 归档的锚点及提交后启动的 UI 静态/构建检查则在精确 CodeHead 上执行。

| 命令/覆盖 | 结果 | 日志子目录 |
| --- | --- | --- |
| 红回归：plugin 当前身份、1.0.1 生成者/导出拒绝/旧 runtime | exit 1；预期 4 失败、3 通过 | `red` |
| 上述回归加当前导出、release 身份与 runtime-state | exit 0；19 通过 | `focused` |
| Monitor package/CLI/models/exports 四模块 | exit 0；164 通过 | `monitor-modules` |
| Monitor runtime/service 两模块 | exit 0；109 通过、1 个既有弃用警告 | `monitor-affected` |
| Toolkit plugin/setup/generation/release 四模块，归档锚点单独执行 | exit 0；418 通过、1 项归档锚点按计划移至提交后单独运行 | `toolkit-modules` |
| Toolkit security/build/CLI/MCP/migration/inventory 六模块 | exit 0；274 通过、1 个既有 runpy 警告 | `toolkit-affected-r2` |
| 产品提交后的 Git archive/bootstrap 锚点 | exit 0；1 通过 | `archive-anchor` |
| `npm.cmd run test` | exit 0；49 文件、417 测试通过 | `ui-test` |
| `npm.cmd run typecheck` / `typecheck:e2e` / `lint` | 各 exit 0 | `ui-typecheck`、`ui-typecheck-e2e`、`ui-lint` |
| `npm.cmd run build` / `verify:dist` | 各 exit 0；7 文件逐字节一致 | `ui-build`、`ui-verify-dist` |
| 与 accepted base 比较 package-lock 435 个包条目，忽略顶层和根包的版本字段 | exit 0；其余 JSON 逐项相同 | `lock-graph` |
| 产品 HEAD 的两项 release trust hash 对照 setup 常量 | exit 0；两项匹配 | `trust-hashes` |

`toolkit-affected` 首跑在 collection 阶段因该批次未设置双包 `PYTHONPATH` 出现 `ModuleNotFoundError`，exit 2，分类 **ENVIRONMENT**。保留原始错误；在独立 `toolkit-affected-r2` 运行根修正环境并重跑，未修改产品。红回归预期失败属于 **PRODUCT（先红后绿证据）**。UI 测试的 jsdom navigation 提示和构建的 chunk 尺寸建议均不影响退出码。

本轮运行根仅为 `D:\codex-tmp\mv11216\r`。其中各 `red`、`focused`、`monitor-modules`、`monitor-affected`、`toolkit-modules`、`toolkit-affected`、`toolkit-affected-r2`、`archive-anchor`、`ui-test`、`ui-typecheck`、`ui-typecheck-e2e`、`ui-lint`、`ui-build`、`ui-verify-dist` 的 `p`、`cache`、`npm-cache`、`vitest-cache`、`pip-cache` 等子目录属于可清理的本轮测试工作目录/缓存；`output.log`、`command.txt`、红回归与环境失败的最小证据、`lock-graph` 和 `trust-hashes` 的核对脚本及结果保留。主代理是唯一清理 owner，不删除源、可复用 fixture、共享依赖或他人运行文件。

实现者不自行接受差异。浏览器、物理设备、安装与完整发布资格未在本版本源码切片核验，归后续相应 owner；本地假运行时与 jsdom 结果不代表上述外部证据。
