import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/preact";
import {App} from "../src/app";
import {statusResult,watchGroup} from "./fixtures";
import type {LiveHandlers,MonitorStatus,WatchGroup} from "../src/api/contract";

const chart=vi.hoisted(()=>({init:vi.fn(),resize:vi.fn(),dispose:vi.fn(),setOption:vi.fn(),on:vi.fn(),off:vi.fn()}));
const live=vi.hoisted(()=>({sockets:[] as LiveHandlers[]}));
vi.mock("echarts/core",()=>({init:chart.init,use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
vi.mock("../src/api/live",()=>({openLive:(_origin:string,_cursor:bigint|null,handlers:LiveHandlers)=>{
  void _origin;void _cursor;live.sockets.push(handlers);handlers.onOpen();return()=>{};
}}));

const ok=<T,>(data:T)=>({ok:true,data} as const);
const failed=(code:string)=>({ok:false,code,message:"service unavailable"} as const);
const deferred=<T,>()=>{
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(done=>{resolve=done;});
  return{promise,resolve};
};
const withProbe=(connected:boolean):MonitorStatus=>{
  const status=statusResult();
  return{...status,probe:{connected,probeId:connected?"p1":null},probeConnected:connected};
};
const group=(items:WatchGroup["items"]):WatchGroup=>({...watchGroup(),items});
const api=(status:MonitorStatus=withProbe(true),groups:WatchGroup[]=[])=>({
  status:vi.fn(async()=>ok(status)),
  probes:vi.fn(async()=>ok({probes:[{probeId:"p1",vendor:"Acme",product:"Probe",boardName:null}]})),
  groups:vi.fn(async()=>ok({groups,nextCursor:null,revision:"0"})),
  connect:vi.fn(async(_id:string)=>{void _id;return ok({connected:true});}),
  reconnect:vi.fn(async()=>ok({connected:true})),
  release:vi.fn(async()=>ok({released:true})),
});
let prepared:ReturnType<typeof api>|null=null;
vi.mock("../src/api/client",()=>({createMonitorApi:()=>prepared}));

beforeEach(()=>{
  live.sockets.length=0;
  chart.init.mockReturnValue(chart);
  vi.stubGlobal("requestAnimationFrame",(callback:FrameRequestCallback)=>{callback(0);return 1;});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
});
afterEach(()=>{prepared=null;vi.clearAllMocks();vi.unstubAllGlobals();});

const liveMain=()=>document.querySelector<HTMLElement>(".live-main")!;
const chartRegion=()=>document.querySelector<HTMLElement>(".chart-region")!;
const device=()=>document.querySelector<HTMLElement>("#device-details")!;
const openDevice=()=>fireEvent.click(screen.getByRole("button",{name:"连接与固件详情"}));

it("puts source and always reachable values above a chart that occupies no row until a variable or register curve is selected",async()=>{
  prepared=api(withProbe(true),[group([{kind:"variable",expression:"counter"},{kind:"register",registerPath:"TIM2.CNT"}])]);
  render(<App/>);
  await screen.findByText("Project");
  const main=liveMain();
  expect([...main.children].map(child=>child.className)).toEqual(expect.arrayContaining(["sampling-toolbar","live-source"]));
  expect(main.className).toContain("without-curves");
  expect(chartRegion()).not.toBeVisible();
  expect(screen.getByRole("region",{name:"最新数值"})).toBeVisible();
  expect(main.querySelector(".live-source")!.compareDocumentPosition(main.querySelector(".values-region")!)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(main.querySelector(".values-region")!.compareDocumentPosition(chartRegion())&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await waitFor(()=>expect(chart.init).toHaveBeenCalledTimes(1));

  fireEvent.click(screen.getAllByRole("button",{name:"显示曲线"})[0]!);
  expect(chartRegion()).toBeVisible();
  expect(screen.getByText("已选择曲线，等待采样数据。")).toBeVisible();
  expect(main.className).toContain("with-curves");
  fireEvent.click(screen.getByRole("button",{name:"放大波形"}));
  expect(main.className).toContain("chart-emphasized");
  expect(screen.getByRole("region",{name:"最新数值"})).toBeVisible();
  expect(screen.getByRole("button",{name:"隐藏曲线"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"隐藏曲线"}));
  expect(chartRegion()).not.toBeVisible();
  expect(main.className).not.toContain("chart-emphasized");
  fireEvent.click(screen.getAllByRole("button",{name:"显示曲线"})[1]!);
  expect(chartRegion()).toBeVisible();
  expect(main.className).not.toContain("chart-emphasized");
  expect(screen.getByText("已选择曲线，等待采样数据。")).toBeVisible();
  expect(chart.init).toHaveBeenCalledTimes(1);
  expect(chart.dispose).not.toHaveBeenCalled();
  expect(chart.resize).toHaveBeenCalled();
});

it("keeps the eight-curve cap and selected-curve removal available in the enlarged layout",async()=>{
  prepared=api(withProbe(true),[group(Array.from({length:9},(_,index)=>({kind:"variable",expression:`point${index}`})))]);
  render(<App/>);
  await screen.findByText("Project");
  for(let index=0;index<8;index++)fireEvent.click(screen.getAllByRole("button",{name:"显示曲线"})[0]!);
  expect(screen.getByText("已选择 8 / 8 条曲线")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"放大波形"}));
  expect(screen.getByRole("button",{name:"显示曲线"})).toBeDisabled();
  fireEvent.click(screen.getByText("已选曲线"));
  fireEvent.click(screen.getByRole("button",{name:/移除曲线.*point0/}));
  expect(screen.getAllByRole("button",{name:"显示曲线"})[0]).toBeEnabled();
  expect(screen.getByRole("region",{name:"最新数值"})).toBeVisible();
});

it.each([
  ["connect",false,"连接"],
  ["reconnect",true,"重新连接"],
  ["release",true,"释放探针"],
] as const)("closes the device drawer only after its adopted %s write ACK, before status followup settles",async(method,connected,label)=>{
  prepared=api(withProbe(connected));
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>> | ReturnType<typeof ok<{released:boolean}>>>();
  const statusFollowup=deferred<ReturnType<typeof ok<MonitorStatus>>>();
  prepared[method].mockReturnValueOnce(write.promise as never);
  prepared.status.mockReturnValueOnce(Promise.resolve(ok(withProbe(connected)))).mockReturnValueOnce(statusFollowup.promise);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:label}));
  expect(device()).toBeVisible();
  await act(async()=>write.resolve(method==="release"?ok({released:true}):ok({connected:true})));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"连接与固件详情"}));
  await act(async()=>statusFollowup.resolve(ok(withProbe(method!=="release"))));
});

