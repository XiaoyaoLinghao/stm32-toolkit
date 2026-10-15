# MONITOR-ENTRY-01 实现回报

- Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`。
- 产品 CodeHead（本报告提交之前）：`0bbca0538489def23675a93b9834d6c2812bf7b5`，本地分支 `codex/monitor-entry-01-fixed-url`。
- 实现与实现测试：单一 `gpt-6-sol/max` 子代理，在隔离工作树 `D:\codex-tmp\men1015\impl`。主对话代理独立审查、复验并裁决本地代码；实现代理不自我验收。没有 push、PR、合并、tag、发布或其他远端动作。

本地未发布候选现在支持 `serve`/`open` 的可选固定端口。未指定端口仍由系统动态分配；指定值只接受 ASCII 十进制 `1..65535`，绑定仅使用 IPv4 `127.0.0.1`，占用时不回退。`open` 成功后输出无 token 的短根地址，`serve` 的 JSON 输出保持原契约。服务按**实际端口**统一设置和读取 `stm32_monitor_session_<port>` cookie；旧固定名称不作为认证凭据。前端在清除敏感 URL 信息之前，按序列化的原始 `href` 严格识别普通根地址，仅对该地址以同源凭据请求状态并复用现有类型守卫；有效 fragment 仍使用原 bootstrap，非法 fragment、查询和 `/?`、`/#` 均不降级到 cookie 路径。普通根地址收到 401/403 时只呈现 `MONITOR_SESSION_EXPIRED`，不展示原始响应内容。原 App/controller 所有权和生命周期不变。

独立审查第一轮发现一个 P2：原先对 `:80` 的严格字符串要求会拒绝浏览器规范化后的 HTTP 默认端口。规范和计划随后冻结了同一 authority 的两种精确表示。修订后，实际端口 80 的 endpoint URL 为 `http://127.0.0.1`，Host 只接受 `127.0.0.1` 或 `127.0.0.1:80`，Origin 只接受对应的两个精确 HTTP origin；其他端口仍只接受显式端口。共享表示和匹配位于现有 auth 适配边界，并由 endpoint、静态服务和认证使用；cookie 后缀仍为实际端口 80。新增纯 auth/endpoint 回归覆盖两种表示、非 80 严格性及错误主机、协议和端口拒绝。主对话代理审查完整 accepted-base→CodeHead 差异，独立 `gpt-6.1-sol/max` reviewer 确认该 P2 已闭合且无新实质缺陷；主对话代理裁决**本地代码 ACCEPTED**，真实浏览器用户路径仍待验。

实现代理在产品提交 `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` 运行以下检查；Python 选择器共 **52 passed**，UI 定向测试 **2 files / 35 tests passed**。`0bbc` 的修订只影响 Python auth、service、相关 Python 测试和指南；`git diff e3d6438e 0bbca053 -- tools/stm32-monitor/ui tools/stm32-monitor/src/stm32_monitor/ui_dist` 为空，因此下列 e3d UI 检查可按相同字节复用，不能把它们误写成实现代理在 0bbc 重跑。

