import {afterEach,expect,it,vi} from "vitest";
import {createController} from "../src/controller";
import {initialState,reducer} from "../src/state/reducer";
import {selectedGroup} from "../src/state/selectors";
import {statusResult,watchGroup} from "./fixtures";
import type {ApiResult,GroupDraft,GroupPage,HistoryPage,HistoryQuery,MonitorApi,VariableDescriptor,WatchGroup} from "../src/api/contract";
import type {MonitorAction,MonitorState,RequestScope} from "../src/state/model";
import {openLive} from "../src/api/live";

vi.mock("../src/api/live",()=>({openLive:vi.fn(()=>()=>{})}));
afterEach(()=>vi.mocked(openLive).mockClear());
const ok=<T>(data:T)=>({ok:true,data} as const);
const err=(code:string)=>({ok:false,code,message:code} as const);
const page=(groups:readonly WatchGroup[],nextCursor:string|null=null):GroupPage=>({groups,nextCursor,revision:"r1"});
const historyPage=(nextCursor:string|null=null):HistoryPage=>({batches:[],valueCount:0n,nextCursor,serializedBytes:0n});
function deferred<T>(){
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(r=>{resolve=r;});
  return{promise,resolve};
}
function makeApi(overrides:Partial<MonitorApi>={}):MonitorApi{
  const group=watchGroup();
  return{
    status:vi.fn(async()=>ok(statusResult())),probes:vi.fn(async()=>ok({probes:[]})),
    groups:vi.fn(async()=>ok(page([group]))),
    createGroup:vi.fn(async()=>ok(group)),updateGroup:vi.fn(async()=>ok(group)),
    history:vi.fn(async()=>ok(historyPage())),exportStatus:vi.fn(async()=>ok({exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    createExport:vi.fn(async()=>ok({exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n})),
    downloadExport:vi.fn(async()=>err("DOWNLOAD_FAILED")),
    ...overrides,
  } as MonitorApi;
}
function harness(api:MonitorApi){
  let state:MonitorState=initialState;
  const actions:MonitorAction[]=[];
  const dispatch=(action:MonitorAction)=>{state=reducer(state,action);actions.push(action);};
  const controller=createController(api,dispatch,()=>state);
  return{controller,state:()=>state,dispatch,actions};
}
const failureId=(state:MonitorState,scope:RequestScope)=>state.failures[scope]!.requestId;
const draft=(name:string):GroupDraft=>({sourceGroupId:null,expectedRevision:null,name,description:"",intervalMs:250,
  items:[{kind:"variable",expression:"counter"}]});
const variable=(selector:string):VariableDescriptor=>({selector,typeName:"int",kind:"scalar",byteSize:4,signed:true,
  encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]});

it("retries the whole initial snapshot after page two fails and opens one live connection",async()=>{
  const group=watchGroup();
  let failed=false;
  const groups=vi.fn(async(cursor?:string)=>{
    if(cursor===undefined)return ok(page([group],"c2"));
    if(!failed){failed=true;return err("GROUPS_DOWN");}
    return ok(page([{...group,groupId:"g2"}]));
  });
  const h=harness(makeApi({groups}));
  await h.controller.loadInitial();
  expect(h.state().status).toBeNull();
  expect(h.state().groups).toHaveLength(0);
  expect(h.state().failures.initial?.recovery).toBe("read-retry");
  expect(openLive).not.toHaveBeenCalled();
  await h.controller.retry("initial",failureId(h.state(),"initial"));
  expect(h.state().groups).toHaveLength(2);
  expect(openLive).toHaveBeenCalledTimes(1);
  await h.controller.loadInitial();
  expect(openLive).toHaveBeenCalledTimes(1);
  h.controller.close();
});

it("shows the first ordinary initial failure without waiting for another read",async()=>{
  const oldProbes=deferred<Awaited<ReturnType<MonitorApi["probes"]>>>();
  const probes=vi.fn().mockImplementationOnce(()=>oldProbes.promise)
    .mockImplementationOnce(async()=>ok({probes:[]}));
  const status=vi.fn().mockImplementationOnce(async()=>err("STATUS_DOWN"))
    .mockImplementationOnce(async()=>ok(statusResult()));
  const h=harness(makeApi({status,probes}));
  await h.controller.loadInitial();
  expect(h.state().pending.initial).toBeUndefined();
  expect(h.state().failures.initial?.code).toBe("STATUS_DOWN");
  await h.controller.retry("initial",failureId(h.state(),"initial"));
  expect(h.state().status).not.toBeNull();
  expect(openLive).toHaveBeenCalledTimes(1);
  oldProbes.resolve(err("MONITOR_AUTH_REQUIRED"));
  await Promise.resolve();
  await Promise.resolve();
  expect(h.state().blockingError).toBeNull();
});

it("still blocks on a late fatal from the latest failed initial attempt",async()=>{
  const late=deferred<Awaited<ReturnType<MonitorApi["probes"]>>>();
  const h=harness(makeApi({status:vi.fn(async()=>err("STATUS_DOWN")),probes:vi.fn(()=>late.promise)}));
  await h.controller.loadInitial();
  expect(h.state().failures.initial?.code).toBe("STATUS_DOWN");
  late.resolve(err("MONITOR_AUTH_REQUIRED"));
  await Promise.resolve();
  await Promise.resolve();
  expect(h.state().blockingError?.code).toBe("MONITOR_AUTH_REQUIRED");
  expect(h.state().failures.initial).toBeUndefined();
});

it("prefers fatal access rejection over simultaneous ordinary initial failure",async()=>{
  const h=harness(makeApi({status:vi.fn(async()=>err("STATUS_DOWN")),
    probes:vi.fn(async()=>err("MONITOR_AUTH_REQUIRED"))}));
  await h.controller.loadInitial();
  expect(h.state().blockingError?.code).toBe("MONITOR_AUTH_REQUIRED");
  expect(h.state().failures.initial).toBeUndefined();
  expect(openLive).not.toHaveBeenCalled();
});

it("close and supersession stop stale groups pagination before page two",async()=>{
  const first=deferred<ApiResult<GroupPage>>();
  const groups=vi.fn()
    .mockImplementationOnce(()=>first.promise)
    .mockImplementation(async()=>ok(page([])));
  const h=harness(makeApi({groups}));
  const loading=h.controller.loadInitial();
  h.controller.close();
  first.resolve(ok(page([],"next")));
  await loading;
  expect(groups).toHaveBeenCalledTimes(1);
  expect(openLive).not.toHaveBeenCalled();
  const nextFirst=deferred<ApiResult<GroupPage>>();
  const list=vi.fn().mockImplementationOnce(()=>nextFirst.promise).mockImplementation(async()=>ok(page([])));
  const second=harness(makeApi({groups:list}));
  const stale=second.controller.refreshGroups();
  await second.controller.refreshGroups();
  nextFirst.resolve(ok(page([],"old-next")));
  await stale;
  expect(list).toHaveBeenCalledTimes(2);
});

it("fatal authorization aborts a pending initial group cursor chain",async()=>{
  const first=deferred<ApiResult<GroupPage>>();
  const groups=vi.fn(()=>first.promise);
  const h=harness(makeApi({status:vi.fn(async()=>err("MONITOR_ORIGIN_REJECTED")),groups}));
  const loading=h.controller.loadInitial();
  await Promise.resolve();
  expect(h.state().blockingError?.code).toBe("MONITOR_ORIGIN_REJECTED");
  first.resolve(ok(page([],"must-not-fetch")));
  await loading;
  expect(groups).toHaveBeenCalledTimes(1);
});

it("old success cannot erase newer failure or override access blocking",async()=>{
  const slow=deferred<Awaited<ReturnType<MonitorApi["status"]>>>();
  const api=makeApi({status:vi.fn().mockImplementationOnce(()=>slow.promise)
    .mockImplementationOnce(async()=>err("STATUS_DOWN"))});
  const h=harness(api);
  const old=h.controller.refreshStatus();
  await h.controller.refreshStatus();
  expect(h.state().failures.status?.code).toBe("STATUS_DOWN");
  slow.resolve(ok(statusResult()));
  await old;
  expect(h.state().status).toBeNull();
  expect(h.state().failures.status?.code).toBe("STATUS_DOWN");
  const pendingHistory=deferred<Awaited<ReturnType<MonitorApi["history"]>>>();
  const blocked=harness(makeApi({history:vi.fn(()=>pendingHistory.promise),
    status:vi.fn(async()=>err("MONITOR_PEER_REJECTED"))}));
  const history=blocked.controller.loadHistory({startNs:0n,endNs:1n});
  await blocked.controller.refreshStatus();
  pendingHistory.resolve(ok(historyPage()));
  await history;
  expect(blocked.state().blockingError?.code).toBe("MONITOR_PEER_REJECTED");
  expect(blocked.state().history.page).toBeNull();
});

it("failed complete group refresh preserves its prior list and edited draft",async()=>{
  const existing=watchGroup(),other={...existing,groupId:"other"};
  const groups=vi.fn()
    .mockImplementationOnce(async()=>ok(page([other],"more")))
    .mockImplementationOnce(async()=>err("PAGE_DOWN"))
    .mockImplementationOnce(async()=>ok(page([other],"more")))
    .mockImplementationOnce(async()=>ok(page([existing])));
  const h=harness(makeApi({groups}));
  h.dispatch({type:"initial.loaded",status:statusResult(),probes:[],groups:[existing]});
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"unsaved"}});
  await h.controller.refreshGroups();
  expect(h.state().groups).toEqual([existing]);
  expect(h.state().groupDraft.name).toBe("unsaved");
  await h.controller.retry("groups.list",failureId(h.state(),"groups.list"));
  expect(h.state().groups).toHaveLength(2);
  expect(h.state().groupDraft.name).toBe("unsaved");
});

