import {expect,it,vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/preact";
import {App} from "../src/app";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

function ok<T>(data:T){return {ok:true,data} as const;}
function err(code:string,message:string){return {ok:false,code,message} as const;}

function apiOverrides(){
  return{
    status:vi.fn(async()=>ok({workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,probe:{connected:true,probeId:"p1"},sampling:{state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:true,samplingActive:false})),
    probes:vi.fn(async()=>ok({probes:[{probeId:"p1",vendor:"ST",product:"ST-Link",boardName:null}]})),
    groups:vi.fn(async()=>ok({groups:[],nextCursor:null,revision:"0"})),
    variables:vi.fn(async()=>ok({items:[{selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]}],nextCursor:null})),
    registers:vi.fn(async()=>ok({items:[],nextCursor:null})),
    createGroup:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    updateGroup:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    deleteGroup:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    importGroups:vi.fn(async()=>ok([])),
    connect:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    reconnect:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    release:vi.fn(async()=>ok({released:true})),
    start:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    pause:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    resume:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    stop:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    history:vi.fn(async()=>ok({batches:[],valueCount:0n,nextCursor:null,serializedBytes:0n})),
    createExport:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    exportStatus:vi.fn(async()=>err("UNAVAILABLE","not configured")),
    downloadExport:vi.fn(async()=>err("UNAVAILABLE","not configured")),
  };
}

vi.mock("../src/api/client",()=>({
  createMonitorApi:()=>apiOverrides(),
}));

vi.mock("../src/api/live",()=>({openLive:()=>()=>{}}));

it("App retains the workbench and edited group draft when creation fails",async()=>{
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"新建观测组"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Motor"}});
  fireEvent.click(screen.getByRole("button",{name:"浏览变量与寄存器"}));
  fireEvent.input(screen.getByPlaceholderText("输入符号或寄存器前缀"),{target:{value:"counter"}});
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  await waitFor(()=>{expect(screen.getByRole("button",{name:"加入观测组草稿"})).toBeTruthy();});
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  fireEvent.click(screen.getByRole("button",{name:"创建观测组"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("UNAVAILABLE");
  expect(screen.getByRole("navigation",{name:"主导航"})).toBeTruthy();
  expect(screen.getByLabelText("名称")).toHaveValue("Motor");
  expect(screen.getByRole("button",{name:"重试上次操作"})).toBeTruthy();
});

it("App records a history query after loading history through the panel",async()=>{
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  const start=screen.getByLabelText("开始时间（UTC）") as HTMLInputElement;
  const end=screen.getByLabelText("结束时间（UTC）") as HTMLInputElement;
  fireEvent.input(start,{target:{value:"2026-08-10T00:00:00"}});
  fireEvent.input(end,{target:{value:"2026-08-10T00:00:02"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  await waitFor(()=>{expect(screen.getByText("此范围内暂无历史记录。")).toBeTruthy();});
});