| 执行者 / 产品 SHA | 命令或检查 | 实际结果与证据 |
| --- | --- | --- |
| 实现代理 / `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` | 下方相同的纯 Python selectors | 52 passed；`D:\codex-tmp\men1015\run\logs\pytest-codehead.log`，`.exit` 为 0 |
| 实现代理 / `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` | `npm.cmd run typecheck`、`npm.cmd run typecheck:e2e`、`npm.cmd run lint`（`tools/stm32-monitor/ui`） | 各 exit 0；`run\logs\typecheck-codehead.*`、`typecheck-e2e-codehead.*`、`lint-codehead.*` |
| 实现代理 / `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` | `npm.cmd test -- tests/bootstrap.test.ts tests/main.test.tsx` | 2 files / 35 tests passed；`run\logs\vitest-codehead.*`，exit 0 |
| 实现代理 / `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` | `npm.cmd run verify:dist` | 7 files byte-identical；`run\logs\verify-dist-codehead.*`，exit 0。生成资产由此前本地 build 产生并包含在产品提交中 |
| 实现代理 / `0bbca0538489def23675a93b9834d6c2812bf7b5` | 下方完整纯 Python 命令 | **54 passed**，exit 0；`D:\codex-tmp\men1015\run\logs\pytest-port80-codehead.log`、`.exit`。52→54 为修订后增加两项覆盖，不是失败或回退 |
| 主对话代理 / clean detached `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` | `npm.cmd test`、`npm.cmd run typecheck`、`npm.cmd run typecheck:e2e`、`npm.cmd run lint`、`npm.cmd run build`、`npm.cmd run verify:dist` | 独立 34 files / **292 tests passed**，类型检查、lint、build、7 个分发文件字节比对均通过；这是主代理证据，不是实现代理的 35-test 记录 |
| 主对话代理 / clean detached `0bbca0538489def23675a93b9834d6c2812bf7b5` | 同一完整纯 Python selectors；`npm.cmd run verify:dist`；Node `URL` 纯解析；UI/dist 字节差异检查 | 独立 **54 passed**，7 files byte-identical；Node 解析确认 HTTP `:80` 两种形式的 canonical 表示一致；e3d→0bbc UI 源和 dist 无字节变化。真实传输与浏览器没有因此变成 PASS |

最新产品 CodeHead 的实现代理 Python 命令如下，从工作树根执行。`TEMP`、`TMP`、`TMPDIR` 指向 `D:\codex-tmp\men1015\run\temp`，`PYTHONDONTWRITEBYTECODE=1`，`PYTHONPATH` 包含本隔离树的 Monitor 与 Toolkit `src`；Node 的 `npm_config_cache` 指向同一运行根的 `npm-cache`。第一个产品提交采用相同 selectors，当时少两项 port-80 回归。

```powershell
python -m pytest -o addopts= -p no:cacheprovider --basetemp D:\codex-tmp\men1015\run\pytest-port80-codehead `
  tools/stm32-monitor/tests/test_auth.py `
  tools/stm32-monitor/tests/test_models.py::test_monitor_config_canonicalizes_external_roots_without_creating_state `
  tools/stm32-monitor/tests/test_models.py::test_monitor_config_accepts_explicit_port_and_rejects_invalid_values `
  tools/stm32-monitor/tests/test_models.py::test_monitor_config_rejects_state_inside_project_and_unsafe_session `
  tools/stm32-monitor/tests/test_service.py::test_cookie_names_use_actual_endpoint_port_and_ignore_legacy_name `
  tools/stm32-monitor/tests/test_cli.py::test_version_command_reports_the_package_version `
  tools/stm32-monitor/tests/test_cli.py::test_cli_rejects_legacy_and_override_options `
  tools/stm32-monitor/tests/test_cli.py::test_cli_port_parser_accepts_ascii_decimal_and_rejects_invalid_values `
  tools/stm32-monitor/tests/test_cli.py::test_module_entrypoint_delegates_to_cli_without_importing_legacy_runtime
```

**ENVIRONMENT / 未执行的真实路径：** 本机已知 Python `asyncio.run` 在 Windows socketpair 创建时阻塞、Node localhost 自访问得到 `EACCES`、独立 Chromium 无法启动，且本机浏览器访问 localhost 的授权已被拒绝。最小既有阻断证据为 `D:\codex-tmp\mui1015\run\browser-blockers.txt`；本切片没有重复监听、浏览器或网络绕行。指定端口真实绑定/冲突/清理、HTTP 与 WS 的实际 cookie/Host/Origin 往返、双服务与重启，以及关标签页后短地址恢复、浏览器视觉/无障碍检查均**未获真实环境 PASS**；相关测试源已添加或保留，交由主对话代理在获准可用环境补验。纯函数、解析器、fake/window 单测只证明各自的代码分支，不代表完整用户路径或发布/硬件验收。指南说明本行为属于未发布的 ENTRY01 源码候选，已安装 v1.0.1 在更新为包含该切片的构建前不支持 `--port`。