it("confirmed retry captures original draft and blocks a second group write",async()=>{
  const pending=deferred<Awaited<ReturnType<MonitorApi["createGroup"]>>>();
  const create=vi.fn().mockImplementationOnce(async()=>err("REJECTED"))
    .mockImplementationOnce(()=>pending.promise);
  const h=harness(makeApi({createGroup:create}));
  h.dispatch({type:"group.draft.changed",draft:draft("original")});
  await h.controller.createGroup();
  const id=failureId(h.state(),"groups.create");
  expect(h.state().failures["groups.create"]?.recovery).toBe("write-confirm");
  h.dispatch({type:"group.draft.changed",draft:draft("new draft")});
  const retried=h.controller.retry("groups.create",id);
  await h.controller.retry("groups.create",id);
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(2);
  expect(create.mock.calls[1]?.[0]?.name).toBe("original");
  pending.resolve(ok(watchGroup()));
  await retried;
  expect(h.state().groupDraft.name).toBe("new draft");
});

it("uncertain group write reconciles once without repeating POST",async()=>{
  const pending=deferred<ApiResult<GroupPage>>();
  const create=vi.fn(async()=>err("MONITOR_TRANSPORT_FAILED"));
  const groups=vi.fn(()=>pending.promise);
  const h=harness(makeApi({createGroup:create,groups}));
  h.dispatch({type:"group.draft.changed",draft:draft("x")});
  await h.controller.createGroup();
  const id=failureId(h.state(),"groups.create");
  expect(h.state().failures["groups.create"]?.recovery).toBe("reconcile");
  const refresh=h.controller.retry("groups.create",id);
  await h.controller.retry("groups.create",id);
  expect(groups).toHaveBeenCalledTimes(1);
  expect(create).toHaveBeenCalledTimes(1);
  expect(h.state().reconciling["groups.create"]).toBe(id);
  pending.resolve(ok(page([])));
  await refresh;
  expect(h.state().reconciling["groups.create"]).toBeUndefined();
  expect(h.state().failures["groups.create"]?.requestId).toBe(id);
});

