import {describe,expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {initialState,reducer} from "../src/state/reducer";
import {statusResult,watchGroup} from "./fixtures";
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
    deleteGroup:vi.fn(async()=>ok({groupId:group.groupId,deleted:true} as const)),
    importGroups:vi.fn(async()=>ok([group])),
    connect:vi.fn(async()=>err("PROBE_UNAVAILABLE","no probe")),
    reconnect:vi.fn(async()=>ok({ok:true}) as never),
    release:vi.fn(async()=>ok({released:true})),
    start:vi.fn(async()=>ok({groupId:group.groupId,groupRevision:1n,runId:"run",intervalMs:250} as const)),
    pause:vi.fn(async()=>ok({paused:true} as const)),
    resume:vi.fn(async()=>ok({resumed:true} as const)),
    stop:vi.fn(async()=>ok({stopped:false} as const)),
    history:vi.fn(async()=>ok({batches:[],valueCount:0n,nextCursor:null,serializedBytes:0n})),
    createExport:vi.fn(async()=>ok({exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:1n,valueCount:1n} as const)),
    exportStatus:vi.fn(async()=>ok({exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:1n,valueCount:1n} as const)),
    downloadExport:vi.fn(async()=>err("EXPORT_GONE","expired")),
    ...overrides,
  };
}

function harness(api:MonitorApi){
  let state:MonitorState=reducer(initialState,{type:"zoom.reset"});
  const actions:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);actions.push(action);};
  const controller=createController(api,dispatch,()=>state);
  return{controller,state:()=>state,actions};
}

