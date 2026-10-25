import {afterEach,expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {App} from "../src/app";
import {sourcePage,sourceTreePage,watchGroup} from "./fixtures";
import type {ApiResult,WatchGroup} from "../src/api/contract";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
vi.mock("../src/api/live",()=>({openLive:()=>()=>{}}));

const ok=<T,>(data:T)=>({ok:true,data} as const);
const failed=(code:string)=>({ok:false,code,message:"service unavailable"} as const);
const api=()=>({
  status:vi.fn(async()=>ok({workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,probe:{connected:true,probeId:"p1"},sampling:{state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:true,samplingActive:false})),
  probes:vi.fn(async()=>ok({probes:[]})),
  groups:vi.fn(async()=>ok({groups:[] as WatchGroup[],nextCursor:null,revision:"0"})),
  variables:vi.fn(async()=>ok({items:[{selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[],group:{id:"cu:1",label:"main.c"}}],nextCursor:null})),
  registers:vi.fn(async()=>ok({items:[],nextCursor:null})),
  sourceTree:vi.fn(async()=>ok(sourceTreePage())),
  sourceVariables:vi.fn(async()=>ok(sourcePage())),
  sourceSelection:vi.fn(async()=>failed("MONITOR_SOURCE_SELECTION_UNAVAILABLE")),
  history:vi.fn(async(_query:unknown)=>{void _query;return failed("HISTORY_DOWN");}),
  createGroup:vi.fn(async()=>failed("CREATE_DOWN")),
  importGroups:vi.fn(async()=>failed("IMPORT_DOWN")),
});
let prepared:ReturnType<typeof api>|null=null;
vi.mock("../src/api/client",()=>({createMonitorApi:()=>prepared}));
afterEach(()=>{prepared=null;});

it("opens the group drawer after a directory add and retains the unsaved draft across close and pages",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  expect(screen.getByLabelText("源码目录")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab",{name:"固件变量与寄存器"}));
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  fireEvent.click(await screen.findByText("main.c · 已加载 1 项"));
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  expect(screen.getByRole("dialog",{name:"观测组"})).toBeTruthy();
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Motor"}});
  fireEvent.click(screen.getByRole("button",{name:"收起目录"}));
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"展开目录"}));
  fireEvent.click(screen.getByRole("button",{name:"展开目录"}));
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(screen.getByLabelText("名称")).toHaveValue("Motor");
  expect(screen.getByRole("button",{name:"创建观测组"})).toBeEnabled();
  expect(prepared.createGroup).not.toHaveBeenCalled();
});

it("keeps a hidden history failure reachable through the persistent problem entry with its original retry",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:"2026-08-10T00:00:00.000"}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:"2026-08-10T00:00:02.000"}});
  fireEvent.click(screen.getByRole("button",{name:"查询历史"}));
  await waitFor(()=>expect(prepared!.history).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  fireEvent.click(screen.getByRole("button",{name:/操作问题 1/}));
  expect(screen.getByRole("dialog",{name:"诊断详情"})).toHaveTextContent("HISTORY_DOWN");
  fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  await waitFor(()=>expect(prepared!.history).toHaveBeenCalledTimes(2));
  expect(prepared.history.mock.calls[1]?.[0]).toEqual(prepared.history.mock.calls[0]?.[0]);
});

it("keeps the pending group navigation dialog visible across pages and gives only it keyboard focus",async()=>{
  prepared=api();
  const first=watchGroup(),second={...first,groupId:"other",name:"Other"};
  prepared.groups=vi.fn(async()=>ok({groups:[first,second],nextCursor:null,revision:"0"}));
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Unsent"}});
  act(()=>{
    screen.getByRole("button",{name:"Other (1)"}).click();
    screen.getByRole("button",{name:"关闭观测组"}).click();
  });
  const confirm=await screen.findByRole("dialog",{name:"未保存的观测组修改"});
  expect(document.activeElement===confirm||confirm.contains(document.activeElement)).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  expect(screen.getByRole("dialog",{name:"未保存的观测组修改"})).toBeTruthy();
  fireEvent.keyDown(document.activeElement!,{key:"Tab",shiftKey:true});
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"放弃修改并继续"}));
  fireEvent.keyDown(document.activeElement!,{key:"Escape"});
  expect(screen.queryByRole("dialog",{name:"未保存的观测组修改"})).toBeNull();
  expect(screen.getByRole("dialog",{name:"观测组"})).toBeTruthy();
  expect(screen.getByLabelText("名称")).toHaveValue("Unsent");
});

