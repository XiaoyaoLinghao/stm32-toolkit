import {expect,it,vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/preact";
import {App} from "../src/app";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

function ok<T>(data:T){return {ok:true,data} as const;}
function err(code:string,message:string){return {ok:false,code,message} as const;}

function apiOverrides(){
  return{
    status:vi.fn(async()=>ok({workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,probe:{connected:false,probeId:null},sampling:{state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:false,samplingActive:false})),
    probes:vi.fn(async()=>ok({probes:[]})),
    groups:vi.fn(async()=>ok({groups:[],nextCursor:null,revision:"0"})),
    variables:vi.fn(async()=>ok({items:[],nextCursor:null})),
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

it("App renders a blocking error when a create-group request fails",async()=>{
  render(<App/>);
  await screen.findByText("Project");
  fireEvent.click(screen.getByRole("button",{name:"New group"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("UNAVAILABLE");
});

it("App records a history query after loading history through the panel",async()=>{
  render(<App/>);
  await screen.findByText("Project");
  const start=screen.getByLabelText("History start") as HTMLInputElement;
  const end=screen.getByLabelText("History end") as HTMLInputElement;
  fireEvent.input(start,{target:{value:"2026-08-10T00:00:00"}});
  fireEvent.input(end,{target:{value:"2026-08-10T00:00:02"}});
  fireEvent.click(screen.getByRole("button",{name:"Load history"}));
  await waitFor(()=>{expect(screen.getByText("No history rows for this query.")).toBeTruthy();});
});