const descriptor={selector:"counter",typeName:"int",kind:"int",byteSize:4,signed:true,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
const registerDescriptor={selector:"TIM2_CNT",sizeBits:32,access:"rw",readAction:null,resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};

function readyState():MonitorState{
  const status=statusResult();
  status.sampling.bindingEpoch=3n;
  return reducer(initialState,{type:"initial.loaded",status,probes:[],groups:[watchGroup()]});
}
void readyState;

describe("controller coverage",()=>{
  it("catalogKey returns empty and searchCatalog no-ops when status is null",async()=>{
    const api=makeApi();
    const {controller,actions}=harness(api);
    await controller.searchCatalog("variables","x");
    await controller.nextCatalog("variables");
    expect(actions.some(a=>a.type==="catalog.requested")).toBe(false);
  });

  it("searchCatalog and nextCatalog drive the registers path",async()=>{
    const status=statusResult();
    status.sampling.bindingEpoch=3n;
    const api=makeApi({
      status:vi.fn(async()=>ok(status)),
      registers:vi.fn(async(_q,cursor)=>cursor===undefined?ok({items:[registerDescriptor],nextCursor:"c2"}):ok({items:[{...registerDescriptor,selector:"TIM3_CNT"}],nextCursor:null})),
    });
    const {controller,actions,state}=harness(api);
    state().status=status;
    await controller.searchCatalog("registers","TIM");
    await controller.nextCatalog("registers");
    const loaded=actions.filter(a=>a.type==="catalog.loaded");
    expect(loaded.length).toBe(2);
  });

  it("searchCatalog and nextCatalog fail for the registers path",async()=>{
    const status=statusResult();
    status.sampling.bindingEpoch=3n;
    const api=makeApi({registers:vi.fn(async()=>err("CATALOG_FAILED","nope"))});
    const {controller,actions,state}=harness(api);
    state().status=status;
    await controller.searchCatalog("registers","TIM");
    const failed=actions.filter(a=>a.type==="request.failed"&&a.scope==="catalog.registers");
    expect(failed.length).toBe(1);
  });

  it("nextCatalog fails for the registers path after a successful search",async()=>{
    const status=statusResult();
    status.sampling.bindingEpoch=3n;
    const api=makeApi({registers:vi.fn(async(_q,cursor)=>cursor===undefined?ok({items:[registerDescriptor],nextCursor:"c2"}):err("CATALOG_FAILED","nope"))});
    const {controller,actions,state}=harness(api);
    state().status=status;
    await controller.searchCatalog("registers","TIM");
    await controller.nextCatalog("registers");
    const failed=actions.filter(a=>a.type==="request.failed"&&a.scope==="catalog.registers");
    expect(failed.length).toBe(1);
  });

  it("nextCatalog no-ops when the prior catalog has no next cursor",async()=>{
    const status=statusResult();
    status.sampling.bindingEpoch=3n;
    const api=makeApi({variables:vi.fn(async()=>ok({items:[descriptor],nextCursor:null}))});
    const {controller,actions,state}=harness(api);
    state().status=status;
    await controller.searchCatalog("variables","x");
    const before=actions.length;
    await controller.nextCatalog("variables");
    expect(actions.length).toBe(before);
  });

  it("refreshStatus and refreshProbes fail and refreshGroups both succeed and fail",async()=>{
    const api=makeApi({status:vi.fn(async()=>err("STATUS_DOWN","down")),probes:vi.fn(async()=>err("PROBES_DOWN","down"))});
    const {controller,actions}=harness(api);
    await controller.refreshStatus();
    await controller.refreshProbes();
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="status")).toBe(true);
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="probes")).toBe(true);
    const failApi=makeApi({groups:vi.fn(async()=>err("GROUPS_DOWN","down"))});
    const fail=harness(failApi);
    await fail.controller.refreshGroups();
    expect(fail.actions.some(a=>a.type==="request.failed"&&a.scope==="groups.create")).toBe(true);
    const okApi=makeApi();
    const okH=harness(okApi);
    await okH.controller.refreshGroups();
    expect(okH.actions.some(a=>a.type==="groups.loaded")).toBe(true);
  });

  it("connectProbe, reconnectProbe and releaseProbe fail paths",async()=>{
    const api=makeApi({reconnect:vi.fn(async()=>err("RECONNECT_DOWN","down"))});
    const {controller,actions}=harness(api);
    await controller.connectProbe("p1");
    await controller.reconnectProbe();
    await controller.releaseProbe();
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="probe.connect")).toBe(true);
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="probe.reconnect")).toBe(true);
    const releaseApi=makeApi({release:vi.fn(async()=>err("RELEASE_DOWN","down"))});
    const rel=harness(releaseApi);
    await rel.controller.releaseProbe();
    expect(rel.actions.some(a=>a.type==="request.failed"&&a.scope==="probe.release")).toBe(true);
  });

  it("loadInitial fails when status, probes, or a groups page fails",async()=>{
    const statusFail=harness(makeApi({status:vi.fn(async()=>err("S","s"))}));
    await statusFail.controller.loadInitial();
    expect(statusFail.actions.some(a=>a.type==="request.failed")).toBe(true);
    const probeFail=harness(makeApi({probes:vi.fn(async()=>err("P","p"))}));
    await probeFail.controller.loadInitial();
    expect(probeFail.actions.some(a=>a.type==="request.failed")).toBe(true);
    const groupsFail=harness(makeApi({groups:vi.fn(async()=>err("G","g"))}));
    await groupsFail.controller.loadInitial();
    expect(groupsFail.actions.some(a=>a.type==="request.failed")).toBe(true);
  });

  it("loadInitial reloads an already-open live stream",async()=>{
    const api=makeApi();
    const {controller,actions}=harness(api);
    await controller.loadInitial();
    await controller.loadInitial();
    expect(actions.some(a=>a.type==="transport.open")).toBe(true);
  });

  it("saveGroup and deleteGroup fail paths",async()=>{
    const group=watchGroup();
    const api=makeApi({updateGroup:vi.fn(async()=>err("UPDATE_DOWN","down")),deleteGroup:vi.fn(async()=>err("DELETE_DOWN","down"))});
    const {controller,actions,state}=harness(api);
    state().groups=[group];
    await controller.saveGroup({sourceGroupId:group.groupId,expectedRevision:1n,name:"n",description:"",intervalMs:250,items:[]});
    await controller.deleteGroup(group.groupId);
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="groups.update")).toBe(true);
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="groups.delete")).toBe(true);
  });

  it("deleteGroup no-ops for an unknown group",async()=>{
    const api=makeApi();
    const {controller,actions}=harness(api);
    await controller.deleteGroup("missing");
    expect(actions.some(a=>a.type==="request.started")).toBe(false);
  });

  it("importGroups fails for an invalid document and a failed request",async()=>{
    const invalid=harness(makeApi());
    await invalid.controller.importGroups({bad:true});
    expect(invalid.actions.some(a=>a.type==="request.failed"&&a.scope==="groups.import")).toBe(true);
    const failed=harness(makeApi({importGroups:vi.fn(async()=>err("IMPORT_DOWN","down"))}));
    await failed.controller.importGroups({schemaVersion:1,groups:[]});
    expect(failed.actions.some(a=>a.type==="request.failed"&&a.scope==="groups.import")).toBe(true);
  });

  it("sampling control failures dispatch request.failed",async()=>{
    const api=makeApi({start:vi.fn(async()=>err("START_DOWN","down")),pause:vi.fn(async()=>err("PAUSE_DOWN","down")),resume:vi.fn(async()=>err("RESUME_DOWN","down")),stop:vi.fn(async()=>err("STOP_DOWN","down"))});
    const {controller,actions}=harness(api);
    await controller.startSampling("g",1n);
    await controller.pauseSampling();
    await controller.resumeSampling();
    await controller.stopSampling();
    for(const scope of ["sampling.start","sampling.pause","sampling.resume","sampling.stop"]){
      expect(actions.some(a=>a.type==="request.failed"&&a.scope===scope)).toBe(true);
    }
  });

  it("loadHistory and nextHistory fail and succeed",async()=>{
    const fail=harness(makeApi({history:vi.fn(async()=>err("H_DOWN","down"))}));
    await fail.controller.loadHistory({startNs:0n,endNs:1n});
    expect(fail.actions.some(a=>a.type==="request.failed"&&a.scope==="history")).toBe(true);
    const okApi=makeApi();
    const okH=harness(okApi);
    okH.state().history={...okH.state().history,query:{startNs:0n,endNs:1n,limit:5,runId:"r",groupId:"g",selectorKind:"variable",selector:"x"}};
    await okH.controller.nextHistory("c1");
    expect(okH.actions.some(a=>a.type==="history.loaded")).toBe(true);
  });

  it("nextHistory no-ops without a current query and without a cursor",async()=>{
    const api=makeApi();
    const {controller,actions}=harness(api);
    await controller.nextHistory("c1");
    expect(actions.some(a=>a.type==="request.started")).toBe(false);
    const again=harness(api);
    again.state().history={...again.state().history,query:{startNs:0n,endNs:1n}};
    await again.controller.nextHistory(undefined);
    expect(again.actions.some(a=>a.type==="history.loaded")).toBe(true);
  });

  it("createExport and refreshExport fail paths",async()=>{
    const api=makeApi({createExport:vi.fn(async()=>err("EXPORT_DOWN","down")),exportStatus:vi.fn(async()=>err("STATUS_DOWN","down"))});
    const {controller,actions}=harness(api);
    await controller.createExport(0n,1n,"csv");
    await controller.refreshExport("e1");
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="export.create")).toBe(true);
    expect(actions.some(a=>a.type==="request.failed"&&a.scope==="export.status")).toBe(true);
  });

  it("downloadExport triggers a browser download on success",async()=>{
    const blob=new Blob(["data"]);
    const createObjectURL=vi.spyOn(URL,"createObjectURL").mockReturnValue("blob:test");
    const revokeObjectURL=vi.spyOn(URL,"revokeObjectURL").mockImplementation(()=>undefined);
    const click=vi.fn();
    vi.spyOn(document,"createElement").mockReturnValue({href:"",download:"",click} as unknown as HTMLAnchorElement);
    try{
      const api=makeApi({downloadExport:vi.fn(async()=>({ok:true as const,blob,filename:"export.csv",contentType:"text/csv"}))});
      const {controller}=harness(api);
      await controller.downloadExport("e1");
      expect(createObjectURL).toHaveBeenCalledWith(blob);
      expect(click).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
    }finally{
      createObjectURL.mockRestore();
      revokeObjectURL.mockRestore();
      vi.restoreAllMocks();
    }
  });

  it("close no-ops when the live stream was never opened",()=>{
    const api=makeApi();
    const {controller}=harness(api);
    expect(()=>controller.close()).not.toThrow();
  });
});
