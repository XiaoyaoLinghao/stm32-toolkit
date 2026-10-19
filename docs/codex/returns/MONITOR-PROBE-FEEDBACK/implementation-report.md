# Monitor 探针反馈修复：实现返回

## 身份与范围

- Accepted base：`1c320d9dc102ca11a280b97e210517ac5a852b63`。
- 产品、测试、发布资产 CodeHead：`abcf1b488a0bbc72f5efc1e2352a1b30991a5a13`。
- 分支：`codex/monitor-connect-feedback`；实现树：`D:\codex-tmp\mc1019\fix`。规格/计划基于文档头 `886acbc377ad66a10c1136f0dcac629c0d71a6de`。实现者负责产品、实现测试及本报告；主代理和独立审查者负责复核及接受，本报告不自行给出接受结论。
- 只修改 App 展示层、中文词条、样式、真实 HTTP 适配器 App 回归及生成 `ui_dist`。controller、公共 reducer/model、API 协议、后端、依赖、版本、固件均未改。无 push、PR、merge、tag、release、安装、浏览器自动化、认证 HTTP 或新增硬件操作。

## 用户行为与边界

有效的连接、重连或释放 HTTP ACK 经既有 reducer 按 scope/requestId 实际采用后，当前工作台显示可关闭、可访问的中文成功状态；设备按钮拥有同一抽屉代次与请求身份时，原自动返回和焦点恢复继续执行。提示表达本次操作的结果，不承诺未来持续连接。

设备抽屉就地显示当前探针写入的处理中状态；失败和未知结果显示原诊断码，未知结果明确标记“未确认”。“查看操作诊断”仅切到原有 OperationRegion 及其重试/确认流程。较新的探针操作取代较旧的就地结果；新的已采用 ACK 取代旧成功提示。Live“已连接”状态不能创建成功回执或关闭抽屉，独立 status 刷新失败不抹去已采用的探针 ACK。分组目录、数值/波形、草稿、历史和导出合同保持原样。

## 验证证据

所有命令在 `D:\codex-tmp\mc1019\fix\tools\stm32-monitor\ui` 以 PowerShell 7 和 `C:\Program Files\nodejs\node.exe` 执行；每次同时绑定 `TEMP`、`TMP`、`TMPDIR` 到相应的 `D:\codex-tmp\mc1019\fix-check\<run>\tmp`，并设置 `PYTHONDONTWRITEBYTECODE=1`。日志和退出码保存在相应 `<run>` 下。复用了从 `D:\codex-tmp\mv1019\review\tools\stm32-monitor\ui\node_modules` 复制到本树的依赖，没有安装或写入借用依赖树。

| 检查 | 精确命令主体 | 结果 |
| --- | --- | --- |
| 聚焦回归 | `node node_modules/vitest/vitest.mjs run tests/probe-feedback-app.test.tsx tests/values-first-app.test.tsx --maxWorkers 4 --testTimeout 15000 --no-cache --configLoader runner` | `focused-green4`：2 文件、21 项通过，exit 0；其中 6 项新测试使用真实 `createMonitorApi` 和 fetch 协议封套。 |
| 最终 UI unit/a11y | `node node_modules/vitest/vitest.mjs run --maxWorkers 4 --testTimeout 15000 --no-cache --configLoader runner` | `full-ui`：53 文件、460 项通过，exit 0。jsdom 输出既有 navigation advisory；未将其作浏览器 PASS。 |
| 类型 | `node node_modules/typescript/bin/tsc -p tsconfig.json`、`node node_modules/typescript/bin/tsc -p tsconfig.e2e.json` | `typecheck2`、`typecheck-e2e2` 均 exit 0；未启动浏览器。 |
| Lint | `node node_modules/eslint/bin/eslint.js src tests` | `lint-final`：exit 0。 |
| 生成资产 | `node node_modules/vite/bin/vite.js build --configLoader runner`、`node scripts/verify-dist.mjs` | `build`、`verify-dist` 均 exit 0；7 文件逐字节一致。 |
| 差异 | `git diff --cached --check` | exit 0；只暂存归属路径，随后冻结上述 CodeHead。 |

新测试覆盖 live 已连接先于有效 ACK、无效绑定封套、传输失败、连接/重连/释放三种有效 ACK 的成功提示与焦点、独立 status 失败、较新探针操作替换旧结果。原 15 项 values-first App 回归共同通过。测试的封套来自本地 Python wire fixture 与离线模拟 fetch/live；不是本次真实浏览器、用户实际 HTTP 响应或物理探针结果。

初次红测 `focused-red` 因测试读取 fixture 使用了非 file URL 而在收集阶段失败，归类 INFRASTRUCTURE，修正为现有 `STM32_MONITOR_WIRE_FIXTURE` 入口；`focused-red2` 的 5 项失败包含预期缺失反馈以及测试查询时序/拆分文本断言，后者已修正。实现后早期类型检查发现本地 `flatMap` 联合类型推断错误，归类 PRODUCT 编译错误，改为显式展示类型；最终类型检查与全量均通过。保留各次日志，不把红测或中间失败归为最终通过。

## 限制与清理

本次未读取用户那次连接的 HTTP ACK 或已打开页面资源，不能断言先前未自动返回的根因；真实浏览器布局、认证路径和新增硬件均按规格 DEFERRED。主代理需在精确 CodeHead 的干净树中审完整 accepted-base 差异、运行其指定精选复核并决定接受与更新 8765。

测试后对本轮 `fix-check` 下明确列出的独占 `tmp` 目录做了路径归属与 reparse 预检；唯一一次原生 PowerShell `Remove-Item -LiteralPath -Recurse -Force` 清理命令在执行前被自动策略拒绝（`blocked by policy`）。没有重试、绕过或触及旧轮被拒绝的目录；日志、退出码及尚存 tmp 路径保留，见 `D:\codex-tmp\mc1019\fix-check\cleanup.txt`。