it("accepted group create keeps its identity and family lock through failed follow-up GET",async()=>{
  const created={...watchGroup(),groupId:"created",revision:7n};
  const pending=deferred<ApiResult<GroupPage>>();
  const create=vi.fn(async()=>ok(created));
  const groups=vi.fn(()=>pending.promise);
  const h=harness(makeApi({createGroup:create,groups}));
  h.dispatch({type:"group.draft.changed",draft:draft("saved")});
  const saving=h.controller.createGroup();
  await Promise.resolve();
  expect(h.state().groupDraft.sourceGroupId).toBe("created");
  expect(h.state().groupDraft.expectedRevision).toBe(7n);
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(1);
  pending.resolve(err("GROUPS_DOWN"));
  await saving;
  expect(h.state().failures["groups.list"]?.code).toBe("GROUPS_DOWN");
  expect(selectedGroup(h.state())?.groupId).toBe("created");
  expect(h.state().groups.some(group=>group.groupId==="created")).toBe(true);
  await h.controller.createGroup();
  expect(create).toHaveBeenCalledTimes(1);
});

it("upserts a returned group without overwriting a newer selected draft",async()=>{
  const existing=watchGroup(),created={...existing,groupId:"created",revision:7n};
  const pending=deferred<ApiResult<typeof created>>();
  const h=harness(makeApi({createGroup:vi.fn(()=>pending.promise),groups:vi.fn(async()=>err("GROUPS_DOWN"))}));
  h.dispatch({type:"initial.loaded",status:statusResult(),probes:[],groups:[existing]});
  h.dispatch({type:"group.draft.changed",draft:draft("new")});
  const saving=h.controller.createGroup();
  h.dispatch({type:"group.selected",groupId:existing.groupId});
  h.dispatch({type:"group.draft.changed",draft:{...h.state().groupDraft,name:"editing existing"}});
  pending.resolve(ok(created));
  await saving;
  expect(h.state().groups.map(group=>group.groupId)).toEqual([existing.groupId,"created"]);
  expect(h.state().selectedGroupId).toBe(existing.groupId);
  expect(h.state().groupDraft.name).toBe("editing existing");
});