it("retains a parsed group import preview after ordinary drawer close and reopen",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.click(screen.getByRole("button",{name:"导入观测组"}));
  await userEvent.upload(screen.getByTestId("group-import-file"),new File([
    JSON.stringify({schemaVersion:1,groups:[{name:"Alpha",description:"",intervalMs:250,
      items:[{kind:"variable",expression:"a"}]}]}),
  ],"groups.json",{type:"application/json"}));
  expect(await screen.findByText(/Alpha · 1 个对象/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(screen.getByText(/Alpha · 1 个对象/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"确认导入"})).toBeEnabled();
  expect(prepared.importGroups).not.toHaveBeenCalled();
});

it("retains unsubmitted history and manual export ranges with the confirmation across page changes",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.input(screen.getByLabelText("开始时间（UTC）"),{target:{value:"2026-08-10T00:00:00.000"}});
  fireEvent.input(screen.getByLabelText("结束时间（UTC）"),{target:{value:"2026-08-10T00:00:02.000"}});
  fireEvent.input(screen.getByLabelText("导出开始时间（UTC）"),{target:{value:"2026-08-11T00:00:00.000"}});
  fireEvent.input(screen.getByLabelText("导出结束时间（UTC）"),{target:{value:"2026-08-11T00:00:03.000"}});
  fireEvent.click(screen.getByRole("button",{name:"创建 CSV 导出"}));
  expect(screen.getByRole("dialog",{name:"确认历史导出"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  expect(screen.getByRole("dialog",{name:"确认历史导出"})).toBeTruthy();
  expect(document.activeElement?.closest("[role='dialog']")).toHaveAttribute("aria-label","确认历史导出");
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  expect(screen.getByLabelText("开始时间（UTC）")).toHaveValue("2026-08-10T00:00");
  expect(screen.getByLabelText("结束时间（UTC）")).toHaveValue("2026-08-10T00:00:02.000");
  expect(screen.getByLabelText("导出开始时间（UTC）")).toHaveValue("2026-08-11T00:00");
  expect(screen.getByLabelText("导出结束时间（UTC）")).toHaveValue("2026-08-11T00:00:03.000");
  fireEvent.keyDown(document.activeElement!,{key:"Escape"});
  expect(screen.queryByRole("dialog",{name:"确认历史导出"})).toBeNull();
});

it("allows an acknowledgement-required register into the draft but blocks an unsampleable register",async()=>{
  const register={selector:"GPIO.IDR",sizeBits:32,access:"ro",readAction:"safe",resetValue:null,resetMask:null,
    fields:[],sampleable:true,requiresAccessAcknowledgement:true,group:{id:"svd:gpio",label:"GPIO"}};
  prepared={...api(),registers:vi.fn(async()=>ok({items:[
    {...register,selector:"GPIO.ODR",sampleable:false,requiresAccessAcknowledgement:false},
    register,
  ],nextCursor:null}))} as unknown as ReturnType<typeof api>;
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("tab",{name:"固件变量与寄存器"}));
  fireEvent.click(screen.getByRole("tab",{name:"寄存器"}));
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  fireEvent.click(await screen.findByText("GPIO · 已加载 2 项"));
  const add=screen.getAllByRole("button",{name:"加入观测组草稿"});
  expect(add[0]).toBeDisabled();
  expect(add[1]).toBeEnabled();
  expect(screen.getByText(/需要现有访问能力确认/)).toBeTruthy();
  fireEvent.click(add[1]!);
  expect(screen.getByRole("dialog",{name:"观测组"})).toHaveTextContent("GPIO.IDR");
});

it("keeps a write retry confirmation above diagnostics and Escape cancels only that confirmation",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("tab",{name:"固件变量与寄存器"}));
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  fireEvent.click(await screen.findByText("main.c · 已加载 1 项"));
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Motor"}});
  fireEvent.click(screen.getByRole("button",{name:"创建观测组"}));
  await waitFor(()=>expect(prepared!.createGroup).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  const inner=screen.getByRole("dialog",{name:"确认重试上次写入"});
  expect(document.activeElement===inner||inner.contains(document.activeElement)).toBe(true);
  fireEvent.keyDown(document.activeElement!,{key:"Tab",shiftKey:true});
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"取消"}));
  fireEvent.keyDown(document.activeElement!,{key:"Escape"});
  expect(screen.queryByRole("dialog",{name:"确认重试上次写入"})).toBeNull();
  expect(screen.getByRole("dialog",{name:"诊断详情"})).toBeTruthy();
  expect(prepared.createGroup).toHaveBeenCalledTimes(1);
});

