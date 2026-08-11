import {expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {initialState,reducer} from "../src/state/reducer";
import {statusResult,watchGroup} from "./fixtures";
import {parseLossless} from "../src/api/wire";
import type {MonitorAction,MonitorState} from "../src/state/model";
import type {MonitorApi} from "../src/api/contract";

const ok=<T>(data:T)=>({ok:true,data} as const);
const err=(code:string,message:string)=>({ok:false,code,message} as const);

function makeApi(overrides:Partial<MonitorApi>={}):MonitorApi{
  const group=watchGroup();
  return{
    status:vi.fn(async()=>ok(statusResult())),
    probes:vi.fn(async()=>ok({probes:[]})),
    variables:vi.fn(async()=>ok({items:[],nextCursor:null})),
    registers:vi.fn(async()=>ok({items:[],nextCursor:null})),
    groups:vi.fn(async()=>ok({groups:[group],nextCursor:null,revision:"0"})),
    createGroup:vi.fn(async()=>ok(group)),
    updateGroup:vi.fn(async()=>ok(group)),
    deleteGroup:vi.fn(async()=>ok({groupId:group.groupId,deleted:true})),
    importGroups:vi.fn(async()=>ok([group])),
    connect:vi.fn(async()=>err("PROBE_UNAVAILABLE","no probe")),
    reconnect:vi.fn(async()=>ok({ok:true}) as never),
    release:vi.fn(async()=>ok({released:true})),
    start:vi.fn(async()=>ok({groupId:group.groupId,groupRevision:1n,runId:"run",intervalMs:250})),
    pause:vi.fn(async()=>ok({paused:true})),
    resume:vi.fn(async()=>ok({resumed:true})),
    stop:vi.fn(async()=>ok({stopped:false})),
    history:vi.fn(async()=>ok({batches:[],valueCount:0n,nextCursor:null,serializedBytes:0n})),
    createExport:vi.fn(async()=>ok({exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    exportStatus:vi.fn(async()=>ok({exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    downloadExport:vi.fn(async()=>err("EXPORT_GONE","expired")),
    ...overrides,
  };
}

function harness(api:MonitorApi){
  let state:MonitorState=initialState;
  const actions:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);actions.push(action);};
  const controller=createController(api,dispatch,()=>state);
  return{controller,state:()=>state,actions,dispatch};
}

it("loadInitial dispatches initial.loaded and opens live",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.loadInitial();
  expect(actions.some(a=>a.type==="initial.loaded")).toBe(true);
  expect(actions.some(a=>a.type==="transport.open")).toBe(true);
});

it("loadInitial fails when first groups page fails",async()=>{
  const api=makeApi({groups:vi.fn(async()=>err("GROUPS_FAILED","cannot list"))});
  const {controller,actions}=harness(api);
  await controller.loadInitial();
  expect(actions.some(a=>a.type==="request.failed"&&a.scope==="initial")).toBe(true);
});

it("loadInitial follows group cursors",async()=>{
  const group=watchGroup();
  const calls:Parameters<MonitorApi["groups"]>[]=[];
  const api=makeApi({groups:vi.fn(async(cursor)=>{
    calls.push(cursor as never);
    return cursor===undefined
      ?ok({groups:[group],nextCursor:"c1",revision:"0"})
      :ok({groups:[{...group,groupId:"group2"}],nextCursor:null,revision:"1"});
  })});
  const {controller,actions}=harness(api);
  await controller.loadInitial();
  expect(calls.length).toBe(2);
  const loaded=actions.find(a=>a.type==="initial.loaded");
  if(loaded!==undefined&&loaded.type==="initial.loaded")expect(loaded.groups.length).toBe(2);
});

it("refreshStatus and refreshProbes dispatch loaded actions",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.refreshStatus();
  await controller.refreshProbes();
  expect(actions.some(a=>a.type==="status.loaded")).toBe(true);
  expect(actions.some(a=>a.type==="probes.loaded")).toBe(true);
});

it("refreshStatus fails and dispatches request.failed",async()=>{
  const api=makeApi({status:vi.fn(async()=>err("STATUS_FAILED","down"))});
  const {controller,actions}=harness(api);
  await controller.refreshStatus();
  const failed=actions.find(a=>a.type==="request.failed"&&a.scope==="status");
  expect(failed).toBeDefined();
  if(failed!==undefined&&failed.type==="request.failed")expect(failed.code).toBe("STATUS_FAILED");
});

it("connectProbe succeeds and refreshes status",async()=>{
  const group=watchGroup();
  const api=makeApi({
    connect:vi.fn(async()=>ok({logicalProjectId:"p",workspaceId:"w",observationSessionId:"o",flashSessionId:"f",leaseId:"l",probeId:"p1",targetDevice:"T",debugTarget:"cortex_m",buildId:"b".repeat(64),elfSha256:"e".repeat(64),elfSize:4096,elfPath:"build/fw.elf",inputSnapshotSha256:"i".repeat(64),gitHead:"g".repeat(40),gitDirty:false,confirmedAtUtc:"2026-08-10T00:00:00Z",memoryRegions:[{name:"FLASH",origin:0x08000000,length:0x10000,attributes:"rx"}]})),
  });
  const {controller,actions}=harness(api);
  await controller.connectProbe("p1");
  expect(actions.some(a=>a.type==="request.cleared"&&a.scope==="probe.connect")).toBe(true);
  void group;
});

it("reconnectProbe fails and dispatches request.failed",async()=>{
  const api=makeApi({reconnect:vi.fn(async()=>err("RECONNECT_FAILED","cannot"))});
  const {controller,actions}=harness(api);
  await controller.reconnectProbe();
  const failed=actions.find(a=>a.type==="request.failed"&&a.scope==="probe.reconnect");
  expect(failed).toBeDefined();
});

it("releaseProbe succeeds and refreshes status",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.releaseProbe();
  expect(actions.some(a=>a.type==="request.cleared"&&a.scope==="probe.release")).toBe(true);
});

it("searchCatalog dispatches catalog.loaded for variables",async()=>{
  const descriptor={selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
  const status=statusResult();
  status.sampling.bindingEpoch=3n;
  const api=makeApi({status:vi.fn(async()=>ok(status)),variables:vi.fn(async()=>ok({items:[descriptor],nextCursor:null}))});
  const {controller,actions,state}=harness(api);
  state().status=status;
  await controller.searchCatalog("variables","counter");
  const loaded=actions.find(a=>a.type==="catalog.loaded");
  expect(loaded).toBeDefined();
  if(loaded!==undefined&&loaded.type==="catalog.loaded")expect(loaded.items.length).toBe(1);
});

it("nextCatalog pages through variables",async()=>{
  const descriptor={selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
  const status=statusResult();
  status.sampling.bindingEpoch=3n;
  const api=makeApi({
    status:vi.fn(async()=>ok(status)),
    variables:vi.fn(async(_q,cursor)=>cursor===undefined?ok({items:[descriptor],nextCursor:"c2"}):ok({items:[{...descriptor,selector:"other"}],nextCursor:null})),
  });
  const {controller,actions,state}=harness(api);
  state().status=status;
  await controller.searchCatalog("variables","counter");
  await controller.nextCatalog("variables");
  const loaded=actions.filter(a=>a.type==="catalog.loaded");
  expect(loaded.length).toBe(2);
});

it("createGroup succeeds and refreshes groups",async()=>{
  const api=makeApi();
  const {controller,actions,state}=harness(api);
  state().groupDraft={...state().groupDraft,name:"New",items:[{kind:"variable",expression:"x"}]};
  await controller.createGroup();
  expect(actions.some(a=>a.type==="groups.loaded")).toBe(true);
});

it("saveGroup succeeds for existing groups",async()=>{
  const group=watchGroup();
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.saveGroup({sourceGroupId:group.groupId,expectedRevision:1n,name:"Renamed",description:"",intervalMs:250,items:[{kind:"variable",expression:"counter"}]});
  expect(actions.some(a=>a.type==="groups.loaded")).toBe(true);
});

it("saveGroup no-ops for new groups without sourceGroupId",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.saveGroup({sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]});
  expect(actions.some(a=>a.type==="request.started")).toBe(false);
});

it("deleteGroup succeeds for existing groups",async()=>{
  const group=watchGroup();
  const api=makeApi();
  const {controller,actions,state}=harness(api);
  state().groups=[group];
  await controller.deleteGroup(group.groupId);
  expect(actions.some(a=>a.type==="groups.loaded")).toBe(true);
});

it("importGroups succeeds for valid documents",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  const document=parseLossless('{"schemaVersion":1,"groups":[]}');
  await controller.importGroups(document);
  expect(actions.some(a=>a.type==="groups.loaded")).toBe(true);
});

it("startSampling and pause/resume/stop refresh status",async()=>{
  const group=watchGroup();
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.startSampling(group.groupId,1n);
  await controller.pauseSampling();
  await controller.resumeSampling();
  await controller.stopSampling();
  const statusCount=actions.filter(a=>a.type==="status.loaded").length;
  expect(statusCount).toBeGreaterThanOrEqual(4);
});

it("loadHistory dispatches history.loaded on success",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.loadHistory({startNs:0n,endNs:1000n});
  const loaded=actions.find(a=>a.type==="history.loaded");
  expect(loaded).toBeDefined();
  if(loaded!==undefined&&loaded.type==="history.loaded")expect(loaded.query.startNs).toBe(0n);
});