it("does not replay failed probe or sampling writes after their target changes",async()=>{
  const connected={...statusResult(),probe:{connected:true,probeId:"probe-1"},probeConnected:true,
    sampling:{...statusResult().sampling,groupId:"group",runId:"run-1",bindingEpoch:1n,state:"RUNNING" as const,active:true}};
  const release=vi.fn(async()=>err("RELEASE_DOWN"));
  const pause=vi.fn(async()=>err("PAUSE_DOWN"));
  const h=harness(makeApi({release,pause}));
  h.dispatch({type:"initial.loaded",status:connected,probes:[],groups:[watchGroup()]});
  await h.controller.releaseProbe();
  const releaseId=failureId(h.state(),"probe.release");
  expect(h.state().failures["probe.release"]?.summary).toContain("probe-1");
  await h.controller.pauseSampling();
  const pauseId=failureId(h.state(),"sampling.pause");
  expect(h.state().failures["sampling.pause"]?.summary).toContain("run-1");
  h.dispatch({type:"status.loaded",status:{...connected,probe:{connected:true,probeId:"probe-2"},
    sampling:{...connected.sampling,runId:"run-2",bindingEpoch:2n}}});
  await h.controller.retry("probe.release",releaseId);
  await h.controller.retry("sampling.pause",pauseId);
  expect(release).toHaveBeenCalledTimes(1);
  expect(pause).toHaveBeenCalledTimes(1);
  expect(h.state().failures["probe.release"]).toBeUndefined();
  expect(h.state().failures["sampling.pause"]).toBeUndefined();
});

it("does not replay an old sampling start against a newly connected probe",async()=>{
  const status={...statusResult(),probe:{connected:true,probeId:"probe-1"},probeConnected:true};
  const start=vi.fn(async()=>err("START_DOWN"));
  const h=harness(makeApi({start}));
  h.dispatch({type:"initial.loaded",status,probes:[],groups:[watchGroup()]});
  await h.controller.startSampling("group",1n);
  const id=failureId(h.state(),"sampling.start");
  expect(h.state().failures["sampling.start"]?.summary).toContain("probe-1");
  h.dispatch({type:"status.loaded",status:{...status,probe:{connected:true,probeId:"probe-2"}}});
  await h.controller.retry("sampling.start",id);
  expect(start).toHaveBeenCalledTimes(1);
  expect(h.state().failures["sampling.start"]).toBeUndefined();
});

