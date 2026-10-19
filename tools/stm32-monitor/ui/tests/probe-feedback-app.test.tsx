import {readFileSync} from "node:fs";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/preact";
import {App} from "../src/app";
import {encodeJson} from "../src/api/wire";
import type {LiveHandlers,MonitorStatus} from "../src/api/contract";
import {statusResult} from "./fixtures";

const chart=vi.hoisted(()=>({init:vi.fn(),resize:vi.fn(),dispose:vi.fn(),setOption:vi.fn(),on:vi.fn(),off:vi.fn()}));
const live=vi.hoisted(()=>({sockets:[] as LiveHandlers[]}));
vi.mock("echarts/core",()=>({init:chart.init,use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
vi.mock("../src/api/live",()=>({openLive:(_origin:string,_cursor:bigint|null,handlers:LiveHandlers)=>{
  void _origin;void _cursor;live.sockets.push(handlers);handlers.onOpen();return()=>{};
}}));

type WireEnvelope={protocol:string;toolkitVersion:string;monitorVersion:string;ok:boolean;operation:string;code:string;message:string;data:unknown;details:Record<string,unknown>};
const fixture=JSON.parse(readFileSync(process.env.STM32_MONITOR_WIRE_FIXTURE!,"utf8")) as {connect:WireEnvelope;reconnect:WireEnvelope};
const envelope=(operation:string,data:unknown):WireEnvelope=>({...fixture.connect,operation,data});
const response=(value:unknown)=>new Response(encodeJson(value));
const deferred=<T,>()=>{let resolve!:(value:T)=>void;let reject!:(error:Error)=>void;
  const promise=new Promise<T>((done,fail)=>{resolve=done;reject=fail;});return{promise,resolve,reject};};
const withProbe=(connected:boolean):MonitorStatus=>({...statusResult(),
  probe:{connected,probeId:connected?"probe":null},probeConnected:connected});
const device=()=>document.querySelector<HTMLElement>("#device-details")!;
const openDevice=()=>fireEvent.click(screen.getByRole("button",{name:"连接与固件详情"}));
const connectedLive=()=>act(()=>live.sockets[0]!.onEnvelope({
  event:{eventId:1n,type:"state",data:{stateRevision:1n,gap:false,status:withProbe(true)}},subscriberDropped:0n,
}));

function installFetch(initialConnected:boolean,write:Promise<Response>|((path:string)=>Promise<Response>),followup?:Promise<Response>){
  let statusCalls=0;
  const fetchMock=vi.fn((input:RequestInfo|URL):Promise<Response>=>{
    const path=new URL(String(input)).pathname;
    if(path==="/api/v1/status")return ++statusCalls===1
      ?Promise.resolve(response(envelope("monitor.status",withProbe(initialConnected))))
      :followup??Promise.resolve(response(envelope("monitor.status",withProbe(true))));
    if(path==="/api/v1/probes")return Promise.resolve(response(envelope("monitor.probes.list",{
      probes:[{probeId:"probe",vendor:"Acme",product:"Probe",boardName:null}],
    })));
    if(path==="/api/v1/groups")return Promise.resolve(response(envelope("monitor.groups.list",{
      groups:[],nextCursor:null,revision:"0",
    })));
    if(path.startsWith("/api/v1/probe/"))return typeof write==="function"?write(path):write;
    throw new Error(`Unexpected ${path}`);
  });
  vi.stubGlobal("fetch",fetchMock);
  return fetchMock;
}

beforeEach(()=>{
  live.sockets.length=0;
  chart.init.mockReturnValue(chart);
  vi.stubGlobal("requestAnimationFrame",(callback:FrameRequestCallback)=>{callback(0);return 1;});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
});
afterEach(()=>{vi.clearAllMocks();vi.unstubAllGlobals();});

it("replaces an earlier probe result with the next adopted operation",async()=>{
  installFetch(true,path=>Promise.resolve(response(path.endsWith("/reconnect")?{
    ...fixture.reconnect,ok:false,code:"PROBE_UNAVAILABLE",message:"probe unavailable",data:null,
  }:envelope("monitor.probe.release",{released:true}))));
  render(<App/>);await screen.findByText("Project");openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"重新连接"}));
  await waitFor(()=>expect(within(device()).getByRole("alert")).toHaveTextContent("PROBE_UNAVAILABLE"));
  fireEvent.click(within(device()).getByRole("button",{name:"释放探针"}));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(screen.getByRole("status",{name:"探针操作结果"})).toHaveTextContent("探针释放成功");
  openDevice();
  expect(within(device()).queryByRole("alert")).not.toBeInTheDocument();
});