it("nextHistory pages without a cursor and fails when history errors",async()=>{
  const query={startNs:0n,endNs:1000n};
  const api=makeApi({history:vi.fn(async()=>err("HISTORY_FAILED","nope"))});
  const {controller,actions,state}=harness(api);
  state().history.query=query;
  await controller.nextHistory("c1");
  const failed=actions.find(a=>a.type==="request.failed"&&a.scope==="history");
  expect(failed).toBeDefined();
});

it("createExport and refreshExport dispatch export.loaded",async()=>{
  const api=makeApi();
  const {controller,actions}=harness(api);
  await controller.createExport(0n,1000n,"csv");
  await controller.refreshExport("e1");
  const loaded=actions.filter(a=>a.type==="export.loaded");
  expect(loaded.length).toBe(2);
});

it("downloadExport dispatches request.failed on failure",async()=>{
  const api=makeApi({downloadExport:vi.fn(async()=>err("EXPORT_GONE","expired"))});
  const {controller,actions}=harness(api);
  await controller.downloadExport("e1");
  const failed=actions.find(a=>a.type==="request.failed"&&a.scope==="export.download");
  expect(failed).toBeDefined();
});

it("close invokes the live stream closer",async()=>{
  const api=makeApi();
  const {controller}=harness(api);
  await controller.loadInitial();
  expect(()=>controller.close()).not.toThrow();
});
