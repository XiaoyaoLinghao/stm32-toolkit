import {expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/preact";
import type {HistoryPage,HistoryQuery} from "../src/api/contract";
import {HistoryPanel,historyInput,inputNs} from "../src/components/HistoryPanel";

const a:HistoryQuery={startNs:1_786_320_000_000_000_000n,endNs:1_786_320_002_000_000_000n,runId:"run-a",limit:50};
const bStart="2026-08-11T00:00:00.000",bEnd="2026-08-11T00:00:02.000";
const page:HistoryPage={batches:[],valueCount:0n,nextCursor:"next-a",serializedBytes:0n};
const deferred=()=>{let resolve!:()=>void;const promise=new Promise<void>(done=>{resolve=done;});return{promise,resolve};};

it("keeps draft B and its validation while A succeeds, and identifies pending versus accepted ranges",async()=>{
  const running=deferred(),onLoad=vi.fn(()=>running.promise);
  const {rerender}=render(<HistoryPanel query={null} page={null} inFlight={null} failure={null} onLoad={onLoad} onPage={vi.fn()}/>);
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:historyInput(a.startNs)}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:historyInput(a.endNs)}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({startNs:a.startNs,endNs:a.endNs}));
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:bStart}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:bEnd}});
  rerender(<HistoryPanel query={null} page={null} inFlight={{requestId:7n,query:a,navigation:"replace"}} busy failure={null} onLoad={onLoad} onPage={vi.fn()}/>);
  expect(screen.getByText(/正在查询范围（UTC）/)).toHaveTextContent("2026-08-10T00:00:00.000Z");
  expect(screen.queryByText("此范围内暂无历史记录。")).toBeNull();
  expect(screen.getByRole("button",{name:"查询历史"})).toBeDisabled();
  running.resolve();
  await waitFor(()=>expect(onLoad).toHaveBeenCalledTimes(1));
  rerender(<HistoryPanel query={a} page={page} inFlight={null} failure={null} onLoad={onLoad} onPage={vi.fn()}/>);
  expect(screen.getByLabelText("开始时间（UTC）")).toHaveValue(bStart.slice(0,16));
  expect(screen.getByLabelText("结束时间（UTC）")).toHaveValue(bEnd);
  expect(screen.getByText(/当前结果范围（UTC）/)).toHaveTextContent("2026-08-10T00:00:00.000Z");
  expect(screen.getByText(/当前结果范围（UTC）/)).toHaveTextContent("起点包含，终点不含");
  expect(screen.getByText("此范围内暂无历史记录。")).toBeTruthy();
});

it("locks query and page synchronously in one event, then releases after settlement",async()=>{
  const running=deferred(),onLoad=vi.fn(()=>running.promise),onPage=vi.fn();
  render(<HistoryPanel query={a} page={page} inFlight={null} failure={null} onLoad={onLoad} onPage={onPage}/>);
  const load=screen.getByRole("button",{name:"查询历史"}),next=screen.getByRole("button",{name:"下一页"});
  load.click();load.click();next.click();
  expect(onLoad).toHaveBeenCalledTimes(1);
  expect(onPage).not.toHaveBeenCalled();
  running.resolve();
  await waitFor(()=>{next.click();expect(onPage).toHaveBeenCalledWith("next-a");});
});

it("rejects negative or overflowing history bounds without changing shared export conversion",()=>{
  const onLoad=vi.fn();
  render(<HistoryPanel query={null} page={null} inFlight={null} failure={null} onLoad={onLoad} onPage={vi.fn()}/>);
  const start=screen.getByLabelText("开始时间（UTC）"),end=screen.getByLabelText("结束时间（UTC）");
  fireEvent.input(start,{target:{value:"1969-12-31T23:59:59.000"}});
  fireEvent.input(end,{target:{value:"1970-01-01T00:00:01.000"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  expect(onLoad).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(inputNs("1969-12-31T23:59:59.000")).toBe(-1_000_000_000n);
  fireEvent.input(start,{target:{value:"2300-01-01T00:00:00.000"}});
  fireEvent.input(end,{target:{value:"2300-01-02T00:00:00.000"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  expect(onLoad).not.toHaveBeenCalled();
});

it("keeps the last successful range visible while a different range is pending",()=>{
  const pending={startNs:a.startNs+10_000_000_000n,endNs:a.endNs+10_000_000_000n};
  render(<HistoryPanel query={a} page={page} inFlight={{requestId:8n,query:pending,navigation:"replace"}} busy failure={null} onLoad={vi.fn()} onPage={vi.fn()}/>);
  expect(screen.getByText(/当前结果范围（UTC）/)).toHaveTextContent("2026-08-10T00:00:00.000Z");
  expect(screen.getByText(/正在查询范围（UTC）/)).toHaveTextContent("2026-08-10T00:00:10.000Z");
  expect(screen.getByText("查询期间仍显示上次成功结果。")).toBeTruthy();
  expect(screen.getByRole("button",{name:"下一页"})).toBeDisabled();
});

it("preserves an invalid edited draft and its alert when a successful result arrives",()=>{
  const {rerender}=render(<HistoryPanel query={a} page={page} inFlight={null} failure={null} onLoad={vi.fn()} onPage={vi.fn()}/>);
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:"1969-12-31T00:00:00.000"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  expect(screen.getByRole("alert")).toBeTruthy();
  rerender(<HistoryPanel query={{...a,startNs:a.startNs+10_000_000_000n,endNs:a.endNs+10_000_000_000n}} page={page} inFlight={null} failure={null} onLoad={vi.fn()} onPage={vi.fn()}/>);
  expect(screen.getByLabelText("结束时间（UTC）")).toHaveValue("1969-12-31T00:00");
  expect(screen.getByRole("alert")).toBeTruthy();
});

it("identifies each returned value by UTC, run, sequence and ordinal even when the read failed",()=>{
  const one:HistoryPage={...page,batches:[{
    binding:{workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"pr",targetDevice:"T",physicalTarget:"T",buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"i".repeat(64),gitHead:"g".repeat(40),gitDirty:false,flashSessionId:"f",leaseId:"l",dwarfSha256:"d".repeat(64),svdSha256:null},
    groupId:"g",groupRevision:1n,runId:"run-9",sequence:7n,startOrdinal:21n,batchValueCount:1n,
    scheduledUnixNs:0n,scheduledAtUtc:"2026-08-10T00:00:00Z",capturedUnixNs:0n,capturedAtUtc:"2026-08-10T00:00:01.125Z",
    latencyNs:1n,actualRateHz:1,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,
    values:[{watch:{kind:"variable",expression:"counter"},status:"ERROR",typedValue:null,code:"READ_FAILED",definition:null}],
  }]};
  render(<HistoryPanel query={a} page={one} inFlight={null} failure={null} onLoad={vi.fn()} onPage={vi.fn()}/>);
  const row=screen.getAllByRole("row")[1];
  expect(row).toHaveTextContent("2026-08-10T00:00:01.125Z");
  expect(row).toHaveTextContent("counter");
  expect(row).toHaveTextContent("READ_FAILED");
  expect(row).toHaveTextContent("run-9");
  expect(row).toHaveTextContent("序号：7");
  expect(row).toHaveTextContent("值序位：21");
});
