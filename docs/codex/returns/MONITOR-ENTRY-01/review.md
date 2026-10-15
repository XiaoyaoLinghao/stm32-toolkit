# MONITOR-ENTRY-01 独立审查

- Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`。
- Product CodeHead：`0bbca0538489def23675a93b9834d6c2812bf7b5`。
- 裁决：**ACCEPTED（本地代码）**。所有可运行的切片检查通过，无未关闭产品缺陷。真实监听、HTTP/WS、浏览器恢复和视觉证据仍为下述 DEFERRED，不能据此宣称完整用户路径或发布验收通过。
- 规范、集成、完整差异审查与验收 owner：主对话代理。单一实现 owner：`gpt-6-sol/max`；只读辅助 reviewer：用户追加授权的 `gpt-6.1-sol/max`。实现者未自行验收。

## 完整差异与问题闭合

主代理在独立 clean review 树审查 accepted base 到初始产品提交 `e3d6438e88b2453e0c2c246b0ccc41bf5e9b3a52` 的全部差异：CLI/config/runtime/service、启动认证分支、集中中文错误、所有受影响测试、用户指南、生成资产及规范/计划。随后完整审查该提交到 Product CodeHead 的修订差异。辅助 reviewer 独立审查相同的完整产品差异与修订，两段覆盖完整 accepted-base-to-product-head。

唯一 P2：初始实现允许 `--port 80`，但旧 Host/Origin 精确字符串要求显式 `:80`，与浏览器序列化省略 HTTP 默认端口冲突。第一轮裁决 REVISION_REQUIRED，主代理冻结 auth adapter 共享表示契约后，由原实现 owner 修正。

闭合证据：auth.py 的共享 authority/origin 函数供认证、endpoint URL 和静态资源检查复用；实际 80 仅接受无端口与显式 `:80` 两种精确形式；非 80 仍要求唯一显式端口。endpoint 输出省略 `:80`，cookie 后缀仍为实际端口 80。新增纯回归覆盖正确形式、别名/错误协议/端口/畸形来源拒绝及非默认端口边界。缺失 Origin、Fetch Metadata、token、bootstrap、方法与 WS 的既有证明规则未放宽。最终无其他实质审查发现。

## 主代理独立验证

| 检查 | 精确提交与结果 | 最小证据 |
| --- | --- | --- |
| 纯 Python auth/config/parser/service-auth | Product CodeHead，54 passed | `D:\codex-tmp\men1015\verify-correction\results.json`、`pytest.log` |
| 生成资产复建一致性 | Product CodeHead，7 文件字节一致，exit 0 | 同目录 `verify-dist.log` |
| 默认端口纯 URL 解析 | 两种输入均解析为 `http://127.0.0.1/`；无网络 | 同目录 `url-parser.log`、`url-parser.exit` |
| 完整 UI unit、双类型检查、lint、build | 初始产品提交，34 文件/292 tests 及所有命令 exit 0 | `D:\codex-tmp\men1015\verify-final\results.json` 及对应命令日志 |
| UI 证据复用边界 | 初始产品提交至 Product CodeHead 的 `tools/stm32-monitor/ui` 与 `ui_dist` 差异为空；相关字节未变 | Git diff；最终重新通过 verify:dist |
| 完整差异格式、review 树 | `git diff --check` exit 0；验证前后精确提交一致且 clean | 验证 results.json 的 head/status 与本次审查 |

Python 完整节点与实际命令参数记录在 results.json 和任务脚本 `D:\codex-tmp\men1015\verify-correction.ps1`；所有 TEMP/TMP/TMPDIR、pytest 与 npm 缓存位于本轮根目录。实现者的检查与本表独立，详见 implementation.md；未将他人证据归给实现者。

## 待验与交付边界

- **ENVIRONMENT / DEFERRED，后续 owner 为主对话代理**：在获准且可用的 Windows Python event loop/loopback 和浏览器环境中，验证真实固定端口监听、端口冲突清理、双服务 cookie、同端口重启拒绝旧 cookie、完整 HTTP/WS 与书签恢复。UI01 已记录 socketpair/浏览器启动及访问权限阻塞，本轮不重复或绕过。最小既有证据保留于 `D:\codex-tmp\mui1015\run\browser-blockers.txt`。
- **DEFERRED，后续 owner 为主对话代理**：真实浏览器视觉、不同视口与可访问性检查。未生成或声称通过页面截图；原内联预览错误也未据此宣称修复。
- 书签恢复依赖服务仍运行、同一浏览器配置及有效会话 cookie；不承诺浏览器整体关闭后 cookie 持久化。会话失效需停止原服务并以相同端口重新 open，由启动器交付授权，不要求手输或保存 token。
- 本地源码候选，尚未发布。原工作区保持不动；没有 push、PR、merge、tag/release 或其他远端动作授权。
- 用户请求全局子代理默认改为 Sol 6.1/max；配置目录不在当前可写范围，尚未修改。`D:\codex-tmp\men1015\set-codex-subagents.py` 默认只读校验通过，用户可在本机终端用 `--apply` 应用；保留主模型及无关设置。该限制不影响本轮明确指定的 Sol 6.1/max reviewer。

主代理已完整复核实现报告的单文件提交；产品 CodeHead 后只有报告变更。清理 owner 为主对话代理；已移除 31 个本轮依赖副本、临时/缓存目录及重复开发日志，阻塞路径 0。保留源代码、Git、配置脚本与上述最小证据；清理清单位于任务根目录 `cleanup.json`。
