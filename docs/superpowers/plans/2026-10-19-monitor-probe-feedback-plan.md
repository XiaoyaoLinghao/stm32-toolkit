# Monitor 探针反馈修复计划

依据[已授权规格](../specs/2026-10-19-monitor-probe-feedback-design.md)，Accepted base `1c320d9dc102ca11a280b97e210517ac5a852b63`。用户已要求修复，既有批准的ACK成功返回边界不变，无另行计划审批停点。

1. `values_first_impl`独占App、必要纯展示组件/中文词条/CSS、真实适配器App测试、受影响测试、生成ui_dist与`docs/codex/returns/MONITOR-PROBE-FEEDBACK/implementation-report.md`。不改controller、公共reducer、API协议/后端或依赖。主代理拥有规格/计划/SOP/审查部署记录；`values_first_review`独立只读审查。无重叠写入或递归委派。
2. 先补真实createMonitorApi/fetch链路测试，不用mock API成功对象跳过解析；明确失败分类，再实现当前界面的成功/未确认反馈和必要App修正。不能凭live状态关闭，保持所有旧生命周期回归。
3. 工件、TEMP/TMP/TMPDIR、缓存和日志仅放`D:\codex-tmp\mc1019`的各自根；复用复制的依赖，不安装、不写借用缓存。聚焦后一次最终UI全量（maxWorkers4/testTimeout15000）、两个typecheck、lint、build、verify:dist。核对精确路径后清理一次性工件，保留必要日志。
4. 产品/测试/dist先提交并冻结CodeHead，再报告单独提交。主代理在干净精确Head树审全base差异及精选集成；独立审查同一完整差异。产品修订回原作者，同一问题两轮不收敛则回设计。
5. 接受后由主代理重新核对旧17680/exec87113归属与创建时间，正常停止并用原project/data/session公开open更新8765，仅验证源码/资源/OS监听。认证交付不等于browser bootstrap或物理PASS。源码变量目录的引擎与公共合同先独立冻结，再另派单一实现者，不将缺引擎伪装为完成。
