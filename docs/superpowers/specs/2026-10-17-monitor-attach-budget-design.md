# Monitor 有界附加预算与超时语义修复

## 身份、权限与范围

Accepted base：`0b9f3a75c6490f1f7c2706b1eef907f0fa252de6`，其产品字节与已接受 CodeHead `c5f38e76a568e51cbb420ea46e24be0d78a47083` 相同。分支 `codex/monitor-attach-budget`；无 PR 或远端动作授权。主代理负责规范、调度、完整差异审查和验收；ui03_impl（gpt-6-sol/max）唯一实现；ui02_contract_review 独立审查。原脏工作区保留。

用户于 2026-10-17 明确要求继续排查修复 F429 超时并允许修复后再一次采样、波形和 CSV；先前已授予本地开发测试无需逐次审批。该授权覆盖本规范和计划内的本地修复与一次物理续验，不包含浏览器绕过、远端动作、安装、烧录、复位、显式 halt/resume 或第二次自动尝试。

## 三个用户场景

1. Monitor 连接处于正常启动过程的探针时，单次附加可以使用底层已有的有限启动时间；真实成功后才发布固件绑定。通用客户端和读请求的默认期限保持 5 秒。
2. 附加或后续探针请求真正超时时，Monitor 保留 `MONITOR_PROBE_TIMEOUT` 分类和已清理的诊断；工作台就地显示“探针请求超时”，不自动重连，也不伪称固件来源变化。
3. 修复通过离线审查后，当前 F429 使用原固件进行一次正常 OBSERVE 连接，目录定位 `App/vs10_app.c / testtime`，新建独立演示组，以 1000 ms 间隔采样 30 秒。核验持续增大、身份及丢样，导出本轮 CSV，并绘制真实数据曲线。

非目标：改变 Probe Service 的锁、绝对截止时间、候选绑定提交/放弃状态、worker 生命周期、超时清理或授权；改变正常 OBSERVE 的硬件副作用；扩大全局默认超时、读超时或 worker 操作预算；新增 UI 自动重试；发布新版本或进行真实浏览器验证。

## 已证实问题与未确定部分

上次 `mh1017/capture-events.jsonl` 记录 `PROBE_TIMEOUT / service-attach-deadline`，绑定尚未建立，既有清理均 succeeded。通用 `ProbeClient.attach` 继承 request 的 5000 ms 默认值；Monitor 直接使用该客户端。底层 worker 的 open_attach 使用现有 30 秒 call 预算。Service 从附加请求准入开始计算同一个绝对截止时间，包含排队和 backend。这证实 Monitor 的预算提前截断底层有限操作，但未证实本次 pyOCD 卡在哪个阶段、或延长预算必定解决硬件故障。

`monitor_observation._failure_code` 把 PROBE_TIMEOUT 归入 MONITOR_PROVENANCE_CHANGED；这属于已证实错误分类丢失。lastVerifiedTargetState=null 不证明目标运行或停止。上次约 10.7 秒是含清理的总时长，不能当作附加耗时。

## 冻结合同和唯一状态所有者

- `ProbeClient` 增加向后兼容的关键字构造选项 `attach_timeout_ms=5000`。类型必须为严格 int（不含 bool），范围 1..300000 ms，非法值在发送前拒绝。仅 `attach` 转发该值到已有 request timeout_ms；所有其他操作不变。
- Monitor 定义唯一常量 35000 ms，通过默认 client factory 创建 ProbeClient。35 秒是现有 worker 30 秒加 5 秒准入/完成余量的明确产品策略，不是硬件实测值。保留单参数 client_factory 测试注入合同，不改变 bind_debug_firmware 参数或公共协议版本。同一个 Monitor client 的初始绑定和后续重验证使用相同预算。
- Probe Service 仍唯一拥有请求绝对 deadline、排队、附加候选状态和清理。worker 仍拥有原 30 秒操作上限；不增锁、不重启 timer、不接纳迟到成功、不循环重试。HTTP transport 原 305 秒上限不变。
- `PROBE_TIMEOUT` 映射为 `MONITOR_PROBE_TIMEOUT`，贯穿 observation open、revalidate/read 中既有映射路径及 ProbeSession 阻断码归一化。超时不得发布部分 binding 或样本。相邻 busy/firmware/SVD/DWARF/unknown 分类及 cleanup failure 优先级保持。仅保留现有白名单 attachDiagnostic，不新增原始后端文本或令牌。
- UI 仅新增超时中文标题与适当行动说明，沿用现有工作台失败卡和人工重试机制，不扩展页面、协议或 fatal 规则。构建产物与源码一致。
- 实测唯一所有者为主代理；实现者和审查者不得连接硬件。新采样使用独立运行根，原 mh1017 证据及现有组/历史完整保留。

## 验收与风险

离线必须证实：缺省客户端仍发 5000；Monitor 默认 factory 的附加发 35000；读请求仍为原值；输入边界拒绝；有界慢附加在 Monitor 预算内可成功（fake/integration，不宣称物理）；真实超时/取消仍走既有关闭且不可复用迟到候选；错误诊断透传、cleanup 优先、无部分运行状态；UI 就地中文错误与人工恢复不变。

运行级风险：更长的附加等待是有界的用户可感知变化；当前硬件根因可能不只是预算。单次续验若失败，保留原诊断并停止后续硬件，不增加第二次调用、reset、under-reset 或烧录。实际数据不满足持续变化或身份条件时不能报告物理 PASS。

主代理执行一次最多 30 秒采样；至少 20 个有效递增 uint32 值、稳定 run/group/binding、严格时间/序列顺序、无 history/deadline 丢弃。导出前证明未过滤的精确时间窗口只包含本轮数据；导出后逐行、数量、hash 校验 CSV。真实波形来自校验后的物理数据，不冒充浏览器截图。浏览器继续 DEFERRED。