it("keeps a live connected state separate from a valid parsed connect ACK, then reports success and returns focus",async()=>{
  const write=deferred<Response>(),followup=deferred<Response>();
  const fetchMock=installFetch(false,write.promise,followup.promise);
  render(<App/>);await screen.findByText("Project");openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));
  expect(within(device()).getByRole("status")).toHaveTextContent(/连接探针.*正在处理/);
  connectedLive();
  expect(within(device()).getByText("（已连接）")).toBeVisible();
  expect(device()).toBeVisible();
  expect(screen.queryByText("探针连接成功")).not.toBeInTheDocument();
  await act(async()=>write.resolve(response(fixture.connect)));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(screen.getByRole("status",{name:"探针操作结果"})).toHaveTextContent("探针连接成功");
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"连接与固件详情"}));
  expect(fetchMock.mock.calls.some(([input])=>new URL(String(input)).pathname==="/api/v1/status")).toBe(true);
  await act(async()=>followup.resolve(response(envelope("monitor.status",withProbe(true)))));
  fireEvent.click(screen.getByRole("button",{name:"关闭探针操作结果"}));
  expect(screen.queryByRole("status",{name:"探针操作结果"})).not.toBeInTheDocument();
});

it.each(["malformed","transport"] as const)("does not convert live connected state into a %s connect ACK",async(kind)=>{
  const write=deferred<Response>();installFetch(false,write.promise);
  render(<App/>);await screen.findByText("Project");openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:"连接"}));connectedLive();
  if(kind==="malformed"){
    const data={...(fixture.connect.data as Record<string,unknown>)};delete data.svdReadableRegions;
    await act(async()=>write.resolve(response({...fixture.connect,data})));
  }else await act(async()=>write.reject(new Error("offline transport failure")));
  expect(device()).toBeVisible();
  expect(screen.queryByRole("status",{name:"探针操作结果"})).not.toBeInTheDocument();
  const code=kind==="malformed"?"MONITOR_RESPONSE_INVALID":"MONITOR_TRANSPORT_FAILED";
  await waitFor(()=>expect(within(device()).getByRole("alert")).toHaveTextContent(code));
  expect(within(device()).getByRole("alert")).toHaveTextContent("未确认");
  fireEvent.click(within(device()).getByRole("button",{name:"查看操作诊断"}));
  expect(screen.getByRole("dialog",{name:"诊断详情"})).toBeVisible();
  expect(within(screen.getByRole("dialog",{name:"诊断详情"})).getByRole("button",{name:"刷新核对"})).toBeVisible();
});

it.each([
  ["reconnect",true,"重新连接","探针重新连接成功",fixture.reconnect],
  ["release",true,"释放探针","探针释放成功",envelope("monitor.probe.release",{released:true})],
] as const)("reports parsed %s ACK success independently of a later status failure",async(method,connected,label,success,ack)=>{
  const write=deferred<Response>();
  const statusFailure={...fixture.connect,ok:false,operation:"monitor.status",code:"STATUS_DOWN",message:"status offline",data:null};
  installFetch(connected,write.promise,Promise.resolve(response(statusFailure)));
  render(<App/>);await screen.findByText("Project");openDevice();
  fireEvent.click(within(device()).getByRole("button",{name:label}));
  await act(async()=>write.resolve(response(ack)));
  await waitFor(()=>expect(device()).not.toBeVisible());
  expect(screen.getByRole("status",{name:"探针操作结果"})).toHaveTextContent(success);
  await waitFor(()=>expect(screen.getByRole("button",{name:"操作问题 1"})).toBeVisible());
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"连接与固件详情"}));
});
