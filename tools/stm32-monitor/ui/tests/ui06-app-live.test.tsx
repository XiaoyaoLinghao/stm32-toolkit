import {expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/preact";
import type {LiveHandlers,MonitorStatus,ObservationBinding,SampleBatch,WatchGroup} from "../src/api/contract";
import {App} from "../src/app";
import {sourcePage,sourceTreePage} from "./fixtures";

const controls=vi.hoisted(()=>({sockets:[] as LiveHandlers[]}));
vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
let preparedApi:object|null=null;
vi.mock("../src/api/client",()=>({createMonitorApi:()=>preparedApi}));
vi.mock("../src/api/live",()=>({openLive:(_origin:string,_cursor:bigint|null,handlers:LiveHandlers)=>{controls.sockets.push(handlers);return()=>{};}}));
const at="2026-08-10T00:00:01.123Z";
const binding:ObservationBinding={workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"probe",targetDevice:"STM32",physicalTarget:"target",buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,flashSessionId:"flash",leaseId:"lease",dwarfSha256:"dwarf",svdSha256:null};
const status:MonitorStatus={workspaceId:"w",sessionId:"s",project:{logicalProjectId:"p",name:"Project",targetDevice:"STM32"},firmware:{buildId:"build",elfSha256:"elf",inputSnapshotSha256:"snapshot",gitHead:"head",gitDirty:false,targetDevice:"STM32"},probe:{connected:true,probeId:"probe"},sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:"g",groupRevision:1n,runId:"run",lastSequence:null,bindingEpoch:4n,subscriberDrops:1n,historyDrops:2n,deadlineDrops:3n,serviceDrops:4n},probeConnected:true,samplingActive:true};
const group:WatchGroup={groupId:"g",name:"Old",description:"",intervalMs:250,items:[{kind:"variable",expression:"x"}],revision:1n,createdAtUtc:"now",updatedAtUtc:"now"};
const batch:SampleBatch={binding,groupId:"g",groupRevision:1n,runId:"run",sequence:1n,scheduledUnixNs:1n,scheduledAtUtc:"earlier",capturedUnixNs:2n,capturedAtUtc:at,latencyNs:2_500_000n,actualRateHz:4,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,values:[{watch:{kind:"variable",expression:"x"},status:"OK",typedValue:{expression:"x",typeName:"float",value:12.5,rawHex:"0x1",bitWidth:32},code:null,definition:null}]};
const ok=<T,>(data:T)=>({ok:true,data} as const);

it("immediately clears old run samples after a group revision ACK and keeps source identity honest",async()=>{
  controls.sockets.length=0;
  let finishGroups!:(value:ReturnType<typeof ok<{groups:WatchGroup[];nextCursor:null;revision:string}>>)=>void;
  const followup=new Promise<ReturnType<typeof ok<{groups:WatchGroup[];nextCursor:null;revision:string}>>>(resolve=>{finishGroups=resolve;});
  const groups=vi.fn().mockResolvedValueOnce(ok({groups:[group],nextCursor:null,revision:"0"})).mockReturnValueOnce(followup);
  const revised={...group,revision:2n,name:"New version"};
  preparedApi={status:vi.fn(async()=>ok(status)),probes:vi.fn(async()=>ok({probes:[]})),groups,
    sourceTree:vi.fn(async()=>ok(sourceTreePage(status))),
    sourceVariables:vi.fn(async()=>ok(sourcePage(status))),
    updateGroup:vi.fn(async()=>ok(revised))};
  render(<App/>);
  await screen.findByText("Project");
  await waitFor(()=>expect(controls.sockets).toHaveLength(1));
  act(()=>controls.sockets[0]!.onOpen());
  act(()=>controls.sockets[0]!.onEnvelope({event:{eventId:1n,type:"sample",data:{batch,serviceSubscriberDrops:0n}},subscriberDropped:0n}));
  expect(screen.getByText("12.5")).toBeTruthy();
  expect(screen.queryByText(/上次样本/)).toBeNull();
  const footer=within(document.querySelector(".workbench-footer")!);
  expect(footer.getByRole("region",{name:"采样状态汇总"})).toHaveTextContent("运行组 Old · 版本 1");
  expect(footer.getByRole("region",{name:"采样状态汇总"})).toHaveTextContent("丢弃合计 10");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"New version"}});
  fireEvent.click(screen.getByRole("button",{name:"保存观测组"}));
  await waitFor(()=>expect(groups).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  expect(screen.queryByText(/上次样本（UTC）/)).toBeNull();
  expect(screen.getByText(/运行组版本未在列表中核对；尚未收到样本/)).toBeTruthy();
  expect(screen.getByText(/当前运行：/)).toHaveTextContent("g");
  expect(screen.getByText(/当前运行：/)).not.toHaveTextContent("New version");
  expect(screen.queryByText("12.5")).toBeNull();
  const summary=footer.getByRole("region",{name:"采样状态汇总"});
  expect(summary).toHaveTextContent("运行组 未核对组 · 版本 1");
  expect(summary).toHaveTextContent("等待本轮样本");
  expect(summary).not.toHaveTextContent("New version");
  fireEvent.click(screen.getByRole("button",{name:"诊断详情"}));
  const diagnostics=screen.getByRole("dialog",{name:"诊断详情"});
  const stats=within(diagnostics).getByRole("region",{name:"采样状态汇总"});
  expect(stats).toHaveTextContent("尚未收到样本");
  expect(stats).not.toHaveTextContent("2500000 ns");
  expect(stats).toHaveTextContent("丢弃：订阅者 1 · 历史 2 · 截止时间 3 · 服务 4");
  expect(stats).toHaveTextContent("运行组 未核对组 · 版本 1");
  finishGroups(ok({groups:[revised],nextCursor:null,revision:"1"}));
});