it("history failed forward and backward retries update the accepted stack only on success",async()=>{
  const responses=[err("FORWARD_DOWN"),ok(historyPage(null)),err("BACK_DOWN"),ok(historyPage("c2"))];
  const calls:HistoryQuery[]=[];
  const api=makeApi({history:vi.fn(async(query)=>{calls.push({...query});return responses.shift()!;})});
  const h=harness(api);
  h.dispatch({type:"history.loaded",query:{startNs:0n,endNs:2n},page:historyPage("c2")});
  await h.controller.nextHistory("c2");
  expect(h.state().history.cursorStack).toEqual([]);
  expect(h.state().history.query?.cursor).toBeUndefined();
  await h.controller.retry("history",failureId(h.state(),"history"));
  expect(h.state().history.cursorStack).toEqual([undefined]);
  expect(h.state().history.query?.cursor).toBe("c2");
  await h.controller.nextHistory(undefined);
  expect(h.state().history.cursorStack).toEqual([undefined]);
  await h.controller.retry("history",failureId(h.state(),"history"));
  expect(h.state().history.cursorStack).toEqual([]);
  expect(h.state().history.query?.cursor).toBeUndefined();
  expect(calls.map(query=>query.cursor)).toEqual(["c2","c2",undefined,undefined]);
});

it("export range stays bound to its ID; stale status cannot replace a newer create",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["exportStatus"]>>>();
  const artifact=(id:string)=>({exportId:id,format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n});
  const create=vi.fn().mockImplementationOnce(async()=>ok(artifact("e1")))
    .mockImplementationOnce(async()=>ok(artifact("e2")));
  const h=harness(makeApi({createExport:create,exportStatus:vi.fn(()=>old.promise)}));
  await h.controller.createExport(1n,2n,"csv");
  const oldStatus=h.controller.refreshExport("e1");
  await h.controller.createExport(3n,4n,"csv");
  old.resolve(ok(artifact("e1")));
  await oldStatus;
  expect(h.state().exports.artifact?.exportId).toBe("e2");
  expect(h.state().exports.submitted).toEqual({exportId:"e2",startNs:3n,endNs:4n,format:"csv"});
});

it("export status and download failures settle and retry their captured task ID",async()=>{
  const artifact={exportId:"e1",format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n};
  const status=vi.fn().mockImplementationOnce(async()=>err("STATUS_DOWN"))
    .mockImplementationOnce(async()=>ok({...artifact,bytes:2n}));
  const download=vi.fn(async(exportId:string)=>{void exportId;return err("DOWNLOAD_DOWN");});
  const h=harness(makeApi({createExport:vi.fn(async()=>ok(artifact)),exportStatus:status,downloadExport:download}));
  await h.controller.createExport(10n,20n,"csv");
  await h.controller.refreshExport("e1");
  expect(h.state().pending["export.status"]).toBeUndefined();
  expect(h.state().exports.artifact?.bytes).toBe(1n);
  await h.controller.retry("export.status",failureId(h.state(),"export.status"));
  expect(h.state().exports.artifact?.bytes).toBe(2n);
  expect(h.state().exports.submitted?.startNs).toBe(10n);
  await h.controller.downloadExport("e1");
  const id=failureId(h.state(),"export.download");
  expect(h.state().pending["export.download"]).toBeUndefined();
  await h.controller.retry("export.download",id);
  expect(download).toHaveBeenCalledTimes(2);
  expect(download.mock.calls.every(call=>call[0]==="e1")).toBe(true);
});