it("keeps device context for a failed or unknown write",async()=>{
  prepared=api(withProbe(false));
  prepared.connect.mockResolvedValueOnce(failed("UNAVAILABLE") as never).mockResolvedValueOnce(failed("MONITOR_WRITE_RESULT_UNKNOWN") as never);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(document.querySelector(".operation-region")).toHaveTextContent("UNAVAILABLE"));
  expect(device()).toBeVisible();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(document.querySelector(".operation-region")).toHaveTextContent("MONITOR_WRITE_RESULT_UNKNOWN"));
  expect(device()).toBeVisible();
});

it("retains the first bound intent when a same-tick second connect is rejected by the controller gate",async()=>{
  prepared=api(withProbe(false));
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>>>();
  const statusFollowup=deferred<ReturnType<typeof ok<MonitorStatus>>>();
  prepared.connect.mockReturnValueOnce(write.promise);
  prepared.status.mockReturnValueOnce(Promise.resolve(ok(withProbe(false)))).mockReturnValueOnce(statusFollowup.promise);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  const connect=within(device()).getByRole("button",{name:"连接"});
  act(()=>{connect.click();expect(connect).toBeEnabled();connect.click();});
  expect(prepared.connect).toHaveBeenCalledTimes(1);
  await act(async()=>write.resolve(ok({connected:true})));
  await waitFor(()=>expect(device()).not.toBeVisible());
  await act(async()=>statusFollowup.resolve(ok(withProbe(true))));
});

it("does not close a reopened or switched drawer for an earlier write ACK",async()=>{
  prepared=api(withProbe(false));
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>>>();
  prepared.connect.mockReturnValueOnce(write.promise);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  fireEvent.click(within(device()).getByRole("button",{name:"关闭设备详情"}));
  openDevice();
  await act(async()=>write.resolve(ok({connected:true})));
  expect(device()).toBeVisible();
});

