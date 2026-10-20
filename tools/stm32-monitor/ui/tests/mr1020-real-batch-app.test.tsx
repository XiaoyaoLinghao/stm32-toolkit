import {existsSync,readFileSync} from "node:fs";
import {resolve} from "node:path";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/preact";
import {App} from "../src/app";
import {parseLiveEnvelope} from "../src/api/live";
import {encodeJson} from "../src/api/wire";
import type {LiveHandlers,MonitorStatus,WatchGroup} from "../src/api/contract";
import {sourceTreePage} from "./fixtures";

const chart=vi.hoisted(()=>({init:vi.fn(),resize:vi.fn(),dispose:vi.fn(),setOption:vi.fn(),on:vi.fn(),off:vi.fn()}));
const live=vi.hoisted(()=>({sockets:[] as LiveHandlers[]}));
vi.mock("echarts/core",()=>({init:chart.init,use:vi.fn()}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{},DataZoomComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));
vi.mock("../src/api/live",async importOriginal=>{
  const actual=await importOriginal<typeof import("../src/api/live")>();
  return{...actual,openLive:(_origin:string,_cursor:bigint|null,handlers:LiveHandlers)=>{
    void _origin;void _cursor;live.sockets.push(handlers);handlers.onOpen();return()=>{};
  }};
});

const envelope=(operation:string,data:unknown)=>({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.4.0",
  monitorVersion:"0.4.0",ok:true,operation,code:"OK",message:"",data,details:{}});
const response=(operation:string,data:unknown)=>new Response(encodeJson(envelope(operation,data)));
const archived=resolve(process.cwd(),"tests/fixtures/mr1020_testtime_sanitized.jsonl");
const full=process.env.MONITOR_REAL_BATCHES_JSONL;
const lines=(path:string)=>readFileSync(path,"utf8").trim().split(/\r?\n/);

function setup(raw:readonly string[]){
  const first=JSON.parse(raw[0]!) as {binding:Record<string,string|boolean|null>;groupId:string;groupRevision:number;runId:string};
  const binding=first.binding;
  const group:WatchGroup={groupId:first.groupId,name:"Today's testtime",description:"",intervalMs:250,
    items:[{kind:"variable",expression:"testtime"}],revision:BigInt(first.groupRevision),
    createdAtUtc:"2026-10-20T00:18:00Z",updatedAtUtc:"2026-10-20T00:18:00Z"};
  const running:MonitorStatus={workspaceId:String(binding.workspaceId),sessionId:String(binding.sessionId),
    project:{logicalProjectId:String(binding.logicalProjectId),name:"Recorded MR",targetDevice:String(binding.targetDevice)},
    firmware:{buildId:String(binding.buildId),elfSha256:String(binding.elfSha256),
      inputSnapshotSha256:String(binding.inputSnapshotSha256),gitHead:String(binding.gitHead),
      gitDirty:false,targetDevice:String(binding.targetDevice)},
    probe:{connected:true,probeId:String(binding.probeId)},
    sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:first.groupId,
      groupRevision:BigInt(first.groupRevision),runId:first.runId,lastSequence:null,bindingEpoch:1n,
      subscriberDrops:0n,historyDrops:0n,deadlineDrops:2n,serviceDrops:0n},
    probeConnected:true,samplingActive:true};
  let current=running;
  const fetchMock=vi.fn((input:RequestInfo|URL):Promise<Response>=>{
    const path=new URL(String(input)).pathname;
    if(path==="/api/v1/status")return Promise.resolve(response("monitor.status",current));
    if(path==="/api/v1/probes")return Promise.resolve(response("monitor.probes.list",{probes:[]}));
    if(path==="/api/v1/groups")return Promise.resolve(response("monitor.groups.list",{groups:[group],nextCursor:null,revision:"1"}));
    if(path==="/api/v1/catalog/source-tree"){
      const page=sourceTreePage(current);
      return Promise.resolve(response("monitor.catalog.source.tree",{...page,
        identity:{...page.identity,sourceSnapshotSha256:String(binding.inputSnapshotSha256)}}));
    }
    if(path==="/api/v1/sampling/stop"){
      current={...current,sampling:{...current.sampling,state:"IDLE",active:false,
        groupId:null,groupRevision:null,runId:null},samplingActive:false};
      return Promise.resolve(response("monitor.sampling.stop",{stopped:true}));
    }
    throw new Error(`Unexpected ${path}`);
  });
  vi.stubGlobal("fetch",fetchMock);
  return{first,group};
}

function deliver(raw:string,eventId:number){
  const text=`{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.live","code":"OK","message":"","data":{"eventId":${eventId},"type":"sample","data":{"batch":${raw},"serviceSubscriberDrops":0}},"details":{"subscriberDropped":0}}`;
  const parsed=parseLiveEnvelope(text);
  expect(parsed.ok).toBe(true);
  if(parsed.ok)live.sockets[0]!.onEnvelope(parsed.data);
}

beforeEach(()=>{
  live.sockets.length=0;chart.init.mockReturnValue(chart);
  vi.stubGlobal("requestAnimationFrame",(callback:FrameRequestCallback)=>{callback(0);return 1;});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
});
afterEach(()=>{vi.clearAllMocks();vi.unstubAllGlobals();});

async function replay(raw:readonly string[]){
  const {first}=setup(raw);
  render(<App/>);
  await screen.findByText("Recorded MR");
  await waitFor(()=>expect(live.sockets).toHaveLength(1));
  act(()=>{for(let index=0;index<raw.length-1;index++)deliver(raw[index]!,index+1);});
  const before=JSON.parse(raw[raw.length-2]!) as {values:[{typedValue:{value:number}}]};
  expect(screen.getByRole("region",{name:"最新数值"})).toHaveTextContent(String(before.values[0].typedValue.value));
  expect(document.querySelector(".live-source")).toHaveTextContent("当前采样轮次");
  expect(document.querySelector(".chart-region")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"显示曲线"}));
  const chartHost=document.querySelector(".chart-host")!;
  await waitFor(()=>expect(chartHost).toHaveAttribute("data-chart-realized-points",String(raw.length-1)));
  fireEvent.click(screen.getByRole("button",{name:"隐藏曲线"}));
  fireEvent.click(screen.getByRole("button",{name:"显示曲线"}));
  expect(chartHost).toHaveAttribute("data-chart-realized-points",String(raw.length-1));
  act(()=>deliver(raw[raw.length-1]!,raw.length));
  const last=JSON.parse(raw[raw.length-1]!) as {values:[{typedValue:{value:number}}]};
  expect(screen.getByRole("region",{name:"最新数值"})).toHaveTextContent(String(last.values[0].typedValue.value));
  await waitFor(()=>expect(chartHost).toHaveAttribute("data-chart-realized-points",String(raw.length)));
  fireEvent.click(screen.getByRole("button",{name:"停止采样"}));
  await waitFor(()=>expect(document.querySelector(".live-source")).toHaveTextContent("已停止 · 上次采样（非最新）"));
  expect(document.querySelector(".live-source")).toHaveTextContent(first.runId);
  expect(screen.getByRole("region",{name:"最新数值"})).toHaveTextContent(String(last.values[0].typedValue.value));
  expect(chartHost).toHaveAttribute("data-chart-realized-points",String(raw.length));
}

it("replays recorded testtime wire batches through real client and App, including late curve and stopped snapshot",async()=>{
  await replay(lines(archived));
});

it.skipIf(full===undefined||!existsSync(full))("replays all 293 sanitized batches from today's read-only SQLite audit",async()=>{
  const raw=lines(full!);
  expect(raw).toHaveLength(293);
  await replay(raw);
});