it("retires an old export status failure when a new artifact is created but keeps its download retry",async()=>{
  const artifact=(exportId:string)=>({exportId,format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n});
  const status=vi.fn(async()=>err("STATUS_DOWN"));
  const download=vi.fn(async(exportId:string)=>{void exportId;return err("DOWNLOAD_DOWN");});
  const create=vi.fn().mockImplementationOnce(async()=>ok(artifact("e1")))
    .mockImplementationOnce(async()=>ok(artifact("e2")));
  const h=harness(makeApi({createExport:create,exportStatus:status,downloadExport:download}));
  await h.controller.createExport(1n,2n,"csv");
  await h.controller.refreshExport("e1");
  const oldStatusId=failureId(h.state(),"export.status");
  await h.controller.downloadExport("e1");
  const oldDownloadId=failureId(h.state(),"export.download");
  await h.controller.createExport(3n,4n,"csv");
  expect(h.state().failures["export.status"]).toBeUndefined();
  await h.controller.retry("export.status",oldStatusId);
  expect(status).toHaveBeenCalledTimes(1);
  await h.controller.retry("export.download",oldDownloadId);
  expect(download).toHaveBeenCalledTimes(2);
  expect(download.mock.calls[1]?.[0]).toBe("e1");
});

it("retires an in-flight old export status error after a new artifact arrives",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["exportStatus"]>>>();
  const artifact=(exportId:string)=>({exportId,format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n});
  const create=vi.fn().mockImplementationOnce(async()=>ok(artifact("e1")))
    .mockImplementationOnce(async()=>ok(artifact("e2")));
  const h=harness(makeApi({createExport:create,exportStatus:vi.fn(()=>old.promise)}));
  await h.controller.createExport(1n,2n,"csv");
  const pending=h.controller.refreshExport("e1");
  await h.controller.createExport(3n,4n,"csv");
  expect(h.state().pending["export.status"]).toBeUndefined();
  old.resolve(err("STATUS_DOWN"));
  await pending;
  expect(h.state().failures["export.status"]).toBeUndefined();
  expect(h.state().exports.artifact?.exportId).toBe("e2");
});

it("blocks on fatal export status after its old artifact pending was retired",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["exportStatus"]>>>();
  const artifact=(exportId:string)=>({exportId,format:"csv" as const,sha256:"a".repeat(64),bytes:1n,valueCount:1n});
  const create=vi.fn().mockImplementationOnce(async()=>ok(artifact("e1")))
    .mockImplementationOnce(async()=>ok(artifact("e2")));
  const status=vi.fn(()=>old.promise);
  const h=harness(makeApi({createExport:create,exportStatus:status}));
  await h.controller.createExport(1n,2n,"csv");
  const pending=h.controller.refreshExport("e1");
  await h.controller.createExport(3n,4n,"csv");
  expect(h.state().pending["export.status"]).toBeUndefined();
  old.resolve(err("MONITOR_AUTH_REQUIRED"));
  await pending;
  expect(h.state().blockingError?.code).toBe("MONITOR_AUTH_REQUIRED");
  await h.controller.refreshExport("e2");
  await h.controller.createExport(5n,6n,"csv");
  expect(status).toHaveBeenCalledTimes(1);
  expect(create).toHaveBeenCalledTimes(2);
});

it("retires obsolete catalog failure and pending read on binding change",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["variables"]>>>();
  const variables=vi.fn().mockImplementationOnce(async()=>err("CATALOG_DOWN"))
    .mockImplementationOnce(()=>old.promise);
  const h=harness(makeApi({variables}));
  const firstStatus=statusResult();
  h.dispatch({type:"initial.loaded",status:firstStatus,probes:[],groups:[]});
  await h.controller.searchCatalog("variables","old");
  const failedId=failureId(h.state(),"catalog.variables");
  const pending=h.controller.searchCatalog("variables","later");
  const nextStatus={...firstStatus,sampling:{...firstStatus.sampling,bindingEpoch:firstStatus.sampling.bindingEpoch+1n}};
  h.dispatch({type:"status.loaded",status:nextStatus});
  expect(h.state().failures["catalog.variables"]).toBeUndefined();
  expect(h.state().pending["catalog.variables"]).toBeUndefined();
  await h.controller.retry("catalog.variables",failedId);
  expect(variables).toHaveBeenCalledTimes(2);
  old.resolve(err("LATE_CATALOG_DOWN"));
  await pending;
  expect(h.state().failures["catalog.variables"]).toBeUndefined();
});

