# MONITOR-CATALOG-TREE 实现记录

- Full accepted base：`c836df30de046e2d630157caeaa5a006eb870ce2`
- 产品 CodeHead（本报告提交前）：`67c22e4c33a2a145401f9e5175418513df1da7ce`
- 分支：`codex/monitor-catalog-tree`；实现树：`D:\codex-tmp\mufin1015\impl`
- 规范和计划由主代理冻结；实现者只报告离线结果，完整差异审查、独立验证、接受与服务更新由主代理负责。

## 已连接的用户场景

变量目录从实际定义所在的 DWARF 编译单元取得 `cu:<offset>` 和安全源文件标签。同名文件的不同 CU 仍是两个组，项目内可信绝对来源显示项目相对路径，外部、相对编译目录、缺失或异常编码来源降级为 basename 或“未标注编译单元”；不读取源码文件，不改变歧义符号排除。SVD 在展开后的真实外设名处生成 `svd:<UTF-8 SHA256>`，点号外设及其簇寄存器保持同组，旧访问风险字段与采样限制不变。

Toolkit descriptor 的可选不可变 `catalog_group` 只在内存传递，两个 descriptor 和 `CatalogPage.to_dict()` 仍输出旧 JSON。Monitor runtime 的单一纯适配器逐 item 添加必需 `group:{id,label}`，无元数据时使用类别不同的固定未知组。当前 Python wire fixture 使用该适配器生成变量/寄存器成功信封，TS 严格 wrapper guard 保留原 descriptor guard 并拒绝缺失、畸形或额外字段。

前端以原生 `details/summary` 展示两级目录，空查询默认收起、非空搜索默认展开，按绑定、类别、已提交 query 保存分页中的展开选择。显示每组和目录已加载数量、更多结果提示，原 selector 直接加草稿；旧查询/绑定、忙碌和不可采样限制保持。页内矛盾由 wire guard 拒收；跨页同 id 异 label 或同 selector 异组由 controller 以 `MONITOR_RESPONSE_INVALID` 拒收整页，旧结果保留且原 cursor 可重试；相同 selector 的重复 descriptor 保留首项。

## 离线证据

所有命令在上述实现树执行；UI 命令工作目录为 `tools/stm32-monitor/ui`。Python 为 `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`，`PYTHONPATH` 指向本树 Toolkit 与 Monitor `src`；设置 `PYTHONDONTWRITEBYTECODE=1`。`TEMP`、`TMP`、`TMPDIR` 均为 `D:\codex-tmp\mct1016\impl-test\tmp`，pytest 显式指定本轮 `--basetemp` 和 cache dir；未安装依赖。以下日志由实现者保留，命令以此环境为共同前缀。

| 检查 | 命令及退出码 | 结果 |
| --- | --- | --- |
| 红回归 | `python -m pytest tools/stm32-toolkit/tests/test_dwarf_declarations.py::test_catalog_listing_exposes_only_the_concrete_definition tools/stm32-toolkit/tests/test_svd.py::test_selects_one_exact_device_and_expands_register_metadata -q --basetemp=.../pytest-red -o cache_dir=.../pytest-cache`，exit 1；`npm run test -- --run tests/catalog-tree.test.ts`，exit 1 | 旧 descriptor 无 `catalog_group`，Python 2 FAIL；旧严格 guard 拒绝带组的合法目录 wire，UI 1 FAIL。`impl-test/logs/red-python.log`、`red-ui.log`。分类：PRODUCT。 |
| 相关 Python | `python -m pytest tools/stm32-toolkit/tests/test_dwarf.py tools/stm32-toolkit/tests/test_dwarf_declarations.py tools/stm32-toolkit/tests/test_svd.py tools/stm32-toolkit/tests/test_risk_svd_peripheral_public.py tools/stm32-monitor/tests/test_runtime.py -q --basetemp=.../pytest-final -o cache_dir=.../pytest-cache`，exit 0 | 281 tests PASS，涵盖合成多CU、安全路径、异常编码、点号外设/簇/分页、旧 JSON、Monitor typed/fallback wire。`impl-test/logs/python-final.log`。此批次在产品提交前执行；之后只修改 UI 测试 fixture 与一个 TS null guard，所测 Python 源码和测试字节未变。 |
| 首次完整 UI 后的 fixture 适配 | `npm run test`，exit 1；`npm run test -- --run tests/app-errors.test.tsx tests/recovery.test.ts tests/catalog-tree.test.tsx`，exit 0 | 旧 fake API 给目录页无必需 group，4 个旧测试失败、2 个 App 异步错误；补齐新合同 fixture 与空查询折叠点击后，3 文件/34 tests PASS。未减弱读取重试、cursor 或 App 草稿保护。`impl-test/logs/ui-full.log`、`ui-fixture-fix.log`。分类：PRODUCT（测试契约适配）。 |
| 精确产品头完整 UI | 在 clean `67c22e4c33a2a145401f9e5175418513df1da7ce` 上 `npm run test`，exit 0 | 50 files / 428 tests PASS；`impl-test/logs/ui-full-codehead.log`。未运行浏览器 E2E。 |
| 静态与分发 | `npm run typecheck`、`npm run typecheck:e2e`、`npm run lint`、`npm run build`、`npm run verify:dist`，均 exit 0 | `verify:dist OK (7 files byte-identical)`；日志 `typecheck-final2.log`、`typecheck-e2e-final.log`、`lint-codehead.log`、`build-final.log`、`verify-dist-final.log`。TypeScript、构建均为提交前相同冻结字节，lint 又在精确产品头执行。 |
| 当前 Python → TS wire | `python tools/stm32-monitor/ui/tests/generate_wire_fixture.py --output D:\codex-tmp\mct1016\impl-test\current-wire-codehead.json --project D:\codex-tmp\mufin1015\impl`，exit 0；与跟踪 fixture 比较 SHA-256，exit 0 | 两者同为 `FB1FD70E6F63C192A106D4ED18124E6CBAD395109D2A6206F8B046AB1C5D5A9E`。`contract.test.ts` 以严格 guard 消费这份 Python 输出，现有 connect/reconnect fixture 回归仍保留。 |

## 边界与留存

本轮只覆盖离线软件证据；未操作服务、浏览器、HTTP、用户数据库、探针或板子，也未推送或修改远端。既有实机样本不代表新目录已在实机 UI 验收。未扩张函数/结构体/数组深层树，也未安装依赖、改版本或改变采样/身份/授权合同。

本轮实现者输出根为 `D:\codex-tmp\mct1016\impl-test`。保留 `logs` 下红测、首次失败与最终成功日志，以及 `current-wire-codehead.json` 供独立审查；`tmp`、`npm-cache`、`pytest-red`、`pytest-focused`、`pytest-dwarf-groups`、`pytest-svd-groups`、`pytest-runtime`、`pytest-dwarf-encoding`、`pytest-final`、`pytest-cache`、重复的 `current-wire.json` 均为本轮可丢弃产物，由主代理按绝对路径核对后清理。实现树 `node_modules` 是原有 lock 匹配依赖，按主代理后续需要暂留。
