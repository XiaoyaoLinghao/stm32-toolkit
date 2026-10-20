import {readFileSync} from "node:fs";
import {resolve} from "node:path";
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

const wire=JSON.parse(readFileSync(resolve(process.cwd(),"../tests/fixtures/source_catalog_envelope.json"),"utf8"));
const envelope=(operation:string,data:unknown)=>({...wire,operation,data});
const response=(value:unknown)=>new Response(encodeJson(value),{headers:{"Content-Type":"application/json"}});
const connected=():MonitorStatus=>{const base=statusResult();return{...base,probe:{connected:true,probeId:"probe"},probeConnected:true,
  firmware:{buildId:"build",elfSha256:"e".repeat(64),inputSnapshotSha256:"b".repeat(64),gitHead:"a".repeat(40),
    gitDirty:false,targetDevice:base.project.targetDevice}};};
const catalog=(status:MonitorStatus)=>({...wire,data:{...wire.data,
  identity:{...wire.data.identity,buildId:status.firmware?.buildId??null,elfSha256:status.firmware?.elfSha256??null},
  items:wire.data.items.map((item:Record<string,unknown>)=>({...item,canAdd:status.probe.connected,
    reason:status.probe.connected?null:"probe_required"}))}});
const fileId="1".repeat(64),scopeId="2".repeat(64);
const sourceTree=(status:MonitorStatus,parent:string|null)=>envelope("monitor.catalog.source.tree",{
 ...catalog(status).data,total:1,nextCursor:null,items:parent===null?
  [{kind:"file",id:fileId,parentId:null,file:"Src/main.c",name:"main.c",variableCount:1,scopeCount:1}]:
  [{kind:"scope",id:scopeId,parentId:fileId,file:"Src/main.c",name:"global",function:null,line:null,variableCount:1}],
});
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done;});return{promise,resolve};};

function installFetch(status:MonitorStatus,selection?:Promise<Response>){
  const calls:string[]=[];
  const fetchMock=vi.fn((input:RequestInfo|URL):Promise<Response>=>{
    const request=new URL(String(input)),path=request.pathname;calls.push(path);
    if(path==="/api/v1/status")return Promise.resolve(response(envelope("monitor.status",status)));
    if(path==="/api/v1/probes")return Promise.resolve(response(envelope("monitor.probes.list",{probes:[]})));
    if(path==="/api/v1/groups")return Promise.resolve(response(envelope("monitor.groups.list",{groups:[],nextCursor:null,revision:"0"})));
    if(path==="/api/v1/catalog/source-tree")return Promise.resolve(response(sourceTree(status,request.searchParams.get("parentId"))));
    if(path==="/api/v1/catalog/source-variables")return Promise.resolve(response(catalog(status)));
    if(path==="/api/v1/catalog/source-selection")return selection??Promise.resolve(response(envelope(
      "monitor.catalog.source.selection",{catalogId:wire.data.catalogId,item:{kind:"variable",expression:"counter"}})));
    throw new Error(`Unexpected ${path}`);
  });
  vi.stubGlobal("fetch",fetchMock);
  return calls;
}

beforeEach(()=>{
  live.sockets.length=0;chart.init.mockReturnValue(chart);
  vi.stubGlobal("requestAnimationFrame",(callback:FrameRequestCallback)=>{callback(0);return 1;});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
});
afterEach(()=>{vi.clearAllMocks();vi.unstubAllGlobals();});

it("autoloads the shared source wire page without a probe and expands file and scope",async()=>{
  const calls=installFetch(statusResult());render(<App/>);
  expect(await screen.findByText("已加载 1 / 1 个文件",{exact:false})).toBeVisible();
  expect(calls).toContain("/api/v1/catalog/source-tree");
  const region=screen.getByRole("region",{name:"源码目录结果"});
  fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
  fireEvent.click(await within(region).findByRole("button",{name:"展开 global"}));
  expect(await within(region).findByText("counter")).toBeVisible();
  expect(within(region).getByRole("button",{name:"加入观测组草稿 counter"})).toBeDisabled();
});

it("sends an explicit root refresh through App, controller, and the real client",async()=>{
  installFetch(statusResult());render(<App/>);
  await screen.findByRole("region",{name:"源码目录结果"});
  fireEvent.click(screen.getByRole("button",{name:"刷新源码目录"}));
  await waitFor(()=>expect(vi.mocked(fetch).mock.calls.some(([input])=>{
    const request=new URL(String(input));
    return request.pathname==="/api/v1/catalog/source-tree"&&request.searchParams.get("refresh")==="1"&&
      !request.searchParams.has("catalogId")&&!request.searchParams.has("cursor")&&
      !request.searchParams.has("parentId");
  })).toBe(true));
});

it("uses a fresh real-client selection ACK for the draft and never reopens a drawer after a view switch",async()=>{
  const status=connected(),late=deferred<Response>(),calls=installFetch(status,late.promise);
  render(<App/>);
  const region=await screen.findByRole("region",{name:"源码目录结果"});
  await waitFor(()=>expect(within(region).getByRole("button",{name:"展开 Src/main.c"})).toBeVisible());
  fireEvent.click(within(region).getByRole("button",{name:"展开 Src/main.c"}));
  fireEvent.click(await within(region).findByRole("button",{name:"展开 global"}));
  const add=await within(region).findByRole("button",{name:"加入观测组草稿 counter"});
  expect(add).toBeEnabled();
  fireEvent.click(add);
  await waitFor(()=>expect(calls).toContain("/api/v1/catalog/source-selection"));
  fireEvent.click(screen.getByRole("button",{name:"历史记录"}));
  await act(async()=>late.resolve(response(envelope("monitor.catalog.source.selection",
    {catalogId:wire.data.catalogId,item:{kind:"variable",expression:"counter"}}))));
  const groupDrawer=[...document.querySelectorAll<HTMLElement>(".workbench-drawer")]
    .find(element=>element.getAttribute("aria-label")==="观测组")!;
  expect(groupDrawer).not.toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"实时监视"}));
  await waitFor(()=>expect(within(region).getByText("已加入组草稿（尚未保存）")).toBeVisible());
  fireEvent.click(screen.getByRole("button",{name:"编辑并保存"}));
  expect(within(screen.getByRole("dialog",{name:"观测组"})).getByText("counter")).toBeVisible();
});
