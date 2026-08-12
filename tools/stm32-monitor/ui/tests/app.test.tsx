import {expect,it,vi,beforeEach} from "vitest";
import {render,screen} from "@testing-library/preact";
import {App} from "../src/app";

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
  expect(screen.getByLabelText("Probe")).toBeTruthy();
  expect(screen.getByLabelText("Watch groups")).toBeTruthy();
  expect(screen.getByLabelText("Live values")).toBeTruthy();
  expect(screen.getByLabelText("Catalog")).toBeTruthy();
  expect(screen.getByLabelText("Sampling status")).toBeTruthy();
});
