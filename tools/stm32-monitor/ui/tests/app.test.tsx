import {expect,it,vi,beforeEach} from "vitest";
import {render,screen} from "@testing-library/preact";
import {App} from "../src/app";

vi.mock("echarts/core",()=>({init:vi.fn(()=>null),use:vi.fn(),default:{init:vi.fn(()=>null),use:vi.fn()}}));
vi.mock("echarts/charts",()=>({LineChart:class{}}));
vi.mock("echarts/components",()=>({GridComponent:class{},TooltipComponent:class{},LegendComponent:class{}}));
vi.mock("echarts/renderers",()=>({CanvasRenderer:class{}}));

vi.mock("../src/api/client",()=>({
  createMonitorApi:()=>{
    return{
      status:vi.fn(async()=>({ok:true,data:{workspaceId:"workspace",sessionId:"session",project:{logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"},firmware:null,probe:{connected:false,probeId:null},sampling:{state:"IDLE",active:false,blockedCode:null,groupId:null,groupRevision:null,runId:null,lastSequence:null,bindingEpoch:0n,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n},probeConnected:false,samplingActive:false}})),
      probes:vi.fn(async()=>({ok:true,data:{probes:[]}})),
      groups:vi.fn(async()=>({ok:true,data:{groups:[],nextCursor:null,revision:"0"}})),
      variables:vi.fn(async()=>({ok:true,data:{items:[],nextCursor:null}})),
      registers:vi.fn(async()=>({ok:true,data:{items:[],nextCursor:null}})),
      createGroup:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      updateGroup:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      deleteGroup:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      importGroups:vi.fn(async()=>({ok:true,data:[]})),
      connect:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      reconnect:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      release:vi.fn(async()=>({ok:true,data:{released:true}})),
      start:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      pause:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      resume:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      stop:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      history:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      createExport:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      exportStatus:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
      downloadExport:vi.fn(async()=>({ok:false,code:"UNAVAILABLE",message:"not configured"})),
    };
  },
}));

vi.mock("../src/api/live",()=>({
  openLive:()=>()=>{},
}));

beforeEach(()=>{
  window.history.replaceState(null,"","/");
});

it("App renders the monitor shell with identity and probe panels after load",async()=>{
  render(<App/>);
  expect(await screen.findByText("Project")).toBeTruthy();
  screen.getByRole("button",{name:"连接与固件详情"}).click();
  expect(screen.getByLabelText("探针连接")).toBeTruthy();
  expect(screen.getByLabelText("观测组")).toBeTruthy();
  expect(screen.getByLabelText("最新数值")).toBeTruthy();
  screen.getByRole("button",{name:"浏览变量与寄存器"}).click();
  expect(screen.getByLabelText("变量与寄存器目录")).toBeTruthy();
  expect(screen.getByLabelText("采样状态汇总")).toBeTruthy();
});