it("does not let a late ACK close a device drawer opened after switching through diagnostics",async()=>{
  prepared=api(withProbe(false));
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>>>();
  prepared.connect.mockReturnValueOnce(write.promise);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  fireEvent.click(screen.getByRole("button",{name:"操作问题 0"}));
  expect(screen.getByRole("dialog",{name:"诊断详情"})).toBeVisible();
  openDevice();
  await act(async()=>write.resolve(ok({connected:true})));
  expect(device()).toBeVisible();
});

it("preserves group navigation and its nested confirmation when a prior device write succeeds",async()=>{
  const first=watchGroup(),second={...first,groupId:"other",name:"Other"};
  prepared=api(withProbe(false),[first,second]);
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>>>();
  prepared.connect.mockReturnValueOnce(write.promise);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"Unsent"}});
  fireEvent.click(screen.getByRole("button",{name:"Other (1)"}));
  expect(screen.getByRole("dialog",{name:"未保存的观测组修改"})).toBeVisible();
  await act(async()=>write.resolve(ok({connected:true})));
  expect(screen.getByRole("dialog",{name:"观测组"})).toBeVisible();
  expect(screen.getByRole("dialog",{name:"未保存的观测组修改"})).toBeVisible();
  expect(screen.getByLabelText("名称")).toHaveValue("Unsent");
});

it("does not treat a diagnostic retry success as a new device-button success",async()=>{
  prepared=api(withProbe(false));
  prepared.connect.mockResolvedValueOnce(failed("UNAVAILABLE") as never).mockResolvedValueOnce(ok({connected:true}));
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"操作问题 1"})).toBeVisible());
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  fireEvent.click(screen.getByRole("button",{name:"确认重试上次写入"}));
  await waitFor(()=>expect(prepared!.connect).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect(screen.getByRole("button",{name:"操作问题 0"})).toBeVisible());
  openDevice();
  expect(device()).toBeVisible();
});

it("retires a stale diagnostic retry without closing the device drawer or resending a write",async()=>{
  prepared=api(withProbe(false));
  prepared.connect.mockResolvedValueOnce(failed("UNAVAILABLE") as never);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"操作问题 1"})).toBeVisible());
  await waitFor(()=>expect(live.sockets).toHaveLength(1));
  const changed={...withProbe(true),probe:{connected:true,probeId:"other"}};
  act(()=>live.sockets[0]!.onEnvelope({event:{eventId:1n,type:"state",data:{status:changed,stateRevision:1n,gap:false}},subscriberDropped:0n}));
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  fireEvent.click(screen.getByRole("button",{name:"重试上次操作"}));
  fireEvent.click(screen.getByRole("button",{name:"确认重试上次写入"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"操作问题 0"})).toBeVisible());
  expect(prepared.connect).toHaveBeenCalledTimes(1);
  openDevice();
  expect(device()).toBeVisible();
});

it("keeps a fatal access block authoritative over a pending device return",async()=>{
  prepared=api(withProbe(false));
  prepared.connect.mockResolvedValueOnce(failed("MONITOR_ACCESS_REJECTED") as never);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_ACCESS_REJECTED"));
  expect(document.querySelector("#device-details")).toBeNull();
  expect(prepared.status).toHaveBeenCalledTimes(1);
});

it("returns focus to the visible header device trigger when the original toolbar trigger is hidden",async()=>{
  prepared=api(withProbe(false));
  const write=deferred<ReturnType<typeof ok<{connected:boolean}>>>();
  prepared.connect.mockReturnValueOnce(write.promise);
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"查看采样设备详情"}));
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  await act(async()=>write.resolve(ok({connected:true})));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"连接与固件详情"}));
});

it("keeps the device drawer closed on a probe ACK even when its independent status GET fails",async()=>{
  prepared=api(withProbe(false));
  prepared.status.mockResolvedValueOnce(ok(withProbe(false))).mockResolvedValueOnce(failed("STATUS_DOWN") as never);
  render(<App/>);
  await screen.findByText("Project");
  openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(screen.getByRole("button",{name:"操作问题 1"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"操作问题 1"}));
  expect(screen.getByRole("dialog",{name:"诊断详情"})).toHaveTextContent("STATUS_DOWN");
});