it("recovers modal focus when a deferred group write disables the focused control",async()=>{
  prepared=api();
  let listed=false;
  prepared.groups=vi.fn(async()=>{
    const groups=listed?[watchGroup()]:[];
    listed=true;
    return ok({groups,nextCursor:null,revision:"0"});
  });
  let settle!:(value:ApiResult<WatchGroup>)=>void;
  const pending=new Promise<ApiResult<WatchGroup>>(resolve=>{settle=resolve;});
  prepared.createGroup=vi.fn(()=>pending) as unknown as ReturnType<typeof api>["createGroup"];
  const view=render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("tab",{name:"固件变量与寄存器"}));
  fireEvent.click(screen.getByRole("button",{name:"搜索/加载"}));
  fireEvent.click(await screen.findByText("main.c · 已加载 1 项"));
  fireEvent.click(screen.getByRole("button",{name:"加入观测组草稿"}));
  const dialog=screen.getByRole("dialog",{name:"观测组"});
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Motor"}});
  const create=screen.getByRole("button",{name:"创建观测组"});
  await waitFor(()=>expect(create).toBeEnabled());
  create.focus();
  expect(document.activeElement).toBe(create);
  fireEvent.click(create);
  await waitFor(()=>expect(create).toBeDisabled());
  // Edge drops focus to body when the write disables the focused control;
  // reproduce that body-focus loss explicitly in jsdom.
  (document.activeElement as HTMLElement|null)?.blur();
  await waitFor(()=>expect(dialog.contains(document.activeElement)).toBe(true));
  await act(async()=>{settle(ok(watchGroup()));});
  await waitFor(()=>expect(screen.getByRole("button",{name:"Group (1)"})).toBeTruthy());
  expect(dialog.contains(document.activeElement)).toBe(true);
  fireEvent.keyDown(document.body,{key:"Escape"});
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"观测组"})).toBeNull());
  await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole("button",{name:"编辑并保存"})));
  fireEvent.keyDown(document.body,{key:"Escape"});
  fireEvent.keyDown(document.body,{key:"Tab"});
  expect(screen.queryByRole("dialog",{name:"观测组"})).toBeNull();
  view.unmount();
  expect(()=>{
    fireEvent.keyDown(document.body,{key:"Escape"});
    fireEvent.keyDown(document.body,{key:"Tab"});
  }).not.toThrow();
});

it("exposes the Monitor brand as the page heading and the live source as a focusable named region",async()=>{
  prepared=api();
  render(<App/>);
  await screen.findByText("Project");
  const heading=screen.getByRole("heading",{level:1,name:"Monitor"});
  expect(heading).toBeVisible();
  const source=screen.getByRole("region",{name:"采样数据来源"});
  expect(source).toHaveAttribute("tabindex","0");
  expect(source).toHaveTextContent("下次目标预览；尚未开始采样。");
  source.focus();
  expect(document.activeElement).toBe(source);
});

it("keeps Tab and body Escape inside the topmost nested modal and cleans up after close",async()=>{
  prepared=api();
  const first=watchGroup(),second={...first,groupId:"other",name:"Other"};
  prepared.groups=vi.fn(async()=>ok({groups:[first,second],nextCursor:null,revision:"0"}));
  const view=render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Unsent"}});
  act(()=>{screen.getByRole("button",{name:"Other (1)"}).click();});
  const navigation=await screen.findByRole("dialog",{name:"未保存的观测组修改"});
  const keep=screen.getByRole("button",{name:"继续编辑"});
  keep.addEventListener("keydown",event=>event.preventDefault(),{once:true});
  fireEvent.keyDown(keep,{key:"Escape"});
  fireEvent.keyDown(keep,{key:"a"});
  expect(screen.getByRole("dialog",{name:"未保存的观测组修改"})).toBeTruthy();
  screen.getByRole("button",{name:"连接与固件详情"}).focus();
  expect(document.activeElement===navigation||navigation.contains(document.activeElement)).toBe(true);
  fireEvent.keyDown(document.body,{key:"Tab"});
  expect(document.activeElement).toBe(keep);
  const discard=screen.getByRole("button",{name:"放弃修改并继续"});
  fireEvent.keyDown(document.body,{key:"Tab",shiftKey:true});
  expect(document.activeElement).toBe(discard);
  fireEvent.keyDown(document.body,{key:"Escape"});
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"未保存的观测组修改"})).toBeNull());
  expect(screen.getByRole("dialog",{name:"观测组"})).toBeTruthy();
  expect(screen.getByLabelText("名称")).toHaveValue("Unsent");
  fireEvent.keyDown(document.body,{key:"Escape"});
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"观测组"})).toBeNull());
  await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole("button",{name:"编辑并保存"})));
  fireEvent.keyDown(document.body,{key:"Escape"});
  fireEvent.keyDown(document.body,{key:"Tab"});
  expect(screen.queryByRole("dialog",{name:"观测组"})).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"编辑并保存"}));
  view.unmount();
  expect(()=>{
    fireEvent.keyDown(document.body,{key:"Escape"});
    fireEvent.keyDown(document.body,{key:"Tab"});
  }).not.toThrow();
});
