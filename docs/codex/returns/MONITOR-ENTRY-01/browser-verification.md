# MONITOR-ENTRY-01 真实运行补验

- 日期：2026-10-15；授权：用户明确要求在权限放开后启动固定端口真实页面，验证关闭标签页后的短地址恢复并展示。
- Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`；被测产品提交：`0bbca0538489def23675a93b9834d6c2812bf7b5`；隔离源树 `D:\codex-tmp\men1015\review`，验证前后 clean。
- 主代理负责真实 CLI 启动、浏览器、证据核对和验收；独立 `gpt-6.1-sol/max` 验证代理执行后端检查。无产品修改、安装、板卡连接或远端动作。
- 本轮运行根：`D:\codex-tmp\mbv1015`，cleanup owner 为主代理。标准测试流程与当前执行记录已读取；本轮只补 Monitor 软件与浏览器证据。

## 已完成

1. Windows CPython 3.12.10 的默认 ProactorEventLoop、socketpair、IPv4 loopback 预检通过，旧环境阻塞已不适用于本轮后端。
2. 独立验证在精确产品提交运行 service/CLI 全文件及 12 个 runtime 生命周期节点：**75 passed，exit 0，11.18 秒**。覆盖真实 HTTP/WS、固定端口冲突不回退、多个服务 cookie 并存、同端口重启拒绝旧 cookie、锁和取消清理。一个 aiohttp `filter_cookies(str)` 弃用警告未造成失败。完整命令、环境、源身份及 stdout 保留在 `backend/results.json`、`backend/backend.log`、`backend/preflight.log`；验证无存活自有进程。
3. 主代理通过真实产品 `python -B -m stm32_monitor open ... --port 8765` 启动未连接硬件的独立验证工程。实际仅监听 `127.0.0.1:8765`，PID 27372；终端仅输出 `http://127.0.0.1:8765/`，stderr 为空。工程/data、完整 argv 见 `evidence/execution-card.json`。
4. 启动器自动打开 Edge；浏览器标签元数据显示标题“STM32 监视器”，URL 已为无 token 的短根地址。此项证明自动交付与地址清除的观测，不替代页面渲染、cookie 成功或重新打开验收。

## 浏览器断点

首次读取真实标签页被 Browser Use origin approval gate 拒绝。用户随后明确确认已允许，再次正常读取返回“saved user permission or managed policy denies access”。未取得 DOM、截图或执行关闭/重开；未用其它浏览器、CDP、网络读取或代理绕过。事件记录：`evidence/browser-events.json`。

**PENDING**：在应用网站权限中解除 `127.0.0.1` 的保存拒绝规则后，由主代理继续同一真实浏览器的页面检查、关闭标签页、仅以短地址重新打开及视觉确认。不得将后端 75 项 PASS、标签标题或地址清除当作这些场景通过。

真实服务与验证工程/data 保留运行，供用户查看和后续补验。一次性 `backend/t` 清理被自动策略拒绝（仅返回 blocked by policy），保留该绝对路径且不绕过；记录为 `evidence/cleanup.json`。源代码与最小有效证据继续保留。
