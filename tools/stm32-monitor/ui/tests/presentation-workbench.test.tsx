import {expect,it,vi} from "vitest";
import {cleanup,render,screen} from "@testing-library/preact";
import {initialState,reducer} from "../src/state/reducer";
import {statusResult} from "./fixtures";
import {LiveTable} from "../src/components/LiveTable";
import {SamplingControls} from "../src/components/SamplingControls";
import {NoticeRegion} from "../src/components/NoticeRegion";
import {FailureMessage} from "../src/components/FailureMessage";
import {TransportStatus} from "../src/components/TransportStatus";
import {copy,errorText,formatCopy,latencyText,noticeText,operationSummary,recoveryAction,recoveryText,samplingState} from "../src/presentation/zh";

it("keeps large and signed latency values exact and gives unknown codes a neutral explanation",()=>{
  expect(latencyText(1_234_567_890_123_456_789_123n)).toBe("1234567890123.45 s");
  expect(latencyText(-1500n)).toBe("-1.50 μs");
  expect(samplingState("FUTURE_STATE")).toBe("状态未知");
  expect(errorText("UNKNOWN_CODE").title).toBe("操作未完成");
  expect(noticeText("unknown notice from reducer")).toBe("监视状态已变化，请查看详情。");
});

it("does not attribute a shared invalid-request code to group editing",()=>{
  const guidance=errorText("MONITOR_REQUEST_INVALID");
  expect(guidance.title).toBe("请求无效");
  expect(guidance.action).toBe("请检查当前操作的输入后重新提交。");
  expect(recoveryText("input","groups.update")).toBe("请修改草稿或观测对象后重新提交。");
  expect(recoveryText("input","export.create")).toBe(guidance.action);
});

it("names a failed operation with its submitted page and identity for safe retry",()=>{
  expect(operationSummary("catalog.variables","counter","next-cursor")).toBe("变量目录搜索 · counter · 下一页");
  expect(operationSummary("history","0","1000000000","next-cursor")).toContain("翻页");
  expect(operationSummary("groups.import","2")).toBe("导入观测组 · 2 组");
  expect(operationSummary("sampling.start","g1","probe-1","run-1")).toContain("轮次 run-1");
  expect(operationSummary("probe.release")).toContain("探针 未知");
  expect(operationSummary("export.create","csv","0","1000000000")).toContain("CSV");
  expect(recoveryText("input","groups.import")).toBe("请检查导入文件内容或数量，再重新选择文件。");
  expect(recoveryText("read-retry","initial")).toBe(recoveryAction("read-retry","initial"));
});

it("labels missing operation context and incomplete source facts without invented identities",()=>{
  expect(operationSummary("export.create")).toContain("1970-01-01T00:00:00.000Z");
  expect(operationSummary("history")).not.toContain("翻页");
  expect(operationSummary("catalog.registers")).not.toContain("下一页");
  expect(operationSummary("sampling.start")).toContain("观测组 未知 · 探针 未知 · 轮次 未开始");
  expect(formatCopy.registerUnavailable(null,null)).toContain("access: 未知；readAction: 未知");
  expect(copy.sourceIssues(0,true)).toBe("说明与诊断 · 目录覆盖未完成");
  expect(copy.sourceIssues(0,false)).toBe("说明与诊断");
  expect(recoveryText("none","export.create")).toBe(copy.unknownExport);
});

it("shows probe timeout as a recoverable probe request failure",()=>{
  const guidance=errorText("MONITOR_PROBE_TIMEOUT");
  expect(guidance.title).toBe("探针请求超时");
  expect(guidance.action).toBe("请查看详细信息。");
  const started=reducer(initialState,{type:"request.started",scope:"probe.connect",requestId:1n});
  const failed=reducer(started,{type:"request.failed",scope:"probe.connect",requestId:1n,code:"MONITOR_PROBE_TIMEOUT",message:"Monitor observation could not be established"});
  render(<FailureMessage failure={failed.failures["probe.connect"]!}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("探针请求超时");
  expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_PROBE_TIMEOUT");
});

it("shows interrupted values as stale, and exposes a blocked sampling state without changing control rules",()=>{
  const watch={kind:"variable" as const,expression:"counter"};
  const row={watch,displayValue:"42",rawHex:null,typeName:"uint32_t",capturedAtUtc:"2026-08-10T00:00:00Z",trend:"none" as const,errorCode:null,numericValue:42};
  const base=statusResult();
  const running={...base,sampling:{...base.sampling,state:"RUNNING" as const,active:true}};
  const opened=reducer(reducer(initialState,{type:"status.loaded",status:running}),{type:"transport.open"});
  const stale=reducer(opened,{type:"transport.stale"});
  expect(stale.transport.stale).toBe(true);
  render(<TransportStatus sampling={stale.status!.sampling.state} phase={stale.transport.phase} stale={stale.transport.stale}/>);
  expect(screen.getByText("设备采样状态：采样中")).toBeTruthy();
  expect(screen.getByRole("status")).toHaveTextContent("数据连接中断 · 等待重新连接");
  render(<LiveTable rows={[row]} selectedSeries={[]} fresh={!stale.transport.stale} onSeriesToggle={vi.fn()}/>);
  expect(screen.getByLabelText("最新数值")).toHaveTextContent("非最新数据");
  cleanup();
  const blocked={...running.sampling,state:"PAUSED_BLOCKED" as const,blockedCode:"MONITOR_PROBE_BUSY"};
  render(<SamplingControls status={blocked} group={null} failure={null} onStart={vi.fn()} onPause={vi.fn()} onResume={vi.fn()} onStop={vi.fn()}/>);
  expect(screen.getByRole("status")).toHaveTextContent("采样受阻");
  expect(screen.queryByRole("button",{name:"继续采样"})).toBeNull();
  expect(screen.queryByRole("button",{name:"开始采样"})).toBeNull();
  expect(screen.getByRole("button",{name:"停止采样"})).toBeEnabled();
});

it("translates binding changes while preserving raw notices and request failures in details",()=>{
  const base=statusResult();
  const before=reducer(initialState,{type:"status.loaded",status:base});
  const changed=reducer(before,{type:"status.loaded",status:{...base,project:{...base.project,logicalProjectId:"new-project"}}});
  expect(changed.notices).toHaveLength(1);
  render(<NoticeRegion notices={changed.notices}/>);
  expect(screen.getByText(/连接身份或采样轮次已变化/)).toBeTruthy();
  const started=reducer(changed,{type:"request.started",scope:"history",requestId:1n});
  const failed=reducer(started,{type:"request.failed",scope:"history",requestId:1n,code:"UNKNOWN_CODE",message:"raw diagnostic"});
  expect(failed.blockingError).toBeNull();
  render(<FailureMessage failure={failed.failures.history!}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("操作未完成");
  expect(screen.getByRole("alert")).toHaveTextContent("UNKNOWN_CODE");
  expect(screen.getByRole("alert")).toHaveTextContent("raw diagnostic");
});