it("blocks on fatal catalog result after a binding change retired its pending record",async()=>{
  const old=deferred<Awaited<ReturnType<MonitorApi["variables"]>>>();
  const variables=vi.fn(()=>old.promise);
  const h=harness(makeApi({variables}));
  const firstStatus=statusResult();
  h.dispatch({type:"initial.loaded",status:firstStatus,probes:[],groups:[]});
  const pending=h.controller.searchCatalog("variables","old");
  h.dispatch({type:"status.loaded",status:{...firstStatus,
    sampling:{...firstStatus.sampling,bindingEpoch:firstStatus.sampling.bindingEpoch+1n}}});
  expect(h.state().pending["catalog.variables"]).toBeUndefined();
  old.resolve(err("MONITOR_ORIGIN_REJECTED"));
  await pending;
  expect(h.state().blockingError?.code).toBe("MONITOR_ORIGIN_REJECTED");
  await h.controller.searchCatalog("variables","new");
  expect(variables).toHaveBeenCalledTimes(1);
});

it("retiring a failed catalog binding removes its enabled retry",async()=>{
  const variables=vi.fn(async()=>err("CATALOG_DOWN"));
  const h=harness(makeApi({variables}));
  const firstStatus=statusResult();
  h.dispatch({type:"initial.loaded",status:firstStatus,probes:[],groups:[]});
  await h.controller.searchCatalog("variables","old");
  const id=failureId(h.state(),"catalog.variables");
  h.dispatch({type:"status.loaded",status:{...firstStatus,
    sampling:{...firstStatus.sampling,bindingEpoch:firstStatus.sampling.bindingEpoch+1n}}});
  expect(h.state().failures["catalog.variables"]).toBeUndefined();
  await h.controller.retry("catalog.variables",id);
  expect(variables).toHaveBeenCalledTimes(1);
});

it("retries the failed catalog continuation with its exact cursor and retained rows",async()=>{
  const variables=vi.fn().mockImplementationOnce(async()=>ok({items:[variable("first")],nextCursor:"c2"}))
    .mockImplementationOnce(async()=>err("PAGE_DOWN"))
    .mockImplementationOnce(async()=>ok({items:[variable("second")],nextCursor:null}));
  const h=harness(makeApi({variables}));
  h.dispatch({type:"initial.loaded",status:statusResult(),probes:[],groups:[]});
  await h.controller.searchCatalog("variables","counter");
  await h.controller.nextCatalog("variables");
  expect(h.state().catalog.variables?.items.map(item=>item.selector)).toEqual(["first"]);
  expect(h.state().catalog.variables?.nextCursor).toBe("c2");
  await h.controller.retry("catalog.variables",failureId(h.state(),"catalog.variables"));
  expect(variables.mock.calls.map(call=>call[1])).toEqual([undefined,"c2","c2"]);
  expect(h.state().catalog.variables?.items.map(item=>item.selector)).toEqual(["first","second"]);
});

it("does not append a catalog cursor twice when dispatch is deferred until render",async()=>{
  const variables=vi.fn().mockImplementationOnce(async()=>ok({items:[variable("first")],nextCursor:"c2"}))
    .mockImplementation(async()=>ok({items:[variable("second")],nextCursor:null}));
  const api=makeApi({variables});
  let rendered=reducer(initialState,{type:"initial.loaded",status:statusResult(),probes:[],groups:[]});
  const queued:MonitorAction[]=[];
  const controller=createController(api,action=>queued.push(action),()=>rendered);
  const flush=()=>{for(const action of queued.splice(0))rendered=reducer(rendered,action);};
  await controller.searchCatalog("variables","counter");
  flush();
  await controller.nextCatalog("variables");
  await controller.nextCatalog("variables");
  expect(variables.mock.calls.map(call=>call[1])).toEqual([undefined,"c2","c2"]);
  flush();
  expect(rendered.catalog.variables?.items.map(item=>item.selector)).toEqual(["first","second"]);
  controller.close();
});
