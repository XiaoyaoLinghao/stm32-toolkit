import {expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/preact";
import type {LiveHandlers} from "../src/api/contract";
import {App} from "../src/app";

const controls=vi.hoisted(()=>({sockets:[] as {handlers:LiveHandlers;close:ReturnType<typeof vi.fn>}[],statusCalls:vi.fn()}));
vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
const status=()=>({workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,
  probe:{connected:false,probeId:null},sampling:{state:"IDLE" as const,active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,
    subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:false,samplingActive:false});
const ok=<T,>(data:T)=>({ok:true,data} as const);
vi.mock("../src/api/client",()=>({createMonitorApi:()=>({
  status:async()=>{controls.statusCalls();return ok(status());},probes:async()=>ok({probes:[]}),groups:async()=>ok({groups:[],nextCursor:null,revision:"0"}),
  variables:async()=>ok({items:[],nextCursor:null}),registers:async()=>ok({items:[],nextCursor:null}),
})}));
vi.mock("../src/api/live",()=>({openLive:(_origin:string,_cursor:bigint|null,handlers:LiveHandlers)=>{
  const socket={handlers,close:vi.fn()};controls.sockets.push(socket);return socket.close;
}}));

it("shows connection and gap actions while preserving a draft and history navigation",async()=>{
  controls.sockets.length=0;controls.statusCalls.mockClear();
  render(<App/>);
  await screen.findByText("Project");
  expect(screen.getByText("正在连接实时数据")).toBeTruthy();
  expect(screen.queryByText("实时数据已连接")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  fireEvent.click(screen.getByRole("button",{name:"新建观测组"}));
  fireEvent.input(screen.getByLabelText("名称"),{target:{value:"未保存的草稿"}});
  act(()=>controls.sockets[0]!.handlers.onClosed());
  expect(screen.getByText("数据连接中断 · 等待重新连接")).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(screen.getByLabelText("名称")).toHaveValue("未保存的草稿");
  fireEvent.click(screen.getByRole("button",{name:"关闭观测组"}));
  fireEvent.click(screen.getByRole("button",{name:"操作问题 0"}));
  fireEvent.click(screen.getByRole("button",{name:"重新连接实时数据"}));
  await waitFor(()=>expect(controls.sockets).toHaveLength(2));
  expect(screen.getByRole("button",{name:"取消连接"})).toBeEnabled();
  act(()=>controls.sockets[1]!.handlers.onOpen());
  expect(screen.getByText("实时数据已连接")).toBeTruthy();
  expect(screen.getByText("非最新数据")).toBeTruthy();
  act(()=>controls.sockets[1]!.handlers.onEnvelope({event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:true,status:status()}},subscriberDropped:0n}));
  expect(screen.getByText("需要刷新状态")).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"刷新状态"}));
  await waitFor(()=>expect(screen.queryByText("需要刷新状态")).toBeNull());
  expect(controls.statusCalls).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole("button",{name:"关闭诊断详情"}));
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(screen.getByLabelText("名称")).toHaveValue("未保存的草稿");
});
