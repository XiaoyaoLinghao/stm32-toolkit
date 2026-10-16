# MONITOR-CONNECT-RESPONSE 实现记录

- Full accepted base：`dcd0a21f605782929051c26773a01e18c02ff55f`
- 产品 CodeHead（本报告提交前）：`8bfba36d365df07acd6854ca2dfd1c9974393bef`
- 分支：`codex/monitor-connect-response`；实现树：`D:\codex-tmp\mufin1015\impl`
- 规范和计划由主代理冻结；本记录仅报告实现者的离线结果，独立审查与接受由主代理负责。

## 原因与修复

Python `DebugFirmwareBinding.to_dict()` 的合法连接响应包含必需 `svdReadableRegions`，而前端 exact guard 的字段表遗漏该字段，导致成功的 `monitor.probe.connect` / `monitor.probe.reconnect` 响应被映射为 `MONITOR_RESPONSE_INVALID`。现将该字段加入只读类型及严格 guard，按现有 `MemoryRegionBinding` 规则验证每项，并拒绝空数组。仍拒绝缺失、`null`、畸形和额外字段。

状态 reducer 在真实 binding/run 变化时依旧清空旧实时数据；现在仅在插入层按提示 `kind + text` 去重，保留首条 ID。相同 HTTP/WS 状态不重置已接受样本；新轮次样本仍进入数值和采样率；事件缺口提示与普通重置提示分别保留。未改变身份判定、事件顺序、revision、gap、样本接收或导出合同。

Python 生成器现在为连接和重连分别写出当前模型的成功信封，且使用不同的 linker `memoryRegions` 与 SVD `svdReadableRegions`；提交的合成 fixture 与现场生成结果逐字节相同。客户端、严格拒绝、reducer 回归和既有 controller fake 均同步更新。既有构建将变动编入 `ui_dist`，版本仍为 1.1.2。

## 离线证据

工作目录为上述实现树；UI 命令工作目录为 `tools/stm32-monitor/ui`。Python 使用 `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`，`PYTHONPATH` 指向本树的 `tools/stm32-monitor/src` 与 `tools/stm32-toolkit/src`。所有命令均设置 `TEMP`、`TMP`、`TMPDIR` 为 `D:\codex-tmp\mcr1016\impl-test` 下各自的 `tmp`，`PYTHONDONTWRITEBYTECODE=1`，npm 检查另将 `npm_config_cache` 指向各自子目录并关闭 update notifier。未安装依赖。

| 检查 | 命令及退出码 | 结果与证据 |
| --- | --- | --- |
| 旧 guard 红测 | 当前 Python `tests/generate_wire_fixture.py --output tests/wire-fixture.json --project D:\codex-tmp\mufin1015\impl`，exit 0；`npm run test -- tests/contract.test.ts`，exit 1 | 旧 guard 拒绝 Python 生成的成功 connect；`D:\codex-tmp\mcr1016\impl-test\red-contract.log`。新增回归在修复前为 4 failures、27 pass：`red-focused.log`。分类：PRODUCT。 |
| 当前 Python fixture 一致性 | 相同生成器重新写 `D:\codex-tmp\mcr1016\impl-test\wire-fixture-current.json`，exit 0；与已提交 `tests/wire-fixture.json` 比较 SHA-256 | 两者均为 `99E08408E8F24CB1A752C8DDFACAFDE1759B43324D24B44DD3846A015511245A`；`fixture-final.log`。UI `contract.test.ts` 经 `STM32_MONITOR_WIRE_FIXTURE` 消费此已核对的当前 Python fixture。 |
| 完整 UI 单元 | `npm run test`，exit 0 | 49 files / 420 tests PASS；`D:\codex-tmp\mcr1016\impl-test\full-ui-final\output.log`。此批次在产品提交前的冻结相同源码/测试字节上执行，提交后工作树 clean。 |
| 静态检查 | `npm run typecheck`；`npm run typecheck:e2e`；`npm run lint`，均 exit 0 | 分别见 `typecheck-final`、`typecheck-e2e-final`、`lint-final` 子目录的 `output.log`。E2E 仅静态 typecheck，未启动浏览器。 |
| 构建和分发 | `npm run build`；`npm run verify:dist`，均 exit 0 | `build-final/output.log`；`verify-dist-final/output.log`：7 files byte-identical。 |
| 精确 CodeHead 核对 | 在 `8bfba36d365df07acd6854ca2dfd1c9974393bef` 的 clean 工作树执行 `npm run test -- tests/contract.test.ts tests/reducer.test.ts tests/client.test.ts tests/controller.test.ts` 和 `npm run verify:dist`，均 exit 0 | 4 files / 55 tests PASS，7 files byte-identical；`codehead-focused/output.log` 与 `codehead-dist/output.log`。 |

## 边界与留存

未启动服务或浏览器，未读取网页/用户数据库，未连接、复位、烧录或采样硬件，未改变后端/固件/依赖/版本，也未执行远端动作。既有真实样本不作为本 CodeHead 的新实机 PASS。服务更新和独立接受留给主代理。

本轮新增输出仅在 `D:\codex-tmp\mcr1016\impl-test`；保留 `red-contract.log`、`red-focused.log`、最终各 `output.log`、`fixture-final.log` 与当前 Python fixture 供审查。各检查子目录下 `tmp`、`npm-cache` 以及重复的中间成功日志在审查后可由主代理按路径核对清理。复制到本实现树的 `tools/stm32-monitor/ui/node_modules` 按主代理后续切片需要暂时保留；其来源仍是既有 lock-matched 依赖，无安装操作。
