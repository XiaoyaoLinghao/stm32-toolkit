import {afterEach,expect,it,vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/preact";
import {App} from "../src/app";
import {watchGroup} from "./fixtures";

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
    variables:vi.fn(async()=>ok({items:[{selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[],group:{id:"cu:1",label:"main.c"}}],nextCursor:null})),
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

let preparedApi:object|null=null;
afterEach(()=>{preparedApi=null;});
vi.mock("../src/api/client",()=>({
  createMonitorApi:()=>preparedApi??apiOverrides(),
}));

vi.mock("../src/api/live",()=>({openLive:()=>()=>{}}));

function queuedNameInputAndSave(nextName:string,saveLabel:string):void{
  const input=screen.getByLabelText("名称") as HTMLInputElement;
  const oldSave=screen.getByRole("button",{name:saveLabel});
  input.value=nextName;
  input.dispatchEvent(new Event("input",{bubbles:true}));
  oldSave.click();
}

it("keeps a queued newer create draft after the old Save ACK and a failed list GET",async()=>{
  const created={...watchGroup(),groupId:"created",name:"A",revision:1n};
  const groups=vi.fn().mockResolvedValueOnce(ok({groups:[],nextCursor:null,revision:"0"}))
    .mockResolvedValue(err("GROUPS_DOWN","list unavailable"));
  const create=vi.fn(async()=>ok(created));
  const update=vi.fn(async()=>ok({...created,name:"B",revision:2n}));
  preparedApi={...apiOverrides(),groups,createGroup:create,updateGroup:update};
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.click(screen.getByRole("button",{name:"新建观测组"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"A"}});
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  await screen.findByText("main.c · 已加载 1 项");
  fireEvent.click(screen.getByText("main.c · 已加载 1 项"));
  await screen.findByRole("button",{name:"加入观测组草稿"});
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  queuedNameInputAndSave("B","创建观测组");
  expect(create).toHaveBeenCalledWith(expect.objectContaining({name:"A"}));
  await waitFor(()=>expect(groups).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("名称")).toHaveValue("B");
  expect(screen.getByText(/有未保存的修改/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"保存观测组"}));
  await waitFor(()=>expect(update).toHaveBeenCalledWith("created",expect.objectContaining({expectedRevision:1n,name:"B"})));
});

it("keeps a queued newer update draft and advances its revision after a failed list GET",async()=>{
  const existing=watchGroup(),saved={...existing,name:"A",revision:2n};
  const groups=vi.fn().mockResolvedValueOnce(ok({groups:[existing],nextCursor:null,revision:"0"}))
    .mockResolvedValue(err("GROUPS_DOWN","list unavailable"));
  const update=vi.fn().mockResolvedValueOnce(ok(saved)).mockResolvedValue(ok({...saved,name:"B",revision:3n}));
  preparedApi={...apiOverrides(),groups,updateGroup:update};
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"A"}});
  queuedNameInputAndSave("B","保存观测组");
  expect(update).toHaveBeenCalledWith(existing.groupId,expect.objectContaining({expectedRevision:1n,name:"A"}));
  await waitFor(()=>expect(groups).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("名称")).toHaveValue("B");
  expect(screen.getByText(/有未保存的修改/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"保存观测组"}));
  await waitFor(()=>expect(update).toHaveBeenCalledWith(existing.groupId,expect.objectContaining({expectedRevision:2n,name:"B"})));
});

it("App retains the workbench and edited group draft when creation fails",async()=>{
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.click(screen.getByRole("button",{name:"新建观测组"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Motor"}});
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.input(screen.getByPlaceholderText("输入符号或寄存器前缀"),{target:{value:"counter"}});
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  await waitFor(()=>{expect(screen.getByRole("button",{name:"加入观测组草稿"})).toBeTruthy();});
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  fireEvent.click(screen.getByRole("button",{name:"创建观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(await screen.findByRole("button",{name:"操作问题 1"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("UNAVAILABLE");
  expect(screen.getByRole("navigation",{name:"主导航"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"关闭诊断详情"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(screen.getByLabelText("名称")).toHaveValue("Motor");
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  expect(screen.getByRole("button",{name:"重试上次操作"})).toBeTruthy();
},15000);

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
