# Monitor 本地完成与推送前交付

2026-10-16：本次授权的本地开发、适用测试、独立审查、集成和 8765 服务更新已完成。未执行 GitHub push、PR 修改、远端 merge、tag/release 或远端删除。真实浏览器和硬件/发布验证按用户要求继续暂缓，本候选不是新发布版本。

## 已连通场景

- 中文默认、浅色工作台与就地错误恢复保留，普通失败可以在当前工作台按原操作重试。
- UI04：波形按各自实际采集时刻对齐，图内和工具栏缩放同步；读取空缺不连线，最多 8 条曲线且始终可移除。
- UI05：切组/新建保护草稿；明确编辑组与采样目标；保存 ACK 保留较新输入，冲突后先刷新权威列表再允许写入；目录及导入预览有明确反馈。
- UI06：历史在途范围与已有结果分开，晚到结果或重试不覆盖新输入，分页及导出基于成功结果；实时表核对当前运行组版本并显示 UTC，断流/版本变化后的旧指标明确标记。
- 最终集成保留远端补充的认证非泄露、导入卸载测试与发布文档；历史专属错误提示与导出通用提示已拆分。无未闭合本地产品阻断。

## 提交与验证

交付分支：`codex/monitor-workbench-local-complete`，工作树 `D:\codex-tmp\mufin1015\impl`。固定产品 CodeHead：`de6f3434865f3c85119e566c314ded0c6ea3e232`。后续提交仅为报告/接受/交付文档；本文件不写自己的最终 SHA，完整交付 HEAD 见本次返回或 `git rev-parse HEAD`。

本地候选包含已读远端 master `3edd82e6b8f2ebd5df88dcafde1e75f722357c3e`，本次结束前只读检查仍未变化。origin 已核对为预期 GitHub 仓库。分支在本机，尚未推送；任何未来远端动作须遵循新的明确授权。

| 已接受切片 | 产品 CodeHead | 证据 |
| --- | --- | --- |
| UI01 中文工作台 | 67f0ec4fbc375ed60e1f857b4cae248bf73d1589 | MONITOR-UI-01/review.md |
| ENTRY01 固定入口 | 0bbca0538489def23675a93b9834d6c2812bf7b5 | MONITOR-ENTRY-01/review.md |
| UI-POLISH 视图/导入生命周期 | 2af7f3c2f750669b5176503f61d3f14dd11cf8d3 | MONITOR-UI-POLISH/review.md |
| UI02 就地恢复 | da7f1e7798ae9120f0eb130ec4286da12e9ef379 | MONITOR-UI-02/review.md |
| UI03 实时连接恢复 | 92c537835dbbad9b09096da003e77d2a4ff6a11d | MONITOR-UI-03/review.md |
| UI04 波形查看 | 19acd9bd9f944f4072490e7571563d2593f59eb3 | MONITOR-UI-04/review.md |
| UI05 组编辑/冲突恢复 | 24c550be5ae6061671ba922dd86c7bc243ac51a6 | MONITOR-UI-05/review.md |
| UI06 历史/采集时效 | 0edb2183c154d366d3f261a90e08d6ed54505e26 | MONITOR-UI-06/review.md |
| 最终本地集成 | de6f3434865f3c85119e566c314ded0c6ea3e232 | 本目录 review.md |

最终实现者 **49 文件 / 417 项 UI 测试**、两个 TypeScript 检查、lint、build、verify:dist 全部通过；主代理在干净精确 CodeHead 独立复验 **11 文件 / 102 项**及 typecheck、verify:dist 通过。7 个生成资源逐字节一致。上述测试数是各自覆盖，不相加成独立用例总数。完整命令与证据见 implementation.md、review.md 和任务根 `verify-final/results.json`。

## 服务与保留边界

入口：`http://127.0.0.1:8765/`。旧受管 session1069/PID29524 已通过 Ctrl-C 退出，并确认端口释放；新受管 session18685/PID10168 从 `D:\codex-tmp\mufin1015\review` 的精确产品 CodeHead 启动，UTC 开始时间 `2026-10-15T17:11:39.8616826Z`，OS 确认仅监听 127.0.0.1:8765。记录在 `D:\codex-tmp\mufin1015\service.json`。

沿用原展示 project/data/session，经公共 serve 命令启动，输出只保留短入口，没有记录 token，也没有手删运行记录或锁。活动源码树和展示数据必须保留。服务由当前受管进程运行；没有安装开机自启、Windows 服务或新发布包。

**外部证据 DEFERRED**：真实浏览器/不同视口/手势/axe、关闭页面后短地址重开、完整 HTTP/WS、物理采样与发布矩阵。后续 owner 为主代理及对应硬件/发布 owner；OS 监听、jsdom、构建均不替代这些证据。既有入口合同依赖同一浏览器的有效会话 cookie，服务重启后的新授权由 open 启动器交付，不要求手工保存或输入 token；本轮未执行浏览器恢复测试。

## 清理与原工作区

主代理已清理 UI04 33、UI05 39、UI06 21、最终集成 29 个自有临时/缓存/复制依赖或中间运行目录，各当前片清理记录无删除失败；分别见 `D:\codex-tmp\mu41015\cleanup.json`、`mu51015\cleanup.json`、`mu61015\cleanup.json`、`mufin1015\cleanup.json`。保留源码/Git/跟踪资产、最终原始日志、最小红/失败依据及活动服务所需文件，没有删除共享依赖源。

另一个旧服务目录 `D:\codex-tmp\mu31015\service-temp` 的删除命令被自动审批策略拒绝（只返回 blocked by policy，未给具体规则），因此保留；没有重试或绕过，不影响新服务。记录在 `mufin1015\old-service-cleanup.json`。

原始 `D:\workspace\stm32-toolkit` 仍为 master `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`，121 项 tracked changes、4 项 untracked entries 保持，本任务未修改它。旧不可访问临时目录的既有警告仍保留，未扩展清理范围。
