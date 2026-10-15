# MONITOR-UI-POLISH 实现回报

## 身份与责任

- 切片：已批准 MONITOR-UI-01 的 S2 交互收尾；规范 `docs/superpowers/specs/2026-10-12-monitor-ui-design.md`，计划 `docs/superpowers/plans/2026-10-15-monitor-ui-polish-plan.md`。
- Full accepted base：`4a90d7385db0b42bc2d103ba90ab41a2f89f7d05`。
- 产品 CodeHead（写此报告之前）：`2af7f3c2f750669b5176503f61d3f14dd11cf8d3`，分支 `codex/monitor-ui-01-polish`，本地实现树 `D:\codex-tmp\muf1015\impl`。首轮产品提交 `bc01aee11e907f66664e3582c0e2742d77a0700e` 已按独立审查意见在同一分支修订。
- 实现和以下验证由实现代理执行；完整差异审查与验收由主代理独立负责。本轮没有远端、浏览器、硬件、安装或权限操作。

## 行为与文件

- `ui/src/components/GroupPanel.tsx`：导入展示状态包含关闭、选择、读取、预览、错误。新选择立即撤销旧确认并显示中文读取状态；每次选择、关闭、取消和卸载使旧读取代次失效。预览携带所属读取代次，确认处理器同步核对该代次与当前 ref、挂载状态，因此同一事件批次内已废弃的旧确认也无法提交。失败、无效 JSON 和无效 schema 只显示对应中文错误，不保留可确认的旧文档。同一文件可立即重选，旧读取完成时不会清空新文件框。仅有效预览中的文档可经确认传给现有 `onImport`。
- `ui/src/components/LiveTable.tsx` 与 `ui/src/presentation/zh.ts`：未选中按钮提示下一步“显示曲线”，已选中提示“隐藏曲线”；`aria-pressed` 仍反映传入的选中真相，回调及 key 不变。新增读取状态文案也只在中文展示字典中。
- `ui/tests/groups-import-lifecycle.test.tsx` 和 `live-table-interaction.test.tsx`：受控 FileReader 回归覆盖读取失败、JSON/schema 错误、乱序完成与旧失败晚到、关闭/取消/卸载、同文件重选、实际导入参数和曲线双向动作。新增同一原生事件批次内 `change→旧确认`、`取消→旧确认`、`关闭→旧确认` 的真实不提交断言。`components.test.tsx` 与 `components-coverage.test.tsx` 更新已改变的按钮名称断言；`ui/e2e/acceptance.ts` 更新同一用户动作的定位标签，未运行浏览器。
- `src/stm32_monitor/ui_dist/**`：由现有 `npm run build` 生成并纳入产品 CodeHead；没有修改 API、controller、reducer、group-transfer、Python、依赖锁或构建配置。上述 `ui/` 和 `src/` 均相对于 `tools/stm32-monitor/`。

## 执行证据

环境：Windows PowerShell，`C:\Program Files\nodejs\node.exe` v24.18.0、npm 11.16.0。先核对原工作目录的 `node_modules/.package-lock.json` 与本树 lockfile：所有已安装版本一致，无缺失必需包；51 个缺失项均为其他平台 optional 包。依赖只复制到本实现树 `tools/stm32-monitor/ui/node_modules`，未安装或联网。所有执行绑定 `TEMP`、`TMP`、`TMPDIR` 到 `D:\codex-tmp\muf1015\run\temp`，`npm_config_cache` 到同一 run 根的 `npm-cache`。

受控回归先在原产品字节运行：`run/red-import.txt` 记录旧确认未撤销、乱序提交错误、读取失败未处理拒绝、读取中无取消及同文件无法重选；`run/red-live.txt` 记录缺少正确的下一步曲线动作。首轮 CodeHead 上的 `run/revision-red.txt` 又证明三个同批次旧确认处理器会错误提交。修订后相关组件集 `run/revision-targeted.txt` 为 5 文件、51 测试通过。一次提交前 lint 因测试桩未使用形参失败，已归类为 TEST 并修复，保留 `run/lint-precommit.txt`。首轮 CodeHead 的 301 项 UI unit PASS 保留其原始提交归属，不代替修订提交的复验。

在精确 CodeHead `2af7f3c2f750669b5176503f61d3f14dd11cf8d3` 上，从 `tools/stm32-monitor/ui` 执行以下命令，原始 stdout/stderr 均保留在 `D:\codex-tmp\muf1015\run`：

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `npm run typecheck` | exit 0 | `revision-final-typecheck.txt` |
| `npm run typecheck:e2e` | exit 0 | `revision-final-typecheck-e2e.txt` |
| `npm run lint` | exit 0 | `revision-final-lint.txt` |
| `npm run test` | exit 0；36 文件、304 测试通过 | `revision-final-ui-unit.txt` |
| `npm run build` | exit 0 | `revision-final-build.txt` |
| `npm run verify:dist` | exit 0；7 个产物文件逐字节一致 | `revision-final-verify-dist.txt` |

`npm run test` 的 jsdom 输出包含 `Not implemented: navigation to another Document`，但全部测试通过；构建输出有既有 500 kB chunk 大小建议，构建成功。最终构建后工作树无未提交产品差异。

## 保留边界与清理归属

浏览器、截图、axe 和真实关闭重开按本轮用户指示保持 PENDING，由主代理在后续恢复验证时执行；本报告不将组件测试称作浏览器或视觉验收。此前与本次 UI 字节无关的后端证据由主代理按适用性复用，本实现者没有重跑或重新归属。没有实机或发布结论。

主代理为 cleanup owner。请在独立审查不再需要后，按精确路径处理本轮独立依赖副本 `D:\codex-tmp\muf1015\impl\tools\stm32-monitor\ui\node_modules`，以及 `D:\codex-tmp\muf1015\run\temp`、`npm-cache`、`vitest-cache`、`vitest-cache-revision` 和 run 根各 `.txt` 日志（含 `codehead.txt`、`revision-codehead.txt`）。两个 `vitest-cache*` 目录是从本实现树 `node_modules/.vite/vitest` 移入 run 根的归属明确的测试缓存。保留此报告、源测试、构建资产与审查所需的原始日志，直到主代理完成证据核对。
